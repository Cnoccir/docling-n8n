# app/chat/types.py

"""
Streamlined type definitions for the PDF RAG system.
Optimized for MongoDB document structure and Qdrant vector storage.
"""

from enum import Enum
from typing import Dict, List, Optional, Any, Union, Set
from datetime import datetime
from pydantic import BaseModel, Field
from typing import TYPE_CHECKING

#
# 1. Core Enums
#
class ContentType(str, Enum):
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    CODE = "code"
    EQUATION = "equation"
    DIAGRAM = "diagram"
    PAGE = "page"
    PROCEDURE = "procedure"
    PARAMETER = "parameter"

class ChunkLevel(str, Enum):
    DOCUMENT = "document"
    SECTION = "section"
    PROCEDURE = "procedure"
    STEP = "step"

class EmbeddingType(str, Enum):
    CONCEPTUAL = "conceptual"
    TASK = "task"
    TECHNICAL = "technical"
    GENERAL = "general"

class ResearchMode(str, Enum):
    SINGLE = "single"
    RESEARCH = "research"

class RelationType(str, Enum):
    PART_OF = "part_of"
    USES = "uses"
    IMPLEMENTS = "implements"
    EXTENDS = "extends"
    RELATES_TO = "relates_to"
    CONFIGURES = "configures"
    PREREQUISITE = "prerequisite"
    REFERENCES = "references"

    @classmethod
    def map_type(cls, type_str: str) -> 'RelationType':
        mapping = {
            "part_of": cls.PART_OF,
            "uses": cls.USES,
            "implements": cls.IMPLEMENTS,
            "extends": cls.EXTENDS,
            "relates_to": cls.RELATES_TO,
            "configures": cls.CONFIGURES,
            "prerequisite": cls.PREREQUISITE,
            "references": cls.REFERENCES,
            "is_a": cls.EXTENDS,
            "has_a": cls.PART_OF,
            "contains": cls.PART_OF
        }
        return mapping.get(type_str.lower(), cls.RELATES_TO)

#
# 2. Content Models
#
class ContentMetadata(BaseModel):
    pdf_id: str
    page_number: Optional[int] = 0
    content_type: Optional[Union[ContentType, str]] = ContentType.TEXT
    parent_element_id: Optional[str] = None
    hierarchy_level: Optional[int] = 0
    section_headers: List[str] = Field(default_factory=list)
    technical_terms: List[str] = Field(default_factory=list)
    chunk_level: Optional[ChunkLevel] = None
    embedding_type: Optional[EmbeddingType] = EmbeddingType.GENERAL
    confidence: float = 1.0
    context: Optional[str] = None
    image_path: Optional[str] = None
    table_data: Optional[Dict[str, Any]] = None
    image_metadata: Optional[Dict[str, Any]] = None
    procedure_metadata: Optional[Dict[str, Any]] = None
    parameter_metadata: Optional[Dict[str, Any]] = None
    element_id: Optional[str] = None
    mongo_id: Optional[str] = None
    qdrant_id: Optional[str] = None
    score: float = 0.0
    doc_hash: Optional[str] = None

class ContentElement(BaseModel):
    element_id: str
    content: str
    content_type: Union[ContentType, str]
    pdf_id: str
    page: Optional[int] = 0
    metadata: ContentMetadata
    embedding: Optional[List[float]] = None
    vector_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        element_dict = self.dict(exclude={"embedding"})
        element_dict["content_type"] = str(self.content_type)
        if not element_dict.get("created_at"):
            element_dict["created_at"] = datetime.utcnow()
        element_dict["updated_at"] = datetime.utcnow()
        return element_dict

    def to_qdrant_payload(self) -> Dict[str, Any]:
        payload = {
            "element_id": self.element_id,
            "pdf_id": self.pdf_id,
            "content_type": str(self.content_type),
            "page_number": self.metadata.page_number,
            "chunk_level": str(self.metadata.chunk_level) if self.metadata.chunk_level else None,
            "section": " > ".join(self.metadata.section_headers) if self.metadata.section_headers else None,
            "technical_terms": self.metadata.technical_terms[:10],
            "hierarchy_level": self.metadata.hierarchy_level
        }
        return payload

#
# 3. Chunking Models
#
class ChunkMetadata(BaseModel):
    pdf_id: str
    content_type: str
    chunk_level: ChunkLevel
    chunk_index: int
    page_numbers: List[int] = Field(default_factory=list)
    section_headers: List[str] = Field(default_factory=list)
    parent_chunk_id: Optional[str] = None
    technical_terms: List[str] = Field(default_factory=list)
    embedding_type: EmbeddingType = EmbeddingType.GENERAL
    element_ids: List[str] = Field(default_factory=list)
    token_count: int = 0

class DocumentChunk(BaseModel):
    chunk_id: str
    content: str
    metadata: ChunkMetadata
    embedding: Optional[List[float]] = None
    vector_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        chunk_dict = self.dict(exclude={"embedding"})
        chunk_dict["content_type"] = str(self.metadata.content_type)
        chunk_dict["chunk_level"] = str(self.metadata.chunk_level)
        chunk_dict["embedding_type"] = str(self.metadata.embedding_type)
        chunk_dict["updated_at"] = datetime.utcnow()
        return chunk_dict

    def to_qdrant_payload(self) -> Dict[str, Any]:
        payload = {
            "chunk_id": self.chunk_id,
            "pdf_id": self.metadata.pdf_id,
            "content_type": str(self.metadata.content_type),
            "chunk_level": str(self.metadata.chunk_level),
            "embedding_type": str(self.metadata.embedding_type),
            "page_numbers": self.metadata.page_numbers,
            "section": " > ".join(self.metadata.section_headers) if self.metadata.section_headers else None,
            "technical_terms": self.metadata.technical_terms[:10],
            "token_count": self.metadata.token_count
        }
        return payload

