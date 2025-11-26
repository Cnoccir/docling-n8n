-- V2 RAG Pipeline Database Schema
-- Clean, reference-based design for technical document retrieval

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For fuzzy text search

-- Drop existing functions (to allow schema changes)
DROP FUNCTION IF EXISTS get_document_details(TEXT);
DROP FUNCTION IF EXISTS list_documents(TEXT, TEXT, INTEGER, INTEGER);
DROP FUNCTION IF EXISTS search_documents(TEXT, INTEGER);
DROP FUNCTION IF EXISTS check_document_exists(TEXT);
DROP FUNCTION IF EXISTS search_chunks(vector, TEXT, FLOAT, INTEGER);
DROP FUNCTION IF EXISTS search_chunks_hybrid(vector, TEXT, TEXT, FLOAT, FLOAT, FLOAT, INTEGER);
DROP FUNCTION IF EXISTS get_chunks_by_ids(TEXT[]);
DROP FUNCTION IF EXISTS get_section_by_chunk_id(TEXT, TEXT);

-- Drop existing tables
DROP TABLE IF EXISTS images CASCADE;
DROP TABLE IF EXISTS document_tables CASCADE;
DROP TABLE IF EXISTS chunks CASCADE;
DROP TABLE IF EXISTS document_hierarchy CASCADE;
DROP TABLE IF EXISTS documents CASCADE;
DROP TABLE IF EXISTS document_index CASCADE;

-- Document Index: Master catalog of all documents with versioning
CREATE TABLE document_index (
    id TEXT PRIMARY KEY,  -- Stable document ID (e.g., 'niagara_manual')
    version INTEGER NOT NULL DEFAULT 1,
    
    -- Document metadata
    title TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_hash TEXT,  -- SHA256 of original file for deduplication
    file_size_bytes BIGINT,
    
    -- Processing status
    status TEXT DEFAULT 'processing',  -- 'processing', 'completed', 'failed'
    error_message TEXT,
    
    -- Document statistics
    total_pages INTEGER DEFAULT 0,
    total_chunks INTEGER DEFAULT 0,
    total_sections INTEGER DEFAULT 0,
    total_images INTEGER DEFAULT 0,
    total_tables INTEGER DEFAULT 0,
    
    -- VectifyAI-inspired: Document-level metadata for query routing
    document_type TEXT,  -- 'manual', 'report', 'research', 'legal'
    summary TEXT,  -- AI-generated document summary for routing and context
    tags JSONB DEFAULT '[]',
    categories JSONB DEFAULT '[]',
    language TEXT DEFAULT 'en',
    
    -- Versioning and tracking
    previous_version_id TEXT,  -- Link to previous version
    replaced_by_version_id TEXT,  -- Link to newer version
    
    -- Processing metadata
    processing_duration_seconds FLOAT,
    ingestion_cost_usd FLOAT,
    tokens_used INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,
    
    -- Unique constraint: one version per id+version combo
    UNIQUE(id, version)
);

