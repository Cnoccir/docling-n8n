-- Migration: Add query analytics and cost tracking
-- Purpose: Track all API queries, their costs, and performance metrics

BEGIN;

-- Create query analytics table
CREATE TABLE IF NOT EXISTS query_analytics (
    id SERIAL PRIMARY KEY,
    query_type TEXT NOT NULL,  -- 'chat', 'semantic_search', 'embedding', etc.
    doc_id TEXT,  -- Reference to document if applicable
    query_text TEXT,
    model_used TEXT,  -- e.g., 'gpt-4o-mini', 'text-embedding-3-small'
    tokens_prompt INTEGER,
    tokens_completion INTEGER,
    tokens_total INTEGER,
    cost_usd DECIMAL(10, 8),
    response_time_ms INTEGER,
    success BOOLEAN DEFAULT true,
    error_message TEXT,
    user_id TEXT,  -- For future multi-user support
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_query_analytics_query_type ON query_analytics(query_type);
CREATE INDEX IF NOT EXISTS idx_query_analytics_doc_id ON query_analytics(doc_id);
CREATE INDEX IF NOT EXISTS idx_query_analytics_created_at ON query_analytics(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_query_analytics_success ON query_analytics(success);

-- Add view for daily cost summary
CREATE OR REPLACE VIEW daily_query_costs AS
SELECT
    DATE(created_at) as date,
    query_type,
    COUNT(*) as query_count,
    SUM(tokens_total) as total_tokens,
    SUM(cost_usd) as total_cost_usd,
    AVG(response_time_ms) as avg_response_time_ms,
    SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful_queries,
    SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) as failed_queries
FROM query_analytics
GROUP BY DATE(created_at), query_type
ORDER BY date DESC, query_type;

-- Add view for overall statistics
CREATE OR REPLACE VIEW query_analytics_summary AS
SELECT
    COUNT(*) as total_queries,
    SUM(tokens_total) as total_tokens_used,
    SUM(cost_usd) as total_cost_usd,
    AVG(cost_usd) as avg_cost_per_query,
    AVG(response_time_ms) as avg_response_time_ms,
    SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful_queries,
    SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) as failed_queries,
    MAX(created_at) as last_query_at
FROM query_analytics;

COMMIT;

-- Example queries:
-- SELECT * FROM daily_query_costs WHERE date = CURRENT_DATE;
-- SELECT * FROM query_analytics_summary;
-- SELECT query_type, SUM(cost_usd) FROM query_analytics GROUP BY query_type;
