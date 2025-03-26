"""
Enhanced document processor with MongoDB + Qdrant integration.
Provides multi-level chunking and multi-embedding strategies.
"""

import asyncio
import aiofiles
import base64
import io
import json
import logging
import os
import re
import time
import uuid
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union, Set, Iterator

from openai import AsyncOpenAI
import tiktoken

# Docling imports
from docling_core.types.doc import (
    DoclingDocument,
    NodeItem,
    TextItem,
    TableItem,
    PictureItem,
    SectionHeaderItem,
    DocItemLabel,
    ImageRefMode,
)
from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions
from docling.datamodel.base_models import InputFormat
from docling.document_converter import (
    DocumentConverter,
    PdfFormatOption,
)
from docling.chunking import HybridChunker, BaseChunk

# Import from the new types module
from document_processor.types import (
    ContentType,
    ChunkLevel,
    EmbeddingType,
    ProcessingResult,
    ContentElement,
    ContentMetadata,
    ProcessingConfig,
    DocumentChunk,
    ChunkMetadata,
    ConceptNetwork,
    ConceptRelationship,
    Concept,
    RelationType
)

# Import from utility modules
from api.utils.extraction import (
    extract_technical_terms,
    extract_document_relationships,
    extract_procedures_and_parameters  # New utility function for procedures
)
from api.utils.tokenization import get_tokenizer
from api.utils.document import (
    generate_document_summary,
    create_directory_if_not_exists
)
from api.utils.processing import (
    normalize_metadata_for_vectorstore,
    normalize_pdf_id
)

# Import the new unified store
from api.vector_stores import get_vector_store, get_mongo_store, get_qdrant_store

