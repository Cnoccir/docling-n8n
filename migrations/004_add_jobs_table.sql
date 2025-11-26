-- Migration 004: Add jobs table for task tracking
-- This enables queue management, progress tracking, and job control

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    task_id TEXT UNIQUE,  -- Celery task ID
    doc_id TEXT REFERENCES document_index(id) ON DELETE SET NULL,
    
    -- File information
    filename TEXT NOT NULL,
    file_path TEXT,  -- Temporary upload path
    file_size_bytes BIGINT,
    
    -- Status tracking
    status TEXT DEFAULT 'queued' CHECK (status IN (
        'queued', 'processing', 'completed', 'failed', 'cancelled', 'paused'
    )),
    progress INTEGER DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
    current_step TEXT,  -- 'parsing', 'images', 'tables', 'embeddings', 'saving'
    
    -- Timing
    queued_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    estimated_duration_seconds INTEGER,
    actual_duration_seconds INTEGER,
    
    -- Results
    error_message TEXT,
    error_traceback TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    
    -- Metadata
    priority INTEGER DEFAULT 0,  -- Higher = process first
    worker_id TEXT,
    
    -- Processing stats (populated on completion)
    total_pages INTEGER,
    total_chunks INTEGER,
    total_images INTEGER,
    total_tables INTEGER,
    tokens_used INTEGER,
    ingestion_cost_usd FLOAT,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs(status);
CREATE INDEX IF NOT EXISTS jobs_queued_at_idx ON jobs(queued_at DESC);
CREATE INDEX IF NOT EXISTS jobs_priority_idx ON jobs(priority DESC, queued_at ASC);
CREATE INDEX IF NOT EXISTS jobs_task_id_idx ON jobs(task_id);
CREATE INDEX IF NOT EXISTS jobs_doc_id_idx ON jobs(doc_id);
CREATE INDEX IF NOT EXISTS jobs_worker_id_idx ON jobs(worker_id);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_jobs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update updated_at
DROP TRIGGER IF EXISTS jobs_updated_at_trigger ON jobs;
CREATE TRIGGER jobs_updated_at_trigger
    BEFORE UPDATE ON jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_jobs_updated_at();

-- Function to calculate actual duration on completion
CREATE OR REPLACE FUNCTION calculate_job_duration()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status IN ('completed', 'failed', 'cancelled') AND NEW.started_at IS NOT NULL THEN
        NEW.actual_duration_seconds = EXTRACT(EPOCH FROM (NEW.completed_at - NEW.started_at))::INTEGER;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to calculate duration
DROP TRIGGER IF EXISTS jobs_duration_trigger ON jobs;
CREATE TRIGGER jobs_duration_trigger
    BEFORE UPDATE ON jobs
    FOR EACH ROW
    WHEN (NEW.completed_at IS NOT NULL)
    EXECUTE FUNCTION calculate_job_duration();

-- Function to get queue statistics
CREATE OR REPLACE FUNCTION get_queue_stats()
RETURNS TABLE (
    total_jobs BIGINT,
    queued_jobs BIGINT,
    processing_jobs BIGINT,
    completed_jobs BIGINT,
    failed_jobs BIGINT,
    cancelled_jobs BIGINT,
    avg_duration_seconds FLOAT,
    total_cost_usd FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*)::BIGINT as total_jobs,
        COUNT(*) FILTER (WHERE status = 'queued')::BIGINT as queued_jobs,
        COUNT(*) FILTER (WHERE status = 'processing')::BIGINT as processing_jobs,
        COUNT(*) FILTER (WHERE status = 'completed')::BIGINT as completed_jobs,
        COUNT(*) FILTER (WHERE status = 'failed')::BIGINT as failed_jobs,
        COUNT(*) FILTER (WHERE status = 'cancelled')::BIGINT as cancelled_jobs,
        AVG(actual_duration_seconds)::FLOAT as avg_duration_seconds,
        SUM(ingestion_cost_usd)::FLOAT as total_cost_usd
    FROM jobs;
END;
$$ LANGUAGE plpgsql;

-- Function to get active workers
CREATE OR REPLACE FUNCTION get_active_workers()
RETURNS TABLE (
    worker_id TEXT,
    current_job_id TEXT,
    current_filename TEXT,
    job_progress INTEGER,
    started_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        j.worker_id,
        j.id as current_job_id,
        j.filename as current_filename,
        j.progress as job_progress,
        j.started_at
    FROM jobs j
    WHERE j.status = 'processing'
        AND j.worker_id IS NOT NULL
    ORDER BY j.started_at ASC;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions
GRANT ALL ON TABLE jobs TO postgres;
GRANT EXECUTE ON FUNCTION get_queue_stats() TO postgres;
GRANT EXECUTE ON FUNCTION get_active_workers() TO postgres;

-- Comments
COMMENT ON TABLE jobs IS 'Task queue for document ingestion jobs';
COMMENT ON COLUMN jobs.task_id IS 'Celery task ID for controlling the job';
COMMENT ON COLUMN jobs.priority IS 'Higher values are processed first';
COMMENT ON COLUMN jobs.current_step IS 'Current processing step for progress display';
COMMENT ON FUNCTION get_queue_stats IS 'Get overall queue statistics';
COMMENT ON FUNCTION get_active_workers IS 'Get currently active workers and their jobs';
