"""
Enhanced type definitions for the Docling n8n API integration.
These types are aligned with the full DocumentProcessor capabilities.
"""

from enum import Enum
from typing import Dict, List, Optional, Any, Set, Union
from datetime import datetime
from pydantic import BaseModel, Field


class ContentType(str, Enum):
    """Content type enumeration matching the full DocumentProcessor."""
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    CODE = "code"
    EQUATION = "equation"
    DIAGRAM = "diagram"
    PAGE = "page"
    PROCEDURE = "procedure"
    PARAMETER = "parameter"
    MARKDOWN = "markdown"  # Added for completeness


class ChunkLevel(str, Enum):
    """Chunk level enumeration matching the full DocumentProcessor."""
    DOCUMENT = "document"
    SECTION = "section"
    PROCEDURE = "procedure"
    STEP = "step"


class EmbeddingType(str, Enum):
    """Embedding type enumeration matching the full DocumentProcessor."""
    CONCEPTUAL = "conceptual"
    TASK = "task"
    TECHNICAL = "technical"
    GENERAL = "general"


class ProcessingConfig(BaseModel):
    """
    Configuration options for document processing.
    Enhanced to match full DocumentProcessor capabilities.
    """
    pdf_id: Optional[str] = None
    chunk_size: int = 500
    chunk_overlap: int = 100
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    process_images: bool = True
    process_tables: bool = True
    extract_technical_terms: bool = True
    extract_relationships: bool = True
    extract_procedures: bool = True
    merge_list_items: bool = True
    max_concepts_per_document: int = 200


class TableData(BaseModel):
    """Table data structure."""
    table_id: str
    caption: Optional[str] = None
    headers: List[str] = Field(default_factory=list)
    rows: List[List[Any]] = Field(default_factory=list)
    summary: Optional[str] = None
    page_number: int = 0
    content: Optional[str] = None


class ImageData(BaseModel):
    """Image data structure."""
    image_id: str
    path: Optional[str] = None
    description: Optional[str] = None
    page_number: int = 0
    content: Optional[str] = None
    dimensions: Optional[tuple] = None


class ProcedureStep(BaseModel):
    """Procedure step data structure."""
    step_number: int
    content: str
    warnings: List[str] = Field(default_factory=list)
    parameters: List[str] = Field(default_factory=list)


class Procedure(BaseModel):
    """Procedure data structure."""
    procedure_id: str
    title: str
    content: str
    page: int = 0
    steps: List[ProcedureStep] = Field(default_factory=list)
    parameters: List[str] = Field(default_factory=list)
    section_headers: List[str] = Field(default_factory=list)


class Parameter(BaseModel):
    """Parameter data structure."""
    parameter_id: str
    name: str
    value: str
    type: str
    description: str
    procedure_id: Optional[str] = None
    section_headers: List[str] = Field(default_factory=list)
    page: int = 0


class ConceptRelationship(BaseModel):
    """Concept relationship data structure."""
    source: str
    target: str
    type: str
    weight: float = 0.5
    context: str = ""


class ChunkData(BaseModel):
    """Chunk data structure for vector stores."""
    chunk_id: str
    content: str
    chunk_level: str
    page_numbers: List[int] = Field(default_factory=list)
    section_headers: List[str] = Field(default_factory=list)
    token_count: int = 0


class DocumentSummary(BaseModel):
    """Document summary data structure."""
    title: str
    primary_concepts: List[str] = Field(default_factory=list)
    section_structure: List[str] = Field(default_factory=list)
    document_type: str = "Technical Document"
    key_insights: List[str] = Field(default_factory=list)
    description: Optional[str] = None


class EnhancedProcessingResponse(BaseModel):
    """
    Enhanced response model for document processing.
    Aligns with the full DocumentProcessor capabilities.
    """
    pdf_id: str
    markdown: str
    tables: List[TableData] = Field(default_factory=list)
    images: List[ImageData] = Field(default_factory=list)
    technical_terms: List[str] = Field(default_factory=list)
    procedures: List[Procedure] = Field(default_factory=list)
    parameters: List[Parameter] = Field(default_factory=list)
    concept_relationships: List[ConceptRelationship] = Field(default_factory=list)
    chunks: List[ChunkData] = Field(default_factory=list)
    summary: Optional[DocumentSummary] = None
    processing_time: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class QdrantReadyChunk(BaseModel):
    """Qdrant-ready chunk for vector store ingestion."""
    id: str
    content: str
    metadata: Dict[str, Any]


class MongoDBReadyDocument(BaseModel):
    """MongoDB-ready document for document store ingestion."""
    pdf_id: str
    content: Dict[str, Any]
    tables: List[TableData] = Field(default_factory=list)
    images: List[ImageData] = Field(default_factory=list)
    procedures: List[Procedure] = Field(default_factory=list)
    parameters: List[Parameter] = Field(default_factory=list)
    relationships: List[ConceptRelationship] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    summary: Optional[DocumentSummary] = None


class ProcessingStatus(BaseModel):
    """Processing status model."""
    pdf_id: str
    status: str  # "processing", "completed", "failed"
    progress: float = 0.0
    message: str = ""
