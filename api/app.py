"""
Corrected app.py implementation with:
1. Proper static file serving for assets
2. Rich metadata enrichment for Supabase
3. Enhanced multi-modal extraction endpoint
"""
import logging
import os
import uuid
from typing import List, Optional, Union

from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

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

# Create output directory if it doesn't exist
output_dir = "output"
os.makedirs(output_dir, exist_ok=True)

# Mount static files for serving images and assets
# This allows accessing images via /output/[pdf_id]/assets/images/[image_id].png
app.mount("/output", StaticFiles(directory=output_dir), name="output")

@app.get("/")
async def root():
    """Root endpoint to check if API is running"""
    return {"status": "Docling Extractor API is running"}

@app.post("/api/extract")
async def extract_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    file_id: Optional[str] = Form(None),
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
        doc_id = file_id or f"doc_{uuid.uuid4().hex[:8]}"

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
            "chunks": result.get("text_chunks", []),
            "procedures": result.get("procedures", []),
            "parameters": result.get("parameters", []),
            "metadata": {
                "page_count": result.get("document_metadata", {}).get("page_count", 0),
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
    Returns chunks formatted for Supabase vector store insertion with rich metadata.
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

        # Create processor
        processor = APIDocumentProcessor(
            pdf_id=doc_id,
            config=config
        )

        # Process document
        result = await processor.process_document(content)

        # Format documents for Supabase chunks table WITH RICH METADATA
        supabase_docs = []
        for chunk in result.get("text_chunks", []):
            # Add content type detection
            content = chunk.get("content", "")
            has_code = "```" in content or "`" in content
            has_table = "|" in content and "-" in content
            has_image = "![" in content or "<!-- image -->" in content

            # Enrich metadata for better retrieval
            metadata = chunk.get("metadata", {})
            metadata.update({
                "has_code": has_code,
                "has_table": has_table,
                "has_image": has_image,
                "content_types": ["text"] +
                                (["code"] if has_code else []) +
                                (["table"] if has_table else []) +
                                (["image"] if has_image else [])
            })

            supabase_docs.append({
                "content": content,
                "metadata": metadata
            })

        # Create image references for Supabase
        images = result.get("images", [])
        for image in images:
            # Ensure image path is accessible via static file serving
            if "path" in image and image["path"]:
                # Convert local path to API-accessible URL
                image_filename = os.path.basename(image["path"])
                image["api_path"] = f"/output/{doc_id}/assets/images/{image_filename}"

        # Create table references for Supabase
        tables = result.get("tables", [])
        for table in tables:
            # Ensure CSV path is accessible via static file serving
            if "csv_path" in table and table["csv_path"]:
                # Convert local path to API-accessible URL
                csv_filename = os.path.basename(table["csv_path"])
                table["api_csv_path"] = f"/output/{doc_id}/assets/tables/{csv_filename}"

        # Return Supabase-ready format with rich metadata
        return {
            "file_id": doc_id,
            "file_title": doc_title,
            "document_count": len(supabase_docs),
            "documents": supabase_docs,
            "procedures": result.get("procedures", []),
            "parameters": result.get("parameters", []),
            "images": images,
            "tables": tables,
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
