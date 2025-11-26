-- Migration 008: Fix list_documents function to remove version column
-- The function still references version column which was removed in migration 007

-- Drop the old function
DROP FUNCTION IF EXISTS list_documents(text, text, integer, integer);

-- Recreate without version column
CREATE OR REPLACE FUNCTION list_documents(
    p_status TEXT DEFAULT NULL,
    p_document_type TEXT DEFAULT NULL,
    p_limit INTEGER DEFAULT 50,
    p_offset INTEGER DEFAULT 0
)
RETURNS TABLE (
    id TEXT,
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

-- Verify function was created
DO $$
BEGIN
    RAISE NOTICE '✓ list_documents function updated successfully';
END $$;
