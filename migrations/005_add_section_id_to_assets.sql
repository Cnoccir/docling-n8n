-- ==================== Section ID Migration ====================
-- Add section_id columns to images and document_tables for hierarchy-based retrieval
-- This enables context expansion to retrieve all images/tables in a section
--
-- Run with: psql $DATABASE_URL -f migrations/005_add_section_id_to_assets.sql
-- =========================================================================

-- ==================== Add section_id to images ====================
ALTER TABLE images ADD COLUMN IF NOT EXISTS section_id VARCHAR(50);

-- Create index for fast section-based lookups
CREATE INDEX IF NOT EXISTS idx_images_section_id ON images(section_id);

-- Add helpful comment
COMMENT ON COLUMN images.section_id IS 'Reference to section in document_hierarchy.hierarchy for context expansion';


-- ==================== Add section_id to document_tables ====================
ALTER TABLE document_tables ADD COLUMN IF NOT EXISTS section_id VARCHAR(50);

-- Create index for fast section-based lookups
CREATE INDEX IF NOT EXISTS idx_tables_section_id ON document_tables(section_id);

-- Add helpful comment
COMMENT ON COLUMN document_tables.section_id IS 'Reference to section in document_hierarchy.hierarchy for context expansion';


-- ==================== Verification ====================
-- Verify columns were added
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'images' AND column_name = 'section_id'
    ) THEN
        RAISE NOTICE '✓ images.section_id column added successfully';
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'document_tables' AND column_name = 'section_id'
    ) THEN
        RAISE NOTICE '✓ document_tables.section_id column added successfully';
    END IF;
END $$;
