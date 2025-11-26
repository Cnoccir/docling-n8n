-- Migration 012: Add YouTube and Multi-Source Support
-- Extends existing tables to support video content alongside PDFs

-- ============================================================
-- 1. EXTEND DOCUMENT_INDEX for multi-source content
-- ============================================================

-- Add source type (pdf, youtube, audio, webpage, etc.)
ALTER TABLE document_index
ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT 'pdf';

-- Add source URL (YouTube URL, web page URL, etc.)
ALTER TABLE document_index
ADD COLUMN IF NOT EXISTS source_url TEXT;

-- Video-specific metadata
ALTER TABLE document_index
ADD COLUMN IF NOT EXISTS duration_seconds INTEGER;

ALTER TABLE document_index
ADD COLUMN IF NOT EXISTS youtube_id TEXT;

ALTER TABLE document_index
ADD COLUMN IF NOT EXISTS channel_name TEXT;

ALTER TABLE document_index
ADD COLUMN IF NOT EXISTS playlist_id TEXT;

ALTER TABLE document_index
ADD COLUMN IF NOT EXISTS series_index INTEGER;

-- Create index for source type filtering
CREATE INDEX IF NOT EXISTS idx_document_index_source_type
ON document_index(source_type);

CREATE INDEX IF NOT EXISTS idx_document_index_youtube_id
ON document_index(youtube_id)
WHERE youtube_id IS NOT NULL;

-- ============================================================
-- 2. EXTEND CHUNKS for timestamp support
-- ============================================================

-- Add timestamp fields for video content
ALTER TABLE chunks
ADD COLUMN IF NOT EXISTS timestamp_start FLOAT;

ALTER TABLE chunks
ADD COLUMN IF NOT EXISTS timestamp_end FLOAT;

-- Pre-computed video URL with timestamp (for citations)
ALTER TABLE chunks
ADD COLUMN IF NOT EXISTS video_url_with_timestamp TEXT;

-- Create index for timestamp-based queries
CREATE INDEX IF NOT EXISTS idx_chunks_timestamp
ON chunks(timestamp_start, timestamp_end)
WHERE timestamp_start IS NOT NULL;

-- ============================================================
-- 3. EXTEND IMAGES for video screenshots
-- ============================================================

-- Add timestamp for video screenshots
ALTER TABLE images
ADD COLUMN IF NOT EXISTS timestamp FLOAT;

-- Scene classification for videos (slide, code, diagram, demo)
ALTER TABLE images
ADD COLUMN IF NOT EXISTS scene_type TEXT;

-- Create index for timestamp-based image retrieval
CREATE INDEX IF NOT EXISTS idx_images_timestamp
ON images(timestamp)
WHERE timestamp IS NOT NULL;

-- ============================================================
-- 4. UPDATE EXISTING FUNCTIONS to support source_type
-- ============================================================

-- Drop existing function to recreate with source_type support
DROP FUNCTION IF EXISTS list_documents(TEXT, TEXT, INTEGER, INTEGER);

