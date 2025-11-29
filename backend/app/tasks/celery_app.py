"""Celery application configuration."""
import os
from celery import Celery

# Create Celery app
celery_app = Celery(
    "docling_dashboard",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
    include=['app.tasks.ingest', 'app.tasks.ingest_youtube']
)

# Celery configuration
celery_app.conf.update(
    task_track_started=True,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_time_limit=int(os.getenv("CELERY_TASK_TIME_LIMIT", "3600")),  # 1 hour
    task_soft_time_limit=int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "3300")),  # 55 min
    worker_prefetch_multiplier=int(os.getenv("WORKER_PREFETCH_MULTIPLIER", "1")),
    worker_max_tasks_per_child=int(os.getenv("WORKER_MAX_TASKS_PER_CHILD", "10")),
)
