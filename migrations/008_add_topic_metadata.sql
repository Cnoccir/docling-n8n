-- Migration 008: Add topic metadata for topic-aware retrieval
-- Purpose: Enable filtering and boosting chunks by semantic topics
-- Date: 2024-11-29
-- Phase: Phase 2 of retrieval improvements

-- Add topic columns to chunks table
ALTER TABLE chunks 
ADD COLUMN IF NOT EXISTS topic TEXT,
ADD COLUMN IF NOT EXISTS topics TEXT[] DEFAULT '{}';

-- Add indexes for fast topic filtering
CREATE INDEX IF NOT EXISTS chunks_topic_idx ON chunks(topic);
CREATE INDEX IF NOT EXISTS chunks_topics_idx ON chunks USING GIN(topics);

-- Add topic columns to images and tables for consistency
ALTER TABLE images 
ADD COLUMN IF NOT EXISTS topic TEXT,
ADD COLUMN IF NOT EXISTS topics TEXT[] DEFAULT '{}';

ALTER TABLE document_tables 
ADD COLUMN IF NOT EXISTS topic TEXT,
ADD COLUMN IF NOT EXISTS topics TEXT[] DEFAULT '{}';

-- Indexes for images and tables
CREATE INDEX IF NOT EXISTS images_topic_idx ON images(topic);
CREATE INDEX IF NOT EXISTS images_topics_idx ON images USING GIN(topics);
CREATE INDEX IF NOT EXISTS document_tables_topic_idx ON document_tables(topic);
CREATE INDEX IF NOT EXISTS document_tables_topics_idx ON document_tables USING GIN(topics);

-- Comments
COMMENT ON COLUMN chunks.topic IS 'Primary topic classification (e.g., system_database, graphics, provisioning)';
COMMENT ON COLUMN chunks.topics IS 'Array of all applicable topics for multi-label classification';
COMMENT ON COLUMN images.topic IS 'Primary topic classification for image';
COMMENT ON COLUMN images.topics IS 'Multi-label topics for image';
COMMENT ON COLUMN document_tables.topic IS 'Primary topic classification for table';
COMMENT ON COLUMN document_tables.topics IS 'Multi-label topics for table';

-- Verify migration
DO $$
BEGIN
    -- Check if columns were added
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'chunks' AND column_name = 'topics'
    ) THEN
        RAISE NOTICE '✅ Migration 008 completed successfully';
        RAISE NOTICE 'Topic metadata columns added to chunks, images, and document_tables';
    ELSE
        RAISE EXCEPTION '❌ Migration 008 failed: topics column not found';
    END IF;
END $$;
