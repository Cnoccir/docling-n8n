import logging
import os
import uuid
from typing import List, Optional, Union

from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from document_processor.adapter import APIDocumentProcessor

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Docling Extractor for n8n",
    description="Enhanced document extraction API for n8n RAG workflows",
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

@app.get("/")
async def root():
    """Root endpoint to check if API is running"""
    return {"status": "Docling Extractor API is running"}

@app.post("/api/extract")
async def extract_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    extract_technical_terms: bool = Form(True),
    extract_procedures: bool = Form(True),
    extract_relationships: bool = Form(True),
    process_images: bool = Form(True),
    process_tables: bool = Form(True),
    chunk_size: int = Form(500),
    chunk_overlap: int = Form(100),
):
    """
    Extract content from a document with enhanced metadata.
    Returns format compatible with general use cases.
    """
    try:
        # Generate a unique ID for the document
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"

        # Read file content
        content = await file.read()

        # Create processing config
        config = {
            "extract_technical_terms": extract_technical_terms,
            "extract_procedures": extract_procedures,
            "extract_relationships": extract_relationships,
            "process_images": process_images,
            "process_tables": process_tables,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }

        # Create processor
        processor = APIDocumentProcessor(
            pdf_id=doc_id,
            config=config
        )

        # Process document
        result = await processor.process_document(content)

        # Return standardized result
        return {
            "pdf_id": doc_id,
            "filename": file.filename,
            "markdown": result.get("markdown_content", ""),
            "technical_terms": result.get("technical_terms", []),
            "chunks": result.get("chunks", []),
            "procedures": result.get("procedures", []),
            "parameters": result.get("parameters", []),
            "metadata": {
                "page_count": result.get("page_count", 0),
                "domain_category": result.get("domain_category", "general"),
            }
        }

    except Exception as e:
        logger.error(f"Error processing document: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing document: {str(e)}")

@app.post("/api/extract-supabase-ready")
async def extract_supabase_ready(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    file_id: Optional[str] = Form(None),
    file_title: Optional[str] = Form(None),
    extract_technical_terms: bool = Form(True),
    extract_procedures: bool = Form(True),
    extract_relationships: bool = Form(True),
    process_images: bool = Form(True),
    process_tables: bool = Form(True),
    chunk_size: int = Form(500),
    chunk_overlap: int = Form(100),
):
    """
    Extract content from a document and format for direct integration with the n8n RAG template.
    Returns chunks formatted for Supabase vector store insertion.
    """
    try:
        # Use provided file_id or generate a new one
        doc_id = file_id or f"doc_{uuid.uuid4().hex[:8]}"
        doc_title = file_title or file.filename

        # Read file content
        content = await file.read()

        # Create processing config
        config = {
            "extract_technical_terms": extract_technical_terms,
            "extract_procedures": extract_procedures,
            "extract_relationships": extract_relationships,
            "process_images": process_images,
            "process_tables": process_tables,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }

        # Create processor with enhanced capabilities
        processor = APIDocumentProcessor(
            pdf_id=doc_id,
            config=config
        )

        # Process document with comprehensive extraction
        result = await processor.process_document(content)

        # Format documents for Supabase chunks table
        supabase_docs = []
        for chunk in result.get("text_chunks", []):
            supabase_docs.append({
                "content": chunk.get("content", ""),
                "metadata": chunk.get("metadata", {})
            })

        # Return comprehensive Supabase-ready format
        return {
            "pdf_id": doc_id,
            "file_title": doc_title,
            "document_count": len(supabase_docs),
            "documents": supabase_docs,
            "procedures": result.get("procedures", []),
            "images": result.get("images", []),
            "tables": result.get("tables", []),
            "technical_terms": result.get("technical_terms", []),
            "domain_category": result.get("domain_category", "general"),
            "document_metadata": result.get("document_metadata", {})
        }

    except Exception as e:
        logger.error(f"Error processing document for Supabase: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing document: {str(e)}")
        
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
