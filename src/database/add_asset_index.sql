-- Migration: Add asset_index to document_hierarchy

-- Add asset_index column
ALTER TABLE document_hierarchy 
ADD COLUMN IF NOT EXISTS asset_index JSONB DEFAULT '{}'::jsonb;

-- Create GIN index for asset_index queries
CREATE INDEX IF NOT EXISTS hierarchy_asset_index_idx 
ON document_hierarchy USING GIN(asset_index);

-- Comment
COMMENT ON COLUMN document_hierarchy.asset_index IS 'Asset tracking index with images and tables mapped to sections';
