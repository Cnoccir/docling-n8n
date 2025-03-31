"""
Enhanced document processor with API integration.
Provides multi-level chunking and multi-embedding strategies.
"""

import asyncio
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

# Import from utility modules
from utils.extraction import (
    extract_technical_terms,
    extract_document_relationships,
    extract_procedures_and_parameters
)
from utils.tokenization import get_tokenizer
from utils.processing import (
    normalize_metadata_for_vectorstore,
    process_markdown_text
)

logger = logging.getLogger(__name__)

class DocumentProcessingError(Exception):
    """Custom error for document processing failures."""
    pass

class ContentType:
    """Content types for document elements."""
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    PAGE = "page"
    PROCEDURE = "procedure"
    PARAMETER = "parameter"

class ChunkLevel:
    """Chunking levels for hierarchical chunking."""
    DOCUMENT = "document"
    SECTION = "section"
    PROCEDURE = "procedure"
    STEP = "step"

class EmbeddingType:
    """Embedding types for different content."""
    GENERAL = "general"
    CONCEPTUAL = "conceptual"
    TECHNICAL = "technical"
    TASK = "task"

class ContentMetadata:
    """Metadata for content elements."""
    def __init__(
        self,
        pdf_id: str = "",
        page_number: int = 0,
        content_type: str = ContentType.TEXT,
        technical_terms: List[str] = None,
        section_headers: List[str] = None,
        hierarchy_level: int = 0,
        element_id: str = "",
        chunk_level: str = ChunkLevel.SECTION,
        embedding_type: str = EmbeddingType.GENERAL,
        parent_element_id: str = None,
        context: str = None,
        image_path: str = None,
        docling_ref: Any = None,
        table_data: Dict[str, Any] = None,
        image_metadata: Dict[str, Any] = None,
        procedure_metadata: Dict[str, Any] = None,
        parameter_metadata: Dict[str, Any] = None
    ):
        self.pdf_id = pdf_id
        self.page_number = page_number
        self.content_type = content_type
        self.technical_terms = technical_terms or []
        self.section_headers = section_headers or []
        self.hierarchy_level = hierarchy_level
        self.element_id = element_id
        self.chunk_level = chunk_level
        self.embedding_type = embedding_type
        self.parent_element_id = parent_element_id
        self.context = context
        self.image_path = image_path
        self.docling_ref = docling_ref
        self.table_data = table_data
        self.image_metadata = image_metadata
        self.procedure_metadata = procedure_metadata
        self.parameter_metadata = parameter_metadata

class ContentElement:
    """Content element extracted from document."""
    def __init__(
        self,
        element_id: str,
        content: str,
        content_type: str,
        pdf_id: str,
        metadata: ContentMetadata
    ):
        self.element_id = element_id
        self.content = content
        self.content_type = content_type
        self.pdf_id = pdf_id
        self.metadata = metadata

class ChunkMetadata:
    """Metadata for document chunks."""
    def __init__(
        self,
        pdf_id: str,
        content_type: str,
        chunk_level: str,
        chunk_index: int,
        page_numbers: List[int] = None,
        section_headers: List[str] = None,
        parent_chunk_id: str = None,
        technical_terms: List[str] = None,
        embedding_type: str = None,
        element_ids: List[str] = None,
        token_count: int = 0
    ):
        self.pdf_id = pdf_id
        self.content_type = content_type
        self.chunk_level = chunk_level
        self.chunk_index = chunk_index
        self.page_numbers = page_numbers or []
        self.section_headers = section_headers or []
        self.parent_chunk_id = parent_chunk_id
        self.technical_terms = technical_terms or []
        self.embedding_type = embedding_type or EmbeddingType.GENERAL
        self.element_ids = element_ids or []
        self.token_count = token_count

    def dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pdf_id": self.pdf_id,
            "content_type": self.content_type,
            "chunk_level": self.chunk_level,
            "chunk_index": self.chunk_index,
            "page_numbers": self.page_numbers,
            "section_headers": self.section_headers,
            "parent_chunk_id": self.parent_chunk_id,
            "technical_terms": self.technical_terms,
            "embedding_type": self.embedding_type,
            "element_ids": self.element_ids,
            "token_count": self.token_count
        }