#
# 4. Concept Models
#
class Concept(BaseModel):
    name: str
    occurrences: int = 1
    in_headers: bool = False
    sections: List[str] = Field(default_factory=list)
    first_occurrence_page: Optional[int] = None
    importance_score: float = 0.5
    is_primary: bool = False
    category: Optional[str] = None
    pdf_id: str

class ConceptRelationship(BaseModel):
    source: str
    target: str
    type: RelationType = RelationType.RELATES_TO
    weight: float = 0.5
    context: str = ""
    extraction_method: str = "rule-based"
    pdf_id: str

class ConceptNetwork(BaseModel):
    concepts: List[Concept] = Field(default_factory=list)
    relationships: List[ConceptRelationship] = Field(default_factory=list)
    section_concepts: Dict[str, List[str]] = Field(default_factory=dict)
    primary_concepts: List[str] = Field(default_factory=list)
    pdf_id: Optional[str] = None

    def add_concept(self, concept: Concept) -> None:
        for existing in self.concepts:
            if existing.name.lower() == concept.name.lower():
                existing.occurrences += concept.occurrences
                existing.importance_score = max(existing.importance_score, concept.importance_score)
                existing.is_primary = existing.is_primary or concept.is_primary
                return
        self.concepts.append(concept)

    def add_relationship(self, relationship: ConceptRelationship) -> None:
        for existing in self.relationships:
            if (existing.source.lower() == relationship.source.lower()
                and existing.target.lower() == relationship.target.lower()
                and existing.type == relationship.type):
                existing.weight = max(existing.weight, relationship.weight)
                return
        self.relationships.append(relationship)

    def add_section_concepts(self, section: str, concepts: List[str]) -> None:
        if section not in self.section_concepts:
            self.section_concepts[section] = []
        for concept in concepts:
            if concept not in self.section_concepts[section]:
                self.section_concepts[section].append(concept)

    def calculate_importance_scores(self) -> None:
        pass

#
# 5. Search/Query
#
class SearchQuery(BaseModel):
    query: str
    content_types: Optional[List[Union[ContentType, str]]] = None
    technical_terms: Optional[List[str]] = None
    max_results: Optional[int] = 10
    research_mode: bool = False
    favor_visual: bool = False
    favor_tables: bool = False
    favor_code: bool = False
    active_pdf_ids: Optional[List[str]] = None

class SearchResult(BaseModel):
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    score: float = 0.0
    element_id: Optional[str] = None
    pdf_id: Optional[str] = None
    page_number: Optional[int] = None
    content_type: Optional[str] = ContentType.TEXT
    document_title: Optional[str] = None

#
# 6. Processing
#
class ProcessingConfig(BaseModel):
    pdf_id: str
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
    chunk_levels: Dict[ChunkLevel, int] = Field(
        default_factory=lambda: {
            ChunkLevel.DOCUMENT: 3000,
            ChunkLevel.SECTION: 1500,
            ChunkLevel.PROCEDURE: 800,
            ChunkLevel.STEP: 200
        }
    )
    embedding_types: Dict[EmbeddingType, str] = Field(
        default_factory=lambda: {
            EmbeddingType.CONCEPTUAL: "text-embedding-3-small",
            EmbeddingType.TASK: "text-embedding-3-small",
            EmbeddingType.TECHNICAL: "text-embedding-3-small",
            EmbeddingType.GENERAL: "text-embedding-3-small"
        }
    )

class ProcessingResult(BaseModel):
    pdf_id: str
    elements: List[ContentElement] = Field(default_factory=list)
    chunks: List[DocumentChunk] = Field(default_factory=list)
    processing_metrics: Dict[str, Any] = Field(default_factory=dict)
    markdown_content: str = ""
    markdown_path: str = ""
    concept_network: Optional[ConceptNetwork] = None
    visual_elements: List[ContentElement] = Field(default_factory=list)
    document_summary: Optional[Dict[str, Any]] = None
    procedures: List[Dict[str, Any]] = Field(default_factory=list)
    parameters: List[Dict[str, Any]] = Field(default_factory=list)
    raw_data: Dict[str, Any] = Field(default_factory=dict)

    def get_statistics(self) -> Dict[str, Any]:
        element_types = {}
        for element in self.elements:
            t = str(element.content_type)
            element_types[t] = element_types.get(t, 0) + 1

        top_technical_terms = {}
        for element in self.elements:
            if hasattr(element.metadata, 'technical_terms'):
                for term in element.metadata.technical_terms:
                    top_technical_terms[term] = top_technical_terms.get(term, 0) + 1

        return {
            "element_count": len(self.elements),
            "chunk_count": len(self.chunks),
            "element_types": element_types,
            "procedure_count": len(self.procedures),
            "parameter_count": len(self.parameters),
            "top_technical_terms": dict(
                sorted(top_technical_terms.items(), key=lambda x: x[1], reverse=True)[:20]
            )
        }

# -----------------------
# NO REAL RESEARCHMANAGER HERE
# If you must reference it in type hints:
# -----------------------
if TYPE_CHECKING:
    from app.chat.research.research_manager import ResearchManager
    from app.chat.models import ChatArgs, ResearchContext
