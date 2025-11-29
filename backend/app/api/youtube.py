"""YouTube video API endpoints."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl
from typing import List, Optional
import sys
from pathlib import Path
import uuid

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from database.db_client import DatabaseClient
from app.tasks.ingest_youtube import process_youtube_video
import re

router = APIRouter()


class YouTubeUploadRequest(BaseModel):
    """Request to ingest YouTube video."""
    url: str
    tags: List[str] = []
    categories: List[str] = []


class YouTubeUploadResponse(BaseModel):
    """Response from YouTube upload."""
    job_id: str
    video_id: str
    youtube_id: str
    url: str
    message: str


class VideoListItem(BaseModel):
    """Single video in list."""
    id: str
    title: str
    youtube_id: str
    channel_name: str
    duration_seconds: int
    duration_formatted: str
    source_url: str
    thumbnail_url: Optional[str]
    status: str
    total_chunks: int
    total_images: int
    created_at: str
    processed_at: Optional[str]


class VideoListResponse(BaseModel):
    """Response containing list of videos."""
    documents: List[VideoListItem]
    total: int
    page: int
    page_size: int


class TranscriptSegment(BaseModel):
    """Single transcript segment with timestamp."""
    chunk_id: str
    timestamp_start: float
    timestamp_end: float
    timestamp_formatted: str
    content: str
    video_url: str
    section_path: List[str]


class VideoDetailResponse(BaseModel):
    """Detailed video information."""
    id: str
    title: str
    youtube_id: str
    channel_name: str
    duration_seconds: int
    duration_formatted: str
    source_url: str
    description: Optional[str]
    status: str
    total_chunks: int
    total_images: int
    total_sections: int
    hierarchy: Optional[dict]
    transcript: List[TranscriptSegment]


def extract_youtube_id(url: str) -> str:
    """Extract YouTube video ID from URL."""
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:embed\/)([0-9A-Za-z_-]{11})',
        r'^([0-9A-Za-z_-]{11})$'
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    raise ValueError(f"Invalid YouTube URL: {url}")


def format_duration(seconds: int) -> str:
    """Format duration as HH:MM:SS or MM:SS."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