class DocumentChunk:
    """Document chunk with content and metadata."""
    def __init__(
        self,
        chunk_id: str,
        content: str,
        metadata: ChunkMetadata
    ):
        self.chunk_id = chunk_id
        self.content = content
        self.metadata = metadata

    def dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "metadata": self.metadata.dict()
        }

class RelationType:
    """Relationship types between technical concepts."""
    PART_OF = "part_of"
    USES = "uses"
    IMPLEMENTS = "implements"
    EXTENDS = "extends"
    RELATES_TO = "relates_to"
    CONFIGURES = "configures"
    PREREQUISITE = "prerequisite"
    REFERENCES = "references"

class Concept:
    """Technical concept extracted from document."""
    def __init__(
        self,
        name: str,
        occurrences: int = 1,
        in_headers: bool = False,
        sections: List[str] = None,
        first_occurrence_page: int = None,
        importance_score: float = 0.0,
        is_primary: bool = False,
        category: str = None,
        pdf_id: str = None
    ):
        self.name = name
        self.occurrences = occurrences
        self.in_headers = in_headers
        self.sections = sections or []
        self.first_occurrence_page = first_occurrence_page
        self.importance_score = importance_score
        self.is_primary = is_primary
        self.category = category
        self.pdf_id = pdf_id

class ConceptRelationship:
    """Relationship between technical concepts."""
    def __init__(
        self,
        source: str,
        target: str,
        type: str,
        weight: float = 1.0,
        context: str = "",
        extraction_method: str = "direct",
        pdf_id: str = None
    ):
        self.source = source
        self.target = target
        self.type = type
        self.weight = weight
        self.context = context
        self.extraction_method = extraction_method
        self.pdf_id = pdf_id

class ConceptNetwork:
    """Network of concepts and their relationships."""
    def __init__(self, pdf_id: str = None):
        self.pdf_id = pdf_id
        self.concepts: List[Concept] = []
        self.relationships: List[ConceptRelationship] = []
        self.section_concepts: Dict[str, Set[str]] = defaultdict(set)

        # Track primary concepts
        self.primary_concepts: List[str] = []

    def add_concept(self, concept: Concept) -> None:
        """Add concept to network."""
        self.concepts.append(concept)

        # Update primary concepts list if applicable
        if concept.is_primary and concept.name not in self.primary_concepts:
            self.primary_concepts.append(concept.name)

    def add_relationship(self, relationship: ConceptRelationship) -> None:
        """Add relationship to network."""
        self.relationships.append(relationship)

    def add_section_concepts(self, section_path: str, concepts: List[str]) -> None:
        """Add concepts to a section."""
        self.section_concepts[section_path].update(concepts)

    def calculate_importance_scores(self) -> None:
        """Calculate importance scores for concepts."""
        # Simple implementation - in full version this would be more sophisticated
        for concept in self.concepts:
            # Base score from occurrences
            base_score = min(1.0, 0.1 * concept.occurrences)

            # Bonus for header concepts
            header_bonus = 0.3 if concept.in_headers else 0

            # Bonus for appearing in many sections
            section_bonus = min(0.3, len(concept.sections) * 0.05)

            # Final score
            concept.importance_score = base_score + header_bonus + section_bonus

            # Mark as primary if score is high enough
            concept.is_primary = concept.importance_score > 0.5

            # Update primary concepts list if applicable
            if concept.is_primary and concept.name not in self.primary_concepts:
                self.primary_concepts.append(concept.name)

