"""
Adapter for converting Docling document processing to API-friendly format.
"""

import asyncio
import logging
import os
import time
import uuid
import io
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, BinaryIO, Tuple

# Import our existing utilities
from utils.extraction import (
    extract_technical_terms,
    extract_document_relationships,
    extract_procedures_and_parameters,
    DOMAIN_SPECIFIC_TERMS
)
from utils.tokenization import get_tokenizer
from utils.processing import process_markdown_text

# Import docling components used previously
from docling.document_converter import DocumentConverter, FormatOption, PdfFormatOption
from docling.datamodel.base_models import DocumentStream
from docling.datamodel.pipeline_options import PdfPipelineOptions
from document_processor.core import DocumentProcessor, ContentType, ChunkLevel

logger = logging.getLogger(__name__)

class APIDocumentProcessor:
    """
    Adapter class for n8n integration.
    Simplifies the document processing interface for API use.
    Handles multi-modal content extraction with proper relationships.
    """

    def __init__(
        self,
        pdf_id: str,
        config: Dict[str, Any]
    ):
        self.pdf_id = pdf_id
        self.config = config

        # Setup output directories
        self.output_dir = Path("output") / self.pdf_id
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Create asset directories
        self.assets_dir = self.output_dir / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir = self.assets_dir / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.tables_dir = self.assets_dir / "tables"
        self.tables_dir.mkdir(parents=True, exist_ok=True)

        # Setup tokenizer
        self.tokenizer = get_tokenizer("text-embedding-3-small")

        # Track metrics
        self.metrics = {"timings": {}, "counts": {}}
        self.processing_start = time.time()

        # Track content elements for cross-modal relationships
        self.context_map = {}

    async def process_document(self, content: bytes) -> Dict[str, Any]:
        """Process a document with comprehensive multi-modal extraction"""
        try:
            # Start timing
            start_time = time.time()

            # Use the DocumentProcessor for rich extraction
            processor = DocumentProcessor(
                pdf_id=self.pdf_id,
                config=self.config
            )

            # Get comprehensive results
            logger.info(f"Processing document {self.pdf_id}")
            processing_result = await processor.process_document(content)

            # Get document title or use pdf_id as fallback
            doc_title = getattr(processing_result, "document_summary", {}).get("title", self.pdf_id)
            if not doc_title or doc_title == f"Document {self.pdf_id}":
                doc_title = self.pdf_id

            # Copy images to assets directory if they exist
            await self._copy_images_to_assets(processing_result)

            # Organize content by type for Supabase insertion
            logger.info(f"Extracting multi-modal content for {self.pdf_id}")
            text_chunks = await self._extract_text_chunks(processing_result)
            images = await self._extract_images(processing_result)
            tables = await self._extract_tables(processing_result)

            # Extract procedures and relationships
            primary_concepts = []
            if hasattr(processing_result, "concept_network") and processing_result.concept_network:
                primary_concepts = processing_result.concept_network.primary_concepts

            # Determine document domain category
            domain_category = self._determine_document_category(
                primary_concepts,
                processing_result.markdown_content if hasattr(processing_result, "markdown_content") else ""
            )

            # Track timing
            processing_time = time.time() - start_time

            # Return comprehensive structured results
            return {
                "file_id": self.pdf_id,
                "file_title": doc_title,
                "text_chunks": text_chunks,
                "images": images,
                "tables": tables,
                "procedures": processing_result.procedures if hasattr(processing_result, "procedures") else [],
                "technical_terms": primary_concepts,
                "domain_category": domain_category,
                "document_metadata": {
                    "page_count": processing_result.document_summary.get("pages", 0) if hasattr(processing_result, "document_summary") else 0,
                    "section_structure": processing_result.document_summary.get("section_structure", []) if hasattr(processing_result, "document_summary") else [],
                    "primary_technical_terms": primary_concepts,
                    "content_types": self._get_content_types(processing_result),
                    "processing_time": processing_time
                }
            }
        except Exception as e:
            logger.error(f"Error processing document: {str(e)}", exc_info=True)
            raise

    async def _copy_images_to_assets(self, processing_result) -> None:
        """Copy extracted images to the assets directory with improved file handling."""
        try:
            if not hasattr(processing_result, "visual_elements"):
                return

            for element in processing_result.visual_elements:
                if element.content_type != "image" or not hasattr(element.metadata, 'image_path'):
                    continue

                src_path = element.metadata.image_path
                if not src_path or not os.path.exists(src_path):
                    continue

                # Create destination path in assets
                dest_filename = os.path.basename(src_path)
                dest_path = str(self.images_dir / dest_filename)

                # Copy image file with proper error handling and retries
                try:
                    # Make sure we're not trying to copy to the same location
                    if os.path.abspath(src_path) == os.path.abspath(dest_path):
                        logger.info(f"Source and destination are the same, skipping copy: {src_path}")
                        continue

                    # Try to copy with retries if the file is in use
                    max_retries = 3
                    for retry in range(max_retries):
                        try:
                            # Use shutil.copy2 to preserve metadata
                            shutil.copy2(src_path, dest_path)
                            logger.info(f"Copied image from {src_path} to {dest_path}")
                            break
                        except PermissionError as e:
                            if retry < max_retries - 1:
                                # If file is in use, wait and retry
                                logger.warning(f"File in use, retrying in 0.5s: {e}")
                                await asyncio.sleep(0.5)
                            else:
                                # If all retries fail, log warning but continue
                                logger.warning(f"Failed to copy image after {max_retries} retries: {e}")
                except Exception as copy_error:
                    logger.warning(f"Failed to copy image: {copy_error}")
        except Exception as e:
            logger.warning(f"Error copying images to assets: {str(e)}")

    async def _extract_text_chunks(self, processing_result) -> List[Dict[str, Any]]:
        """
        Extract text chunks with proper metadata and context relationships.
        """
        text_chunks = []
        seen_context_ids = set()

        # Process chunks from the processing result
        if hasattr(processing_result, "chunks") and processing_result.chunks:
            for chunk in processing_result.chunks:
                # Create a consistent context ID
                context_id = f"ctx_{self.pdf_id}_{chunk.metadata.chunk_index}"

                # Skip duplicates
                if context_id in seen_context_ids:
                    continue
                seen_context_ids.add(context_id)

                # Extract section headers
                section_headers = chunk.metadata.section_headers if hasattr(chunk.metadata, "section_headers") else []

                # Determine hierarchy level from chunk level
                hierarchy_level = 0
                if hasattr(chunk.metadata, "chunk_level"):
                    chunk_level = chunk.metadata.chunk_level
                    if chunk_level == ChunkLevel.DOCUMENT:
                        hierarchy_level = 0
                    elif chunk_level == ChunkLevel.SECTION:
                        hierarchy_level = 1
                    elif chunk_level == ChunkLevel.PROCEDURE:
                        hierarchy_level = 2
                    elif chunk_level == ChunkLevel.STEP:
                        hierarchy_level = 3
                    else:
                        hierarchy_level = 1  # Default to section level

                # Store in context map
                self.context_map[context_id] = {
                    "content_type": "text",
                    "section_headers": section_headers
                }

                # Check for content types in the chunk
                has_code = False
                has_table = False
                has_image = False

                # Check if metadata has content_types
                if hasattr(chunk.metadata, 'content_types'):
                    has_code = "code" in chunk.metadata.content_types
                    has_table = "table" in chunk.metadata.content_types
                    has_image = "image" in chunk.metadata.content_types

                # Add chunk to results
                text_chunks.append({
                    "content": chunk.content,
                    "metadata": {
                        "file_id": self.pdf_id,
                        "file_title": getattr(processing_result, "document_title", self.pdf_id),
                        "page_numbers": chunk.metadata.page_numbers if hasattr(chunk.metadata, "page_numbers") else [],
                        "section_headers": section_headers,
                        "technical_terms": chunk.metadata.technical_terms if hasattr(chunk.metadata, "technical_terms") else [],
                        "hierarchy_level": hierarchy_level,
                        "chunk_level": chunk.metadata.chunk_level if hasattr(chunk.metadata, "chunk_level") else "section",
                        "has_code": has_code,
                        "has_table": has_table,
                        "has_image": has_image,
                        "context_id": context_id
                    }
                })

        # If no chunks were found in processing_result.chunks, try to process from elements
        elif hasattr(processing_result, "elements") and processing_result.elements:
            # Group text elements by section
            section_elements = {}

            for idx, element in enumerate(processing_result.elements):
                if element.content_type != "text":
                    continue

                # Get section path as string
                section_path = " > ".join(element.metadata.section_headers) if hasattr(element.metadata, "section_headers") else "unknown"

                if section_path not in section_elements:
                    section_elements[section_path] = []

                section_elements[section_path].append(element)

            # Create chunks for each section
            for section_idx, (section_path, elements) in enumerate(section_elements.items()):
                # Skip empty sections
                if not elements:
                    continue

                # Create context ID for this section
                context_id = f"ctx_{self.pdf_id}_section_{section_idx}"

                # Get section headers as list
                section_headers = section_path.split(" > ") if section_path != "unknown" else []

                # Combine text elements into a single chunk
                combined_text = "\n\n".join(element.content for element in elements)

                # Get technical terms
                technical_terms = set()
                for element in elements:
                    if hasattr(element.metadata, "technical_terms"):
                        technical_terms.update(element.metadata.technical_terms)

                # Get page numbers
                page_numbers = set()
                for element in elements:
                    if hasattr(element.metadata, "page_number") and element.metadata.page_number:
                        page_numbers.add(element.metadata.page_number)

                # Store in context map
                self.context_map[context_id] = {
                    "content_type": "text",
                    "section_headers": section_headers
                }

                # Add section chunk
                text_chunks.append({
                    "content": combined_text,
                    "metadata": {
                        "file_id": self.pdf_id,
                        "file_title": getattr(processing_result, "document_title", self.pdf_id),
                        "page_numbers": list(page_numbers),
                        "section_headers": section_headers,
                        "technical_terms": list(technical_terms),
                        "hierarchy_level": 1,  # Section level
                        "chunk_level": "section",
                        "has_code": False,
                        "has_table": False,
                        "has_image": False,
                        "context_id": context_id
                    }
                })

        # If still no chunks, just process the markdown directly
        elif hasattr(processing_result, "markdown_content") and processing_result.markdown_content:
            # Process markdown into chunks
            md_chunks = process_markdown_text(
                text=processing_result.markdown_content,
                chunk_size=self.config.get("chunk_size", 500),
                chunk_overlap=self.config.get("chunk_overlap", 100)
            )

            # Convert to our format
            for idx, md_chunk in enumerate(md_chunks):
                context_id = f"ctx_{self.pdf_id}_md_{idx}"

                # Store in context map
                self.context_map[context_id] = {
                    "content_type": "text",
                    "section_headers": md_chunk["metadata"]["section_headers"]
                }

                text_chunks.append({
                    "content": md_chunk["content"],
                    "metadata": {
                        "file_id": self.pdf_id,
                        "file_title": getattr(processing_result, "document_title", self.pdf_id),
                        "page_numbers": [md_chunk["metadata"]["page_number"]] if md_chunk["metadata"]["page_number"] else [],
                        "section_headers": md_chunk["metadata"]["section_headers"],
                        "technical_terms": md_chunk["metadata"]["technical_terms"],
                        "hierarchy_level": len(md_chunk["metadata"]["section_headers"]),
                        "chunk_level": "section",
                        "has_code": "code" in md_chunk["metadata"]["content_types"],
                        "has_table": "table" in md_chunk["metadata"]["content_types"],
                        "has_image": "image" in md_chunk["metadata"]["content_types"],
                        "context_id": context_id
                    }
                })

        return text_chunks

    async def _extract_images(self, processing_result) -> List[Dict[str, Any]]:
        """
        Extract images with proper metadata and context relationships.
        """
        images = []

        # Extract from visual_elements
        if hasattr(processing_result, "visual_elements") and processing_result.visual_elements:
            for element in processing_result.visual_elements:
                if element.content_type != "image" or not hasattr(element.metadata, 'image_metadata'):
                    continue

                # Get image metadata
                img_meta = element.metadata.image_metadata if hasattr(element.metadata, 'image_metadata') else {}

                # Create relative path
                img_path = element.metadata.image_path if hasattr(element.metadata, 'image_path') else None
                if not img_path:
                    continue

                # Generate caption from metadata or element content
                caption = img_meta.get("description", "")
                if not caption and hasattr(element, "content"):
                    caption = element.content.replace("![", "").split("](")[0].strip()

                # Create context ID for relationships
                context_id = f"img_ctx_{self.pdf_id}_{element.element_id[-8:]}"

                # Get section context
                section_headers = []
                if hasattr(element.metadata, "section_headers") and element.metadata.section_headers:
                    section_headers = element.metadata.section_headers

                # Extract page number
                page_number = None
                if hasattr(element.metadata, "page_number"):
                    page_number = element.metadata.page_number

                # Store in context map
                self.context_map[context_id] = {
                    "content_type": "image",
                    "section_headers": section_headers
                }

                # Extract image dimensions
                width = 0
                height = 0
                if img_meta and "features" in img_meta and "dimensions" in img_meta["features"]:
                    dimensions = img_meta["features"]["dimensions"]
                    if isinstance(dimensions, tuple) and len(dimensions) == 2:
                        width, height = dimensions

                # Extract technical terms
                technical_terms = []
                if hasattr(element.metadata, "technical_terms"):
                    technical_terms = element.metadata.technical_terms

                # Create an analysis object if missing
                analysis = {}
                if img_meta and "analysis" in img_meta:
                    analysis = img_meta["analysis"]
                else:
                    # Generate basic image analysis
                    analysis = {
                        "description": caption,
                        "type": "unknown"
                    }

                # Get image format
                img_format = "PNG"
                if img_meta and "paths" in img_meta and "format" in img_meta["paths"]:
                    img_format = img_meta["paths"]["format"]

                images.append({
                    "image_id": element.element_id,
                    "file_id": self.pdf_id,
                    "caption": caption,
                    "page_number": page_number,
                    "section_headers": section_headers,
                    "path": img_path,
                    "width": width,
                    "height": height,
                    "format": img_format,
                    "technical_terms": technical_terms,
                    "analysis": analysis,
                    "context_id": context_id
                })

        # Extract from elements if no visual_elements
        elif hasattr(processing_result, "elements") and processing_result.elements:
            for element in processing_result.elements:
                if element.content_type != "image":
                    continue

                # Get image path
                img_path = element.metadata.image_path if hasattr(element.metadata, 'image_path') else None
                if not img_path:
                    continue

                # Create context ID
                context_id = f"img_ctx_{self.pdf_id}_{element.element_id[-8:]}"

                # Get section headers
                section_headers = []
                if hasattr(element.metadata, "section_headers"):
                    section_headers = element.metadata.section_headers

                # Get caption from content
                caption = ""
                if hasattr(element, "content"):
                    caption = element.content.replace("![", "").split("](")[0].strip()

                # Store in context map
                self.context_map[context_id] = {
                    "content_type": "image",
                    "section_headers": section_headers
                }

                # Extract technical terms
                technical_terms = []
                if hasattr(element.metadata, "technical_terms"):
                    technical_terms = element.metadata.technical_terms

                images.append({
                    "image_id": element.element_id,
                    "file_id": self.pdf_id,
                    "caption": caption,
                    "page_number": element.metadata.page_number if hasattr(element.metadata, "page_number") else None,
                    "section_headers": section_headers,
                    "path": img_path,
                    "width": 0,
                    "height": 0,
                    "format": "PNG",
                    "technical_terms": technical_terms,
                    "analysis": {"description": caption},
                    "context_id": context_id
                })

        return images

    async def _extract_tables(self, processing_result) -> List[Dict[str, Any]]:
        """
        Extract tables with proper metadata and context relationships.
        """
        tables = []

        # First check elements for tables
        if hasattr(processing_result, "elements") and processing_result.elements:
            for element in processing_result.elements:
                if element.content_type != "table" or not hasattr(element.metadata, 'table_data'):
                    continue

                # Get table data
                tbl_data = element.metadata.table_data

                # Create context ID
                context_id = f"tbl_ctx_{self.pdf_id}_{element.element_id[-8:]}"

                # Get section headers
                section_headers = []
                if hasattr(element.metadata, "section_headers"):
                    section_headers = element.metadata.section_headers

                # Store in context map
                self.context_map[context_id] = {
                    "content_type": "table",
                    "section_headers": section_headers
                }

                # Extract technical terms
                technical_terms = []
                if hasattr(element.metadata, "technical_terms"):
                    technical_terms = element.metadata.technical_terms

                # Get markdown
                markdown = tbl_data.get("markdown", "")
                if not markdown and hasattr(element, "content"):
                    markdown = element.content

                # Get caption
                caption = tbl_data.get("caption", "")
                if not caption and "summary" in tbl_data:
                    caption = tbl_data["summary"]

                # Get headers and data
                headers = tbl_data.get("headers", [])
                data = tbl_data.get("rows", [])
                if not data and "data" in tbl_data:
                    data = tbl_data["data"]

                # Get or create CSV path
                csv_path = tbl_data.get("csv_path", None)
                if not csv_path and headers and data:
                    # Generate a CSV file
                    import csv
                    csv_filename = f"{element.element_id}.csv"
                    csv_path = str(self.tables_dir / csv_filename)
                    try:
                        with open(csv_path, 'w', newline='') as csvfile:
                            writer = csv.writer(csvfile)
                            writer.writerow(headers)
                            writer.writerows(data)
                    except Exception as csv_error:
                        logger.warning(f"Failed to create CSV file: {csv_error}")
                        csv_path = None

                tables.append({
                    "table_id": element.element_id,
                    "file_id": self.pdf_id,
                    "caption": caption,
                    "page_number": element.metadata.page_number if hasattr(element.metadata, "page_number") else None,
                    "section_headers": section_headers,
                    "headers": headers,
                    "data": data,
                    "markdown": markdown,
                    "technical_terms": technical_terms,
                    "context_id": context_id,
                    "csv_path": csv_path
                })

        return tables

    def _get_content_types(self, result) -> List[str]:
        """Determine content types present in the document"""
        types = ["text"]

        # Check elements
        if hasattr(result, "elements"):
            if any(e.content_type == "image" for e in result.elements):
                types.append("images")
            if any(e.content_type == "table" for e in result.elements):
                types.append("tables")

        # Check visual elements
        if hasattr(result, "visual_elements") and result.visual_elements:
            types.append("images")

        # Check procedures
        if hasattr(result, "procedures") and result.procedures:
            types.append("procedures")

        return types

    def _extract_technical_terms(self, text: str) -> List[str]:
        """Extract technical terms from the document content"""
        return extract_technical_terms(text)

    def _determine_document_category(self, technical_terms: List[str], content: str) -> str:
        """Determine the document category based on technical terms and content."""
        # Initialize a score for each domain category
        category_scores = {category: 0 for category in DOMAIN_SPECIFIC_TERMS.keys()}
        for term in technical_terms:
            term_lower = term.lower()
            for category, keywords in DOMAIN_SPECIFIC_TERMS.items():
                if any(keyword in term_lower or term_lower in keyword for keyword in keywords):
                    category_scores[category] += 1

        # Choose the category with the highest score (if any)
        best_category = max(category_scores, key=category_scores.get)
        if category_scores[best_category] == 0:
            return "general"
        return best_category