def format_timestamp(seconds: float) -> str:
    """Format timestamp as MM:SS."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


@router.post("/upload", response_model=YouTubeUploadResponse)
async def upload_youtube_video(request: YouTubeUploadRequest):
    """
    Start ingestion of YouTube video.

    This creates a job and submits it to Celery for async processing.
    """
    db = DatabaseClient()

    try:
        # Extract YouTube ID
        youtube_id = extract_youtube_id(request.url)

        # Check if video already exists
        with db.conn.cursor() as cur:
            cur.execute("""
                SELECT id, status
                FROM document_index
                WHERE youtube_id = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (youtube_id,))

            existing = cur.fetchone()

        if existing:
            if existing[1] == 'completed':
                raise HTTPException(
                    status_code=409,
                    detail=f"Video already processed: {existing[0]}"
                )
            elif existing[1] == 'processing':
                raise HTTPException(
                    status_code=409,
                    detail=f"Video currently being processed: {existing[0]}"
                )
            # If failed, allow reprocessing

        # Generate IDs
        job_id = str(uuid.uuid4())
        video_id = f"video_{youtube_id}"

        # Create job in database
        with db.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO jobs (
                    id, doc_id, filename, status, progress, current_step
                )
                VALUES (%s, %s, %s, 'queued', 0, 'Waiting to start')
            """, (job_id, video_id, f"YouTube: {youtube_id}"))
            db.conn.commit()

        # Submit to Celery
        process_youtube_video.delay(
            job_id=job_id,
            url=request.url,
            video_id=video_id,
            tags=request.tags,
            categories=request.categories
        )

        return YouTubeUploadResponse(
            job_id=job_id,
            video_id=video_id,
            youtube_id=youtube_id,
            url=request.url,
            message=f"Video ingestion started. Job ID: {job_id}"
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.conn.close()


@router.get("/videos", response_model=VideoListResponse)
async def list_youtube_videos(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None
):
    """
    List all YouTube videos.

    Filters:
    - status: 'completed', 'processing', 'failed'
    """
    db = DatabaseClient()

    try:
        # Get total count
        with db.conn.cursor() as cur:
            where_clause = "WHERE source_type = 'youtube'"
            count_params = []

            if status:
                where_clause += " AND status = %s"
                count_params.append(status)

            cur.execute(f"""
                SELECT COUNT(*)
                FROM document_index
                {where_clause}
            """, count_params)

            total = cur.fetchone()[0]

        # Get videos
        with db.conn.cursor() as cur:
            # Build query with optional status filter
            where_clause = "WHERE source_type = 'youtube'"
            params = []

            if status:
                where_clause += " AND status = %s"
                params.append(status)

            params.extend([limit, offset])

            cur.execute(f"""
                SELECT
                    id, title, youtube_id, channel_name, duration_seconds,
                    source_url, status, total_chunks, total_images,
                    created_at, processed_at
                FROM document_index
                {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, params)

            results = cur.fetchall()

        videos = []
        for row in results:
            videos.append(VideoListItem(
                id=row[0],
                title=row[1],
                youtube_id=row[2],
                channel_name=row[3] or 'Unknown',
                duration_seconds=row[4] or 0,
                duration_formatted=format_duration(row[4] or 0),
                source_url=row[5],
                thumbnail_url=f"https://img.youtube.com/vi/{row[2]}/maxresdefault.jpg",
                status=row[6],
                total_chunks=row[7] or 0,
                total_images=row[8] or 0,
                created_at=row[9].isoformat() if row[9] else None,
                processed_at=row[10].isoformat() if row[10] else None
            ))

        return VideoListResponse(
            documents=videos,
            total=total,
            page=offset // limit + 1,
            page_size=limit
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.conn.close()


@router.get("/videos/{video_id}", response_model=VideoDetailResponse)
async def get_video_details(video_id: str):
    """
    Get detailed video information including full transcript.
    """
    db = DatabaseClient()

    try:
        # Get video metadata
        with db.conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id, title, youtube_id, channel_name, duration_seconds,
                    source_url, summary, status, total_chunks, total_images,
                    total_sections
                FROM document_index
                WHERE id = %s AND source_type = 'youtube'
            """, (video_id,))

            video = cur.fetchone()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Get hierarchy
        with db.conn.cursor() as cur:
            cur.execute("""
                SELECT hierarchy
                FROM document_hierarchy
                WHERE doc_id = %s
            """, (video_id,))

            hierarchy_row = cur.fetchone()
            hierarchy = hierarchy_row[0] if hierarchy_row else None

        # Get transcript
        with db.conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id, timestamp_start, timestamp_end, content,
                    video_url_with_timestamp, section_path
                FROM chunks
                WHERE doc_id = %s
                ORDER BY timestamp_start
            """, (video_id,))

            transcript_rows = cur.fetchall()

        transcript = []
        for row in transcript_rows:
            transcript.append(TranscriptSegment(
                chunk_id=row[0],
                timestamp_start=row[1],
                timestamp_end=row[2],
                timestamp_formatted=format_timestamp(row[1]),
                content=row[3],
                video_url=row[4] or '',
                section_path=row[5] or []
            ))

        return VideoDetailResponse(
            id=video[0],
            title=video[1],
            youtube_id=video[2],
            channel_name=video[3] or 'Unknown',
            duration_seconds=video[4] or 0,
            duration_formatted=format_duration(video[4] or 0),
            source_url=video[5],
            description=video[6],
            status=video[7],
            total_chunks=video[8] or 0,
            total_images=video[9] or 0,
            total_sections=video[10] or 0,
            hierarchy=hierarchy,
            transcript=transcript
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.conn.close()


@router.get("/videos/{video_id}/screenshots")
async def get_video_screenshots(
    video_id: str,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None
):
    """
    Get screenshots for a video, optionally filtered by timestamp range.
    """
    db = DatabaseClient()

    try:
        with db.conn.cursor() as cur:
            where_clauses = ["doc_id = %s"]
            params = [video_id]

            if start_time is not None:
                where_clauses.append("timestamp >= %s")
                params.append(start_time)

            if end_time is not None:
                where_clauses.append("timestamp <= %s")
                params.append(end_time)

            where_clause = " AND ".join(where_clauses)

            cur.execute(f"""
                SELECT
                    id, timestamp, s3_url, caption, scene_type,
                    ocr_text, page_number
                FROM images
                WHERE {where_clause}
                ORDER BY timestamp
            """, params)

            results = cur.fetchall()

        screenshots = []
        for row in results:
            screenshots.append({
                'id': row[0],
                'timestamp': row[1],
                'timestamp_formatted': format_timestamp(row[1]) if row[1] else None,
                's3_url': row[2],
                'caption': row[3],
                'scene_type': row[4],
                'ocr_text': row[5],
                'page_number': row[6]
            })

        return screenshots

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.conn.close()


@router.delete("/videos/{video_id}")
async def delete_video(video_id: str):
    """
    Delete a video and all associated data.

    This will delete:
    - Document index entry
    - All chunks and embeddings (CASCADE)
    - Hierarchy data (CASCADE)
    - Screenshots (database references, CASCADE)
    - Associated jobs (manually deleted)

    Note: S3 files are not automatically deleted for safety.
    """
    db = DatabaseClient()

    try:
        with db.conn.cursor() as cur:
            # Check if exists and get details
            cur.execute("""
                SELECT id, title, youtube_id, channel_name,
                       total_chunks, total_images, duration_seconds
                FROM document_index
                WHERE id = %s AND source_type = 'youtube'
            """, (video_id,))

            video = cur.fetchone()

            if not video:
                raise HTTPException(status_code=404, detail="Video not found")

            video_id, title, youtube_id, channel_name, total_chunks, total_images, duration_seconds = video

            # Count associated jobs before deletion
            cur.execute("""
                SELECT COUNT(*)
                FROM jobs
                WHERE doc_id = %s
            """, (video_id,))
            job_count = cur.fetchone()[0]

            # Delete associated jobs (not handled by CASCADE)
            cur.execute("""
                DELETE FROM jobs
                WHERE doc_id = %s
            """, (video_id,))

            # Delete cascades to chunks, images, tables, hierarchy
            cur.execute("""
                DELETE FROM document_index
                WHERE id = %s
            """, (video_id,))

            db.conn.commit()

        return {
            "doc_id": video_id,
            "status": "deleted",
            "message": f"Video '{title}' deleted successfully",
            "deleted": {
                "video": title,
                "youtube_id": youtube_id,
                "channel": channel_name,
                "duration_seconds": duration_seconds or 0,
                "chunks": total_chunks or 0,
                "screenshots": total_images or 0,
                "jobs": job_count,
                "hierarchy": 1,
                "note": "S3 screenshot files were not deleted (preserved for safety)"
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        db.conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.conn.close()