class ProcessingConfig:
    """Configuration for document processing."""
    def __init__(
        self,
        pdf_id: str = "",
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        embedding_model: str = "text-embedding-3-small",
        process_images: bool = True,
        process_tables: bool = True,
        extract_technical_terms: bool = True,
        extract_relationships: bool = True,
        extract_procedures: bool = True,
        max_concepts_per_document: int = 100
    ):
        self.pdf_id = pdf_id
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.embedding_model = embedding_model
        self.process_images = process_images
        self.process_tables = process_tables
        self.extract_technical_terms = extract_technical_terms
        self.extract_relationships = extract_relationships
        self.extract_procedures = extract_procedures
        self.max_concepts_per_document = max_concepts_per_document

    def dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {k: v for k, v in self.__dict__.items()}

class ProcessingResult:
    """Result of document processing."""
    def __init__(
        self,
        pdf_id: str,
        elements: List[ContentElement] = None,
        chunks: List[DocumentChunk] = None,
        processing_metrics: Dict[str, Any] = None,
        markdown_content: str = "",
        markdown_path: str = "",
        concept_network: ConceptNetwork = None,
        visual_elements: List[ContentElement] = None,
        document_summary: Dict[str, Any] = None,
        procedures: List[Dict[str, Any]] = None,
        parameters: List[Dict[str, Any]] = None,
        raw_data: Dict[str, Any] = None
    ):
        self.pdf_id = pdf_id
        self.elements = elements or []
        self.chunks = chunks or []
        self.metrics = processing_metrics or {}
        self.markdown_content = markdown_content
        self.markdown_path = markdown_path
        self.concept_network = concept_network
        self.visual_elements = visual_elements or []
        self.document_summary = document_summary or {}
        self.procedures = procedures or []
        self.parameters = parameters or []
        self.raw_data = raw_data or {}

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the processed document."""
        # Count element types
        element_types = defaultdict(int)
        for elem in self.elements:
            element_types[elem.content_type] += 1

        # Get top technical terms
        technical_term_counts = defaultdict(int)
        for elem in self.elements:
            for term in elem.metadata.technical_terms:
                technical_term_counts[term] += 1

        top_technical_terms = dict(sorted(
            technical_term_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:20])

        return {
            "pdf_id": self.pdf_id,
            "total_elements": len(self.elements),
            "total_chunks": len(self.chunks),
            "element_types": dict(element_types),
            "top_technical_terms": top_technical_terms,
            "procedures_count": len(self.procedures),
            "parameters_count": len(self.parameters),
            "primary_concepts": self.concept_network.primary_concepts if self.concept_network else []
        }

class DocumentProcessor:
    """
    Enhanced document processor with API integration.
    Provides multi-level chunking and multi-embedding strategies.
    """

    def __init__(self, pdf_id: str, config: Union[ProcessingConfig, Dict[str, Any]], openai_client=None):
        self.pdf_id = pdf_id

        # Convert dict config to ProcessingConfig if needed
        if isinstance(config, dict):
            self.config = ProcessingConfig(**config)
        else:
            self.config = config

        self.openai_client = openai_client
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

        logger.info(f"Initialized DocumentProcessor for PDF {pdf_id}")

    def _setup_directories(self):
        """Create output directories if needed."""
        self.temp_dir = os.path.join("temp", self.pdf_id)
        os.makedirs(self.temp_dir, exist_ok=True)

    async def process_document(self, content: Optional[bytes] = None) -> ProcessingResult:
        """
        Process document with enhanced extraction.

        Args:
            content: Optional binary content of the document

        Returns:
            ProcessingResult with structured content
        """
        logger.info(f"Starting enhanced document processing for {self.pdf_id}")
        start_time = time.time()

        try:
            # 1. Get document content
            if content:
                # If content is provided directly (API case)
                document_content = content
            else:
                # Try to get content from temp file
                document_content = self._get_content()

            if not document_content:
                raise DocumentProcessingError(f"No content found for PDF {self.pdf_id}")

            # 2. Convert document to Docling format
            logger.info(f"Converting document {self.pdf_id}")
            self.docling_doc = await self._convert_document(document_content)

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

            # 9. Generate a document summary
            logger.info(f"Generating document summary for {self.pdf_id}")
            document_summary = await self._generate_document_summary(
                text=md_content,
                technical_terms=all_technical_terms
            )

            # 10. Predict document category
            predicted_category = self._predict_document_category(all_technical_terms, md_content)
            logger.info(f"Predicted document category: {predicted_category}")

            # 11. Create processing result
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
                parameters=self.parameters,
                raw_data={
                    "langgraph": {
                        "node_ready": True,
                        "document_structure": self.section_hierarchy,
                        "primary_concepts": [c.name for c in self.concept_network.concepts[:5]] if self.concept_network and self.concept_network.concepts else [],
                        "technical_domain": predicted_category,
                        "processing_timestamp": datetime.utcnow().isoformat()
                    }
                }
            )

            # 12. Save results to disk
            try:
                await self._save_results(result)
            except Exception as save_error:
                logger.warning(f"Error saving results: {str(save_error)}")
                # Continue processing, don't abort due to save failure

            # Record total processing time
            self.metrics["timings"]["total"] = time.time() - start_time
            logger.info(f"Completed enhanced processing for {self.pdf_id}")

            return result
        except Exception as e:
            logger.error(f"Document processing failed: {str(e)}", exc_info=True)
            # Create a minimal result with error information
            error_result = ProcessingResult(
                pdf_id=self.pdf_id,
                elements=[],
                raw_data={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            return error_result

    def _get_content(self) -> bytes:
        """Get document content from temp file."""
        try:
            # In API context, we've already saved the content to a temp file
            temp_path = self.output_dir / "temp" / f"{self.pdf_id}.pdf"
            if temp_path.exists():
                return temp_path.read_bytes()
            else:
                raise DocumentProcessingError(f"No content found for PDF {self.pdf_id}")
        except Exception as e:
            logger.error(f"Content access failed: {str(e)}")
            raise DocumentProcessingError(f"Content access failed: {str(e)}")

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
            pipeline_options.do_table_structure = self.config.process_tables

            # CRITICAL: These settings preserve images
            pipeline_options.images_scale = 2.0  # Higher resolution
            pipeline_options.generate_page_images = self.config.process_images
            pipeline_options.generate_picture_images = self.config.process_images

            # OCR and table settings
            ocr_options = TesseractCliOcrOptions(force_full_page_ocr=False)
            pipeline_options.ocr_options = ocr_options
            if pipeline_options.table_structure_options:
                pipeline_options.table_structure_options.do_cell_matching = True

            # Initialize converter
            pdf_format_option = PdfFormatOption(pipeline_options=pipeline_options)
            converter = DocumentConverter(
                allowed_formats=[InputFormat.PDF],
                format_options={InputFormat.PDF: pdf_format_option}
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

            # Use standard file I/O instead of aiofiles for simplicity
            with open(self.markdown_path, "w", encoding="utf-8") as f:
                f.write(md_content)

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

    def _add_concepts_to_section(self, section_path: str, concepts: List[str]) -> None:
        """Add concepts to a section in the concept network."""
        # Skip if no section path or concepts
        if not section_path or not concepts:
            return

        # Add to concept network's section mapping
        self.concept_network.add_section_concepts(section_path, concepts)

    def _determine_chunk_level(self, text: str, hierarchy_level: int, section_path: List[str]) -> str:
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

    def _determine_embedding_type(self, text: str, technical_terms: List[str]) -> str:
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

        # Define domain-specific terms dictionary
        DOMAIN_SPECIFIC_TERMS = {
            # Programming and Development
            "programming": ["function", "method", "class", "object", "variable", "parameter", "argument",
                           "api", "interface", "library", "framework", "runtime", "compiler", "interpreter"],

            # Data and Databases
            "data": ["database", "query", "schema", "table", "record", "field", "index", "key", "join",
                    "sql", "nosql", "orm", "etl", "data model", "data structure"],

            # Web Technologies
            "web": ["http", "https", "rest", "soap", "api", "endpoint", "request", "response",
                   "frontend", "backend", "client", "server", "html", "css", "javascript"],

            # Infrastructure and DevOps
            "infrastructure": ["server", "cloud", "container", "kubernetes", "docker", "vm",
                              "ci/cd", "pipeline", "deployment", "infrastructure", "network"],

            # AI and Machine Learning
            "ai": ["algorithm", "model", "neural network", "training", "inference", "classification",
                  "regression", "clustering", "deep learning", "machine learning", "dataset"],

            # Building Automation Systems
            "building_automation": ["hvac", "temperature", "sensor", "controller", "thermostat", "building",
                                   "zone", "setpoint", "automation", "bms", "bas", "actuator", "relay"],

            # Business and Management
            "business": ["management", "strategy", "process", "policy", "compliance", "governance",
                         "stakeholder", "roi", "kpi", "metric", "performance", "objective"]
        }

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
        content_type: str,
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

        # Domain-specific detection
        domain_specific = {
            "technical_drawing": ["technical drawing", "schematic", "diagram", "blueprint"],
            "user_interface": ["interface", "ui", "screen", "dashboard", "form"],
            "chart": ["chart", "graph", "plot", "trend", "histogram", "bar chart"],
            "architecture": ["architecture", "system", "component", "flow"]
        }

        for category, terms in domain_specific.items():
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
                        # Using the same DOMAIN_SPECIFIC_TERMS dictionary from _track_domain_terms
                        DOMAIN_SPECIFIC_TERMS = {
                            # Programming and Development
                            "programming": ["function", "method", "class", "object", "variable", "parameter", "argument",
                                           "api", "interface", "library", "framework", "runtime", "compiler", "interpreter"],

                            # Data and Databases
                            "data": ["database", "query", "schema", "table", "record", "field", "index", "key", "join",
                                    "sql", "nosql", "orm", "etl", "data model", "data structure"],

                            # Web Technologies
                            "web": ["http", "https", "rest", "soap", "api", "endpoint", "request", "response",
                                   "frontend", "backend", "client", "server", "html", "css", "javascript"],

                            # Infrastructure and DevOps
                            "infrastructure": ["server", "cloud", "container", "kubernetes", "docker", "vm",
                                              "ci/cd", "pipeline", "deployment", "infrastructure", "network"],

                            # AI and Machine Learning
                            "ai": ["algorithm", "model", "neural network", "training", "inference", "classification",
                                  "regression", "clustering", "deep learning", "machine learning", "dataset"],

                            # Building Automation Systems
                            "building_automation": ["hvac", "temperature", "sensor", "controller", "thermostat", "building",
                                                   "zone", "setpoint", "automation", "bms", "bas", "actuator", "relay"],

                            # Business and Management
                            "business": ["management", "strategy", "process", "policy", "compliance", "governance",
                                         "stakeholder", "roi", "kpi", "metric", "performance", "objective"]
                        }

                        term_lower = term.lower()
                        for category, domain_terms in DOMAIN_SPECIFIC_TERMS.items():
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
            relationships = []
            if self.config.extract_relationships:
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
                    type=rel.get("relationship_type", RelationType.RELATES_TO),
                    weight=rel.get("confidence", 0.75),
                    context=rel.get("context", ""),
                    extraction_method=rel.get("extraction_method", "document-based"),
                    pdf_id=self.pdf_id
                )
                self.concept_network.add_relationship(relationship)

            # 9. Calculate importance scores and identify primary concepts
            self.concept_network.calculate_importance_scores()

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
        # If no domain term counters, return general
        if not self.domain_term_counters:
            return "general"

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
                return top_category

        # If still no clear category, check content for key terms
        content_lower = content.lower()

        # Check for programming content
        programming_terms = ["function", "class", "api", "code", "library", "framework"]
        if any(term in content_lower for term in programming_terms):
            return "programming"

        # Check for data content
        data_terms = ["database", "data model", "query", "sql", "nosql", "dataset"]
        if any(term in content_lower for term in data_terms):
            return "data"

        # Check for business content
        business_terms = ["business", "management", "strategy", "market", "stakeholder"]
        if any(term in content_lower for term in business_terms):
            return "business"

        # Check for infrastructure content
        infrastructure_terms = ["server", "cloud", "container", "network", "deployment"]
        if any(term in content_lower for term in infrastructure_terms):
            return "infrastructure"

        # If still no clear category, return general
        return "general"

    async def _generate_document_summary(self, text: str, technical_terms: List[str]) -> Dict[str, Any]:
        """
        Generate a document summary from text and technical terms.

        Args:
            text: Document text
            technical_terms: Extracted technical terms

        Returns:
            Summary dictionary
        """
        # Create basic summary based on text analysis
        # In the full implementation, this would use an OpenAI API call

        # Extract title from first heading (any markdown heading level)
        title_match = re.search(r'^\s*#+\s*(.+)', text, re.MULTILINE)
        title = title_match.group(1) if title_match else f"Document {self.pdf_id}"

        # Create a basic description from first paragraphs
        description_text = text[:1000]  # Get first 1000 chars
        description_text = re.sub(r'#.*', '', description_text, flags=re.MULTILINE)  # Remove headers
        description_text = re.sub(r'\n\n+', '\n\n', description_text)  # Normalize spacing
        paragraphs = re.split(r'\n\s*\n', description_text.strip())  # Robust paragraph split
        description = ' '.join(p for p in paragraphs[:2] if len(p) > 30)  # Get first 2 substantial paragraphs

        # Extract primary concepts
        primary_concepts = []
        if self.concept_network and self.concept_network.primary_concepts:
            primary_concepts = self.concept_network.primary_concepts[:10]
        elif technical_terms:
            primary_concepts = technical_terms[:10]

        # Get document sections
        section_structure = []
        for section_path in self.section_hierarchy:
            if section_path:
                section_structure.append(" > ".join(section_path))

        # Create the summary
        summary = {
            "title": title,
            "description": description[:500],  # Limit description length
            "primary_concepts": primary_concepts,
            "section_structure": section_structure[:20],  # Limit to top 20 sections
            "pages": self.metrics.get("counts", {}).get("pages", 0),
            "technical_terms_count": len(technical_terms),
            "extracted_at": datetime.utcnow().isoformat()
        }

        return summary

    async def _save_results(self, result: ProcessingResult) -> None:
        """Save processing results to disk for later access."""
        try:
            # Make sure the output directory exists
            self.output_dir.mkdir(parents=True, exist_ok=True)

            # Save a summary JSON file
            summary_path = self.output_dir / "result_summary.json"
            summary_data = {
                "pdf_id": result.pdf_id,
                "element_count": len(result.elements),
                "chunk_count": len(result.chunks),
                "procedures_count": len(result.procedures),
                "parameters_count": len(result.parameters),
                "primary_concepts": result.concept_network.primary_concepts if hasattr(result, "concept_network") and result.concept_network else [],
                "timestamp": datetime.utcnow().isoformat()
            }

            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary_data, f, ensure_ascii=False, indent=2)

            logger.info(f"Saved result summary to {summary_path}")
        except Exception as e:
            # Log the error but don't fail the processing
            logger.warning(f"Error saving results: {str(e)}")

async def process_technical_document(pdf_id: str, content: bytes, config: dict, openai_client=None):
    processor = DocumentProcessor(pdf_id=pdf_id, config=config, openai_client=openai_client)
    return await processor.process_document(content)

__all__ = ["DocumentProcessor", "ProcessingConfig", "process_technical_document"]
