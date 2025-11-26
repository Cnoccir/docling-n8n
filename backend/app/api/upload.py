"""Upload API endpoints."""
import os
import uuid
import aiofiles
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import List, Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from database.db_client import DatabaseClient
from app.tasks.ingest import process_document

router = APIRouter()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/tmp/uploads")
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", "104857600"))  # 100MB
ALLOWED_EXTENSIONS = os.getenv("ALLOWED_EXTENSIONS", ".pdf").split(",")

# Ensure upload directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)


def generate_doc_id(filename: str) -> str:
    """Generate unique document ID."""
    base_name = os.path.splitext(filename)[0]
    # Clean filename for use as ID
    clean_name = "".join(c if c.isalnum() or c in ['-', '_'] else '_' for c in base_name)
    return f"{clean_name}_{uuid.uuid4().hex[:8]}"


@router.post("/single")
async def upload_single(
    file: UploadFile = File(...),
    document_type: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    categories: Optional[str] = Form(None),
    priority: int = Form(0),
    reprocess: bool = Form(False)
):
    """
    Upload a single PDF document for processing.

    Args:
        file: PDF file
        document_type: Type of document (manual, report, etc.)
        tags: Comma-separated tags
        categories: Comma-separated categories
        priority: Processing priority (higher = first)
        reprocess: Allow reprocessing if document already exists (creates new version)
    """
    print(f"\n📤 UPLOAD START: {file.filename}")
    
    # Validate file
    if not file.filename.lower().endswith(tuple(ALLOWED_EXTENSIONS)):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Check file size
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset
    
    if file_size > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size: {MAX_UPLOAD_SIZE / 1024 / 1024}MB"
        )
    
    # Generate document ID
    doc_id = generate_doc_id(file.filename)
    
    # Save file temporarily
    file_path = os.path.join(UPLOAD_DIR, f"{doc_id}.pdf")
    print(f"📁 Saving to: {file_path}")
    
    try:
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        print(f"✅ File saved: {len(content)} bytes")
    except Exception as e:
        print(f"❌ File save error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    # Parse tags and categories
    tags_list = [t.strip() for t in tags.split(",")] if tags else None
    categories_list = [c.strip() for c in categories.split(",")] if categories else None
    
    # Create job in database
    db = DatabaseClient()
    job_id = str(uuid.uuid4())
    print(f"💾 Creating job: {job_id}")
    
    try:
        with db:
            with db.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO jobs (
                        id, filename, file_path, file_size_bytes, 
                        status, priority
                    )
                    VALUES (%s, %s, %s, %s, 'queued', %s)
                    RETURNING id
                """, (job_id, file.filename, file_path, file_size, priority))
                db.conn.commit()
        print(f"✅ Job created in DB")
        
        # Submit to Celery
        print(f"🚀 Submitting to Celery...")
        task = process_document.apply_async(
            args=[job_id, file_path, doc_id, file.filename, document_type, tags_list, categories_list, reprocess],
            priority=priority
        )
        print(f"✅ Task submitted: {task.id}")
        
        # Update job with task_id
        print(f"💾 Updating job with task_id...")
        try:
            # Use fresh database instance since previous connection is closed
            db2 = DatabaseClient()
            with db2:
                with db2.conn.cursor() as cur:
                    cur.execute("""
                        UPDATE jobs SET task_id = %s WHERE id = %s
                    """, (task.id, job_id))
                    db2.conn.commit()
            print(f"✅ Task ID updated in DB")
        except Exception as e:
            print(f"🔥 ERROR updating task_id in DB: {type(e).__name__}: {str(e)}")
            print(f"🔥 task.id={task.id}, job_id={job_id}")
            import traceback
            traceback.print_exc()
            raise
        
        response_data = {
            "job_id": job_id,
            "task_id": task.id,
            "doc_id": doc_id,
            "filename": file.filename,
            "status": "queued",
            "message": "Document queued for processing"
        }
        print(f"📤 Returning response: {response_data}")
        return response_data
    
    except Exception as e:
        # Clean up file on error
        try:
            os.remove(file_path)
        except:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk")
async def upload_bulk(
    files: List[UploadFile] = File(...),
    document_type: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    categories: Optional[str] = Form(None),
    priority: int = Form(0),
    reprocess: bool = Form(False)
):
    """
    Upload multiple PDF documents for processing.

    Args:
        files: List of PDF files
        document_type: Type of documents
        tags: Comma-separated tags (applied to all)
        categories: Comma-separated categories (applied to all)
        priority: Processing priority
        reprocess: Allow reprocessing if documents already exist
    """
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 files per batch")
    
    results = []
    
    for file in files:
        try:
            result = await upload_single(
                file=file,
                document_type=document_type,
                tags=tags,
                categories=categories,
                priority=priority,
                reprocess=reprocess
            )
            results.append({"filename": file.filename, "status": "queued", **result})
        except Exception as e:
            results.append({
                "filename": file.filename,
                "status": "error",
                "error": str(e)
            })
    
    successful = sum(1 for r in results if r["status"] == "queued")
    failed = len(results) - successful
    
    return {
        "total": len(files),
        "successful": successful,
        "failed": failed,
        "results": results
    }

