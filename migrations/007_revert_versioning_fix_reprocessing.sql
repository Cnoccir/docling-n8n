-- Migration 007: Revert versioning and fix reprocessing
-- This migration reverts the versioning approach and implements proper delete-and-reprocess
--
-- Run with: psql $DATABASE_URL -f migrations/007_revert_versioning_fix_reprocessing.sql
-- =================================================================================

-- Step 1: Delete duplicate document entries (keep only latest version per id)
-- This cleans up the mess from the versioning approach
DELETE FROM document_index
WHERE (id, version) NOT IN (
    SELECT id, MAX(version)
    FROM document_index
    GROUP BY id
);

-- Step 2: Drop the composite primary key
ALTER TABLE document_index DROP CONSTRAINT IF EXISTS document_index_pkey;

-- Step 3: Drop the version column (no longer needed)
ALTER TABLE document_index DROP COLUMN IF EXISTS version;

-- Step 4: Re-add simple primary key on just 'id'
ALTER TABLE document_index ADD PRIMARY KEY (id);

-- Step 5: Drop the version-related index (no longer needed)
DROP INDEX IF EXISTS idx_document_index_id_version;

-- Step 6: Add comment explaining reprocessing behavior
COMMENT ON TABLE document_index IS 'Document metadata and processing status. When reprocessing (reprocess=true), the entire document and all related data (chunks, images, tables, hierarchy) are DELETED before reprocessing.';

-- Step 7: Verification
DO $$
BEGIN
    -- Check that primary key is back to just (id)
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = 'document_index'
          AND tc.constraint_type = 'PRIMARY KEY'
          AND kcu.column_name = 'id'
    ) THEN
        RAISE NOTICE '✓ Primary key restored to (id) only';
    END IF;

    -- Check that version column is gone
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'document_index' AND column_name = 'version'
    ) THEN
        RAISE NOTICE '✓ Version column removed';
    END IF;
END $$;
