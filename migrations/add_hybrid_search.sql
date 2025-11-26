-- Migration: Add Hybrid Search (Full-Text + Semantic)
-- This migration adds content_tsv column and hybrid search function
-- WITHOUT dropping existing data

-- Drop hybrid search function if exists
DROP FUNCTION IF EXISTS search_chunks_hybrid(vector, TEXT, TEXT, FLOAT, FLOAT, FLOAT, INTEGER);

-- Add content_tsv column if it doesn't exist (GENERATED column automatically populates)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'chunks' AND column_name = 'content_tsv'
    ) THEN
        ALTER TABLE chunks 
        ADD COLUMN content_tsv tsvector 
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
        
        RAISE NOTICE 'Added content_tsv column to chunks table';
    ELSE
        RAISE NOTICE 'content_tsv column already exists';
    END IF;
END $$;

-- Create GIN index for full-text search
CREATE INDEX IF NOT EXISTS chunks_content_tsv_idx ON chunks USING GIN(content_tsv);

-- Create hybrid search function
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