-- Recreated list_documents with source_type filter
CREATE OR REPLACE FUNCTION list_documents(
    p_status TEXT DEFAULT NULL,
    p_document_type TEXT DEFAULT NULL,
    p_source_type TEXT DEFAULT NULL,  -- NEW PARAMETER
    p_limit INTEGER DEFAULT 50,
    p_offset INTEGER DEFAULT 0
)
RETURNS TABLE(
    id TEXT,
    title TEXT,
    filename TEXT,
    status TEXT,
    document_type TEXT,
    source_type TEXT,
    source_url TEXT,
    youtube_id TEXT,
    channel_name TEXT,
    duration_seconds INTEGER,
    total_pages INTEGER,
    total_chunks INTEGER,
    total_images INTEGER,
    total_tables INTEGER,
    summary TEXT,
    tags JSONB,
    categories JSONB,
    created_at TIMESTAMP WITH TIME ZONE,
    processed_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id,
        d.title,
        d.filename,
        d.status,
        d.document_type,
        d.source_type,
        d.source_url,
        d.youtube_id,
        d.channel_name,
        d.duration_seconds,
        d.total_pages,
        d.total_chunks,
        d.total_images,
        d.total_tables,
        d.summary,
        d.tags,
        d.categories,
        d.created_at,
        d.processed_at
    FROM document_index d
    WHERE
        (p_status IS NULL OR d.status = p_status)
        AND (p_document_type IS NULL OR d.document_type = p_document_type)
        AND (p_source_type IS NULL OR d.source_type = p_source_type)
    ORDER BY d.created_at DESC
    LIMIT p_limit
    OFFSET p_offset;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 5. NEW FUNCTION: Search across multiple source types
-- ============================================================

CREATE OR REPLACE FUNCTION search_chunks_multi_source(
    p_query_embedding vector(1536),
    p_query_text TEXT,
    p_source_types TEXT[] DEFAULT ARRAY['pdf', 'youtube'],
    p_doc_ids TEXT[] DEFAULT NULL,
    p_semantic_weight FLOAT DEFAULT 0.5,
    p_keyword_weight FLOAT DEFAULT 0.5,
    p_top_k INTEGER DEFAULT 15
)
RETURNS TABLE(
    chunk_id TEXT,
    doc_id TEXT,
    doc_title TEXT,
    source_type TEXT,
    content TEXT,
    page_number INTEGER,
    timestamp_start FLOAT,
    timestamp_end FLOAT,
    video_url_with_timestamp TEXT,
    section_path TEXT[],
    combined_score FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id AS chunk_id,
        c.doc_id,
        d.title AS doc_title,
        d.source_type,
        c.content,
        c.page_number,
        c.timestamp_start,
        c.timestamp_end,
        c.video_url_with_timestamp,
        c.section_path,
        (
            (p_semantic_weight * (1 - (c.embedding <=> p_query_embedding))) +
            (p_keyword_weight * ts_rank(c.content_tsv, plainto_tsquery('english', p_query_text)))
        ) AS combined_score
    FROM chunks c
    JOIN document_index d ON c.doc_id = d.id
    WHERE
        d.status = 'completed'
        AND (p_source_types IS NULL OR d.source_type = ANY(p_source_types))
        AND (p_doc_ids IS NULL OR c.doc_id = ANY(p_doc_ids))
    ORDER BY combined_score DESC
    LIMIT p_top_k;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 6. NEW FUNCTION: Get video transcript with timestamps
-- ============================================================

CREATE OR REPLACE FUNCTION get_video_transcript(
    p_video_id TEXT
)
RETURNS TABLE(
    chunk_id TEXT,
    timestamp_start FLOAT,
    timestamp_end FLOAT,
    timestamp_formatted TEXT,
    content TEXT,
    video_url TEXT,
    section_path TEXT[]
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id AS chunk_id,
        c.timestamp_start,
        c.timestamp_end,
        -- Format timestamp as MM:SS
        (FLOOR(c.timestamp_start / 60)::TEXT || ':' ||
         LPAD(FLOOR(c.timestamp_start % 60)::TEXT, 2, '0')) AS timestamp_formatted,
        c.content,
        c.video_url_with_timestamp AS video_url,
        c.section_path
    FROM chunks c
    JOIN document_index d ON c.doc_id = d.id
    WHERE
        d.id = p_video_id
        AND d.source_type = 'youtube'
    ORDER BY c.timestamp_start;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 7. NEW FUNCTION: Get screenshots for video timestamp range
-- ============================================================

CREATE OR REPLACE FUNCTION get_video_screenshots(
    p_video_id TEXT,
    p_start_time FLOAT DEFAULT NULL,
    p_end_time FLOAT DEFAULT NULL
)
RETURNS TABLE(
    image_id TEXT,
    timestamp FLOAT,
    timestamp_formatted TEXT,
    s3_url TEXT,
    caption TEXT,
    scene_type TEXT,
    ocr_text TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        i.id AS image_id,
        i.timestamp,
        (FLOOR(i.timestamp / 60)::TEXT || ':' ||
         LPAD(FLOOR(i.timestamp % 60)::TEXT, 2, '0')) AS timestamp_formatted,
        i.s3_url,
        i.caption,
        i.scene_type,
        i.ocr_text
    FROM images i
    WHERE
        i.doc_id = p_video_id
        AND (p_start_time IS NULL OR i.timestamp >= p_start_time)
        AND (p_end_time IS NULL OR i.timestamp <= p_end_time)
    ORDER BY i.timestamp;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 8. COMMENTS for documentation
-- ============================================================

COMMENT ON COLUMN document_index.source_type IS
'Type of content source: pdf, youtube, audio, webpage, etc.';

COMMENT ON COLUMN document_index.source_url IS
'Original URL of the content (YouTube URL, web page URL, etc.)';

COMMENT ON COLUMN document_index.duration_seconds IS
'Duration in seconds for video/audio content';

COMMENT ON COLUMN chunks.timestamp_start IS
'Start timestamp in seconds for video/audio chunks';

COMMENT ON COLUMN chunks.timestamp_end IS
'End timestamp in seconds for video/audio chunks';

COMMENT ON COLUMN images.timestamp IS
'Timestamp in seconds for video screenshots';

COMMENT ON COLUMN images.scene_type IS
'Type of scene in video: slide, code, diagram, demo, etc.';

-- ============================================================
-- 9. VERIFICATION QUERIES
-- ============================================================

-- Verify columns were added
DO $$
DECLARE
    missing_columns TEXT[];
BEGIN
    SELECT array_agg(column_name)
    INTO missing_columns
    FROM (
        SELECT 'source_type' AS column_name
        UNION SELECT 'source_url'
        UNION SELECT 'youtube_id'
        UNION SELECT 'duration_seconds'
    ) expected
    WHERE NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'document_index'
        AND column_name = expected.column_name
    );

    IF array_length(missing_columns, 1) > 0 THEN
        RAISE EXCEPTION 'Missing columns in document_index: %', missing_columns;
    END IF;

    RAISE NOTICE '✓ All columns added successfully to document_index';
END $$;

-- Test the new functions
DO $$
BEGIN
    RAISE NOTICE '✓ Testing new functions...';

    -- Test list_documents with source_type
    PERFORM list_documents(NULL, NULL, 'pdf', 1, 0);
    RAISE NOTICE '  ✓ list_documents() works';

    -- Test search_chunks_multi_source
    PERFORM search_chunks_multi_source(
        ARRAY[0.1]::vector(1536),
        'test',
        ARRAY['pdf'],
        NULL,
        0.5,
        0.5,
        5
    );
    RAISE NOTICE '  ✓ search_chunks_multi_source() works';

    RAISE NOTICE '✓ Migration 012 completed successfully!';
END $$;
