-- ==================== Full-Text Search Migration ====================
-- This migration adds FTS capabilities to chunks, images, and tables
-- for keyword-based search alongside vector similarity search
--
-- Run with: psql $DATABASE_URL -f migrations/002_add_fts_indexes.sql
-- =========================================================================

-- ==================== Chunks FTS ====================
-- Add FTS column and index for chunk content + section paths

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS fts tsvector;

-- Create GIN index for fast FTS queries
CREATE INDEX IF NOT EXISTS idx_chunks_fts ON chunks USING GIN (fts);

-- Function to update FTS column
CREATE OR REPLACE FUNCTION chunks_fts_update() RETURNS trigger AS $$
BEGIN
  -- Include content and section_path array (converted to string) for search
  NEW.fts := to_tsvector('english', 
    coalesce(NEW.content, '') || ' ' || 
    coalesce(array_to_string(NEW.section_path, ' '), '')
  );
  RETURN NEW;
END
$$ LANGUAGE plpgsql;

-- Trigger to auto-update FTS on insert/update
DROP TRIGGER IF EXISTS trg_chunks_fts ON chunks;
CREATE TRIGGER trg_chunks_fts 
  BEFORE INSERT OR UPDATE ON chunks
  FOR EACH ROW EXECUTE FUNCTION chunks_fts_update();

-- Backfill existing rows
UPDATE chunks SET fts = to_tsvector('english', 
  coalesce(content, '') || ' ' || 
  coalesce(array_to_string(section_path, ' '), '')
);

COMMENT ON COLUMN chunks.fts IS 'Full-text search vector for chunk content and section path';


-- ==================== Images FTS ====================
-- Add FTS for image descriptions (basic_summary + detailed_description)

ALTER TABLE images ADD COLUMN IF NOT EXISTS description_fts tsvector;

CREATE INDEX IF NOT EXISTS idx_images_description_fts ON images USING GIN (description_fts);

CREATE OR REPLACE FUNCTION images_fts_update() RETURNS trigger AS $$
BEGIN
  NEW.description_fts := to_tsvector('english', 
    coalesce(NEW.basic_summary, '') || ' ' || 
    coalesce(NEW.detailed_description, '') || ' ' ||
    coalesce(NEW.caption, '')
  );
  RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_images_fts ON images;
CREATE TRIGGER trg_images_fts 
  BEFORE INSERT OR UPDATE ON images
  FOR EACH ROW EXECUTE FUNCTION images_fts_update();

-- Backfill existing rows
UPDATE images SET description_fts = to_tsvector('english', 
  coalesce(basic_summary, '') || ' ' || 
  coalesce(detailed_description, '') || ' ' ||
  coalesce(caption, '')
);

COMMENT ON COLUMN images.description_fts IS 'Full-text search vector for image descriptions and captions';


-- ==================== Tables FTS ====================
-- Add FTS for table descriptions and key insights

ALTER TABLE document_tables ADD COLUMN IF NOT EXISTS description_fts tsvector;
ALTER TABLE document_tables ADD COLUMN IF NOT EXISTS key_insights_fts tsvector;

CREATE INDEX IF NOT EXISTS idx_tables_description_fts ON document_tables USING GIN (description_fts);
CREATE INDEX IF NOT EXISTS idx_tables_key_insights_fts ON document_tables USING GIN (key_insights_fts);

CREATE OR REPLACE FUNCTION tables_fts_update() RETURNS trigger AS $$
BEGIN
  NEW.description_fts := to_tsvector('english', coalesce(NEW.description, ''));
  -- key_insights is JSONB array, convert to text
  NEW.key_insights_fts := to_tsvector('english', coalesce(NEW.key_insights::text, ''));
  RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tables_fts ON document_tables;
CREATE TRIGGER trg_tables_fts 
  BEFORE INSERT OR UPDATE ON document_tables
  FOR EACH ROW EXECUTE FUNCTION tables_fts_update();

-- Backfill existing rows
UPDATE document_tables SET 
  description_fts = to_tsvector('english', coalesce(description, '')),
  key_insights_fts = to_tsvector('english', coalesce(key_insights::text, ''));

COMMENT ON COLUMN document_tables.description_fts IS 'Full-text search vector for table descriptions';
COMMENT ON COLUMN document_tables.key_insights_fts IS 'Full-text search vector for table key insights';


-- ==================== Keyword Search Functions ====================

-- Search chunks by keyword with optional doc_id filter
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

COMMENT ON FUNCTION search_chunks_keyword IS 'Keyword search over chunks with FTS ranking';


-- Search images by keyword
CREATE OR REPLACE FUNCTION search_images_keyword(
  p_query text,
  p_doc_id text DEFAULT NULL,
  p_limit integer DEFAULT 10
)
RETURNS TABLE (
  id text,
  doc_id text,
  page_number integer,
  s3_url text,
  caption text,
  basic_summary text,
  rank real
) AS $$
BEGIN
  RETURN QUERY
  SELECT 
    i.id,
    i.doc_id,
    i.page_number,
    i.s3_url,
    i.caption,
    i.basic_summary,
    ts_rank(i.description_fts, websearch_to_tsquery('english', p_query)) AS rank
  FROM images i
  WHERE 
    i.description_fts @@ websearch_to_tsquery('english', p_query)
    AND (p_doc_id IS NULL OR i.doc_id = p_doc_id)
  ORDER BY rank DESC
  LIMIT p_limit;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION search_images_keyword IS 'Keyword search over image descriptions';


-- Search tables by keyword
CREATE OR REPLACE FUNCTION search_tables_keyword(
  p_query text,
  p_doc_id text DEFAULT NULL,
  p_limit integer DEFAULT 10
)
RETURNS TABLE (
  id text,
  doc_id text,
  page_number integer,
  markdown text,
  description text,
  key_insights jsonb,
  rank real
) AS $$
BEGIN
  RETURN QUERY
  SELECT 
    t.id,
    t.doc_id,
    t.page_number,
    t.markdown,
    t.description,
    t.key_insights,
    ts_rank(t.description_fts, websearch_to_tsquery('english', p_query)) AS rank
  FROM document_tables t
  WHERE 
    t.description_fts @@ websearch_to_tsquery('english', p_query)
    AND (p_doc_id IS NULL OR t.doc_id = p_doc_id)
  ORDER BY rank DESC
  LIMIT p_limit;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION search_tables_keyword IS 'Keyword search over table descriptions and insights';


-- ==================== Verification ====================

-- Test keyword search
DO $$
BEGIN
  RAISE NOTICE 'FTS indexes created successfully';
  RAISE NOTICE 'Chunks with FTS: %', (SELECT count(*) FROM chunks WHERE fts IS NOT NULL);
  RAISE NOTICE 'Images with FTS: %', (SELECT count(*) FROM images WHERE description_fts IS NOT NULL);
  RAISE NOTICE 'Tables with FTS: %', (SELECT count(*) FROM document_tables WHERE description_fts IS NOT NULL);
END $$;