-- Chunks: Individual pieces of content with vector embeddings
CREATE TABLE chunks (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES document_index(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(1536),
    
    -- Page information (ALWAYS preserved)
    page_number INTEGER NOT NULL,
    bbox JSONB,
    
    -- Hierarchy references (NOT ranges!)
    section_id TEXT,
    parent_section_id TEXT,
    
    -- VectifyAI-inspired: Preserve document structure
    section_path TEXT[],  -- Full path like ['Chapter 1', 'Section 1.1', 'Subsection 1.1.1']
    section_level INTEGER,
    
    -- Metadata
    element_type TEXT DEFAULT 'text',
    metadata JSONB DEFAULT '{}',
    
    -- Full-text search support
    content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Document hierarchy: VectifyAI-inspired PageIndex structure
CREATE TABLE document_hierarchy (
    doc_id TEXT PRIMARY KEY REFERENCES document_index(id) ON DELETE CASCADE,
    
    -- Full hierarchy structure as JSONB
    hierarchy JSONB NOT NULL,
    
    -- PageIndex: Page-level summaries for fast document-level retrieval
    page_index JSONB,  -- {"page_1": {"summary": "...", "section_ids": [...]}, ...}
    
    -- AssetIndex: Track images and tables by section and page
    asset_index JSONB,  -- {"images": {"img_id": {"section_id": "...", "page": 1}}, "tables": {...}}
    
    -- Document metadata
    title TEXT,
    total_pages INTEGER,
    total_chunks INTEGER,
    total_sections INTEGER,
    
    -- VectifyAI concept: Document reasoning path
    reasoning_structure JSONB,  -- Track how sections relate to each other
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for document_index (master catalog)
CREATE INDEX document_index_status_idx ON document_index(status);
CREATE INDEX document_index_created_idx ON document_index(created_at DESC);
CREATE INDEX document_index_type_idx ON document_index(document_type);
CREATE INDEX document_index_hash_idx ON document_index(file_hash);  -- For deduplication
CREATE INDEX document_index_tags_idx ON document_index USING GIN(tags);
CREATE INDEX document_index_categories_idx ON document_index USING GIN(categories);
CREATE INDEX document_index_title_search_idx ON document_index USING GIN(title gin_trgm_ops);  -- Fuzzy search

-- Indexes for chunks (fast lookups)
CREATE INDEX chunks_doc_id_idx ON chunks(doc_id);
CREATE INDEX chunks_section_id_idx ON chunks(section_id);
CREATE INDEX chunks_page_idx ON chunks(page_number);
CREATE INDEX chunks_doc_page_idx ON chunks(doc_id, page_number);  -- Common query pattern
CREATE INDEX chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_section_path_idx ON chunks USING GIN(section_path);  -- For hierarchy navigation
CREATE INDEX chunks_content_tsv_idx ON chunks USING GIN(content_tsv);  -- Full-text search

-- GIN indexes for hierarchy JSON queries
CREATE INDEX hierarchy_jsonb_idx ON document_hierarchy USING GIN(hierarchy);
CREATE INDEX hierarchy_page_index_idx ON document_hierarchy USING GIN(page_index);
CREATE INDEX hierarchy_asset_index_idx ON document_hierarchy USING GIN(asset_index);

-- Full-text search index on document summary
CREATE INDEX document_index_summary_search_idx ON document_index USING GIN(to_tsvector('english', summary));

-- Function: Vector search with filtering (semantic only)
CREATE OR REPLACE FUNCTION search_chunks(
    query_embedding vector(1536),
    filter_doc_id TEXT DEFAULT NULL,
    similarity_threshold FLOAT DEFAULT 0.3,
    max_results INTEGER DEFAULT 10
)
RETURNS TABLE (
    id TEXT,
    doc_id TEXT,
    content TEXT,
    page_number INTEGER,
    section_id TEXT,
    section_path TEXT[],
    metadata JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.doc_id,
        c.content,
        c.page_number,
        c.section_id,
        c.section_path,
        c.metadata,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM chunks c
    WHERE 
        (filter_doc_id IS NULL OR c.doc_id = filter_doc_id)
        AND c.embedding IS NOT NULL
        AND 1 - (c.embedding <=> query_embedding) > similarity_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT max_results;
END;
$$;

-- Function: Hybrid search (semantic + keyword BM25)
CREATE OR REPLACE FUNCTION search_chunks_hybrid(
    query_embedding vector(1536),
    query_text TEXT,
    filter_doc_id TEXT DEFAULT NULL,
    semantic_weight FLOAT DEFAULT 0.7,
    keyword_weight FLOAT DEFAULT 0.3,
    similarity_threshold FLOAT DEFAULT 0.0,
    max_results INTEGER DEFAULT 10
)
RETURNS TABLE (
    id TEXT,
    doc_id TEXT,
    content TEXT,
    page_number INTEGER,
    section_id TEXT,
    section_path TEXT[],
    metadata JSONB,
    semantic_score FLOAT,
    keyword_score FLOAT,
    combined_score FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH semantic_results AS (
        SELECT
            c.id,
            c.doc_id,
            c.content,
            c.page_number,
            c.section_id,
            c.section_path,
            c.metadata,
            1 - (c.embedding <=> query_embedding) AS similarity
        FROM chunks c
        WHERE 
            (filter_doc_id IS NULL OR c.doc_id = filter_doc_id)
            AND c.embedding IS NOT NULL
    ),
    keyword_results AS (
        SELECT
            c.id,
            ts_rank_cd(c.content_tsv, websearch_to_tsquery('english', query_text), 32)::FLOAT AS rank
        FROM chunks c
        WHERE 
            (filter_doc_id IS NULL OR c.doc_id = filter_doc_id)
            AND c.content_tsv @@ websearch_to_tsquery('english', query_text)
    ),
    combined AS (
        SELECT
            s.id,
            s.doc_id,
            s.content,
            s.page_number,
            s.section_id,
            s.section_path,
            s.metadata,
            s.similarity AS semantic_score,
            COALESCE(k.rank, 0.0) AS keyword_score,
            (semantic_weight * s.similarity) + (keyword_weight * COALESCE(k.rank, 0.0)) AS combined_score
        FROM semantic_results s
        LEFT JOIN keyword_results k ON s.id = k.id
    )
    SELECT
        c.id,
        c.doc_id,
        c.content,
        c.page_number,
        c.section_id,
        c.section_path,
        c.metadata,
        c.semantic_score,
        c.keyword_score,
        c.combined_score
    FROM combined c
    WHERE c.combined_score > similarity_threshold
    ORDER BY c.combined_score DESC
    LIMIT max_results;
END;
$$;

-- Function: Get chunks by IDs (for context expansion)
CREATE OR REPLACE FUNCTION get_chunks_by_ids(
    chunk_ids TEXT[]
)
RETURNS TABLE (
    id TEXT,
    doc_id TEXT,
    content TEXT,
    page_number INTEGER,
    section_id TEXT,
    bbox JSONB
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.doc_id,
        c.content,
        c.page_number,
        c.section_id,
        c.bbox
    FROM chunks c
    WHERE c.id = ANY(chunk_ids)
    ORDER BY c.page_number, c.id;
END;
$$;

-- Function: Get section from hierarchy by chunk ID
CREATE OR REPLACE FUNCTION get_section_by_chunk_id(
    p_doc_id TEXT,
    p_chunk_id TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_hierarchy JSONB;
    v_section JSONB;
BEGIN
    -- Get hierarchy
    SELECT hierarchy INTO v_hierarchy
    FROM document_hierarchy
    WHERE doc_id = p_doc_id;
    
    IF v_hierarchy IS NULL THEN
        RETURN NULL;
    END IF;
    
    -- Find section containing this chunk
    SELECT section INTO v_section
    FROM jsonb_array_elements(v_hierarchy->'sections') AS section
    WHERE section->'chunk_ids' @> to_jsonb(p_chunk_id);
    
    RETURN v_section;
END;
$$;

-- Function: List all documents with filtering
CREATE OR REPLACE FUNCTION list_documents(
    p_status TEXT DEFAULT NULL,
    p_document_type TEXT DEFAULT NULL,
    p_limit INTEGER DEFAULT 50,
    p_offset INTEGER DEFAULT 0
)
RETURNS TABLE (
    id TEXT,
    version INTEGER,
    title TEXT,
    filename TEXT,
    status TEXT,
    document_type TEXT,
    total_pages INTEGER,
    total_chunks INTEGER,
    total_sections INTEGER,
    created_at TIMESTAMP WITH TIME ZONE,
    processed_at TIMESTAMP WITH TIME ZONE
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        di.id,
        di.version,
        di.title,
        di.filename,
        di.status,
        di.document_type,
        di.total_pages,
        di.total_chunks,
        di.total_sections,
        di.created_at,
        di.processed_at
    FROM document_index di
    WHERE 
        (p_status IS NULL OR di.status = p_status)
        AND (p_document_type IS NULL OR di.document_type = p_document_type)
    ORDER BY di.created_at DESC
    LIMIT p_limit
    OFFSET p_offset;
END;
$$;

-- Function: Check if document exists (by hash for deduplication)
CREATE OR REPLACE FUNCTION check_document_exists(
    p_file_hash TEXT
)
RETURNS TABLE (
    id TEXT,
    version INTEGER,
    title TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        di.id,
        di.version,
        di.title
    FROM document_index di
    WHERE di.file_hash = p_file_hash
    ORDER BY di.version DESC
    LIMIT 1;
END;
$$;

-- Function: Get document with all metadata
CREATE OR REPLACE FUNCTION get_document_details(
    p_doc_id TEXT
)
RETURNS TABLE (
    id TEXT,
    version INTEGER,
    title TEXT,
    filename TEXT,
    status TEXT,
    document_type TEXT,
    summary TEXT,
    total_pages INTEGER,
    total_chunks INTEGER,
    total_sections INTEGER,
    total_images INTEGER,
    total_tables INTEGER,
    tags JSONB,
    categories JSONB,
    created_at TIMESTAMP WITH TIME ZONE,
    processed_at TIMESTAMP WITH TIME ZONE,
    processing_duration_seconds FLOAT,
    ingestion_cost_usd FLOAT,
    tokens_used INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        di.id,
        di.version,
        di.title,
        di.filename,
        di.status,
        di.document_type,
        di.summary,
        di.total_pages,
        di.total_chunks,
        di.total_sections,
        di.total_images,
        di.total_tables,
        di.tags,
        di.categories,
        di.created_at,
        di.processed_at,
        di.processing_duration_seconds,
        di.ingestion_cost_usd,
        di.tokens_used
    FROM document_index di
    WHERE di.id = p_doc_id;
END;
$$;

-- Function: Search documents by title/tags
CREATE OR REPLACE FUNCTION search_documents(
    p_query TEXT,
    p_limit INTEGER DEFAULT 20
)
RETURNS TABLE (
    id TEXT,
    title TEXT,
    document_type TEXT,
    total_pages INTEGER,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        di.id,
        di.title,
        di.document_type,
        di.total_pages,
        similarity(di.title, p_query) AS similarity
    FROM document_index di
    WHERE 
        di.status = 'completed'
        AND (
            di.title ILIKE '%' || p_query || '%'
            OR di.tags @> to_jsonb(p_query)
            OR similarity(di.title, p_query) > 0.3
        )
    ORDER BY similarity DESC
    LIMIT p_limit;
END;
$$;

-- Images table: Store image URLs and GPT-4o-mini descriptions
CREATE TABLE images (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES document_index(id) ON DELETE CASCADE,
    chunk_id TEXT REFERENCES chunks(id) ON DELETE SET NULL,
    page_number INTEGER NOT NULL,
    bbox JSONB,
    
    -- S3 storage (no base64 to keep DB light)
    s3_url TEXT NOT NULL,
    
    -- Free metadata from Docling
    caption TEXT,
    ocr_text TEXT,
    
    -- Tier 1: Basic classification (cheap, generated during ingestion)
    image_type TEXT,
    basic_summary TEXT,
    
    -- Tier 2: Detailed description (expensive, generated on-demand)
    detailed_description TEXT,
    
    -- Cost tracking
    tokens_used INTEGER DEFAULT 0,
    description_generated BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tables table: Store table data and LLM-extracted insights
CREATE TABLE document_tables (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES document_index(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    bbox JSONB,
    
    -- Table data in multiple formats
    raw_html TEXT,
    markdown TEXT NOT NULL,
    structured_data JSONB,
    
    -- Semantic understanding (LLM-generated)
    title TEXT,
    description TEXT NOT NULL,
    key_insights JSONB,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for images
CREATE INDEX images_doc_id_idx ON images(doc_id);
CREATE INDEX images_chunk_id_idx ON images(chunk_id);
CREATE INDEX images_page_idx ON images(page_number);
CREATE INDEX images_basic_summary_search_idx ON images USING GIN(to_tsvector('english', basic_summary));
CREATE INDEX images_detailed_desc_search_idx ON images USING GIN(to_tsvector('english', detailed_description));

-- Indexes for tables
CREATE INDEX tables_doc_id_idx ON document_tables(doc_id);
CREATE INDEX tables_page_idx ON document_tables(page_number);
CREATE INDEX tables_description_search_idx ON document_tables USING GIN(to_tsvector('english', description));

-- Grants
GRANT ALL ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO postgres;

-- Comments
COMMENT ON TABLE chunks IS 'Individual content chunks with embeddings';
COMMENT ON TABLE document_hierarchy IS 'Document structure with section/page organization';
COMMENT ON COLUMN chunks.section_id IS 'Reference to section in hierarchy JSONB';
COMMENT ON COLUMN chunks.parent_section_id IS 'Direct parent section for quick traversal';
COMMENT ON FUNCTION search_chunks IS 'Vector similarity search with filtering';
COMMENT ON FUNCTION get_chunks_by_ids IS 'Batch fetch chunks by ID list';
COMMENT ON FUNCTION get_section_by_chunk_id IS 'Find section containing a specific chunk';
