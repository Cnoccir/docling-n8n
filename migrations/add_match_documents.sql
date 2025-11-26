-- Migration: Add match_documents function for n8n Supabase Vector Store compatibility
-- This function wraps search_chunks to work with n8n's vector store node

DROP FUNCTION IF EXISTS match_documents(vector(1536), TEXT, FLOAT, INTEGER);

CREATE OR REPLACE FUNCTION match_documents(
    query_embedding vector(1536),
    filter_doc_id TEXT DEFAULT NULL,
    match_threshold FLOAT DEFAULT 0.3,
    match_count INTEGER DEFAULT 10
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
    -- This is a simple wrapper around search_chunks
    -- Returns same structure expected by n8n's Supabase Vector Store node
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
        AND 1 - (c.embedding <=> query_embedding) > match_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

COMMENT ON FUNCTION match_documents IS 'Vector similarity search for n8n Supabase Vector Store. Wrapper around search_chunks.';
