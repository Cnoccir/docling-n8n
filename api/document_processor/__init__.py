"""
Document processor module for PDF extraction API.
"""

from document_processor.adapter import APIDocumentProcessor
from document_processor.core import DocumentProcessor, process_technical_document

__all__ = ['APIDocumentProcessor', 'DocumentProcessor', 'process_technical_document']
