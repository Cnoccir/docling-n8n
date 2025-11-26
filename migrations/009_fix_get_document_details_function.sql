-- Migration 009: Fix get_document_details function to remove version column
-- The function still references version column which was removed in migration 007

-- Drop the old function
DROP FUNCTION IF EXISTS get_document_details(text);

-- Recreate without version column
CREATE OR REPLACE FUNCTION get_document_details(
    p_doc_id TEXT
)
RETURNS TABLE (
    id TEXT,
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

-- Verify function was created
DO $$
BEGIN
    RAISE NOTICE '✓ get_document_details function updated successfully';
END $$;
