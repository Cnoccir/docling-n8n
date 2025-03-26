"""
Document processor module for PDF extraction API.
"""

from .adapter import APIDocumentProcessor
from .core import DocumentProcessor, process_technical_document

__all__ = ['APIDocumentProcessor', 'DocumentProcessor', 'process_technical_document']
