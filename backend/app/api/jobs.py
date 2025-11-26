"""Jobs API endpoints - Queue management."""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from database.db_client import DatabaseClient
from app.models.schemas import JobResponse, JobListResponse, QueueStats, WorkerInfo
from app.tasks.celery_app import celery_app
from app.tasks.ingest import process_document
from app.utils.checkpoint import ProcessingCheckpoint

router = APIRouter()


@router.get("/", response_model=JobListResponse)
def list_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    """
    List all jobs with filtering and pagination.
    
    Args:
        status: Filter by status (queued, processing, completed, failed, cancelled)
        page: Page number (1-indexed)
        page_size: Items per page
    """
    db = DatabaseClient()
    offset = (page - 1) * page_size
    
    try:
        with db:
            with db.conn.cursor() as cur:
                # Build query
                where_clause = ""
                params = []
                if status:
                    where_clause = "WHERE status = %s"
                    params.append(status)
                
                # Get total count
                count_query = f"SELECT COUNT(*) FROM jobs {where_clause}"
                cur.execute(count_query, params)
                total = cur.fetchone()[0]
                
                # Get jobs
                query = f"""
                    SELECT 
                        id, task_id, doc_id, filename, status, progress, 
                        current_step, queued_at, started_at, completed_at,
                        estimated_duration_seconds, actual_duration_seconds,
                        error_message, worker_id, total_pages, total_chunks,
                        total_images, total_tables, tokens_used, ingestion_cost_usd
                    FROM jobs
                    {where_clause}
                    ORDER BY queued_at DESC
                    LIMIT %s OFFSET %s
                """
                cur.execute(query, params + [page_size, offset])
                
                jobs = []
                for row in cur.fetchall():
                    jobs.append(JobResponse(
                        id=row[0],
                        task_id=row[1],
                        doc_id=row[2],
                        filename=row[3],
                        status=row[4],
                        progress=row[5],
                        current_step=row[6],
                        queued_at=row[7],
                        started_at=row[8],
                        completed_at=row[9],
                        estimated_duration_seconds=row[10],
                        actual_duration_seconds=row[11],
                        error_message=row[12],
                        worker_id=row[13],
                        total_pages=row[14],
                        total_chunks=row[15],
                        total_images=row[16],
                        total_tables=row[17],
                        tokens_used=row[18],
                        ingestion_cost_usd=row[19]
                    ))
                
                return JobListResponse(
                    jobs=jobs,
                    total=total,
                    page=page,
                    page_size=page_size
                )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str):
    """Get job details by ID."""
    db = DatabaseClient()
    
    try:
        with db:
            with db.conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        id, task_id, doc_id, filename, status, progress, 
                        current_step, queued_at, started_at, completed_at,
                        estimated_duration_seconds, actual_duration_seconds,
                        error_message, worker_id, total_pages, total_chunks,
                        total_images, total_tables, tokens_used, ingestion_cost_usd
                    FROM jobs
                    WHERE id = %s
                """, (job_id,))
                
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Job not found")
                
                return JobResponse(
                    id=row[0],
                    task_id=row[1],
                    doc_id=row[2],
                    filename=row[3],
                    status=row[4],
                    progress=row[5],
                    current_step=row[6],
                    queued_at=row[7],
                    started_at=row[8],
                    completed_at=row[9],
                    estimated_duration_seconds=row[10],
                    actual_duration_seconds=row[11],
                    error_message=row[12],
                    worker_id=row[13],
                    total_pages=row[14],
                    total_chunks=row[15],
                    total_images=row[16],
                    total_tables=row[17],
                    tokens_used=row[18],
                    ingestion_cost_usd=row[19]
                )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str):
    """Cancel a queued or processing job."""
    db = DatabaseClient()
    
    try:
        # Get job
        with db:
            with db.conn.cursor() as cur:
                cur.execute("SELECT task_id, status FROM jobs WHERE id = %s", (job_id,))
                row = cur.fetchone()
                
                if not row:
                    raise HTTPException(status_code=404, detail="Job not found")
                
                task_id, status = row
                
                if status in ['completed', 'failed', 'cancelled']:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Cannot cancel job with status: {status}"
                    )
                
                # Revoke Celery task
                if task_id:
                    celery_app.control.revoke(task_id, terminate=True)
                
                # Update job status
                cur.execute("""
                    UPDATE jobs 
                    SET status = 'cancelled', completed_at = NOW()
                    WHERE id = %s
                """, (job_id,))
                db.conn.commit()
                
                return {
                    "job_id": job_id,
                    "status": "cancelled",
                    "message": "Job cancelled successfully"
                }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{job_id}/retry")
def retry_job(job_id: str):
    """Retry a failed job."""
    db = DatabaseClient()

    try:
        # Get job
        with db:
            with db.conn.cursor() as cur:
                cur.execute("""
                    SELECT filename, file_path, doc_id, status, retry_count, max_retries
                    FROM jobs
                    WHERE id = %s
                """, (job_id,))

                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Job not found")

                filename, file_path, doc_id, status, retry_count, max_retries = row

                if status != 'failed':
                    raise HTTPException(
                        status_code=400,
                        detail="Only failed jobs can be retried"
                    )

                if retry_count >= max_retries:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Max retries ({max_retries}) exceeded"
                    )

                # Reset job status
                cur.execute("""
                    UPDATE jobs
                    SET status = 'queued',
                        retry_count = retry_count + 1,
                        error_message = NULL,
                        error_traceback = NULL,
                        progress = 0,
                        current_step = NULL,
                        started_at = NULL,
                        completed_at = NULL
                    WHERE id = %s
                    RETURNING retry_count
                """, (job_id,))

                new_retry_count = cur.fetchone()[0]
                db.conn.commit()

                # Re-submit to Celery
                task = process_document.apply_async(
                    args=[job_id, file_path, doc_id, filename]
                )

                # Update task_id
                cur.execute("""
                    UPDATE jobs SET task_id = %s WHERE id = %s
                """, (task.id, job_id))
                db.conn.commit()

                return {
                    "job_id": job_id,
                    "task_id": task.id,
                    "status": "queued",
                    "retry_count": new_retry_count,
                    "message": "Job resubmitted for processing"
                }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{job_id}/resume")
def resume_job(job_id: str):
    """
    Resume a failed job from checkpoint (if available).

    This will reuse any cached data (parsed doc, summaries, processed images/tables)
    to avoid re-processing and save tokens/time.
    """
    db = DatabaseClient()
    checkpoint = ProcessingCheckpoint(job_id)

    try:
        # Check if checkpoint exists
        if not checkpoint.exists():
            raise HTTPException(
                status_code=400,
                detail="No checkpoint found for this job. Use /retry instead."
            )

        # Get job details
        with db:
            with db.conn.cursor() as cur:
                cur.execute("""
                    SELECT filename, file_path, doc_id, status
                    FROM jobs
                    WHERE id = %s
                """, (job_id,))

                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Job not found")

                filename, file_path, doc_id, status = row

                if status not in ['failed', 'cancelled']:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Can only resume failed/cancelled jobs (current status: {status})"
                    )

                # Get checkpoint summary
                checkpoint_summary = checkpoint.get_state_summary()

                # Reset job status to queued
                cur.execute("""
                    UPDATE jobs
                    SET status = 'queued',
                        error_message = NULL,
                        error_traceback = NULL,
                        started_at = NULL,
                        completed_at = NULL
                    WHERE id = %s
                """, (job_id,))
                db.conn.commit()

                # Re-submit to Celery (will use checkpoint)
                task = process_document.apply_async(
                    args=[job_id, file_path, doc_id, filename]
                )

                # Update task_id
                cur.execute("""
                    UPDATE jobs SET task_id = %s WHERE id = %s
                """, (task.id, job_id))
                db.conn.commit()

                return {
                    "job_id": job_id,
                    "task_id": task.id,
                    "status": "queued",
                    "message": "Job resumed from checkpoint",
                    "checkpoint_summary": checkpoint_summary
                }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/queue", response_model=QueueStats)
def get_queue_stats():
    """Get queue statistics."""
    db = DatabaseClient()
    
    try:
        with db:
            with db.conn.cursor() as cur:
                cur.execute("SELECT * FROM get_queue_stats()")
                row = cur.fetchone()
                
                if not row:
                    return QueueStats(
                        total_jobs=0,
                        queued_jobs=0,
                        processing_jobs=0,
                        completed_jobs=0,
                        failed_jobs=0,
                        cancelled_jobs=0,
                        avg_duration_seconds=None,
                        total_cost_usd=None
                    )
                
                return QueueStats(
                    total_jobs=row[0],
                    queued_jobs=row[1],
                    processing_jobs=row[2],
                    completed_jobs=row[3],
                    failed_jobs=row[4],
                    cancelled_jobs=row[5],
                    avg_duration_seconds=row[6],
                    total_cost_usd=row[7]
                )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/workers", response_model=List[WorkerInfo])
def get_active_workers():
    """Get active workers and their current tasks."""
    db = DatabaseClient()
    
    try:
        with db:
            with db.conn.cursor() as cur:
                cur.execute("SELECT * FROM get_active_workers()")
                
                workers = []
                for row in cur.fetchall():
                    workers.append(WorkerInfo(
                        worker_id=row[0],
                        current_job_id=row[1],
                        current_filename=row[2],
                        job_progress=row[3],
                        started_at=row[4]
                    ))
                
                return workers
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

