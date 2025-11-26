-- Update search functions to include metadata and section_path
-- Run with: psql $DATABASE_URL -f migrations/003_update_search_functions.sql

-- Drop existing functions
DROP FUNCTION IF EXISTS search_chunks(vector, text, double precision, integer);
DROP FUNCTION IF EXISTS search_chunks_keyword(text, text, integer);

-- Update vector search function
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

-- Update FTS search function  
CREATE OR REPLACE FUNCTION search_chunks_keyword(
  p_query text,
  p_doc_id text DEFAULT NULL,
  p_limit integer DEFAULT 20
)
RETURNS TABLE (
  id text,
  doc_id text,
  content text,
  page_number integer,
  section_id text,
  section_path text[],
  metadata jsonb,
  rank real
) AS $$
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
    ts_rank(c.fts, websearch_to_tsquery('english', p_query)) AS rank
  FROM chunks c
  WHERE 
    c.fts @@ websearch_to_tsquery('english', p_query)
    AND (p_doc_id IS NULL OR c.doc_id = p_doc_id)
  ORDER BY rank DESC
  LIMIT p_limit;
END;
$$ LANGUAGE plpgsql STABLE;

-- Verification
DO $$
BEGIN
  RAISE NOTICE 'Search functions updated with metadata and section_path support';
END $$;
