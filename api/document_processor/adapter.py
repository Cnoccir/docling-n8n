"""
Adapter for converting Docling document processing to API-friendly format.
"""

import asyncio
import logging
import os
import time
import uuid
import io
from pathlib import Path
from typing import Dict, List, Any, Optional, BinaryIO

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
from document_processor.core import DocumentProcessor

logger = logging.getLogger(__name__)

class APIDocumentProcessor:
    """
    Adapter class for n8n integration.
    Simplifies the document processing interface for API use.
    """

    def __init__(
        self,
        pdf_id: str,
        config: Dict[str, Any]
    ):
        self.pdf_id = pdf_id
        self.config = config
        self.output_dir = Path("output") / self.pdf_id
        os.makedirs(self.output_dir, exist_ok=True)

        # Setup tokenizer
        self.tokenizer = get_tokenizer("text-embedding-3-small")

        # Track metrics
        self.metrics = {"timings": {}, "counts": {}}
        self.processing_start = time.time()

    async def process_document(self, content: bytes) -> Dict[str, Any]:
        """Process a document with comprehensive multi-modal extraction"""
        try:
            # Setup and conversion code remains similar...
            # Use the DocumentProcessor for rich extraction
            processor = DocumentProcessor(
                pdf_id=self.pdf_id,
                config=self.config
            )

            # Get comprehensive results
            processing_result = await processor.process_document(content)

            # Assume the document title is provided in processing_result; fallback to self.pdf_id if not
            doc_title = getattr(processing_result, "document_title", self.pdf_id)

            # Organize content by type for Supabase insertion
            text_chunks = []
            images = []
            tables = []

            # Process text chunks maintaining hierarchy
            for chunk in processing_result.chunks:
                text_chunks.append({
                    "content": chunk.content,
                    "metadata": {
                        "file_id": self.pdf_id,
                        "file_title": doc_title,
                        "page_numbers": chunk.metadata.page_numbers,
                        "section_headers": chunk.metadata.section_headers,
                        "technical_terms": chunk.metadata.technical_terms,
                        "hierarchy_level": chunk.metadata.hierarchy_level,
                        "chunk_level": chunk.metadata.chunk_level,
                        "has_code": "code" in chunk.metadata.content_types if hasattr(chunk.metadata, 'content_types') else False,
                        "has_table": "table" in chunk.metadata.content_types if hasattr(chunk.metadata, 'content_types') else False,
                        "has_image": "image" in chunk.metadata.content_types if hasattr(chunk.metadata, 'content_types') else False,
                        "context_id": f"ctx_{self.pdf_id}_{chunk.metadata.chunk_index}"
                    }
                })

            # Process images with proper metadata
            for element in processing_result.visual_elements:
                if element.content_type == "image" and hasattr(element.metadata, 'image_metadata'):
                    img_meta = element.metadata.image_metadata
                    images.append({
                        "image_id": element.element_id,
                        "file_id": self.pdf_id,
                        "caption": img_meta.get("description", ""),
                        "page_number": element.metadata.page_number,
                        "section_headers": element.metadata.section_headers,
                        "path": element.metadata.image_path,
                        "technical_terms": element.metadata.technical_terms,
                        "context_id": f"img_ctx_{self.pdf_id}_{element.metadata.page_number}_{element.element_id[-8:]}"
                    })

            # Process tables with structure
            for element in processing_result.elements:
                if element.content_type == "table" and hasattr(element.metadata, 'table_data'):
                    tbl_data = element.metadata.table_data
                    tables.append({
                        "table_id": element.element_id,
                        "file_id": self.pdf_id,
                        "caption": tbl_data.get("caption", ""),
                        "page_number": element.metadata.page_number,
                        "section_headers": element.metadata.section_headers,
                        "headers": tbl_data.get("headers", []),
                        "data": tbl_data.get("rows", []),
                        "markdown": tbl_data.get("markdown", ""),
                        "technical_terms": element.metadata.technical_terms,
                        "context_id": f"tbl_ctx_{self.pdf_id}_{element.metadata.page_number}_{element.element_id[-8:]}"
                    })

            # Return comprehensive structured results
            return {
                "file_id": self.pdf_id,
                "file_title": doc_title,
                "text_chunks": text_chunks,
                "images": images,
                "tables": tables,
                "procedures": processing_result.procedures,
                "technical_terms": processing_result.concept_network.primary_concepts if hasattr(processing_result, "concept_network") and processing_result.concept_network else [],
                "domain_category": self._determine_document_category(
                    processing_result.concept_network.primary_concepts if hasattr(processing_result, "concept_network") and processing_result.concept_network else [],
                    processing_result.markdown_content
                ),
                "document_metadata": {
                    "page_count": processing_result.document_summary.get("pages", 0) if hasattr(processing_result, "document_summary") else 0,
                    "section_structure": processing_result.document_summary.get("section_structure", []) if hasattr(processing_result, "document_summary") else [],
                    "primary_technical_terms": processing_result.concept_network.primary_concepts if hasattr(processing_result, "concept_network") and processing_result.concept_network else [],
                    "content_types": self._get_content_types(processing_result)
                }
            }
        except Exception as e:
            logger.error(f"Error processing document: {str(e)}")
            raise

    def _get_content_types(self, result) -> List[str]:
        """Determine content types present in the document"""
        types = ["text"]
        if any(e.content_type == "image" for e in result.elements):
            types.append("images")
        if any(e.content_type == "table" for e in result.elements):
            types.append("tables")
        if getattr(result, "procedures", None):
            types.append("procedures")
        return types

    def _extract_technical_terms(self, text: str) -> List[str]:
        """Extract technical terms from the document content"""
        return extract_technical_terms(text)

    def _generate_chunks(self, text: str) -> List[Dict[str, Any]]:
        """Generate text chunks for embedding"""
        # Process markdown into chunks with metadata
        processed_chunks = process_markdown_text(
            text=text,
            chunk_size=self.config.get("chunk_size", 500),
            chunk_overlap=self.config.get("chunk_overlap", 100)
        )

        # Convert to API format
        chunks = []
        for i, chunk in enumerate(processed_chunks):
            chunks.append({
                "content": chunk["content"],
                "page_numbers": [chunk["metadata"]["page_number"]] if chunk["metadata"]["page_number"] else [],
                "section_headers": chunk["metadata"]["section_headers"],
                "technical_terms": chunk["metadata"]["technical_terms"],
                "chunk_level": "section",  # Simplified for API
                "chunk_index": i
            })

        return chunks

    def _extract_procedures(self, text: str) -> tuple:
        """Extract procedures and parameters using the extraction utility."""
        return extract_procedures_and_parameters(text)

    def _determine_document_category(self, technical_terms: List[str], content: str) -> str:
        """Determine the document category based on technical terms and content.

        Uses a simple heuristic by checking for the presence of domain-specific keywords.
        """
        # Initialize a score for each domain category
        category_scores = {category: 0 for category in DOMAIN_SPECIFIC_TERMS.keys()}
        for term in technical_terms:
            term_lower = term.lower()
            for category, keywords in DOMAIN_SPECIFIC_TERMS.items():
                if term_lower in keywords:
                    category_scores[category] += 1

        # Choose the category with the highest score (if any)
        best_category = max(category_scores, key=category_scores.get)
        if category_scores[best_category] == 0:
            return "general"
        return best_category
