"""
FastAPI application for Docling PDF processing.
Enhanced with full DocumentProcessor capabilities for n8n integration.
"""

import os
import logging
from typing import Optional, Dict, Any, List
import uuid
import json
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

# Import our enhanced document processor
from document_processor.adapter import APIDocumentProcessor

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Enhanced Docling n8n API",
    description="API for processing PDFs with full Docling capabilities, for n8n integration",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
API_KEY = os.getenv("API_KEY")  # Optional API key for protection
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Required for LLM-based extraction
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")  # Directory to store processed documents

# Response models for clear API documentation
class ProcessingResponse(BaseModel):
    """Response model for document processing."""
    pdf_id: str
    markdown: str
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    images: List[Dict[str, Any]] = Field(default_factory=list)
    technical_terms: List[str] = Field(default_factory=list)
    procedures: List[Dict[str, Any]] = Field(default_factory=list)
    parameters: List[Dict[str, Any]] = Field(default_factory=list)
    concept_relationships: List[Dict[str, Any]] = Field(default_factory=list)
    chunks: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    processing_time: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ProcessingStatus(BaseModel):
    """Response model for processing status checks."""
    pdf_id: str
    status: str
    progress: float = 0.0
    message: str = ""

# API key verification if set
async def verify_api_key(api_key: Optional[str] = None):
    """Verify API key if configured."""
    if API_KEY and api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True

def get_openai_client():
    """Get OpenAI client with API key from environment."""
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not found in environment!")
        raise HTTPException(
            status_code=500,
            detail="OpenAI API key not configured. Please set OPENAI_API_KEY environment variable."
        )
    return AsyncOpenAI(api_key=OPENAI_API_KEY)

# Dictionary to store processing status
processing_status = {}

@app.get("/")
async def root():
    """Root endpoint to verify the API is running."""
    return {"status": "Enhanced Docling n8n API is running"}

@app.get("/api/status/{pdf_id}", response_model=ProcessingStatus)
async def get_status(pdf_id: str):
    """Get processing status for a document."""
    if pdf_id not in processing_status:
        return JSONResponse(
            status_code=404,
            content={"detail": f"No processing status found for PDF ID: {pdf_id}"}
        )
    return processing_status[pdf_id]

@app.post("/api/extract", response_model=ProcessingResponse)
async def extract_document(
    background_tasks: BackgroundTasks,
    pdf_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    extract_technical_terms: bool = Form(True),
    extract_procedures: bool = Form(True),
    extract_relationships: bool = Form(True),
    process_images: bool = Form(True),
    process_tables: bool = Form(True),
    chunk_size: int = Form(500),
    chunk_overlap: int = Form(100),
    api_key: Optional[str] = Form(None),
    openai_client: AsyncOpenAI = Depends(get_openai_client)
):
    """
    Extract content from a PDF document using the enhanced DocumentProcessor.

    Parameters:
    - pdf_id: Optional identifier for the PDF (will be generated if not provided)
    - file: PDF file to process
    - extract_technical_terms: Whether to extract technical terms
    - extract_procedures: Whether to extract procedures and parameters
    - extract_relationships: Whether to extract concept relationships
    - process_images: Whether to process images
    - process_tables: Whether to process tables
    - chunk_size: Size of text chunks for extraction (default: 500)
    - chunk_overlap: Overlap between chunks (default: 100)
    - api_key: Optional API key for authentication

    Returns:
    - ProcessingResponse with extracted content and metadata
    """
    # Verify API key if set
    await verify_api_key(api_key)

    logger.info(f"Received extract request for file: {file.filename}")

    # Generate PDF ID if not provided
    if not pdf_id:
        pdf_id = f"doc_{uuid.uuid4().hex[:8]}"
        logger.info(f"Generated PDF ID: {pdf_id}")

    try:
        # Read file content
        content = await file.read()

        # Create processing config
        config = {
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "extract_technical_terms": extract_technical_terms,
            "extract_procedures": extract_procedures,
            "extract_relationships": extract_relationships,
            "process_images": process_images,
            "process_tables": process_tables,
        }

        # Create processor
        processor = APIDocumentProcessor(
            pdf_id=pdf_id,
            config=config,
            openai_client=openai_client
        )

        # Set processing status
        processing_status[pdf_id] = ProcessingStatus(
            pdf_id=pdf_id,
            status="processing",
            progress=0.0,
            message="Processing started"
        )

        # Process document
        result = await processor.process_document(content)

        # Update processing status
        processing_status[pdf_id] = ProcessingStatus(
            pdf_id=pdf_id,
            status="completed",
            progress=100.0,
            message="Processing completed successfully"
        )

        # Optional: Save result to file for later retrieval
        output_path = Path(OUTPUT_DIR) / pdf_id / "result.json"
        os.makedirs(output_path.parent, exist_ok=True)

        # Run in background to avoid blocking
        def save_result():
            with open(output_path, "w") as f:
                json.dump(result, f, default=str)

        background_tasks.add_task(save_result)

        return result

    except Exception as e:
        # Update processing status
        processing_status[pdf_id] = ProcessingStatus(
            pdf_id=pdf_id,
            status="failed",
            progress=0.0,
            message=f"Processing failed: {str(e)}"
        )

        logger.error(f"Error processing document: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing document: {str(e)}")

