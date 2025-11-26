-- Migration 006: Update document_index table for versioning support
-- This migration changes the primary key from (id) to (id, version) to support document reprocessing

-- Step 1: Check if version column exists, if not add it
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'document_index' AND column_name = 'version'
    ) THEN
        ALTER TABLE document_index ADD COLUMN version INTEGER DEFAULT 1 NOT NULL;
        COMMENT ON COLUMN document_index.version IS 'Version number for document reprocessing (v1, v2, v3, etc.)';
    END IF;
END $$;

-- Step 2: Drop foreign key constraints that depend on document_index primary key
ALTER TABLE chunks DROP CONSTRAINT IF EXISTS chunks_doc_id_fkey;
ALTER TABLE document_hierarchy DROP CONSTRAINT IF EXISTS document_hierarchy_doc_id_fkey;
ALTER TABLE images DROP CONSTRAINT IF EXISTS images_doc_id_fkey;
ALTER TABLE document_tables DROP CONSTRAINT IF EXISTS document_tables_doc_id_fkey;
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_doc_id_fkey;

-- Step 3: Drop the existing primary key constraint with CASCADE
ALTER TABLE document_index DROP CONSTRAINT IF EXISTS document_index_pkey CASCADE;

-- Step 4: Add composite primary key on (id, version)
ALTER TABLE document_index ADD PRIMARY KEY (id, version);

-- Step 5: Create regular (non-unique) indexes on related tables for query performance
-- Note: We don't recreate foreign key constraints because:
-- - Multiple versions can have the same id (e.g., Study_Guide-BQL_v1, v2, v3)
-- - Foreign keys require unique constraint on referenced column
-- - Indexes provide query performance without uniqueness constraint
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_document_hierarchy_doc_id ON document_hierarchy(doc_id);
CREATE INDEX IF NOT EXISTS idx_images_doc_id ON images(doc_id);
CREATE INDEX IF NOT EXISTS idx_document_tables_doc_id ON document_tables(doc_id);
CREATE INDEX IF NOT EXISTS idx_jobs_doc_id ON jobs(doc_id);

-- Step 7: Create index on file_hash for duplicate detection (if not exists)
CREATE INDEX IF NOT EXISTS idx_document_index_file_hash ON document_index(file_hash);

-- Step 5: Create index on (id, version DESC) for getting latest version quickly
CREATE INDEX IF NOT EXISTS idx_document_index_id_version ON document_index(id, version DESC);

-- Step 6: Add comments
COMMENT ON TABLE document_index IS 'Document metadata and processing status. Supports multiple versions of same document via composite primary key (id, version).';
COMMENT ON CONSTRAINT document_index_pkey ON document_index IS 'Composite primary key allowing multiple versions of same document';

-- Step 7: Update check_document_exists query to return latest version
-- This is handled in the db_client.py code which already has:
-- SELECT id, version, title, status FROM document_index WHERE file_hash = %s ORDER BY version DESC LIMIT 1