# Import errors
from api.utils.errors import DocumentProcessingError

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """
    Enhanced document processor with MongoDB + Qdrant integration.
    Provides multi-level chunking and multi-embedding strategies.
    """

    def __init__(self, pdf_id: str, config: ProcessingConfig, openai_client: AsyncOpenAI, research_manager=None):
        self.pdf_id = pdf_id
        self.config = config
        self.openai_client = openai_client
        self.research_manager = research_manager
        self.processing_start = datetime.utcnow()
        self.metrics = {"timings": defaultdict(float), "counts": defaultdict(int)}
        self.output_dir = Path("output") / self.pdf_id
        self._setup_directories()
        self.markdown_path = self.output_dir / "content" / "document.md"
        self.docling_doc = None
        self.conversion_result = None
        self.concept_network = ConceptNetwork(pdf_id=self.pdf_id)

        # Track section hierarchy during processing
        self.section_hierarchy = []
        self.section_map = {}  # Maps section titles to their level
        self.element_section_map = {}  # Maps element IDs to their section context

        # Track extracted procedures and parameters
        self.procedures = []
        self.parameters = []

        # Initialize tokenizer for chunking
        self.tokenizer = tiktoken.get_encoding("cl100k_base")  # For OpenAI models

        # Domain-specific counters to detect document type and primary concepts
        self.domain_term_counters = defaultdict(int)

        # Get database stores
        self.vector_store = get_vector_store()
        self.mongo_store = get_mongo_store()
        self.qdrant_store = get_qdrant_store()

        logger.info(f"Initialized DocumentProcessor for PDF {pdf_id} with config: {config}")

    async def process_document(self) -> ProcessingResult:
        """
        Process document with MongoDB + Qdrant integration.
        Preserves document structure and extracts rich metadata.
        Enhanced with multi-level chunking and multi-embedding strategy.
        """
        logger.info(f"Starting enhanced document processing for {self.pdf_id}")
        start_time = time.time()

        try:
            # 1. Download and convert the document
            content = self._download_content()
            if not content:
                raise DocumentProcessingError(f"No content found for PDF {self.pdf_id}")

            # 2. Convert document to Docling format
            logger.info(f"Converting document {self.pdf_id}")
            self.docling_doc = await self._convert_document(content)

            # 3. Extract and save markdown content
            logger.info(f"Exporting document {self.pdf_id} to markdown")
            md_content = await self._extract_markdown(self.docling_doc)
            await self._save_markdown(md_content)

            # 4. Extract content elements with hierarchy preservation
            logger.info(f"Extracting content elements from {self.pdf_id}")
            elements = await self._extract_content_elements(self.docling_doc)

            # 5. Extract procedures and parameters if enabled
            if self.config.extract_procedures:
                logger.info(f"Extracting procedures and parameters from {self.pdf_id}")
                procedures, parameters = await self._extract_procedures_and_parameters(elements, md_content)
                self.procedures = procedures
                self.parameters = parameters

            # 6. Generate optimized chunks using multi-level chunking
            logger.info(f"Generating optimized chunks for {self.pdf_id}")
            chunks = await self._generate_multi_level_chunks(elements, md_content)

            # 7. Build concept network from document content
            logger.info(f"Building concept network for {self.pdf_id}")
            await self._build_concept_network(elements, chunks)

            # 8. Extract all technical terms for document summary
            all_technical_terms = self._extract_all_technical_terms(elements)

            # 9. Generate an enhanced document summary using LLM
            logger.info(f"Generating enhanced document summary for {self.pdf_id}")
            document_summary = await generate_document_summary(
                text=md_content,
                technical_terms=all_technical_terms,
                relationships=self.concept_network.relationships,
                openai_client=self.openai_client
            )

            # 10. Predict document category
            predicted_category = self._predict_document_category(all_technical_terms, md_content)
            logger.info(f"Predicted document category: {predicted_category}")

            # 11. Store processed content in MongoDB + Qdrant
            logger.info(f"Ingesting content to MongoDB + Qdrant for {self.pdf_id}")
            await self._ingest_to_unified_store(elements, chunks, document_summary, predicted_category)

            # 12. Create processing result
            visual_elements = [e for e in elements if e.content_type == ContentType.IMAGE]

            result = ProcessingResult(
                pdf_id=self.pdf_id,
                elements=elements,
                chunks=chunks,
                processing_metrics=self.metrics,
                markdown_content=md_content,
                markdown_path=str(self.markdown_path),
                concept_network=self.concept_network,
                visual_elements=visual_elements,
                document_summary=document_summary,
                procedures=self.procedures,
                parameters=self.parameters
            )

            # 13. Update PDF metadata in database with enhanced summary and description
            await self._update_pdf_metadata(document_summary, predicted_category)

            # 14. Register document metadata with research manager if available
            if self.research_manager:
                document_stats = result.get_statistics()
                self._handle_research_manager_integration(document_summary.get('title', f"Document {self.pdf_id}"), {
                    "total_elements": len(elements),
                    "content_types": document_stats["element_types"],
                    "technical_terms": set(document_stats["top_technical_terms"].keys()),
                    "hierarchies": [" > ".join(s) for s in self.section_hierarchy if s],
                    "concept_network": {
                        "total_concepts": len(self.concept_network.concepts),
                        "total_relationships": len(self.concept_network.relationships),
                        "primary_concepts": self.concept_network.primary_concepts
                    },
                    "procedures": len(self.procedures),
                    "parameters": len(self.parameters),
                    "top_technical_terms": list(document_stats["top_technical_terms"].keys())[:20],
                    "domain_category": predicted_category,
                    "description": document_summary.get('description', '')
                })

            # 15. Save results to disk
            await self._save_results(result)

            # Record total processing time
            self.metrics["timings"]["total"] = time.time() - start_time
            logger.info(f"Completed enhanced processing for {self.pdf_id}")

            return result

        except Exception as e:
            logger.error(f"Document processing failed: {str(e)}", exc_info=True)
            # Update PDF record with error
            try:
                await self._update_pdf_error(str(e))
            except Exception as db_error:
                logger.error(f"Failed to update PDF error status: {str(db_error)}")
            raise

    def _download_content(self) -> bytes:
        """Download document content with error handling."""
        try:
            from app.web.files import download_file_content
            content = download_file_content(self.pdf_id)
            if not content:
                raise DocumentProcessingError(f"Failed to download content for {self.pdf_id}")
            return content
        except Exception as e:
            logger.error(f"Download failed: {str(e)}")
            raise DocumentProcessingError(f"Content download failed: {str(e)}")

    async def _convert_document(self, content: bytes) -> DoclingDocument:
        """Convert raw PDF to DoclingDocument with image preservation."""
        conversion_start = time.time()

        # Save content to temporary file
        temp_path = self.output_dir / "temp" / f"{self.pdf_id}.pdf"
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_bytes(content)

        try:
            # Configure with image preservation
            pipeline_options = PdfPipelineOptions()

            # Core options
            pipeline_options.do_ocr = True
            pipeline_options.do_table_structure = True

            # CRITICAL: These settings preserve images
            pipeline_options.images_scale = 2.0  # Higher resolution
            pipeline_options.generate_page_images = True  # Must be True
            pipeline_options.generate_picture_images = True  # Must be True

            # OCR and table settings
            ocr_options = TesseractCliOcrOptions(force_full_page_ocr=True)
            pipeline_options.ocr_options = ocr_options
            if pipeline_options.table_structure_options:
                pipeline_options.table_structure_options.do_cell_matching = True

            # Initialize converter
            converter = DocumentConverter(
                allowed_formats=[InputFormat.PDF],
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
            )

            # Convert the document
            logger.info(f"Converting document {self.pdf_id} with Docling")
            conversion_result = converter.convert(str(temp_path))
            docling_doc = conversion_result.document

            # Save the conversion result for access to all properties
            self.conversion_result = conversion_result

            # Record metrics
            self.metrics["timings"]["conversion"] = time.time() - conversion_start
            self.metrics["counts"]["pages"] = len(docling_doc.pages) if docling_doc.pages else 0

            logger.info(f"Successfully converted document with {len(docling_doc.pages)} pages")
            return docling_doc

        except Exception as e:
            logger.error(f"Document conversion failed: {e}", exc_info=True)
            raise DocumentProcessingError(f"Document conversion failed: {e}")

    async def _extract_markdown(self, doc: DoclingDocument) -> str:
        """Extract markdown using Docling's export method."""
        try:
            # Use the basic export
            md_content = doc.export_to_markdown()
            return md_content
        except Exception as e:
            logger.warning(f"Basic markdown export failed: {e}")

            # Try alternative approach using generate_multimodal_pages
            try:
                from docling.utils.export import generate_multimodal_pages

                md_parts = []
                for (_, content_md, _, _, _, _) in generate_multimodal_pages(self.conversion_result):
                    if content_md:
                        md_parts.append(content_md)

                return "\n\n".join(md_parts)
            except Exception as e2:
                logger.warning(f"Multimodal export failed: {e2}")

                # Last resort - extract plain text
                try:
                    return doc.export_to_text()
                except Exception as e3:
                    logger.error(f"All export methods failed: {e3}")
                    return ""

    async def _save_markdown(self, md_content: str) -> None:
        """Save markdown content to file with error handling."""
        try:
            self.markdown_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(self.markdown_path, "w", encoding="utf-8") as f:
                await f.write(md_content)
            logger.info(f"Saved markdown content to {self.markdown_path}")
        except Exception as e:
            logger.error(f"Failed to save markdown: {e}")

    async def _extract_content_elements(self, doc: DoclingDocument) -> List[ContentElement]:
        """
        Extract content elements (text, tables, pictures, headings) with enhanced
        hierarchical structure tracking and domain awareness.
        """
        extraction_start = time.time()
        elements = []

        # 1) Create a "page container" element for each page
        page_map = {}
        if doc.pages:
            for page_no, page_obj in doc.pages.items():
                page_id = f"page_{self.pdf_id}_{page_no}"
                page_element = self._create_content_element(
                    element_id=page_id,
                    content=f"Page {page_no}",
                    content_type=ContentType.PAGE,
                    metadata=ContentMetadata(
                        pdf_id=self.pdf_id,
                        page_number=page_no,
                        content_type=ContentType.PAGE,
                        hierarchy_level=0,
                        chunk_level=ChunkLevel.DOCUMENT,  # Always document level for pages
                        embedding_type=EmbeddingType.GENERAL
                    )
                )
                elements.append(page_element)
                page_map[page_no] = page_id

        # Track section hierarchy
        current_section_path = []
        section_levels = {}

        # 2) Process all items with improved hierarchy tracking
        for item, level in doc.iterate_items():
            # Determine page_number from prov
            page_number = 0
            if item.prov and hasattr(item.prov[0], "page_no"):
                page_number = item.prov[0].page_no

            # Enhanced hierarchical section tracking
            if isinstance(item, SectionHeaderItem):
                # Adjust section path based on header level
                while current_section_path and section_levels.get(current_section_path[-1], 0) >= level:
                    current_section_path.pop()

                # Add current section to path
                section_title = item.text.strip()
                current_section_path.append(section_title)
                section_levels[section_title] = level

                # Save to section hierarchy for export
                if current_section_path not in self.section_hierarchy:
                    self.section_hierarchy.append(list(current_section_path))

                # Extract technical terms from section header
                technical_terms = []
                if self.config.extract_technical_terms:
                    technical_terms = extract_technical_terms(section_title)

                # Create header element with proper section context
                hdr_id = f"hdr_{self.pdf_id}_{uuid.uuid4().hex[:8]}"
                hdr_element = self._create_content_element(
                    element_id=hdr_id,
                    content=item.text,
                    content_type=ContentType.TEXT,
                    metadata=ContentMetadata(
                        pdf_id=self.pdf_id,
                        page_number=page_number,
                        content_type=ContentType.TEXT,
                        hierarchy_level=level,
                        technical_terms=technical_terms,
                        section_headers=list(current_section_path),
                        chunk_level=ChunkLevel.SECTION,  # Headers are section level
                        embedding_type=EmbeddingType.CONCEPTUAL,
                        parent_element_id=page_map.get(page_number)
                    )
                )

                # Store section mapping for this element
                self.element_section_map[hdr_id] = list(current_section_path)
                self.section_map[section_title] = level

                elements.append(hdr_element)

                # Add to concept network
                if technical_terms:
                    section_path_str = " > ".join(current_section_path)
                    self._add_concepts_to_section(section_path_str, technical_terms)

                # Track domain-specific terms for document categorization
                self._track_domain_terms(item.text)

            elif isinstance(item, TableItem):
                table_element = self._process_table_item(
                    item,
                    doc,
                    section_headers=list(current_section_path),
                    hierarchy_level=level
                )
                if table_element:
                    # Parent the table to its page
                    if page_number in page_map:
                        table_element.metadata.parent_element_id = page_map[page_number]
                    elements.append(table_element)

                    # Store section mapping
                    self.element_section_map[table_element.element_id] = list(current_section_path)

                    # Track domain-specific terms
                    if table_element.metadata.table_data and table_element.metadata.table_data.get("caption"):
                        self._track_domain_terms(table_element.metadata.table_data["caption"])

            elif isinstance(item, PictureItem):
                pic_element = self._process_picture_item(
                    item,
                    doc,
                    section_headers=list(current_section_path),
                    hierarchy_level=level
                )
                if pic_element:
                    # Parent the picture to its page
                    if page_number in page_map:
                        pic_element.metadata.parent_element_id = page_map[page_number]
                    elements.append(pic_element)

                    # Store section mapping
                    self.element_section_map[pic_element.element_id] = list(current_section_path)

                    # Track domain-specific terms in image descriptions
                    if pic_element.metadata.image_metadata and pic_element.metadata.image_metadata.get("description"):
                        self._track_domain_terms(pic_element.metadata.image_metadata["description"])

            elif isinstance(item, TextItem):
                # skip empty text
                if not item.text.strip():
                    continue

                text_id = f"txt_{self.pdf_id}_{uuid.uuid4().hex[:8]}"

                # Extract technical terms
                technical_terms = []
                if self.config.extract_technical_terms:
                    technical_terms = extract_technical_terms(item.text)

                # Determine chunk level based on content
                chunk_level = self._determine_chunk_level(item.text, level, current_section_path)

                # Determine embedding type based on content
                embedding_type = self._determine_embedding_type(item.text, technical_terms)

                text_element = self._create_content_element(
                    element_id=text_id,
                    content=item.text,
                    content_type=ContentType.TEXT,
                    metadata=ContentMetadata(
                        pdf_id=self.pdf_id,
                        page_number=page_number,
                        content_type=ContentType.TEXT,
                        hierarchy_level=level,
                        technical_terms=technical_terms,
                        section_headers=list(current_section_path),
                        chunk_level=chunk_level,
                        embedding_type=embedding_type,
                        parent_element_id=page_map.get(page_number)
                    )
                )

                elements.append(text_element)

                # Store section mapping
                self.element_section_map[text_id] = list(current_section_path)

                # Add technical terms to section concepts
                if technical_terms and current_section_path:
                    section_path_str = " > ".join(current_section_path)
                    self._add_concepts_to_section(section_path_str, technical_terms)

                # Track domain-specific terms for document categorization
                self._track_domain_terms(item.text)

        # 3. Calculate metrics
        self.metrics["timings"]["extraction"] = time.time() - extraction_start
        self.metrics["counts"]["total_elements"] = len(elements)
        self.metrics["counts"]["text_elements"] = sum(1 for e in elements if e.content_type == ContentType.TEXT)
        self.metrics["counts"]["table_elements"] = sum(1 for e in elements if e.content_type == ContentType.TABLE)
        self.metrics["counts"]["image_elements"] = sum(1 for e in elements if e.content_type == ContentType.IMAGE)

        logger.info(f"Extracted {len(elements)} content elements with hierarchical context")
        return elements

    def _determine_chunk_level(self, text: str, hierarchy_level: int, section_path: List[str]) -> ChunkLevel:
        """
        Determine the appropriate chunk level for content.

        Args:
            text: The text content
            hierarchy_level: The hierarchy level of the text
            section_path: The section path of the text

        Returns:
            Appropriate chunk level
        """
        # Look for procedure indicators
        procedure_indicators = [
            r"(?i)step\s+\d+",
            r"(?i)procedure\s+\d+",
            r"(?i)^\d+\.\s+",
            r"(?i)^\w+\)\s+",
            r"(?i)instructions",
            r"(?i)followed by",
            r"(?i)first.*then.*finally",
            r"(?i)warning|caution|important",
            r"(?i)prerequisites"
        ]

        # Calculate token count for length-based decisions
        token_count = len(self.tokenizer.encode(text))

        # Check for procedure indicators
        if any(re.search(pattern, text) for pattern in procedure_indicators):
            # Check if it's a step or a full procedure
            if token_count < 300 or re.search(r"(?i)^\d+\.\s+", text):
                return ChunkLevel.STEP
            else:
                return ChunkLevel.PROCEDURE

        # Headers and short sections
        if hierarchy_level <= 2 or token_count > 1000:
            return ChunkLevel.SECTION

        # Default to document level for longer content
        if token_count > 2000:
            return ChunkLevel.DOCUMENT

        # Default to section level
        return ChunkLevel.SECTION

    def _determine_embedding_type(self, text: str, technical_terms: List[str]) -> EmbeddingType:
        """
        Determine the appropriate embedding type for content.

        Args:
            text: The text content
            technical_terms: Extracted technical terms

        Returns:
            Appropriate embedding type
        """
        # Check for technical content with lots of parameters
        technical_indicators = [
            r"(?i)parameter",
            r"(?i)configuration",
            r"(?i)setting",
            r"(?i)value",
            r"(?i)specification",
            r"(?i)measurement",
            r"(?i)dimension",
            r"(?i)technical data"
        ]

        # Check for task/procedure content
        task_indicators = [
            r"(?i)step\s+\d+",
            r"(?i)procedure",
            r"(?i)instruction",
            r"(?i)how to",
            r"(?i)process",
            r"(?i)task",
            r"(?i)operation"
        ]

        # Check for conceptual content
        conceptual_indicators = [
            r"(?i)concept",
            r"(?i)overview",
            r"(?i)introduction",
            r"(?i)description",
            r"(?i)theory",
            r"(?i)principle"
        ]

        # Count matches for each type
        technical_count = sum(1 for pattern in technical_indicators if re.search(pattern, text))
        task_count = sum(1 for pattern in task_indicators if re.search(pattern, text))
        conceptual_count = sum(1 for pattern in conceptual_indicators if re.search(pattern, text))

        # Weight by term count as well
        if len(technical_terms) > 5:
            technical_count += 1

        # Select type based on highest count
        if technical_count > task_count and technical_count > conceptual_count:
            return EmbeddingType.TECHNICAL
        elif task_count > technical_count and task_count > conceptual_count:
            return EmbeddingType.TASK
        elif conceptual_count > technical_count and conceptual_count > task_count:
            return EmbeddingType.CONCEPTUAL

        # Default to general if no clear indicator
        return EmbeddingType.GENERAL

    def _track_domain_terms(self, text: str) -> None:
        """
        Track occurrences of domain-specific terms to help categorize the document.

        Args:
            text: Text to analyze for domain terms
        """
        text_lower = text.lower()

        # Import domain-specific terms dictionary
        from app.chat.utils.extraction import DOMAIN_SPECIFIC_TERMS

        # Check each category of domain terms
        for category, terms in DOMAIN_SPECIFIC_TERMS.items():
            for term in terms:
                if term.lower() in text_lower:
                    self.domain_term_counters[category] += 1
                    # Also track the specific term
                    self.domain_term_counters[f"term:{term}"] += 1
                    break  # Only count one match per category per text segment

    def _create_content_element(
        self,
        element_id: str,
        content: str,
        content_type: ContentType,
        metadata: ContentMetadata
    ) -> ContentElement:
        """Create a content element with specified properties."""
        # Ensure metadata has pdf_id set
        if not metadata.pdf_id:
            metadata.pdf_id = self.pdf_id

        # Ensure element_id is in metadata for lookups
        metadata.element_id = element_id

        # Count tokens for reporting
        token_count = len(self.tokenizer.encode(content))

        # Add to metrics
        if not hasattr(self.metrics, "token_counts"):
            self.metrics["token_counts"] = defaultdict(int)
        self.metrics["token_counts"][str(content_type)] += token_count

        return ContentElement(
            element_id=element_id,
            content=content,
            content_type=content_type,
            pdf_id=self.pdf_id,
            metadata=metadata
        )

    def _process_table_item(
        self,
        item: TableItem,
        doc: DoclingDocument,
        section_headers: List[str] = None,
        hierarchy_level: int = 0
    ) -> Optional[ContentElement]:
        """Process a table item with optimized data extraction."""
        try:
            if not hasattr(item, "data") or not item.data:
                return None

            # Initialize headers and rows first
            headers = []
            rows = []
            caption = ""
            markdown = ""

            # Try advanced DataFrame export
            try:
                df = item.export_to_dataframe()
                headers = df.columns.tolist()
                rows = df.values.tolist()
            except Exception as df_error:
                logger.warning(f"DataFrame export failed: {df_error}")
                # Fallback
                try:
                    if hasattr(item.data, "grid"):
                        grid = item.data.grid
                        if grid and len(grid) > 0:
                            headers = [getattr(cell, "text", "") for cell in grid[0]]
                            rows = []
                            for i in range(1, len(grid)):
                                rows.append([getattr(cell, "text", "") for cell in grid[i]])
                except Exception as grid_error:
                    logger.warning(f"Grid extraction failed: {grid_error}")

            # Now filter headers after they're initialized
            headers = [str(h) for h in headers if h is not None]

            # Try caption
            try:
                if hasattr(item, "caption_text") and callable(getattr(item, "caption_text")):
                    caption = item.caption_text(doc) or ""
            except Exception as e:
                logger.warning(f"Caption extraction failed: {e}")

            # Try to get markdown
            try:
                markdown = item.export_to_markdown()
            except Exception as md_error:
                logger.warning(f"Markdown export failed: {md_error}")
                # Manual fallback
                md_lines = []
                if headers:
                    md_lines.append("| " + " | ".join(str(h) for h in headers) + " |")
                    md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
                    for row in rows[:10]:
                        md_lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
                markdown = "\n".join(md_lines)

            # Page number
            page_number = 0
            if item.prov and hasattr(item.prov[0], "page_no"):
                page_number = item.prov[0].page_no

            row_count = len(rows)
            col_count = len(headers) if headers else (len(rows[0]) if rows else 0)
            summary = f"Table with {row_count} rows and {col_count} columns"
            if caption:
                summary = f"{caption} - {summary}"

            # Extract technical terms from table content
            technical_terms = []
            if self.config.extract_technical_terms:
                text_parts = [caption] if caption else []
                text_parts.extend(str(h) for h in headers if h)
                if rows and rows[0]:
                    text_parts.extend(str(cell) for cell in rows[0] if cell)
                technical_terms = extract_technical_terms(" ".join(text_parts))

            # Create table data object
            table_data = {
                "headers": headers,
                "rows": rows[:10],  # Only store the first 10 rows to avoid excessive metadata
                "caption": caption,
                "markdown": markdown,
                "summary": summary,
                "row_count": row_count,
                "column_count": col_count,
                "technical_concepts": technical_terms
            }

            # Determine embedding type for tables
            embedding_type = EmbeddingType.TECHNICAL
            if any(term.lower() in caption.lower() for term in ["procedure", "process", "step", "task"]):
                embedding_type = EmbeddingType.TASK

            element_id = f"tbl_{self.pdf_id}_{uuid.uuid4().hex[:8]}"

            metadata = ContentMetadata(
                pdf_id=self.pdf_id,
                page_number=page_number,
                content_type=ContentType.TABLE,
                technical_terms=technical_terms,
                table_data=table_data,
                section_headers=section_headers or [],
                hierarchy_level=hierarchy_level,
                element_id=element_id,
                chunk_level=ChunkLevel.SECTION,  # Tables are typically section-level
                embedding_type=embedding_type,
                docling_ref=getattr(item, "self_ref", None)
            )

            return ContentElement(
                element_id=element_id,
                content=markdown,
                content_type=ContentType.TABLE,
                pdf_id=self.pdf_id,
                metadata=metadata
            )

        except Exception as e:
            logger.warning(f"Failed to process table item: {e}")
            return None

    def _process_picture_item(
        self,
        item: PictureItem,
        doc: DoclingDocument,
        section_headers: List[str] = None,
        hierarchy_level: int = 0
    ) -> Optional[ContentElement]:
        """Process an image item with comprehensive metadata extraction."""
        try:
            if not hasattr(item, "get_image") or not callable(getattr(item, "get_image")):
                return None

            pil_image = None
            try:
                pil_image = item.get_image(doc)
            except Exception as img_error:
                logger.warning(f"Failed to get image: {img_error}")
                return None

            if not pil_image:
                return None

            image_id = f"img_{self.pdf_id}_{uuid.uuid4().hex[:8]}"

            images_dir = self.output_dir / "assets" / "images"
            images_dir.mkdir(parents=True, exist_ok=True)
            image_path = images_dir / f"{image_id}.png"

            try:
                pil_image.save(image_path, format="PNG")
            except Exception as save_error:
                logger.warning(f"Failed to save image: {save_error}")
                return None

            caption = "Image"
            try:
                if hasattr(item, "caption_text") and callable(getattr(item, "caption_text")):
                    maybe_cap = item.caption_text(doc)
                    if maybe_cap:
                        caption = maybe_cap
            except Exception as caption_error:
                logger.warning(f"Caption extraction failed: {caption_error}")

            page_number = 0
            if item.prov and hasattr(item.prov[0], "page_no"):
                page_number = item.prov[0].page_no

            # Extract context
            context = self._extract_surrounding_context(item, doc)

            # Generate markdown content
            rel_path = str(image_path.relative_to(self.output_dir)) if str(image_path).startswith(str(self.output_dir)) else str(image_path)
            md_content = f"![{caption}]({rel_path})"

            # Extract technical terms from caption and context
            technical_terms = extract_technical_terms(caption + " " + (context or ""))

            # Create image features
            image_features = {
                "dimensions": (pil_image.width, pil_image.height),
                "aspect_ratio": pil_image.width / pil_image.height if pil_image.height > 0 else 1.0,
                "color_mode": pil_image.mode,
                "is_grayscale": pil_image.mode in ("L", "LA")
            }

            # Detect objects in image
            detected_objects = self._detect_objects_in_image(pil_image, caption)

            # Create image analysis
            image_analysis = {
                "description": caption,
                "detected_objects": detected_objects,
                "technical_details": {"width": pil_image.width, "height": pil_image.height},
                "technical_concepts": technical_terms
            }

            # Create image paths
            image_paths = {
                "original": str(image_path),
                "format": "PNG",
                "size": os.path.getsize(image_path) if os.path.exists(image_path) else 0
            }

            # Create complete image metadata
            image_metadata = {
                "image_id": image_id,
                "paths": image_paths,
                "features": image_features,
                "analysis": image_analysis,
                "page_number": page_number
            }

            element_id = image_id

            metadata = ContentMetadata(
                pdf_id=self.pdf_id,
                page_number=page_number,
                content_type=ContentType.IMAGE,
                technical_terms=technical_terms,
                image_metadata=image_metadata,
                section_headers=section_headers or [],
                hierarchy_level=hierarchy_level,
                element_id=element_id,
                chunk_level=ChunkLevel.SECTION,  # Images are typically section-level
                embedding_type=EmbeddingType.CONCEPTUAL,  # Use conceptual embedding for images
                context=context,
                image_path=str(image_path),
                docling_ref=getattr(item, "self_ref", None)
            )

            return ContentElement(
                element_id=element_id,
                content=md_content,
                content_type=ContentType.IMAGE,
                pdf_id=self.pdf_id,
                metadata=metadata
            )

        except Exception as e:
            logger.warning(f"Failed to process picture item: {e}")
            return None

    def _extract_surrounding_context(self, item: Any, doc: DoclingDocument) -> Optional[str]:
        """Extract text surrounding an item to provide context."""
        try:
            context_parts = []
            if hasattr(item, "caption_text") and callable(getattr(item, "caption_text")):
                caption = item.caption_text(doc)
                if caption:
                    context_parts.append(caption)

            page_number = 0
            if hasattr(item, "prov") and item.prov:
                if hasattr(item.prov[0], "page_no"):
                    page_number = item.prov[0].page_no

            # If doc.texts is present, gather some text from same page
            if hasattr(doc, "texts"):
                page_texts = []
                for text_item in doc.texts:
                    text_page = 0
                    if text_item.prov and hasattr(text_item.prov[0], "page_no"):
                        text_page = text_item.prov[0].page_no
                    if text_page == page_number and hasattr(text_item, "text"):
                        page_texts.append(text_item.text)
                # Limit to the first few
                if page_texts:
                    context_parts.append(" ".join(page_texts[:3]))

            return " ".join(context_parts) if context_parts else None
        except Exception as e:
            logger.warning(f"Failed to extract context: {e}")
            return None

    def _detect_objects_in_image(self, image, caption: str) -> List[str]:
        """
        Detect objects in image based on caption and image properties.
        Enhanced with domain-specific detection for technical visualizations.
        """
        objects = []
        caption_lower = caption.lower()

        # Common technical visualization types
        common_visualization_types = {
            "chart", "graph", "diagram", "figure", "table", "schematic",
            "screenshot", "interface", "ui", "drawing", "illustration",
            "architecture", "component", "system", "network", "flow",
            "trend", "history", "visualization", "plot", "panel"
        }

        # Check caption for visualization types
        for obj_type in common_visualization_types:
            if obj_type in caption_lower:
                objects.append(obj_type)

        # Domain-specific detection for Niagara framework
        niagara_specific = {
            "hierarchy": ["hierarchy", "nav tree", "navigation", "structure"],
            "wire_sheet": ["wire sheet", "logic", "function block", "diagram"],
            "trend_chart": ["trend", "chart", "plot", "history", "graph"],
            "px_view": ["px view", "px page", "dashboard", "user interface"]
        }

        for category, terms in niagara_specific.items():
            if any(term in caption_lower for term in terms):
                objects.append(category)

        # If no objects detected yet, check image dimensions for clues
        if not objects:
            width, height = image.size
            if width > height * 1.5:
                objects.append("wide image")
            elif height > width * 1.5:
                objects.append("tall image")

        return objects

    async def _extract_procedures_and_parameters(
        self,
        elements: List[ContentElement],
        md_content: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Extract procedures and parameters from the document content.

        Args:
            elements: List of content elements
            md_content: Markdown content

        Returns:
            Tuple of (procedures, parameters)
        """
        try:
            from app.chat.utils.extraction import extract_procedures_and_parameters

            # Extract procedures and parameters
            procedures, parameters = extract_procedures_and_parameters(md_content)

            # Add section context to procedures
            for proc in procedures:
                # Find section context
                section_headers = []
                for element in elements:
                    if element.metadata.page_number == proc.get("page", 0):
                        if element.metadata.section_headers:
                            section_headers = element.metadata.section_headers
                            break

                proc["section_headers"] = section_headers
                proc["pdf_id"] = self.pdf_id

                # Create a unique ID for the procedure
                proc["procedure_id"] = f"proc_{self.pdf_id}_{uuid.uuid4().hex[:8]}"

                # Create a procedure element
                if proc.get("content"):
                    proc_element = self._create_content_element(
                        element_id=proc["procedure_id"],
                        content=proc["content"],
                        content_type=ContentType.PROCEDURE,
                        metadata=ContentMetadata(
                            pdf_id=self.pdf_id,
                            page_number=proc.get("page", 0),
                            content_type=ContentType.PROCEDURE,
                            section_headers=section_headers,
                            hierarchy_level=2,  # Procedures are usually second level
                            technical_terms=proc.get("parameters", []),
                            procedure_metadata=proc,
                            chunk_level=ChunkLevel.PROCEDURE,
                            embedding_type=EmbeddingType.TASK
                        )
                    )
                    elements.append(proc_element)

            # Add section context to parameters
            for param in parameters:
                # Find section context
                section_headers = []
                for element in elements:
                    if element.metadata.page_number == param.get("page", 0):
                        if element.metadata.section_headers:
                            section_headers = element.metadata.section_headers
                            break

                param["section_headers"] = section_headers
                param["pdf_id"] = self.pdf_id

                # Create a unique ID for the parameter
                param["parameter_id"] = f"param_{self.pdf_id}_{uuid.uuid4().hex[:8]}"

                # Create a parameter element
                if param.get("name") and param.get("description"):
                    content = f"{param['name']}: {param['description']}"
                    param_element = self._create_content_element(
                        element_id=param["parameter_id"],
                        content=content,
                        content_type=ContentType.PARAMETER,
                        metadata=ContentMetadata(
                            pdf_id=self.pdf_id,
                            page_number=param.get("page", 0),
                            content_type=ContentType.PARAMETER,
                            section_headers=section_headers,
                            hierarchy_level=3,  # Parameters are usually third level
                            technical_terms=[param["name"]],
                            parameter_metadata=param,
                            chunk_level=ChunkLevel.STEP,
                            embedding_type=EmbeddingType.TECHNICAL
                        )
                    )
                    elements.append(param_element)

            return procedures, parameters

        except Exception as e:
            logger.error(f"Error extracting procedures and parameters: {str(e)}")
            return [], []

    async def _generate_multi_level_chunks(
        self,
        elements: List[ContentElement],
        md_content: str
    ) -> List[DocumentChunk]:
        """
        Generate multi-level chunks from document content.
        Implements the hierarchical chunking strategy.

        Args:
            elements: List of content elements
            md_content: Markdown content

        Returns:
            List of document chunks at different levels
        """
        chunking_start = time.time()
        chunks = []

        try:
            # Group elements by section and page
            section_elements = defaultdict(list)
            page_elements = defaultdict(list)

            # Map element IDs to elements for easier lookup
            element_map = {e.element_id: e for e in elements}

            # Group by section and page
            for element in elements:
                # Skip page elements
                if element.content_type == ContentType.PAGE:
                    continue

                # Group by section
                section_key = " > ".join(element.metadata.section_headers) if element.metadata.section_headers else "unknown_section"
                section_elements[section_key].append(element)

                # Group by page
                page_elements[element.metadata.page_number].append(element)

            # 1. Create document-level chunks
            doc_chunk_id = f"doc_{self.pdf_id}_overview"
            doc_chunk = DocumentChunk(
                chunk_id=doc_chunk_id,
                content=self._extract_overview_text(md_content, 3000),
                metadata=ChunkMetadata(
                    pdf_id=self.pdf_id,
                    content_type="text",
                    chunk_level=ChunkLevel.DOCUMENT,
                    chunk_index=0,
                    page_numbers=[],
                    section_headers=[],
                    embedding_type=EmbeddingType.CONCEPTUAL,
                    element_ids=[],
                    token_count=len(self.tokenizer.encode(self._extract_overview_text(md_content, 3000)))
                )
            )
            chunks.append(doc_chunk)

            # 2. Create section-level chunks
            section_index = 0
            for section_key, section_elems in section_elements.items():
                # Skip empty sections
                if not section_elems:
                    continue

                # Extract pages covered by this section
                pages = sorted(list(set(e.metadata.page_number for e in section_elems if e.metadata.page_number)))

                # Extract section content
                section_content = "\n\n".join(e.content for e in section_elems)

                # Extract technical terms
                tech_terms = set()
                for elem in section_elems:
                    if hasattr(elem.metadata, 'technical_terms') and elem.metadata.technical_terms:
                        tech_terms.update(elem.metadata.technical_terms)

                # Create section chunk
                section_chunk_id = f"sec_{self.pdf_id}_{section_index}"
                section_chunk = DocumentChunk(
                    chunk_id=section_chunk_id,
                    content=section_content,
                    metadata=ChunkMetadata(
                        pdf_id=self.pdf_id,
                        content_type="text",
                        chunk_level=ChunkLevel.SECTION,
                        chunk_index=section_index,
                        page_numbers=pages,
                        section_headers=section_key.split(" > ") if section_key != "unknown_section" else [],
                        parent_chunk_id=doc_chunk_id,
                        technical_terms=list(tech_terms),
                        embedding_type=EmbeddingType.CONCEPTUAL,
                        element_ids=[e.element_id for e in section_elems],
                        token_count=len(self.tokenizer.encode(section_content))
                    )
                )
                chunks.append(section_chunk)
                section_index += 1

            # 3. Create procedure-level chunks
            procedure_elements = [e for e in elements if e.content_type == ContentType.PROCEDURE]

            for p_index, proc_elem in enumerate(procedure_elements):
                # Find parent section
                parent_section_key = " > ".join(proc_elem.metadata.section_headers) if proc_elem.metadata.section_headers else "unknown_section"
                parent_section_chunk = next((chunk for chunk in chunks if
                                          chunk.metadata.chunk_level == ChunkLevel.SECTION and
                                          " > ".join(chunk.metadata.section_headers) == parent_section_key), None)

                parent_chunk_id = parent_section_chunk.chunk_id if parent_section_chunk else doc_chunk_id

                # Create procedure chunk
                proc_chunk_id = f"proc_{self.pdf_id}_{p_index}"
                proc_chunk = DocumentChunk(
                    chunk_id=proc_chunk_id,
                    content=proc_elem.content,
                    metadata=ChunkMetadata(
                        pdf_id=self.pdf_id,
                        content_type="procedure",
                        chunk_level=ChunkLevel.PROCEDURE,
                        chunk_index=p_index,
                        page_numbers=[proc_elem.metadata.page_number] if proc_elem.metadata.page_number else [],
                        section_headers=proc_elem.metadata.section_headers,
                        parent_chunk_id=parent_chunk_id,
                        technical_terms=proc_elem.metadata.technical_terms,
                        embedding_type=EmbeddingType.TASK,
                        element_ids=[proc_elem.element_id],
                        token_count=len(self.tokenizer.encode(proc_elem.content))
                    )
                )
                chunks.append(proc_chunk)

            # 4. Create parameter-level (step-level) chunks
            parameter_elements = [e for e in elements if e.content_type == ContentType.PARAMETER]

            for param_index, param_elem in enumerate(parameter_elements):
                # Find parent procedure if applicable
                if param_elem.metadata.parameter_metadata and "procedure_id" in param_elem.metadata.parameter_metadata:
                    proc_id = param_elem.metadata.parameter_metadata["procedure_id"]
                    parent_proc_chunk = next((chunk for chunk in chunks if
                                           chunk.metadata.chunk_level == ChunkLevel.PROCEDURE and
                                           proc_id in chunk.metadata.element_ids), None)

                    parent_chunk_id = parent_proc_chunk.chunk_id if parent_proc_chunk else doc_chunk_id
                else:
                    # Find parent section
                    parent_section_key = " > ".join(param_elem.metadata.section_headers) if param_elem.metadata.section_headers else "unknown_section"
                    parent_section_chunk = next((chunk for chunk in chunks if
                                              chunk.metadata.chunk_level == ChunkLevel.SECTION and
                                              " > ".join(chunk.metadata.section_headers) == parent_section_key), None)

                    parent_chunk_id = parent_section_chunk.chunk_id if parent_section_chunk else doc_chunk_id

                # Create parameter chunk
                param_chunk_id = f"param_{self.pdf_id}_{param_index}"
                param_chunk = DocumentChunk(
                    chunk_id=param_chunk_id,
                    content=param_elem.content,
                    metadata=ChunkMetadata(
                        pdf_id=self.pdf_id,
                        content_type="parameter",
                        chunk_level=ChunkLevel.STEP,
                        chunk_index=param_index,
                        page_numbers=[param_elem.metadata.page_number] if param_elem.metadata.page_number else [],
                        section_headers=param_elem.metadata.section_headers,
                        parent_chunk_id=parent_chunk_id,
                        technical_terms=param_elem.metadata.technical_terms,
                        embedding_type=EmbeddingType.TECHNICAL,
                        element_ids=[param_elem.element_id],
                        token_count=len(self.tokenizer.encode(param_elem.content))
                    )
                )
                chunks.append(param_chunk)

            # Record metrics
            self.metrics["timings"]["chunking"] = time.time() - chunking_start
            self.metrics["counts"]["chunks"] = len(chunks)
            self.metrics["counts"]["document_chunks"] = sum(1 for c in chunks if c.metadata.chunk_level == ChunkLevel.DOCUMENT)
            self.metrics["counts"]["section_chunks"] = sum(1 for c in chunks if c.metadata.chunk_level == ChunkLevel.SECTION)
            self.metrics["counts"]["procedure_chunks"] = sum(1 for c in chunks if c.metadata.chunk_level == ChunkLevel.PROCEDURE)
            self.metrics["counts"]["step_chunks"] = sum(1 for c in chunks if c.metadata.chunk_level == ChunkLevel.STEP)

            logger.info(f"Generated {len(chunks)} chunks using multi-level chunking strategy")
            return chunks

        except Exception as e:
            logger.error(f"Error generating multi-level chunks: {str(e)}", exc_info=True)
            return []

    def _extract_overview_text(self, md_content: str, max_tokens: int = 3000) -> str:
        """
        Extract overview text from markdown content.
        Gets the beginning of the document for a document-level overview.

        Args:
            md_content: Markdown content
            max_tokens: Maximum tokens to extract

        Returns:
            Overview text
        """
        # Get encoded tokens
        encoded = self.tokenizer.encode(md_content)

        # Truncate if needed
        if len(encoded) > max_tokens:
            encoded = encoded[:max_tokens]

        # Decode back to text
        return self.tokenizer.decode(encoded)

    def _extract_all_technical_terms(self, elements: List[ContentElement]) -> List[str]:
        """
        Extract all technical terms from document elements with deduplication.

        Args:
            elements: List of content elements

        Returns:
            List of unique technical terms
        """
        all_terms = set()

        for element in elements:
            if hasattr(element, 'metadata') and hasattr(element.metadata, 'technical_terms'):
                all_terms.update(element.metadata.technical_terms)

        return list(all_terms)

    async def _build_concept_network(self, elements: List[ContentElement], chunks: List[DocumentChunk]) -> None:
        """
        Build concept network from document content using optimized extraction methods.
        Enhanced to focus on key technical concepts and domain-specific relationships.
        """
        try:
            # 1. Set enhanced configuration for concept extraction
            MIN_CONCEPT_OCCURRENCES = 1  # Capture ALL technical terms, even rare ones
            MIN_RELATIONSHIP_CONFIDENCE = 0.5  # LOWERED from 0.6 to catch more relationships
            MAX_CONCEPTS = self.config.max_concepts_per_document

            # 2. Extract concepts with improved domain awareness
            concepts_info = defaultdict(lambda: {
                "count": 0,
                "in_headers": False,
                "sections": set(),
                "pages": set(),
                "domain_category": None  # Track domain category for each concept
            })

            # Process elements with deep extraction of all technical terms
            for element in elements:
                if element.metadata.technical_terms:
                    for term in element.metadata.technical_terms:
                        # Include ALL terms - even short ones might be important in technical docs
                        concepts_info[term]["count"] += 1

                        # Track header, section, and page information
                        if element.metadata.hierarchy_level <= 2:
                            concepts_info[term]["in_headers"] = True
                        if element.metadata.section_headers:
                            concepts_info[term]["sections"].update(element.metadata.section_headers)
                        if element.metadata.page_number:
                            concepts_info[term]["pages"].add(element.metadata.page_number)

                        # Check if this is a domain-specific term
                        from app.chat.utils.extraction import DOMAIN_SPECIFIC_TERMS
                        for category, domain_terms in DOMAIN_SPECIFIC_TERMS.items():
                            term_lower = term.lower()
                            if any(dt.lower() in term_lower or term_lower in dt.lower() for dt in domain_terms):
                                concepts_info[term]["domain_category"] = category
                                break

            # 3. Score concepts for importance with enhanced logic
            concept_scores = {}
            for term, info in concepts_info.items():
                # Base score from occurrences with logarithmic scaling to avoid over-penalizing rare terms
                occurrences = info["count"]
                base_score = 0.5 + min(0.5, math.log(occurrences + 1) / 5.0)

                # Bonus for appearing in headers (critical for technical docs)
                header_bonus = 0.3 if info["in_headers"] else 0

                # Bonus for appearing in multiple sections
                section_bonus = min(0.3, len(info["sections"]) * 0.1)

                # Bonus for multi-word terms (likely more specific)
                specificity_bonus = 0.1 if " " in term else 0

                # Domain-specific bonus - prioritize terms from our known domain
                domain_bonus = 0.3 if info["domain_category"] else 0

                # Page coverage bonus - terms that appear across many pages are important
                page_bonus = min(0.2, len(info["pages"]) * 0.02)

                # Combined score
                concept_scores[term] = base_score + header_bonus + section_bonus + specificity_bonus + domain_bonus + page_bonus

            # 4. Select top concepts by importance score
            top_concepts = sorted(
                concept_scores.items(),
                key=lambda x: x[1],
                reverse=True
            )[:MAX_CONCEPTS]

            # 5. Create concept objects for only the top concepts
            concept_objects = []
            top_concept_terms = set(term for term, _ in top_concepts)

            for term, score in top_concepts:
                info = concepts_info[term]
                concept = Concept(
                    name=term,
                    occurrences=info["count"],
                    in_headers=info["in_headers"],
                    sections=list(info["sections"]),
                    first_occurrence_page=min(info["pages"]) if info["pages"] else None,
                    importance_score=score,
                    is_primary=score > 0.8,  # Top concepts are primary
                    category=info["domain_category"],  # Include domain category
                    pdf_id=self.pdf_id
                )
                concept_objects.append(concept)
                self.concept_network.add_concept(concept)

            # 6. Extract all text content for relationship analysis
            full_text = ""
            for element in elements:
                if element.content_type == ContentType.TEXT and element.content:
                    full_text += element.content + "\n\n"

            # 7. Use the extract_document_relationships function with domain awareness
            relationships = extract_document_relationships(
                text=full_text,
                technical_terms=list(top_concept_terms),
                min_confidence=MIN_RELATIONSHIP_CONFIDENCE  # Using lower threshold
            )

            # Log the number of relationships found with the lower threshold
            if relationships:
                logger.info(f"Found {len(relationships)} relationships with confidence threshold {MIN_RELATIONSHIP_CONFIDENCE}")
            else:
                logger.info(f"No relationships found even with lower confidence threshold {MIN_RELATIONSHIP_CONFIDENCE}")

            # 8. Add extracted relationships to the concept network
            for rel in relationships:
                relationship = ConceptRelationship(
                    source=rel["source"],
                    target=rel["target"],
                    type=RelationType.map_type(rel["relationship_type"]),  # Convert to enum
                    weight=rel.get("confidence", 0.75),
                    context=rel.get("context", ""),
                    extraction_method=rel.get("extraction_method", "document-based"),
                    pdf_id=self.pdf_id
                )
                self.concept_network.add_relationship(relationship)

            # 9. Calculate importance scores and identify primary concepts
            self.concept_network.calculate_importance_scores()

            # 10. Register with research manager for reuse
            if self.research_manager:
                self._handle_research_manager_integration(self.concept_network)

            logger.info(
                f"Built optimized concept network with {len(concept_objects)} concepts "
                f"and {len(relationships)} relationships"
            )

        except Exception as e:
            logger.error(f"Concept network building failed: {e}", exc_info=True)
            # Don't fail completely, create an empty network
            self.concept_network = ConceptNetwork(pdf_id=self.pdf_id)

    def _predict_document_category(self, technical_terms: List[str], content: str) -> str:
        """
        Predict document category based on detected domain terms and content.
        Uses a combined approach with priority on vendor-specific matching.

        Args:
            technical_terms: List of technical terms extracted from the document
            content: Full document content

        Returns:
            Predicted category based on domain patterns
        """
        # First, try vendor-specific matching (legacy approach)
        vendor_category = self._vendor_specific_category_match(technical_terms, content)
        if vendor_category != "general":
            # If we have a confident vendor match, return it immediately
            logger.info(f"Predicted vendor-specific category: {vendor_category}")
            return vendor_category

        # If no vendor match, try the domain term counter approach
        if self.domain_term_counters:
            # Get the most frequent category based on term counts
            category_counts = {
                category: count for category, count in self.domain_term_counters.items()
                if not category.startswith("term:")  # Filter out individual term counts
            }

            if category_counts:
                # Get the top category
                top_category = max(category_counts.items(), key=lambda x: x[1])[0]

                # Only use if we have a meaningful number of matches
                if category_counts[top_category] > 2:
                    # Map to output category name
                    doc_type_map = {
                        "niagara": "tridium",
                        "station": "tridium",
                        "hierarchy": "tridium",
                        "component": "tridium",
                        "hvac": "building_automation",
                        "control": "building_automation",
                        "alarm": "building_automation",
                        "trend": "data_visualization",
                        "interval": "data_visualization",
                        "visualization": "data_visualization",
                        "module": "development",
                        "node": "development",
                        "programming": "development",
                        "security": "security",
                        "database": "integration",
                        "network": "networking"
                    }

                    mapped_category = doc_type_map.get(top_category, "general")
                    logger.info(f"Predicted category based on domain terms: {mapped_category}")
                    return mapped_category

        # Fall back to checking document content for known keywords
        content_lower = content.lower()

        # Final check for strong vendor indicators in the content
        if "niagara" in content_lower or "tridium" in content_lower or "jace" in content_lower:
            return "tridium"
        if "honeywell" in content_lower or "webs" in content_lower or "excel web" in content_lower:
            return "honeywell"
        if "johnson" in content_lower or "metasys" in content_lower or "jci" in content_lower:
            return "johnson_controls"

        # If still no clear category, return general
        return "general"

    def _vendor_specific_category_match(self, technical_terms: List[str], content: str) -> str:
        """
        Specialized vendor category matching based on the legacy approach.
        Optimized for building automation vendors.

        Args:
            technical_terms: List of technical terms extracted from the document
            content: Full document content

        Returns:
            Vendor category or "general" if no strong match
        """
        # Define vendor-specific terminology with expanded keyword lists
        vendor_terms = {
            "tridium": {
                # Core platform terms
                "niagara", "jace", "vykon", "workbench", "baja", "fox", "ax", "n4",
                "iojas", "nrio", "ntec", "niagaraax", "niagara4", "station", "tridium",
                "hierarchy", "nav", "navtree", "hierarchy definition", "hierarchyservice",
                # Additional Tridium-specific terms
                "bajascript", "wire sheet", "px", "px page", "slot", "ordinal", "ord",
                "property sheet", "palette", "workbench", "wb", "supervisor", "supervisor web",
                "niagara framework", "ndriver", "ntransport"
            },
            "honeywell": {
                # Core Honeywell terms
                "honeywell", "webs", "websx", "c-bus", "economizer", "spyder", "sylk",
                "excel", "eaglehawk", "jade", "lynx", "centraline", "wcps", "cbs",
                "excel web", "symmetre", "honeyweb", "analytics", "wpa", "ebi",
                # Additional Honeywell-specific terms
                "smartvfd", "honeynet", "arena", "care", "comfort point", "comfortpoint",
                "enterprise buildings integrator", "webs-ax", "webs-n4", "sauter"
            },
            "johnson_controls": {
                # Core JCI terms
                "johnson", "metasys", "fec", "fas", "fms", "cctp", "vma", "vav", "nae",
                "ncm", "adc", "ddc", "vfd", "bacnet", "n2", "fpm", "n1", "bacpack",
                "jci", "field controller", "facility explorer", "jc companion",
                # Additional Johnson Controls terms
                "metasys extended architecture", "network engine", "m4-workstation",
                "fec", "vma", "adc", "tec", "smartvav", "cvs", "cds", "m4", "m5",
                "ms/tp", "n1", "n2", "lon", "johnson controls"
            }
        }

        # Count matches for each vendor
        match_counts = {vendor: 0 for vendor in vendor_terms}
        strong_indicators = {vendor: [] for vendor in vendor_terms}

        # Check each technical term against vendor-specific terminology
        for term in technical_terms:
            term_lower = term.lower()
            for vendor, terms in vendor_terms.items():
                # Check for exact or partial match in vendor terms
                for v_term in terms:
                    if v_term in term_lower or term_lower in v_term:
                        match_counts[vendor] += 1
                        # Keep track of what terms matched for debugging
                        strong_indicators[vendor].append(term)
                        break

        # Check content for direct vendor mentions
        content_lower = content.lower()
        for vendor, terms in vendor_terms.items():
            for term in terms:
                if term in content_lower:
                    # Full term match in content gets higher weight
                    if f" {term} " in f" {content_lower} ":  # Ensure it's a whole word
                        match_counts[vendor] += 1
                    else:
                        match_counts[vendor] += 0.5  # Partial match gets lower weight

        # Log what we found for debugging/visibility
        for vendor, count in match_counts.items():
            if count > 0:
                logger.debug(f"Vendor match: {vendor}, count: {count}, indicators: {strong_indicators[vendor][:5]}")

        # Find the vendor with the highest match count - require stronger confidence
        if max(match_counts.values()) > 2:  # Require at least 2 matches for confident categorization
            best_vendor = max(match_counts.items(), key=lambda x: x[1])[0]
            logger.info(f"Strong vendor match found: {best_vendor} with {match_counts[best_vendor]} indicators")
            return best_vendor

        # If we have some matches but not enough for confidence, check some heuristics
        if max(match_counts.values()) > 0:
            best_vendor = max(match_counts.items(), key=lambda x: x[1])[0]

            # Check for strong vendor-specific titles
            if "metasys" in content_lower[:500]:  # Check document title/header
                return "johnson_controls"
            if "niagara" in content_lower[:500] or "tridium" in content_lower[:500]:
                return "tridium"
            if "honeywell" in content_lower[:500]:
                return "honeywell"

            # Some threshold was met, but not enough for high confidence
            logger.info(f"Potential vendor match: {best_vendor} with {match_counts[best_vendor]} indicators (below confidence threshold)")

        return "general"  # Default category if no strong matches

    async def _ingest_to_unified_store(
        self,
        elements: List[ContentElement],
        chunks: List[DocumentChunk],
        document_summary: Dict[str, Any],
        predicted_category: str
    ) -> bool:
        """
        Ingest processed content into unified store (MongoDB + Qdrant).
        Fixed to handle both sync and async method calls correctly.
        """
        logger.info(f"Ingesting processed content to unified store for {self.pdf_id}")

        try:
            # 1. Create document node - FIXED TO REMOVE AWAIT
            document_title = document_summary.get('title', f"Document {self.pdf_id}")

            metadata = {
                "processed_at": datetime.utcnow().isoformat(),
                "element_count": len(elements),
                "domain_category": predicted_category,
                "document_summary": document_summary
            }

            # FIXED: Don't use await for non-async methods
            doc_created = self.vector_store.create_document_node(
                pdf_id=self.pdf_id,
                title=document_title,
                metadata=metadata
            )

            if not doc_created:
                logger.warning(f"Failed to create document node for {self.pdf_id}, attempting to continue")

            # 2. Add content elements in batches
            batch_size = 20  # Smaller batch size to reduce memory pressure
            added_elements = 0
            failed_elements = 0

            # Process in batches
            for i in range(0, len(elements), batch_size):
                batch = elements[i:i+batch_size]
                batch_success = True

                for element in batch:
                    try:
                        # FIXED: Don't use await for non-async methods
                        success = self.vector_store.add_content_element(element, self.pdf_id)
                        if success:
                            added_elements += 1
                        else:
                            failed_elements += 1
                            batch_success = False
                    except Exception as element_error:
                        logger.error(f"Error adding element {element.element_id}: {str(element_error)}")
                        failed_elements += 1
                        batch_success = False

                # Log progress
                logger.info(f"Added {added_elements}/{len(elements)} elements to unified store, {failed_elements} failed")

                # Force garbage collection
                import gc
                gc.collect()

            # 3. Add concept network data
            # Add concepts in batches
            concept_batch_size = 50
            logger.info(f"Adding {len(self.concept_network.concepts)} concepts in batches")

            for i in range(0, len(self.concept_network.concepts), concept_batch_size):
                concept_batch = self.concept_network.concepts[i:i+concept_batch_size]
                for concept in concept_batch:
                    try:
                        # FIXED: Don't use await for non-async methods
                        self.vector_store.add_concept(
                            concept_name=concept.name,
                            pdf_id=self.pdf_id,
                            metadata={
                                "importance": concept.importance_score,
                                "is_primary": concept.is_primary,
                                "category": concept.category
                            }
                        )
                    except Exception as concept_error:
                        logger.error(f"Error adding concept {concept.name}: {str(concept_error)}")

                # Log progress and cleanup memory
                logger.info(f"Added concepts batch {i//concept_batch_size + 1}/{(len(self.concept_network.concepts) + concept_batch_size - 1)//concept_batch_size}")
                gc.collect()

            # Add relationships in batches
            relationship_batch_size = 50
            logger.info(f"Adding {len(self.concept_network.relationships)} relationships in batches")

            for i in range(0, len(self.concept_network.relationships), relationship_batch_size):
                relationship_batch = self.concept_network.relationships[i:i+relationship_batch_size]
                for relationship in relationship_batch:
                    try:
                        rel_type = relationship.type
                        if hasattr(rel_type, 'value'):
                            rel_type = rel_type.value

                        # FIXED: Don't use await for non-async methods
                        self.vector_store.add_concept_relationship(
                            source=relationship.source,
                            target=relationship.target,
                            rel_type=str(rel_type),
                            pdf_id=self.pdf_id,
                            metadata={
                                "weight": relationship.weight,
                                "context": relationship.context
                            }
                        )
                    except Exception as relationship_error:
                        logger.error(f"Error adding relationship: {str(relationship_error)}")

                # Log progress and cleanup memory
                logger.info(f"Added relationships batch {i//relationship_batch_size + 1}/{(len(self.concept_network.relationships) + relationship_batch_size - 1)//relationship_batch_size}")
                gc.collect()

            # 4. Add procedures and parameters
            if hasattr(self, 'procedures') and self.procedures:
                logger.info(f"Adding {len(self.procedures)} procedures")
                for procedure in self.procedures:
                    try:
                        # FIXED: Don't use await for non-async methods
                        self.vector_store.add_procedure(procedure, self.pdf_id)
                    except Exception as proc_error:
                        logger.error(f"Error adding procedure: {str(proc_error)}")

            if hasattr(self, 'parameters') and self.parameters:
                logger.info(f"Adding {len(self.parameters)} parameters")
                for parameter in self.parameters:
                    try:
                        # FIXED: Don't use await for non-async methods
                        self.vector_store.add_parameter(parameter, self.pdf_id)
                    except Exception as param_error:
                        logger.error(f"Error adding parameter: {str(param_error)}")

            # 5. Final verification
            try:
                # FIXED: Don't use await for non-async methods unless the method is specifically async
                doc_metadata = self.vector_store.get_document_metadata(self.pdf_id)
                if doc_metadata:
                    logger.info(f"Successfully verified document {self.pdf_id} in database")
                else:
                    logger.warning(f"Document {self.pdf_id} verification failed")
            except Exception as verify_error:
                logger.warning(f"Document verification error: {str(verify_error)}")

            logger.info(f"Successfully ingested content to unified store for {self.pdf_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to ingest content to unified store: {str(e)}", exc_info=True)
            return False

    async def _update_pdf_metadata(self, document_summary: Dict[str, Any], predicted_category: str) -> None:
        """
        Update PDF metadata in the database with document summary and category.
        Also sets a meaningful description for the PDF.

        Args:
            document_summary: Document summary with title, concepts, insights, etc.
            predicted_category: Predicted document category
        """
        try:
            from app.web.db.models import Pdf
            from app.web.db import db

            # Fetch the PDF record
            pdf = db.session.execute(
                db.select(Pdf).filter_by(id=self.pdf_id)
            ).scalar_one()

            # Prepare metadata to add
            new_metadata = {
                'document_summary': document_summary,
                'predicted_category': predicted_category,
                'domain_term_counts': dict(self.domain_term_counters),
                'processing_date': datetime.utcnow().isoformat()
            }

            # Update metadata using our method
            pdf.update_metadata(new_metadata)

            # Set category if it's still "general" or not set
            if not pdf.category or pdf.category == 'general':
                pdf.category = predicted_category

            # IMPORTANT: Create a meaningful description from the summary
            description = ""

            # First try using the explicit description field if available
            if document_summary.get('description'):
                description = document_summary['description']
            # Next, try to find a descriptive insight to use
            elif document_summary.get('key_insights'):
                # Sort insights by length (descending) to find the most detailed one
                sorted_insights = sorted(document_summary['key_insights'], key=len, reverse=True)
                if sorted_insights:
                    description = sorted_insights[0]
            # Otherwise, build from title and concepts
            elif document_summary.get('title'):
                title = document_summary['title']
                # Skip generic titles
                if title != "Technical Document":
                    description = title

                # Add primary concepts if available
                if document_summary.get('primary_concepts'):
                    concepts = document_summary['primary_concepts'][:5]
                    if concepts:
                        if description:
                            description += ". "
                        description += f"Key concepts: {', '.join(concepts)}"

            # If still no description, create one from category
            if not description and predicted_category:
                description = f"Technical documentation related to {predicted_category.capitalize()}. "

                # Add primary concepts if available
                if document_summary.get('primary_concepts'):
                    concepts = document_summary['primary_concepts'][:5]
                    if concepts:
                        description += f"Key concepts: {', '.join(concepts)}"

            # Set a default if still empty
            if not description:
                description = f"Technical document with {len(document_summary.get('section_structure', []))} sections"

            # Trim if too long (database constraint might be 500-1000 chars)
            max_length = 500
            if len(description) > max_length:
                description = description[:max_length-3] + "..."

            # Update the description
            pdf.description = description
            logger.info(f"Updated PDF description: {description[:50]}...")

            # Mark as processed
            pdf.processed = True
            pdf.error = None
            pdf.processed_at = datetime.utcnow()

            # Commit changes
            db.session.commit()

            logger.info(f"Updated PDF metadata with summary, category: {predicted_category}, and description")
        except Exception as e:
            logger.error(f"Failed to update PDF metadata: {str(e)}")
            raise

    async def _update_pdf_error(self, error_message: str) -> None:
        """
        Update PDF record with error status.

        Args:
            error_message: Error message to store
        """
        try:
            from app.web.db.models import Pdf
            from app.web.db import db

            # Fetch the PDF record
            pdf = db.session.execute(
                db.select(Pdf).filter_by(id=self.pdf_id)
            ).scalar_one()

            # Update error information
            pdf.processed = False
            pdf.error = error_message
            pdf.processed_at = datetime.utcnow()

            # Commit changes
            db.session.commit()
            logger.info(f"Updated PDF with error status: {self.pdf_id}")
        except Exception as e:
            logger.error(f"Failed to update PDF error status: {str(e)}")
            raise

    def _add_concepts_to_section(self, section_path: str, concepts: List[str]) -> None:
        """Add concepts to a section in the concept network."""
        # Skip if no section path or concepts
        if not section_path or not concepts:
            return

        # Add to concept network's section mapping
        self.concept_network.add_section_concepts(section_path, concepts)

    def _handle_research_manager_integration(self, document_title, metadata):
        """Handle integration with research manager with robust error handling."""
        if not self.research_manager:
            return

        try:
            # Add document information - try multiple method signatures for compatibility
            if hasattr(self.research_manager, 'add_document_metadata'):
                self.research_manager.add_document_metadata(self.pdf_id, metadata)
            elif hasattr(self.research_manager, 'add_document'):
                # Map to expected parameters
                self.research_manager.add_document(
                    pdf_id=self.pdf_id,
                    title=document_title,
                    primary_concepts=self.concept_network.primary_concepts if self.concept_network else [],
                    summary=metadata.get('description', '')
                )

            # Register concept network if present
            if self.concept_network and hasattr(self.research_manager, 'register_concept_network'):
                self.research_manager.register_concept_network(self.pdf_id, self.concept_network)

            # Register primary concepts for cross-document analysis
            if self.concept_network and self.concept_network.primary_concepts:
                for concept in self.concept_network.primary_concepts:
                    if hasattr(self.research_manager, 'register_shared_concept'):
                        self.research_manager.register_shared_concept(
                            concept=concept,
                            pdf_ids={self.pdf_id},
                            confidence=0.95
                        )

        except Exception as e:
            logger.warning(f"Research manager integration error: {str(e)}")

    def _setup_directories(self) -> None:
        """Setup directory structure for processing outputs."""
        try:
            dirs = [
                self.output_dir / "content",
                self.output_dir / "assets" / "images",
                self.output_dir / "assets" / "raw",
                self.output_dir / "metadata",
                self.output_dir / "temp",
            ]
            for d in dirs:
                d.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Directory setup error: {e}")
            try:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                (self.output_dir / "content").mkdir(exist_ok=True)
            except Exception:
                pass

    async def _save_results(self, result: ProcessingResult) -> None:
        """Save processing results to disk with comprehensive organization."""
        try:
            for dir_path in [
                self.output_dir / "content",
                self.output_dir / "metadata",
                self.output_dir / "assets" / "images"
            ]:
                dir_path.mkdir(parents=True, exist_ok=True)

            # Save metadata
            meta_data = {
                "pdf_id": self.pdf_id,
                "processing_info": {
                    "start_time": self.processing_start.isoformat(),
                    "end_time": datetime.utcnow().isoformat(),
                    "config": self.config.dict(),
                },
                "metrics": self.metrics,
                "content_summary": result.get_statistics(),
                "section_hierarchy": self.section_hierarchy,
                "domain_term_counts": dict(self.domain_term_counters),
                "unified_store_status": "ingested"
            }

            # Save metadata
            meta_path = self.output_dir / "metadata" / "processing_result.json"
            try:
                async with aiofiles.open(meta_path, "w") as f:
                    await f.write(json.dumps(meta_data, default=str))
            except Exception as e:
                logger.warning(f"Failed to write metadata: {e}")

            logger.info(f"Successfully saved results for {self.pdf_id}")

        except Exception as e:
            logger.error(f"Failed to save results: {e}")

async def process_technical_document(
    pdf_id: str,
    config: Optional[ProcessingConfig] = None,
    openai_client: Optional[AsyncOpenAI] = None,
    research_manager = None,
    output_dir: Optional[Path] = None
) -> ProcessingResult:
    """
    Process technical document with MongoDB + Qdrant integration.
    Entry point for document processing pipeline.

    Args:
        pdf_id: Document identifier
        config: Processing configuration
        openai_client: OpenAI client
        research_manager: Optional research manager for cross-document analysis
        output_dir: Optional custom output directory

    Returns:
        ProcessingResult with structured content
    """
    logger.info(f"Starting document processing pipeline for {pdf_id}")

    # Default config if not provided
    if not config:
        config = ProcessingConfig(
            pdf_id=pdf_id,
            chunk_size=500,  # Optimal for technical content
            chunk_overlap=100,  # Better context preservation
            embedding_model="text-embedding-3-small",
            process_images=True,
            process_tables=True,
            extract_technical_terms=True,
            extract_relationships=True,
            extract_procedures=True,
            max_concepts_per_document=200
        )

    # Default OpenAI client if not provided
    if not openai_client:
        openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Create processor instance
    processor = DocumentProcessor(pdf_id, config, openai_client, research_manager)

    if output_dir:
        processor.output_dir = output_dir
        processor._setup_directories()

    try:
        # Process document with MongoDB + Qdrant integration
        result = await processor.process_document()

        # Add LangGraph-specific metadata
        if not result.raw_data:
            result.raw_data = {}

        result.raw_data["langgraph"] = {
            "node_ready": True,
            "document_structure": processor.section_hierarchy if hasattr(processor, "section_hierarchy") else [],
            "primary_concepts": [c.name for c in processor.concept_network.concepts[:5]] if processor.concept_network and processor.concept_network.concepts else [],
            "technical_domain": processor._predict_document_category(
                processor._extract_all_technical_terms(result.elements),
                result.markdown_content
            ),
            "processing_timestamp": datetime.utcnow().isoformat(),
            "unified_store_ready": True  # Indicate MongoDB + Qdrant storage is ready
        }

        logger.info(
            f"Completed document processing for {pdf_id} with "
            f"{len(result.elements)} elements, "
            f"{len(result.chunks) if hasattr(result, 'chunks') else 0} chunks, and "
            f"{len(processor.concept_network.concepts) if hasattr(processor, 'concept_network') and processor.concept_network else 0} concepts"
        )
        return result

    except Exception as e:
        logger.error(f"Processing pipeline failed: {e}", exc_info=True)
        error_result = ProcessingResult(
            pdf_id=pdf_id,
            elements=[],
            raw_data={
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": datetime.utcnow().isoformat(),
                "langgraph_ready": False,
                "unified_store_ready": False
            }
        )
        try:
            error_path = Path("output") / pdf_id / "metadata" / "processing_error.json"
            error_path.parent.mkdir(parents=True, exist_ok=True)
            with open(error_path, "w") as f:
                f.write(json.dumps({
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                    "pdf_id": pdf_id,
                    "langgraph_ready": False,
                    "unified_store_ready": False
                }, indent=2))
        except Exception:
            pass
        raise DocumentProcessingError(f"Document processing pipeline failed: {e}")
