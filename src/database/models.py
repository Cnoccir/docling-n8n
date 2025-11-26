"""Data models for V2 RAG pipeline."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class Chunk:
    """A single piece of content with embedding."""
    id: str
    doc_id: str
    content: str
    page_number: int
    
    # Hierarchy references
    section_id: Optional[str] = None
    parent_section_id: Optional[str] = None
    
    # VectifyAI-inspired: Preserve document structure
    section_path: Optional[List[str]] = None  # Full path like ['Chapter 1', 'Section 1.1']
    section_level: Optional[int] = None  # Section depth (0=root, 1=chapter, 2=section, etc.)
    
    # Optional fields
    bbox: Optional[Dict[str, Any]] = None
    element_type: str = "text"
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None


@dataclass
class Section:
    """A section in the document hierarchy."""
    id: str
    title: str
    level: int
    
    # References to chunks in this section
    chunk_ids: List[str] = field(default_factory=list)
    
    # Hierarchy relationships
    parent_section_id: Optional[str] = None
    child_section_ids: List[str] = field(default_factory=list)
    
    # Page span
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    
    # PageIndex enhancement
    summary: Optional[str] = None
    
    # Additional metadata (section_number, section_path, etc.)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Page:
    """A page in the document."""
    page_no: int
    
    # References
    section_ids: List[str] = field(default_factory=list)
    chunk_ids: List[str] = field(default_factory=list)
    image_ids: List[str] = field(default_factory=list)  # NEW: Track specific images
    table_ids: List[str] = field(default_factory=list)  # NEW: Track specific tables
    
    # Optional metadata
    chunk_count: int = 0
    image_count: int = 0
    table_count: int = 0


@dataclass
class DocumentHierarchy:
    """Complete document structure."""
    doc_id: str
    pages: List[Page]
    sections: List[Section]
    
    # Metadata
    title: Optional[str] = None
    total_pages: int = 0
    total_chunks: int = 0
    total_sections: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage."""
        return {
            "pages": [
                {
                    "page_no": p.page_no,
                    "section_ids": p.section_ids,
                    "chunk_ids": p.chunk_ids,
                    "image_ids": p.image_ids,  # NEW
                    "table_ids": p.table_ids,  # NEW
                    "chunk_count": p.chunk_count,
                    "image_count": p.image_count,
                    "table_count": p.table_count
                }
                for p in self.pages
            ],
            "sections": [
                {
                    "id": s.id,
                    "title": s.title,
                    "level": s.level,
                    "chunk_ids": s.chunk_ids,
                    "parent_section_id": s.parent_section_id,
                    "child_section_ids": s.child_section_ids,
                    "start_page": s.start_page,
                    "end_page": s.end_page,
                    "summary": s.summary,
                    "metadata": s.metadata
                }
                for s in self.sections
            ]
        }
    
    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]) -> DocumentHierarchy:
        """Create from dictionary."""
        pages = [
            Page(
                page_no=p["page_no"],
                section_ids=p.get("section_ids", []),
                chunk_ids=p.get("chunk_ids", []),
                image_ids=p.get("image_ids", []),  # NEW
                table_ids=p.get("table_ids", []),  # NEW
                chunk_count=p.get("chunk_count", 0),
                image_count=p.get("image_count", 0),
                table_count=p.get("table_count", 0)
            )
            for p in data.get("pages", [])
        ]
        
        sections = [
            Section(
                id=s["id"],
                title=s["title"],
                level=s["level"],
                chunk_ids=s.get("chunk_ids", []),
                parent_section_id=s.get("parent_section_id"),
                child_section_ids=s.get("child_section_ids", []),
                start_page=s.get("start_page"),
                end_page=s.get("end_page"),
                summary=s.get("summary"),
                metadata=s.get("metadata", {})
            )
            for s in data.get("sections", [])
        ]
        
        return cls(
            doc_id=doc_id,
            pages=pages,
            sections=sections,
            total_pages=len(pages),
            total_sections=len(sections)
        )
    
    def get_section_by_id(self, section_id: str) -> Optional[Section]:
        """Find section by ID."""
        for section in self.sections:
            if section.id == section_id:
                return section
        return None
    
    def get_section_by_chunk_id(self, chunk_id: str) -> Optional[Section]:
        """Find section containing a chunk."""
        for section in self.sections:
            if chunk_id in section.chunk_ids:
                return section
        return None


@dataclass
class QueryResult:
    """Result from a query operation."""
    query: str
    answer: str
    
    # Golden chunks found
    golden_chunks: List[Chunk]
    
    # Context used
    context_chunks: List[Chunk]
    section: Optional[Section] = None
    
    # Metadata
    similarity_scores: List[float] = field(default_factory=list)
    tokens_used: int = 0
    retrieval_strategy: str = "golden_chunk_with_hierarchy"