@app.get("/api/results/{pdf_id}")
async def get_results(pdf_id: str, api_key: Optional[str] = None):
    """
    Get processing results for a document.

    Parameters:
    - pdf_id: Document identifier
    - api_key: Optional API key for authentication

    Returns:
    - Stored processing results
    """
    # Verify API key if set
    await verify_api_key(api_key)

    output_path = Path(OUTPUT_DIR) / pdf_id / "result.json"
    if not output_path.exists():
        return JSONResponse(
            status_code=404,
            content={"detail": f"No results found for PDF ID: {pdf_id}"}
        )

    try:
        with open(output_path, "r") as f:
            result = json.load(f)
        return result
    except Exception as e:
        logger.error(f"Error reading results: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error reading results: {str(e)}")

@app.post("/api/extract-qdrant-ready")
async def extract_qdrant_ready(
    pdf_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    api_key: Optional[str] = Form(None),
    openai_client: AsyncOpenAI = Depends(get_openai_client)
):
    """
    Extract content and return Qdrant-ready chunks.

    Parameters:
    - pdf_id: Optional identifier for the PDF (will be generated if not provided)
    - file: PDF file to process
    - api_key: Optional API key for authentication

    Returns:
    - Qdrant-ready chunks
    """
    # Verify API key if set
    await verify_api_key(api_key)

    # Extract document
    extract_result = await extract_document(
        background_tasks=BackgroundTasks(),
        pdf_id=pdf_id,
        file=file,
        api_key=api_key,
        openai_client=openai_client
    )

    # Process for Qdrant
    processor = APIDocumentProcessor(
        pdf_id=extract_result["pdf_id"],
        config={},
        openai_client=openai_client
    )

    qdrant_chunks = processor.get_qdrant_ready_chunks(extract_result)

    return {
        "pdf_id": extract_result["pdf_id"],
        "qdrant_chunks": qdrant_chunks
    }

@app.post("/api/extract-mongodb-ready")
async def extract_mongodb_ready(
    pdf_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    api_key: Optional[str] = Form(None),
    openai_client: AsyncOpenAI = Depends(get_openai_client)
):
    """
    Extract content and return MongoDB-ready document.

    Parameters:
    - pdf_id: Optional identifier for the PDF (will be generated if not provided)
    - file: PDF file to process
    - api_key: Optional API key for authentication

    Returns:
    - MongoDB-ready document
    """
    # Verify API key if set
    await verify_api_key(api_key)

    # Extract document
    extract_result = await extract_document(
        background_tasks=BackgroundTasks(),
        pdf_id=pdf_id,
        file=file,
        api_key=api_key,
        openai_client=openai_client
    )

    # Process for MongoDB
    processor = APIDocumentProcessor(
        pdf_id=extract_result["pdf_id"],
        config={},
        openai_client=openai_client
    )

    mongodb_doc = processor.get_mongodb_ready_document(extract_result)

    return {
        "pdf_id": extract_result["pdf_id"],
        "mongodb_document": mongodb_doc
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
