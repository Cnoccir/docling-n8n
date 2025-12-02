"""Database client for document RAG system."""
import os
import json
import psycopg2
import psycopg2.extras
from typing import List, Optional, Dict, Any, Tuple
from .models import Chunk, DocumentHierarchy, Section, Page


class DatabaseClient:
    """Handle all database operations."""
    
    def __init__(self):
        self.conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        self.conn.autocommit = False  # Use transactions
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()
    
    # ==================== Document Index Operations ====================
    
    def create_document_index(
        self,
        doc_id: str,
        title: str,
        filename: str,
        file_hash: str,
        file_size_bytes: int,
        document_type: Optional[str] = None,
        summary: Optional[str] = None,
        tags: List[str] = None,
        categories: List[str] = None,
        gdrive_file_id: Optional[str] = None,
        gdrive_link: Optional[str] = None,
        gdrive_folder_id: Optional[str] = None
    ) -> bool:
        """Create document index entry with optional Google Drive info."""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO document_index (
                    id, title, filename, file_hash, file_size_bytes,
                    status, document_type, summary, tags, categories,
                    gdrive_file_id, gdrive_link, gdrive_folder_id
                )
                VALUES (%s, %s, %s, %s, %s, 'processing', %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                RETURNING id
            """, (
                doc_id, title, filename, file_hash, file_size_bytes,
                document_type, summary,
                json.dumps(tags or []),
                json.dumps(categories or []),
                gdrive_file_id,
                gdrive_link,
                gdrive_folder_id
            ))
            result = cur.fetchone()
            self.conn.commit()
            return result is not None
    
    def update_document_status(
        self,
        doc_id: str,
        status: str,
        error_message: Optional[str] = None,
        summary: Optional[str] = None,
        total_pages: int = 0,
        total_chunks: int = 0,
        total_sections: int = 0,
        total_images: int = 0,
        total_tables: int = 0,
        processing_duration: float = 0,
        ingestion_cost: float = 0,
        tokens_used: int = 0
    ):
        """Update document processing status."""
        with self.conn.cursor() as cur:
            # Build dynamic UPDATE query to only update summary if provided
            update_fields = [
                "status = %s",
                "error_message = %s",
                "total_pages = %s",
                "total_chunks = %s",
                "total_sections = %s",
                "total_images = %s",
                "total_tables = %s",
                "processing_duration_seconds = %s",
                "ingestion_cost_usd = %s",
                "tokens_used = %s",
                "processed_at = NOW()",
                "updated_at = NOW()"
            ]
            
            params = [
                status, error_message,
                total_pages, total_chunks, total_sections,
                total_images, total_tables,
                processing_duration, ingestion_cost, tokens_used
            ]
            
            if summary is not None:
                update_fields.insert(1, "summary = %s")
                params.insert(1, summary)
            
            params.append(doc_id)
            
            query = f"UPDATE document_index SET {', '.join(update_fields)} WHERE id = %s"
            cur.execute(query, tuple(params))
            self.conn.commit()
    
    def check_document_exists(self, file_hash: str) -> Optional[Dict[str, Any]]:
        """Check if document already exists by file hash."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, title, status
                FROM document_index
                WHERE file_hash = %s
                LIMIT 1
            """, (file_hash,))
            return cur.fetchone()
    
    def list_documents(
        self,
        status: Optional[str] = None,
        document_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List documents with filtering."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM list_documents(%s, %s, %s, %s)
            """, (status, document_type, limit, offset))
            return cur.fetchall()
    
    def get_document_details(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get full document details."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM get_document_details(%s)
            """, (doc_id,))
            return cur.fetchone()
    
    # ==================== Chunk Operations ====================
    
    def save_chunks(
        self,
        chunks: List[Chunk],
        embeddings: List[List[float]]
    ):
        """Batch insert chunks with embeddings."""
        if not chunks:
            return
        
        # Prepare data for batch insert
        values = []
        for chunk, embedding in zip(chunks, embeddings):
            values.append((
                chunk.id,
                chunk.doc_id,
                chunk.content,
                embedding,
                chunk.page_number,
                json.dumps(chunk.bbox) if chunk.bbox else None,
                chunk.section_id,
                chunk.parent_section_id,
                chunk.section_path if hasattr(chunk, 'section_path') else None,
                chunk.section_level if hasattr(chunk, 'section_level') else None,
                chunk.element_type,
                json.dumps(chunk.metadata),
                chunk.topic if hasattr(chunk, 'topic') else None,  # NEW: Phase 2
                chunk.topics if hasattr(chunk, 'topics') else []  # NEW: Phase 2
            ))
        
        with self.conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO chunks (
                    id, doc_id, content, embedding, page_number, bbox,
                    section_id, parent_section_id, section_path, section_level,
                    element_type, metadata, topic, topics
                )
                VALUES %s
                ON CONFLICT (id) DO NOTHING
                """,
                values,
                template="(%s, %s, %s, %s::vector, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            )
            self.conn.commit()
    
    def get_chunks_by_ids(self, chunk_ids: List[str]) -> List[Chunk]:
        """Get chunks by IDs using SQL function."""
        if not chunk_ids:
            return []
        
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM get_chunks_by_ids(%s)
            """, (chunk_ids,))
            
            rows = cur.fetchall()
            chunks = []
            for row in rows:
                chunk = Chunk(
                    id=row['id'],
                    doc_id=row['doc_id'],
                    content=row['content'],
                    page_number=row['page_number'],
                    section_id=row['section_id'],
                    bbox=row['bbox']
                )
                chunks.append(chunk)
            
            return chunks
    
    def search_chunks(
        self,
        query_embedding: List[float],
        doc_id: Optional[str] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Vector search using SQL function (semantic only)."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM search_chunks(%s::vector, %s, 0.3, %s)
            """, (query_embedding, doc_id, top_k))
            return cur.fetchall()
    
    def search_chunks_hybrid(
        self,
        query_embedding: List[float],
        query_text: str,
        doc_id: Optional[str] = None,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Hybrid search combining semantic + keyword (BM25) search.
        
        Args:
            query_embedding: Vector embedding of the query
            query_text: Raw query text for keyword search
            doc_id: Optional document ID filter
            semantic_weight: Weight for semantic similarity (default 0.7)
            keyword_weight: Weight for keyword matching (default 0.3)
            top_k: Number of results to return
            
        Returns:
            List of chunks with semantic_score, keyword_score, combined_score
        """
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM search_chunks_hybrid(
                    %s::vector, %s, %s, %s, %s, 0.0, %s
                )
            """, (query_embedding, query_text, doc_id, semantic_weight, keyword_weight, top_k))
            return cur.fetchall()
    
    def search_chunks_hybrid_with_topics(
        self,
        query_embedding: List[float],
        query_text: str,
        doc_id: Optional[str] = None,
        include_topics: Optional[List[str]] = None,
        exclude_topics: Optional[List[str]] = None,
        semantic_weight: float = 0.5,
        keyword_weight: float = 0.5,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Hybrid search with topic filtering and boosting (Phase 3).
        
        Args:
            query_embedding: Vector embedding of the query
            query_text: Raw query text for keyword search
            doc_id: Optional document ID filter
            include_topics: Topics to filter/boost (e.g., ['system_database', 'graphics'])
            exclude_topics: Topics to exclude (e.g., ['provisioning'])
            semantic_weight: Weight for semantic similarity (default 0.5)
            keyword_weight: Weight for keyword matching (default 0.5)
            top_k: Number of results to return
            
        Returns:
            List of chunks with semantic_score, keyword_score, topic_boost, final_score
        """
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM search_chunks_hybrid_with_topics(
                    %s::vector, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                query_embedding, 
                query_text, 
                doc_id, 
                include_topics,
                exclude_topics,
                semantic_weight, 
                keyword_weight, 
                top_k
            ))
            return cur.fetchall()
    
    # ==================== Hierarchy Operations ====================
    
    def save_hierarchy(
        self, 
        hierarchy: DocumentHierarchy, 
        page_index: Dict[str, Any] = None,
        asset_index: Dict[str, Any] = None
    ):
        """Save document hierarchy with PageIndex and AssetIndex."""
        hierarchy_json = hierarchy.to_dict()
        
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO document_hierarchy (
                    doc_id, hierarchy, page_index, asset_index, title,
                    total_pages, total_chunks, total_sections
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (doc_id) DO UPDATE SET
                    hierarchy = EXCLUDED.hierarchy,
                    page_index = EXCLUDED.page_index,
                    asset_index = EXCLUDED.asset_index,
                    title = EXCLUDED.title,
                    total_pages = EXCLUDED.total_pages,
                    total_chunks = EXCLUDED.total_chunks,
                    total_sections = EXCLUDED.total_sections,
                    updated_at = NOW()
            """, (
                hierarchy.doc_id,
                json.dumps(hierarchy_json),
                json.dumps(page_index) if page_index else None,
                json.dumps(asset_index) if asset_index else None,
                hierarchy.title,
                hierarchy.total_pages,
                hierarchy.total_chunks,
                hierarchy.total_sections
            ))
            self.conn.commit()
    
    def get_hierarchy(self, doc_id: str) -> Optional[DocumentHierarchy]:
        """Load hierarchy from database."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT hierarchy FROM document_hierarchy WHERE doc_id = %s
            """, (doc_id,))
            
            row = cur.fetchone()
            if not row:
                return None
            
            hierarchy_data = row['hierarchy']
            return DocumentHierarchy.from_dict(doc_id, hierarchy_data)
    
    def get_page_index(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get PageIndex for document."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT page_index FROM document_hierarchy WHERE doc_id = %s
            """, (doc_id,))
            
            row = cur.fetchone()
            return row[0] if row else None
    
    def get_asset_index(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get AssetIndex for document."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT asset_index FROM document_hierarchy WHERE doc_id = %s
            """, (doc_id,))
            
            row = cur.fetchone()
            return row[0] if row else None
    
    # ==================== Image Operations ====================
    
    def save_images(self, images: List[Dict[str, Any]]):
        """Batch insert images."""
        if not images:
            return
        
        values = [
            (
                img['id'],
                img['doc_id'],
                img.get('chunk_id'),
                img['page_number'],
                json.dumps(img.get('bbox')),
                img['s3_url'],
                img.get('caption'),
                img.get('ocr_text'),
                img.get('image_type'),
                img.get('basic_summary'),
                img.get('detailed_description'),
                img.get('tokens_used', 0),
                img.get('description_generated', False),
                img.get('section_id'),  # NEW: section_id for hierarchy
                img.get('topic'),  # NEW: Phase 2
                img.get('topics', [])  # NEW: Phase 2
            )
            for img in images
        ]

        with self.conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO images (
                    id, doc_id, chunk_id, page_number, bbox, s3_url,
                    caption, ocr_text, image_type, basic_summary,
                    detailed_description, tokens_used, description_generated,
                    section_id, topic, topics
                )
                VALUES %s
                ON CONFLICT (id) DO NOTHING
                """,
                values
            )
            self.conn.commit()
    
    def get_images_by_doc(self, doc_id: str) -> List[Dict[str, Any]]:
        """Get all images for a document."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM images WHERE doc_id = %s ORDER BY page_number
            """, (doc_id,))
            return cur.fetchall()
    
    def get_images_by_pages(self, doc_id: str, page_numbers: List[int]) -> List[Dict[str, Any]]:
        """Get images on specific pages."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM images 
                WHERE doc_id = %s AND page_number = ANY(%s)
                ORDER BY page_number
            """, (doc_id, page_numbers))
            return cur.fetchall()
    
    # ==================== Table Operations ====================
    
    def save_tables(self, tables: List[Dict[str, Any]]):
        """Batch insert tables."""
        if not tables:
            return
        
        values = [
            (
                tbl['id'],
                tbl['doc_id'],
                tbl['page_number'],
                json.dumps(tbl.get('bbox')),
                tbl.get('raw_html'),
                tbl['markdown'],
                json.dumps(tbl.get('structured_data')),
                tbl.get('title'),
                tbl['description'],
                json.dumps(tbl.get('key_insights', [])),
                tbl.get('section_id'),  # NEW: section_id for hierarchy
                tbl.get('topic'),  # NEW: Phase 2
                tbl.get('topics', [])  # NEW: Phase 2
            )
            for tbl in tables
        ]
        
        with self.conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO document_tables (
                    id, doc_id, page_number, bbox, raw_html, markdown,
                    structured_data, title, description, key_insights,
                    section_id, topic, topics
                )
                VALUES %s
                ON CONFLICT (id) DO NOTHING
                """,
                values
            )
            self.conn.commit()
    
    def get_tables_by_doc(self, doc_id: str) -> List[Dict[str, Any]]:
        """Get all tables for a document."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM document_tables WHERE doc_id = %s ORDER BY page_number
            """, (doc_id,))
            return cur.fetchall()
    
    def get_tables_by_pages(self, doc_id: str, page_numbers: List[int]) -> List[Dict[str, Any]]:
        """Get tables on specific pages."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM document_tables
                WHERE doc_id = %s AND page_number = ANY(%s)
                ORDER BY page_number
            """, (doc_id, page_numbers))
            return cur.fetchall()

    # ==================== Image Retrieval Operations ====================

    def get_images_for_chunk(self, chunk_id: str) -> List[Dict[str, Any]]:
        """Get images associated with a chunk (same page/section)."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT i.id, i.s3_url, i.caption, i.image_type, i.page_number, i.ocr_text
                FROM images i
                JOIN chunks c ON i.doc_id = c.doc_id AND i.page_number = c.page_number
                WHERE c.id = %s
                ORDER BY i.page_number, i.image_index
                LIMIT 5
            """, (chunk_id,))
            return cur.fetchall()

    def get_screenshots_for_timestamp(
        self, doc_id: str, start_time: float, end_time: float
    ) -> List[Dict[str, Any]]:
        """Get video screenshots within timestamp range (±2 second buffer)."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, s3_url, ocr_text, caption, timestamp
                FROM images
                WHERE doc_id = %s
                  AND timestamp IS NOT NULL
                  AND timestamp >= %s - 2
                  AND timestamp <= %s + 2
                ORDER BY timestamp
                LIMIT 3
            """, (doc_id, start_time, end_time))
            return cur.fetchall()

    def get_images_by_pages(self, doc_id: str, page_numbers: List[int]) -> List[Dict[str, Any]]:
        """Get images on specific pages."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, s3_url, caption, image_type, page_number, ocr_text
                FROM images
                WHERE doc_id = %s AND page_number = ANY(%s)
                ORDER BY page_number, image_index
                LIMIT 10
            """, (doc_id, page_numbers))
            return cur.fetchall()
