-- Migration 011: Add retrieval metrics table
-- Tracks retrieval quality for monitoring and improvement

CREATE TABLE IF NOT EXISTS retrieval_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id TEXT NOT NULL UNIQUE,
    question TEXT NOT NULL,
    doc_id TEXT,
    categories JSONB,  -- Query categories from classifier
    metrics JSONB NOT NULL,  -- Full metrics payload
    created_at TIMESTAMP DEFAULT NOW()
);

-- Index for time-based queries
CREATE INDEX IF NOT EXISTS idx_retrieval_metrics_created
ON retrieval_metrics(created_at DESC);

-- Index for doc_id filtering
CREATE INDEX IF NOT EXISTS idx_retrieval_metrics_doc
ON retrieval_metrics(doc_id);

-- GIN index for categories JSONB
CREATE INDEX IF NOT EXISTS idx_retrieval_metrics_categories
ON retrieval_metrics USING GIN(categories);

-- GIN index for metrics JSONB (for querying specific metrics)
CREATE INDEX IF NOT EXISTS idx_retrieval_metrics_data
ON retrieval_metrics USING GIN(metrics);

COMMENT ON TABLE retrieval_metrics IS 'Tracks retrieval quality metrics for monitoring';
COMMENT ON COLUMN retrieval_metrics.query_id IS 'Unique identifier for this query execution';
COMMENT ON COLUMN retrieval_metrics.categories IS 'Query categories (architecture, graphics, etc.)';
COMMENT ON COLUMN retrieval_metrics.metrics IS 'Full metrics payload: scores, coverage, diversity, etc.';


-- Add helpful views for analysis

-- View: Recent low-coverage queries (potential retrieval issues)
CREATE OR REPLACE VIEW low_coverage_queries AS
SELECT
    query_id,
    question,
    categories,
    (metrics->>'topic_coverage')::float as coverage,
    (metrics->>'avg_score')::float as avg_score,
    created_at
FROM retrieval_metrics
WHERE (metrics->>'topic_coverage')::float < 0.7
ORDER BY created_at DESC;

COMMENT ON VIEW low_coverage_queries IS 'Queries with low topic coverage (< 70%) - potential retrieval issues';


-- View: Daily retrieval quality summary
CREATE OR REPLACE VIEW daily_retrieval_summary AS
SELECT
    DATE(created_at) as date,
    COUNT(*) as total_queries,
    AVG((metrics->>'avg_score')::float) as avg_score,
    AVG((metrics->>'topic_coverage')::float) as avg_coverage,
    AVG((metrics->>'topic_diversity')::float) as avg_diversity
FROM retrieval_metrics
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;

COMMENT ON VIEW daily_retrieval_summary IS 'Daily aggregated retrieval quality metrics';


-- View: Category performance
CREATE OR REPLACE VIEW category_performance AS
SELECT
    category,
    COUNT(*) as query_count,
    AVG((metrics->>'topic_coverage')::float) as avg_coverage,
    AVG((metrics->>'avg_score')::float) as avg_score
FROM retrieval_metrics,
     jsonb_array_elements_text(categories) as category
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY category
ORDER BY query_count DESC;

COMMENT ON VIEW category_performance IS 'Retrieval performance by query category (last 7 days)';
