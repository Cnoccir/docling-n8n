-- Migration 010: Add query cache table
-- Caches LLM responses to reduce costs for frequently asked questions

CREATE TABLE IF NOT EXISTS query_cache (
    cache_key TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    doc_id TEXT,
    answer TEXT NOT NULL,
    citations JSONB NOT NULL,
    model_used TEXT DEFAULT 'gpt-4o-mini',
    question_embedding vector(1536),  -- For semantic matching
    created_at TIMESTAMP DEFAULT NOW(),
    last_accessed_at TIMESTAMP DEFAULT NOW(),
    hit_count INTEGER DEFAULT 0
);

-- Index for semantic similarity search
CREATE INDEX IF NOT EXISTS idx_query_cache_embedding
ON query_cache USING ivfflat (question_embedding vector_cosine_ops)
WITH (lists = 100);

-- Index for doc_id filtering
CREATE INDEX IF NOT EXISTS idx_query_cache_doc
ON query_cache(doc_id);

-- Index for created_at (TTL cleanup)
CREATE INDEX IF NOT EXISTS idx_query_cache_created
ON query_cache(created_at DESC);

-- Index for hit_count (popular queries)
CREATE INDEX IF NOT EXISTS idx_query_cache_hits
ON query_cache(hit_count DESC);

COMMENT ON TABLE query_cache IS 'Caches LLM responses for frequently asked questions';
COMMENT ON COLUMN query_cache.cache_key IS 'SHA256 hash of normalized question + doc_id';
COMMENT ON COLUMN query_cache.question_embedding IS 'Embedding vector for semantic cache matching';
COMMENT ON COLUMN query_cache.hit_count IS 'Number of times this cached answer was reused';
