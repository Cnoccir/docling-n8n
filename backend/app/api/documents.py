"""Documents API endpoints - Query ingested documents."""
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from typing import Optional, List
import sys
from pathlib import Path
import json
import os
import io

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from database.db_client import DatabaseClient
from app.models.schemas import DocumentResponse, DocumentListResponse, ImageResponse, TableResponse
from app.utils.cache import (
    get_cache_key, get_cached, set_cache,
    CACHE_TTL_DOCUMENT_LIST, CACHE_TTL_DOCUMENT_DETAIL,
    CACHE_TTL_CHUNKS, CACHE_TTL_IMAGES, CACHE_TTL_TABLES, CACHE_TTL_HIERARCHY
)
from app.utils.cost_tracker import CostTracker

router = APIRouter()


@router.get("/", response_model=DocumentListResponse)
def list_documents(
    response: Response,
    status: Optional[str] = Query(None, description="Filter by status"),
    document_type: Optional[str] = Query(None, description="Filter by type"),
    search: Optional[str] = Query(None, description="Search by filename or semantic search"),
    semantic: bool = Query(False, description="Use semantic search instead of keyword"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    """
    List all documents with filtering and pagination.

    Args:
        status: Filter by status (processing, completed, failed)
        document_type: Filter by document type
        search: Search by filename (keyword) or semantic meaning (if semantic=true)
        semantic: Enable semantic search using AI embeddings (default: false)
        page: Page number (1-indexed)
        page_size: Items per page

    Examples:
        - GET /api/documents?search=hvac               → Keyword search in filename
        - GET /api/documents?search=hvac&semantic=true → Semantic search across summaries
    """
    # Check cache (include semantic in cache key)
    cache_key = get_cache_key("doc_list", status, document_type, search, semantic, page, page_size)
    cached = get_cached(cache_key)
    if cached:
        response.headers["X-Cache"] = "HIT"
        return cached

    response.headers["X-Cache"] = "MISS"

    # Generate embedding if semantic search requested
    query_embedding = None
    if semantic and search:
        # Track embedding generation cost
        with CostTracker(
            query_type='semantic_search',
            query_text=search
        ) as tracker:
            from utils.embeddings import EmbeddingGenerator
            emb_gen = EmbeddingGenerator()
            query_embedding = emb_gen.generate_embeddings([search])[0]

            # Estimate tokens (rough approximation: 1 token ≈ 4 characters)
            estimated_tokens = len(search) // 4
            tracker.add_tokens(
                prompt_tokens=estimated_tokens,
                completion_tokens=0,
                model=os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')
            )

    db = DatabaseClient()
    offset = (page - 1) * page_size

    try:
        with db:
            with db.conn.cursor() as cur:
                # Build query
                where_clauses = []
                params = []

                if status:
                    where_clauses.append("status = %s")
                    params.append(status)

                if document_type:
                    where_clauses.append("document_type = %s")
                    params.append(document_type)

                # Keyword search (existing - unchanged)
                if search and not semantic:
                    where_clauses.append("(filename ILIKE %s OR title ILIKE %s)")
                    params.extend([f"%{search}%", f"%{search}%"])

                where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

                # Semantic search: order by relevance instead of created_at
                order_clause = "ORDER BY created_at DESC"
                relevance_select = "0::float AS relevance_score"

                if semantic and query_embedding:
                    # Use cosine distance for similarity (lower is better, so 1 - distance gives us higher = better)
                    relevance_select = "(1 - (summary_embedding <=> %s::vector)) AS relevance_score"
                    order_clause = "ORDER BY relevance_score DESC"
                    # Add embedding to params at the beginning (for SELECT clause)
                    params.insert(0, query_embedding)

                # Get total count
                count_query = f"SELECT COUNT(*) FROM document_index {where_clause}"
                # For count query, we need params without the embedding
                count_params = params[1:] if (semantic and query_embedding) else params
                cur.execute(count_query, count_params)
                total = cur.fetchone()[0]

                # Get documents
                query = f"""
                    SELECT
                        id, title, filename, status, document_type,
                        summary, total_pages, total_chunks, total_sections,
                        total_images, total_tables, tags, categories,
                        created_at, processed_at, processing_duration_seconds,
                        ingestion_cost_usd, tokens_used,
                        gdrive_file_id, gdrive_link, gdrive_folder_id,
                        {relevance_select}
                    FROM document_index
                    {where_clause}
                    {order_clause}
                    LIMIT %s OFFSET %s
                """
                cur.execute(query, params + [page_size, offset])
                
                documents = []
                for row in cur.fetchall():
                    documents.append(DocumentResponse(
                        id=row[0],
                        title=row[1],
                        filename=row[2],
                        status=row[3],
                        document_type=row[4],
                        summary=row[5],
                        total_pages=row[6] or 0,
                        total_chunks=row[7] or 0,
                        total_sections=row[8] or 0,
                        total_images=row[9] or 0,
                        total_tables=row[10] or 0,
                        tags=row[11] if row[11] else [],
                        categories=row[12] if row[12] else [],
                        created_at=row[13],
                        processed_at=row[14],
                        processing_duration_seconds=row[15],
                        ingestion_cost_usd=row[16],
                        tokens_used=row[17],
                        gdrive_file_id=row[18],
                        gdrive_link=row[19],
                        gdrive_folder_id=row[20],
                        relevance_score=float(row[21]) if row[21] is not None else 0.0
                    ))
                
                result = DocumentListResponse(
                    documents=documents,
                    total=total,
                    page=page,
                    page_size=page_size
                )
                
                # Cache the result
                set_cache(cache_key, result.dict(), CACHE_TTL_DOCUMENT_LIST)
                return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{doc_id}", response_model=DocumentResponse)
def get_document(doc_id: str, response: Response):
    """Get document details by ID."""
    # Check cache
    cache_key = get_cache_key("doc", doc_id)
    cached = get_cached(cache_key)
    if cached:
        response.headers["X-Cache"] = "HIT"
        return cached
    
    response.headers["X-Cache"] = "MISS"
    db = DatabaseClient()
    
    try:
        with db:
            with db.conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        id, title, filename, status, document_type,
                        summary, total_pages, total_chunks, total_sections,
                        total_images, total_tables, tags, categories,
                        created_at, processed_at, processing_duration_seconds,
                        ingestion_cost_usd, tokens_used,
                        gdrive_file_id, gdrive_link, gdrive_folder_id
                    FROM document_index
                    WHERE id = %s
                """, (doc_id,))

                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Document not found")

                result = DocumentResponse(
                    id=row[0],
                    title=row[1],
                    filename=row[2],
                    status=row[3],
                    document_type=row[4],
                    summary=row[5],
                    total_pages=row[6] or 0,
                    total_chunks=row[7] or 0,
                    total_sections=row[8] or 0,
                    total_images=row[9] or 0,
                    total_tables=row[10] or 0,
                    tags=row[11] if row[11] else [],
                    categories=row[12] if row[12] else [],
                    created_at=row[13],
                    processed_at=row[14],
                    processing_duration_seconds=row[15],
                    ingestion_cost_usd=row[16],
                    tokens_used=row[17],
                    gdrive_file_id=row[18],
                    gdrive_link=row[19],
                    gdrive_folder_id=row[20]
                )
                
                # Cache the result
                set_cache(cache_key, result.dict(), CACHE_TTL_DOCUMENT_DETAIL)
                return result
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{doc_id}/images", response_model=List[ImageResponse])
def get_document_images(doc_id: str):
    """Get all images for a document."""
    db = DatabaseClient()
    
    try:
        with db:
            with db.conn.cursor() as cur:
                cur.execute("""
                    SELECT id, doc_id, page_number, s3_url, caption, image_type, basic_summary
                    FROM images
                    WHERE doc_id = %s
                    ORDER BY page_number, id
                """, (doc_id,))
                
                images = []
                for row in cur.fetchall():
                    images.append(ImageResponse(
                        id=row[0],
                        doc_id=row[1],
                        page_number=row[2],
                        s3_url=row[3],
                        caption=row[4],
                        image_type=row[5],
                        basic_summary=row[6]
                    ))
                
                return images
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{doc_id}/tables", response_model=List[TableResponse])
def get_document_tables(doc_id: str):
    """Get all tables for a document."""
    db = DatabaseClient()
    
    try:
        with db:
            with db.conn.cursor() as cur:
                cur.execute("""
                    SELECT id, doc_id, page_number, markdown, description, key_insights
                    FROM document_tables
                    WHERE doc_id = %s
                    ORDER BY page_number, id
                """, (doc_id,))
                
                tables = []
                for row in cur.fetchall():
                    # Parse key_insights if it's JSONB
                    key_insights = row[5]
                    if isinstance(key_insights, str):
                        try:
                            key_insights = json.loads(key_insights)
                        except:
                            key_insights = []
                    
                    tables.append(TableResponse(
                        id=row[0],
                        doc_id=row[1],
                        page_number=row[2],
                        markdown=row[3],
                        description=row[4],
                        key_insights=key_insights
                    ))
                
                return tables
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{doc_id}/hierarchy")
def get_document_hierarchy(doc_id: str, response: Response):
    """Get document hierarchy structure."""
    # Check cache
    cache_key = get_cache_key("hierarchy", doc_id)
    cached = get_cached(cache_key)
    if cached:
        response.headers["X-Cache"] = "HIT"
        return cached
    
    response.headers["X-Cache"] = "MISS"
    db = DatabaseClient()
    
    try:
        with db:
            with db.conn.cursor() as cur:
                cur.execute("""
                    SELECT hierarchy, page_index, asset_index
                    FROM document_hierarchy
                    WHERE doc_id = %s
                """, (doc_id,))
                
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Hierarchy not found")
                
                result = {
                    "doc_id": doc_id,
                    "hierarchy": row[0],
                    "page_index": row[1],
                    "asset_index": row[2]
                }
                
                # Cache the result
                set_cache(cache_key, result, CACHE_TTL_HIERARCHY)
                return result
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{doc_id}/chunks")
def get_document_chunks(
    doc_id: str,
    response: Response,
    page: int = Query(None, description="Filter by page number"),
    limit: int = Query(50, ge=1, le=200)
):
    """Get document chunks with optional page filter."""
    # Check cache
    cache_key = get_cache_key("chunks", doc_id, page, limit)
    cached = get_cached(cache_key)
    if cached:
        response.headers["X-Cache"] = "HIT"
        return cached
    
    response.headers["X-Cache"] = "MISS"
    db = DatabaseClient()
    
    try:
        with db:
            with db.conn.cursor() as cur:
                where_clause = "WHERE doc_id = %s"
                params = [doc_id]
                
                if page is not None:
                    where_clause += " AND page_number = %s"
                    params.append(page)
                
                cur.execute(f"""
                    SELECT id, content, page_number, bbox, metadata
                    FROM chunks
                    {where_clause}
                    ORDER BY page_number, id
                    LIMIT %s
                """, params + [limit])
                
                chunks = []
                for row in cur.fetchall():
                    chunks.append({
                        "id": row[0],
                        "content": row[1],
                        "page_number": row[2],
                        "bbox": row[3],
                        "metadata": row[4]
                    })
                
                result = {
                    "doc_id": doc_id,
                    "chunks": chunks,
                    "count": len(chunks)
                }
                
                # Cache the result
                set_cache(cache_key, result, CACHE_TTL_CHUNKS)
                return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{doc_id}")
def delete_document(doc_id: str):
    """
    Delete a document and all associated data.

    This will delete:
    - Document index entry
    - All chunks and embeddings (CASCADE)
    - Hierarchy data (CASCADE)
    - Images (database references, CASCADE)
    - Tables (CASCADE)
    - Associated jobs (manually deleted)

    Note: S3 files are not automatically deleted for safety.
    """
    db = DatabaseClient()

    try:
        with db:
            with db.conn.cursor() as cur:
                # Check if document exists and get details
                cur.execute("""
                    SELECT id, title, filename, source_type,
                           total_chunks, total_images, total_tables
                    FROM document_index
                    WHERE id = %s
                """, (doc_id,))
                doc = cur.fetchone()

                if not doc:
                    raise HTTPException(status_code=404, detail="Document not found")

                doc_id, title, filename, source_type, total_chunks, total_images, total_tables = doc

                # Count associated jobs before deletion
                cur.execute("""
                    SELECT COUNT(*)
                    FROM jobs
                    WHERE doc_id = %s
                """, (doc_id,))
                job_count = cur.fetchone()[0]

                # Delete associated jobs (not handled by CASCADE)
                cur.execute("""
                    DELETE FROM jobs
                    WHERE doc_id = %s
                """, (doc_id,))

                # Delete document (cascades to chunks, hierarchy, images, tables)
                cur.execute("DELETE FROM document_index WHERE id = %s", (doc_id,))
                db.conn.commit()

                return {
                    "doc_id": doc_id,
                    "status": "deleted",
                    "message": f"Document '{title}' deleted successfully",
                    "deleted": {
                        "document": filename,
                        "source_type": source_type,
                        "chunks": total_chunks or 0,
                        "images": total_images or 0,
                        "tables": total_tables or 0,
                        "jobs": job_count,
                        "hierarchy": 1,
                        "note": "S3 files were not deleted (preserved for safety)"
                    }
                }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{doc_id}/pdf")
def get_document_pdf(doc_id: str):
    """
    Proxy PDF from Google Drive to bypass CORS restrictions.

    This endpoint:
    1. Gets the Google Drive file ID from database
    2. Downloads the PDF from Google Drive using service account
    3. Streams it to the frontend with proper CORS headers

    This allows embedding PDFs in iframes without CORS issues.
    """
    db = DatabaseClient()

    try:
        with db:
            with db.conn.cursor() as cur:
                cur.execute("""
                    SELECT gdrive_file_id, filename
                    FROM document_index
                    WHERE id = %s
                """, (doc_id,))

                row = cur.fetchone()
                if not row or not row[0]:
                    raise HTTPException(
                        status_code=404,
                        detail="PDF not available. Document may not have been uploaded to Google Drive."
                    )

                file_id = row[0]
                filename = row[1] or 'document.pdf'

        # Download from Google Drive
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload

        credentials_path = os.getenv('GDRIVE_CREDENTIALS_PATH', '/app/service-account-key.json')

        if not os.path.exists(credentials_path):
            raise HTTPException(
                status_code=500,
                detail="Google Drive credentials not configured"
            )

        credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )

        service = build('drive', 'v3', credentials=credentials)

        # Download the file
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)

        done = False
        while done is False:
            status, done = downloader.next_chunk()
            if status:
                print(f"Download progress: {int(status.progress() * 100)}%")

        fh.seek(0)

        # Return PDF with CORS headers
        return StreamingResponse(
            fh,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"inline; filename={filename}",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET",
                "Access-Control-Allow-Headers": "*"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error proxying PDF: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load PDF: {str(e)}"
        )


@router.post("/{doc_id}/gdrive-upload")
def manual_gdrive_upload(doc_id: str):
    """
    Manually upload document to Google Drive and sync the link to database.

    This endpoint is useful when:
    - The automatic upload failed during ingestion
    - You need to re-upload the document
    - The Google Drive link is missing

    It will:
    1. Check if document exists in database
    2. Find the original PDF file
    3. Upload to Google Drive
    4. Update the database with the Google Drive link
    """
    db = DatabaseClient()

    try:
        with db:
            with db.conn.cursor() as cur:
                # Get document info
                cur.execute("""
                    SELECT id, title, filename, gdrive_file_id
                    FROM document_index
                    WHERE id = %s
                """, (doc_id,))

                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Document not found")

                doc_id = row[0]
                title = row[1]
                filename = row[2]
                existing_gdrive_id = row[3]

                if existing_gdrive_id:
                    return {
                        "status": "already_uploaded",
                        "message": f"Document already has Google Drive link. File ID: {existing_gdrive_id}",
                        "gdrive_file_id": existing_gdrive_id
                    }

        # Try to find the PDF file (check multiple locations)
        pdf_path = None
        possible_paths = [
            f"/tmp/uploads/{doc_id}.pdf",
            f"/app/documents/{filename}",
            f"/app/temp/{filename}",
            f"/tmp/uploads/{filename}"
        ]

        for path in possible_paths:
            if os.path.exists(path):
                pdf_path = path
                break

        if not pdf_path:
            raise HTTPException(
                status_code=404,
                detail=f"PDF file not found. Tried paths: {', '.join(possible_paths)}. "
                       "The original file may have been deleted after processing."
            )

        # Upload to Google Drive
        try:
            from gdrive_uploader import GDriveUploader

            print(f"📤 Manually uploading {doc_id} to Google Drive...")
            gdrive = GDriveUploader()
            gdrive_info = gdrive.upload_pdf(
                pdf_path=pdf_path,
                doc_title=title,
                doc_id=doc_id
            )
            print(f"✅ Uploaded to Google Drive: {gdrive_info['link']}")

        except Exception as e:
            print(f"❌ Google Drive upload failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload to Google Drive: {str(e)}"
            )

        # Update database with Google Drive info
        try:
            with db:
                with db.conn.cursor() as cur:
                    cur.execute("""
                        UPDATE document_index
                        SET gdrive_file_id = %s,
                            gdrive_link = %s,
                            gdrive_folder_id = %s,
                            updated_at = NOW()
                        WHERE id = %s
                    """, (
                        gdrive_info['file_id'],
                        gdrive_info['link'],
                        gdrive_info.get('folder_id'),
                        doc_id
                    ))
                    db.conn.commit()

                    print(f"✅ Database updated with Google Drive link")

            return {
                "status": "success",
                "message": "Document uploaded to Google Drive and database updated",
                "gdrive_file_id": gdrive_info['file_id'],
                "gdrive_link": gdrive_info['link'],
                "gdrive_folder_id": gdrive_info.get('folder_id')
            }

        except Exception as e:
            print(f"❌ Database update failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Uploaded to Google Drive but failed to update database: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Manual Google Drive upload failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Manual upload failed: {str(e)}"
        )

