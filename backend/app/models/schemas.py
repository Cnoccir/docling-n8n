"""Pydantic models for API."""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# Job models
class JobCreate(BaseModel):
    filename: str
    document_type: Optional[str] = None
    tags: Optional[List[str]] = None
    categories: Optional[List[str]] = None
    priority: int = 0


class JobResponse(BaseModel):
    id: str
    task_id: Optional[str]
    doc_id: Optional[str]
    filename: str
    status: str
    progress: int
    current_step: Optional[str]
    queued_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    estimated_duration_seconds: Optional[int]
    actual_duration_seconds: Optional[int]
    error_message: Optional[str]
    worker_id: Optional[str]
    total_pages: Optional[int]
    total_chunks: Optional[int]
    total_images: Optional[int]
    total_tables: Optional[int]
    tokens_used: Optional[int]
    ingestion_cost_usd: Optional[float]


class JobListResponse(BaseModel):
    jobs: List[JobResponse]
    total: int
    page: int
    page_size: int


class QueueStats(BaseModel):
    total_jobs: int
    queued_jobs: int
    processing_jobs: int
    completed_jobs: int
    failed_jobs: int
    cancelled_jobs: int
    avg_duration_seconds: Optional[float]
    total_cost_usd: Optional[float]


class WorkerInfo(BaseModel):
    worker_id: str
    current_job_id: Optional[str]
    current_filename: Optional[str]
    job_progress: Optional[int]
    started_at: Optional[datetime]


# Document models
class DocumentResponse(BaseModel):
    id: str
    title: str
    filename: str
    status: str
    document_type: Optional[str]
    summary: Optional[str]
    total_pages: int
    total_chunks: int
    total_sections: int
    total_images: int
    total_tables: int
    tags: List[str]
    categories: List[str]
    created_at: datetime
    processed_at: Optional[datetime]
    processing_duration_seconds: Optional[float]
    ingestion_cost_usd: Optional[float]
    tokens_used: Optional[int]
    gdrive_file_id: Optional[str] = None
    gdrive_link: Optional[str] = None
    gdrive_folder_id: Optional[str] = None
    relevance_score: Optional[float] = 0.0  # For semantic search ranking


class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int
    page: int
    page_size: int


class ImageResponse(BaseModel):
    id: str
    doc_id: str
    page_number: int
    s3_url: str
    caption: Optional[str]
    image_type: Optional[str]
    basic_summary: Optional[str]


class TableResponse(BaseModel):
    id: str
    doc_id: str
    page_number: int
    markdown: str
    description: str
    key_insights: Optional[List[str]]


# WebSocket models
class ProgressUpdate(BaseModel):
    job_id: str
    progress: int
    current_step: str
    status: str
