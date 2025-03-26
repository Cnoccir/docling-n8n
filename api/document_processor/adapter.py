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
from utils.extraction import extract_technical_terms, extract_document_relationships
from utils.tokenization import get_tokenizer
from utils.processing import process_markdown_text

# Import docling
from docling.document_converter import DocumentConverter, FormatOption, PdfFormatOption
from docling.datamodel.base_models import DocumentStream
from docling.datamodel.pipeline_options import PdfPipelineOptions

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
        """
        Process a document from binary content.

        Args:
            content: PDF binary content

        Returns:
            Dictionary with extracted content and metadata
        """
        start_time = time.time()

        try:
            # Setup Docling pipeline options
            pipeline_options = PdfPipelineOptions(
                do_ocr=True,
                do_table_structure=self.config.get("process_tables", True),
                do_code_enrichment=self.config.get("do_code_enrichment", False),
                do_formula_enrichment=self.config.get("do_formula_enrichment", False),
                do_picture_classification=self.config.get("do_picture_classification", False),
            )

            # Create Docling format option
            pdf_format_option = PdfFormatOption(
                pipeline_options=pipeline_options
            )

            # Create document converter
            converter = DocumentConverter(
                format_options={
                    "pdf": pdf_format_option,
                }
            )

            # Save content to temp file
            temp_file = self.output_dir / f"{self.pdf_id}.pdf"
            with open(temp_file, "wb") as f:
                f.write(content)

            # Read the saved file as bytes and wrap in BytesIO
            with open(temp_file, "rb") as f:
                file_bytes = f.read()
            stream = DocumentStream(name=f"{self.pdf_id}.pdf", stream=io.BytesIO(file_bytes))
            conversion_result = converter.convert(stream)

            # Extract document as markdown
            document = conversion_result.document
            markdown_content = document.export_to_markdown()

            # Extract technical terms if enabled
            technical_terms = []
            if self.config.get("extract_technical_terms", True):
                technical_terms = self._extract_technical_terms(markdown_content)

            # Generate chunks
            chunks = self._generate_chunks(markdown_content)

            # Extract procedures and parameters if enabled
            procedures = []
            parameters = []
            if self.config.get("extract_procedures", True):
                procedures, parameters = self._extract_procedures(markdown_content)

            # Determine domain category
            domain_category = self._determine_document_category(technical_terms, markdown_content)

            # Create response
            result = {
                "pdf_id": self.pdf_id,
                "markdown_content": markdown_content,
                "technical_terms": technical_terms,
                "chunks": chunks,
                "procedures": procedures,
                "parameters": parameters,
                "domain_category": domain_category,
                "page_count": len(document.pages) if hasattr(document, "pages") else 0,
                "processing_time": time.time() - start_time
            }

            return result

        except Exception as e:
            logger.error(f"Error processing document: {str(e)}")
            raise

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
        """Extract procedures and parameters"""
        # This is a simplified implementation - in a full version,
        # we would use the extract_procedures_and_parameters from utils
        procedures = []
        parameters = []

        # Placeholder for the real implementation
        # In the full implementation, this would call your existing utility function

        return procedures, parameters

    def _determine_document_category(self, technical_terms: List[str], content: str) -> str:
        """Determine the document category based on technical terms and content"""
        # Simplified implementation
        # This would use your existing categorization logic
        return "general"
