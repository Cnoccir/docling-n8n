-- Add Google Drive fields to document_index table
-- Migration: add_gdrive_fields
-- Date: 2025-11-17

ALTER TABLE document_index
ADD COLUMN IF NOT EXISTS gdrive_file_id TEXT,
ADD COLUMN IF NOT EXISTS gdrive_link TEXT,
ADD COLUMN IF NOT EXISTS gdrive_folder_id TEXT;

-- Add index for faster lookups
CREATE INDEX IF NOT EXISTS idx_gdrive_file_id ON document_index(gdrive_file_id);

-- Add comments for documentation
COMMENT ON COLUMN document_index.gdrive_file_id IS 'Google Drive file ID for the source PDF';
COMMENT ON COLUMN document_index.gdrive_link IS 'Direct link to Google Drive file (webViewLink)';
COMMENT ON COLUMN document_index.gdrive_folder_id IS 'Google Drive folder ID where file is stored';
