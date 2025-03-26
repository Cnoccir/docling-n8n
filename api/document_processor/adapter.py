"""
Enhanced document processor adapter for n8n integration.
This module adapts the full DocumentProcessor for our API needs.
"""

import asyncio
import io
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, BinaryIO, Union
from datetime import datetime

from openai import AsyncOpenAI

# Import the actual DocumentProcessor from your existing code
from document_processor.core import DocumentProcessor as FullDocumentProcessor
from document_processor.core import process_technical_document
from document_processor.base_types import (
    ContentType,
    ProcessingConfig,
    ContentElement,
    ChunkLevel,
    EmbeddingType,
    ProcessingResult
)
from utils.extraction import extract_technical_terms, extract_document_relationships

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class APIDocumentProcessor:
    """
    Document processor adapter for n8n integration.
    Adapts the full DocumentProcessor for API use.
    """

    def __init__(
        self,
        pdf_id: str,
        config: Dict[str, Any],
        openai_client: AsyncOpenAI
    ):
        self.pdf_id = pdf_id
        self.openai_client = openai_client
        self.output_dir = Path("output") / self.pdf_id
        self._setup_directories()

        # Convert config dict to ProcessingConfig
        self.config = ProcessingConfig(
            pdf_id=pdf_id,
            chunk_size=config.get("chunk_size", 500),
            chunk_overlap=config.get("chunk_overlap", 100),
            embedding_model=config.get("embedding_model", "text-embedding-3-small"),
            process_images=config.get("process_images", True),
            process_tables=config.get("process_tables", True),
            extract_technical_terms=config.get("extract_technical_terms", True),
            extract_relationships=config.get("extract_relationships", True),
            extract_procedures=config.get("extract_procedures", True),
            max_concepts_per_document=config.get("max_concepts_per_document", 200)
        )

        # Track timings and counts for metrics
        self.processing_start = time.time()
        self.metrics = {"timings": {}, "counts": {}}

    def _setup_directories(self):
        """Create necessary directories for document processing."""
        # Create main output dir
        os.makedirs(self.output_dir, exist_ok=True)

        # Create subdirectories
        os.makedirs(self.output_dir / "content", exist_ok=True)
        os.makedirs(self.output_dir / "assets" / "images", exist_ok=True)

    async def process_document(self, content: bytes) -> Dict[str, Any]:
        """
        Process a document from binary content using the full DocumentProcessor.

        Args:
            content: PDF binary content

        Returns:
            Dictionary with extracted content and metadata structured for n8n
        """
        logger.info(f"Starting document processing for PDF ID: {self.pdf_id}")
        start_time = time.time()

        try:
            # Save content to a temporary file
            temp_file = self.output_dir / f"{self.pdf_id}.pdf"
            os.makedirs(temp_file.parent, exist_ok=True)
            with open(temp_file, "wb") as f:
                f.write(content)

            # Process the document using the full processor
            result = await process_technical_document(
                pdf_id=self.pdf_id,
                config=self.config,
                openai_client=self.openai_client,
                output_dir=self.output_dir
            )

            # Format result for n8n
            formatted_result = self._format_result_for_n8n(result)

            processing_time = time.time() - start_time
            logger.info(f"Document processing completed in {processing_time:.2f} seconds")

            # Add processing time to the result
            formatted_result["processing_time"] = processing_time

            return formatted_result

        except Exception as e:
            logger.error(f"Error processing document: {str(e)}", exc_info=True)
            raise

    def _format_result_for_n8n(self, result: ProcessingResult) -> Dict[str, Any]:
        """
        Format the DocumentProcessor result for n8n consumption.

        Args:
            result: Processing result from DocumentProcessor

        Returns:
            Dictionary formatted for n8n
        """
        # Extract markdown content from the result
        markdown_content = result.markdown_content if hasattr(result, 'markdown_content') else ""

        # Format tables
        tables = []
        for element in result.elements:
            if element.content_type == ContentType.TABLE:
                table_data = {
                    "table_id": element.element_id,
                    "content": element.content,
                    "page_number": element.metadata.page_number if hasattr(element.metadata, 'page_number') else 0,
                }

                # Add table metadata if available
                if hasattr(element.metadata, 'table_data'):
                    table_data.update({
                        "headers": element.metadata.table_data.get("headers", []),
                        "rows": element.metadata.table_data.get("rows", []),
                        "caption": element.metadata.table_data.get("caption", ""),
                        "summary": element.metadata.table_data.get("summary", "")
                    })

                tables.append(table_data)

        # Format images
        images = []
        for element in result.elements:
            if element.content_type == ContentType.IMAGE:
                image_data = {
                    "image_id": element.element_id,
                    "content": element.content,
                    "page_number": element.metadata.page_number if hasattr(element.metadata, 'page_number') else 0,
                }

                # Add image path if available
                if hasattr(element.metadata, 'image_path'):
                    image_data["path"] = element.metadata.image_path

                # Add image metadata if available
                if hasattr(element.metadata, 'image_metadata'):
                    image_data.update({
                        "description": element.metadata.image_metadata.get("description", ""),
                        "dimensions": element.metadata.image_metadata.get("dimensions", []),
                    })

                images.append(image_data)

        # Extract technical terms
        technical_terms = []
        if result.concept_network and result.concept_network.concepts:
            technical_terms = [concept.name for concept in result.concept_network.concepts]

        # Format procedures
        procedures = []
        if hasattr(result, 'procedures') and result.procedures:
            procedures = result.procedures

        # Format parameters
        parameters = []
        if hasattr(result, 'parameters') and result.parameters:
            parameters = result.parameters

        # Format relationships
        relationships = []
        if result.concept_network and result.concept_network.relationships:
            for rel in result.concept_network.relationships:
                relationship = {
                    "source": rel.source,
                    "target": rel.target,
                    "type": str(rel.type),
                    "weight": rel.weight if hasattr(rel, 'weight') else 0.5,
                    "context": rel.context if hasattr(rel, 'context') else ""
                }
                relationships.append(relationship)

        # Create chunks for vector store ingestion
        chunks = []
        if hasattr(result, 'chunks') and result.chunks:
            for chunk in result.chunks:
                chunks.append({
                    "chunk_id": chunk.chunk_id,
                    "content": chunk.content,
                    "chunk_level": str(chunk.metadata.chunk_level) if hasattr(chunk.metadata, 'chunk_level') else "",
                    "page_numbers": chunk.metadata.page_numbers if hasattr(chunk.metadata, 'page_numbers') else [],
                    "section_headers": chunk.metadata.section_headers if hasattr(chunk.metadata, 'section_headers') else [],
                    "token_count": chunk.metadata.token_count if hasattr(chunk.metadata, 'token_count') else 0
                })

        # Format document summary
        summary = {}
        if hasattr(result, 'document_summary') and result.document_summary:
            summary = result.document_summary

        # Return formatted result
        return {
            "pdf_id": self.pdf_id,
            "markdown": markdown_content,
            "tables": tables,
            "images": images,
            "technical_terms": technical_terms,
            "procedures": procedures,
            "parameters": parameters,
            "concept_relationships": relationships,
            "chunks": chunks,
            "summary": summary,
            "metadata": {
                "element_count": len(result.elements),
                "processing_start": self.processing_start,
                "processing_end": time.time()
            }
        }

    async def extract_technical_terms(self, text: str) -> List[str]:
        """
        Extract technical terms using the full extraction utility.

        Args:
            text: Document text

        Returns:
            List of technical terms
        """
        return extract_technical_terms(text)

    async def extract_relationships(self, text: str, terms: List[str]) -> List[Dict[str, Any]]:
        """
        Extract concept relationships using the full extraction utility.

        Args:
            text: Document text
            terms: List of technical terms

        Returns:
            List of concept relationships
        """
        return extract_document_relationships(text, terms)

    def get_qdrant_ready_chunks(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Format chunks for direct insertion into Qdrant.

        Args:
            result: Formatted processing result

        Returns:
            List of chunks ready for Qdrant insertion
        """
        qdrant_chunks = []

        # Process markdown chunks
        if "chunks" in result:
            for chunk in result["chunks"]:
                qdrant_chunk = {
                    "id": chunk["chunk_id"],
                    "content": chunk["content"],
                    "metadata": {
                        "pdf_id": result["pdf_id"],
                        "chunk_level": chunk["chunk_level"],
                        "page_numbers": chunk["page_numbers"],
                        "section_headers": chunk["section_headers"],
                        "token_count": chunk["token_count"]
                    }
                }
                qdrant_chunks.append(qdrant_chunk)

        return qdrant_chunks

    def get_mongodb_ready_document(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format result for direct insertion into MongoDB.

        Args:
            result: Formatted processing result

        Returns:
            Document ready for MongoDB insertion
        """
        mongodb_doc = {
            "pdf_id": result["pdf_id"],
            "content": {
                "markdown": result["markdown"],
                "technical_terms": result["technical_terms"],
            },
            "tables": result["tables"],
            "images": result["images"],
            "procedures": result["procedures"],
            "parameters": result["parameters"],
            "relationships": result["concept_relationships"],
            "metadata": {
                **result["metadata"],
                "processed_at": datetime.utcnow().isoformat()
            }
        }

        # Add summary if available
        if "summary" in result and result["summary"]:
            mongodb_doc["summary"] = result["summary"]

        return mongodb_doc
