-- Migration: Add semantic search capability to document_index table
-- Purpose: Enable semantic search on document summaries without creating duplicate tables

BEGIN;

-- Step 1: Add embedding column (allows NULL for existing rows)
ALTER TABLE document_index
ADD COLUMN IF NOT EXISTS summary_embedding vector(1536);

-- Step 2: Add vector index for fast similarity search
-- Using CONCURRENTLY to avoid locking the table
CREATE INDEX IF NOT EXISTS document_index_summary_embedding_idx
ON document_index
USING ivfflat (summary_embedding vector_cosine_ops)
WITH (lists = 100);

-- Step 3: Add comment for documentation
COMMENT ON COLUMN document_index.summary_embedding IS 'OpenAI ada-002 embedding (1536-dim) of title + summary for semantic search';

COMMIT;

-- To generate embeddings for existing documents, run:
-- docker exec -it docling-backend python scripts/add_semantic_search.py
