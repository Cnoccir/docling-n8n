"""FastAPI application for document ingestion dashboard with YouTube support."""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import upload, jobs, documents, websocket, chat, chat_multimodal, analytics, youtube, chat_unified

# Create FastAPI app
app = FastAPI(
    title="Docling Dashboard API",
    description="Multi-source ingestion pipeline (PDF + YouTube) with unified RAG",
    version="2.0.0"
)

# CORS Configuration
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers (no trailing slashes to avoid redirects)
app.include_router(upload.router, prefix="/api/upload", tags=["upload"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(chat_multimodal.router, prefix="/api/chat/multimodal", tags=["chat-multimodal"])
app.include_router(chat_unified.router, prefix="/api/chat/unified", tags=["chat-unified"])  # NEW!
app.include_router(youtube.router, prefix="/api/youtube", tags=["youtube"])  # NEW!
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(websocket.router, prefix="/ws", tags=["websocket"])


@app.get("/")
def root():
    """API root endpoint."""
    return {
        "name": "Docling Dashboard API - Multi-Source RAG",
        "version": "2.0.0",
        "endpoints": {
            "upload_pdf": "/api/upload",
            "upload_youtube": "/api/youtube/upload",
            "jobs": "/api/jobs",
            "documents": "/api/documents",
            "videos": "/api/youtube/videos",
            "chat_pdf": "/api/chat",
            "chat_multimodal": "/api/chat/multimodal",
            "chat_unified": "/api/chat/unified",
            "websocket": "/ws/jobs",
            "docs": "/docs"
        },
        "features": {
            "pdf_ingestion": True,
            "youtube_ingestion": True,
            "unified_search": True,
            "multimodal_rag": True
        }
    }


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    import traceback
    error_detail = str(exc)
    error_trace = traceback.format_exc()
    print(f"\n🔥 EXCEPTION: {error_detail}\n{error_trace}\n")
    return JSONResponse(
        status_code=500,
        content={"error": error_detail}
    )
