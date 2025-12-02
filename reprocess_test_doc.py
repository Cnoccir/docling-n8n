"""Direct reprocessing of test document for Phase 2 verification."""
import os
import sys
import time
import uuid
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Add paths
sys.path.insert(0, str(Path(__file__).parent / 'backend'))
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from database.db_client import DatabaseClient


def find_pdf_for_document(doc_id: str) -> str:
    """Find the original PDF file for a document."""
    # Check common upload locations
    upload_dir = Path("C:/Users/tech/Projects/docling-n8n/uploads")
    
    db = DatabaseClient()
    try:
        with db.conn.cursor() as cur:
            cur.execute("SELECT filename FROM document_index WHERE id = %s", (doc_id,))
            row = cur.fetchone()
            if row:
                filename = row[0]
                # Try to find file
                possible_paths = [
                    upload_dir / filename,
                    upload_dir / filename.replace('.mp4', '.pdf'),  # Video transcripts
                    Path(f"C:/Users/tech/Projects/docling-n8n/transcripts/{filename.replace('.mp4', '.pdf')}"),
                ]
                
                for path in possible_paths:
                    if path.exists():
                        return str(path)
    finally:
        db.conn.close()
    
    return None


def trigger_reprocess(doc_id: str, pdf_path: str):
    """Trigger document reprocessing via direct function call."""
    from backend.app.tasks.ingest import process_document
    
    # Create a new job ID
    job_id = str(uuid.uuid4())
    
    db = DatabaseClient()
    try:
        # Get document info
        with db.conn.cursor() as cur:
            cur.execute("""
                SELECT filename, document_type, tags, categories
                FROM document_index 
                WHERE id = %s
            """, (doc_id,))
            row = cur.fetchone()
            if not row:
                print(f"❌ Document {doc_id} not found")
                return False
            
            filename, doc_type, tags, categories = row
        
        # Create job record
        with db.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO jobs (id, status, progress, current_step, created_at)
                VALUES (%s, 'pending', 0, 'queued', NOW())
            """, (job_id,))
            db.conn.commit()
        
        print(f"📝 Job created: {job_id}")
        print(f"📄 Reprocessing: {filename}")
        print(f"📁 PDF path: {pdf_path}")
        print(f"\n⏳ Starting ingestion with topic tagging...")
        print("=" * 80)
        
        # Call process_document directly (synchronous for testing)
        # This bypasses Celery queue but uses same code path
        class MockTask:
            class request:
                id = job_id
        
        mock_task = MockTask()
        
        process_document(
            mock_task,
            job_id=job_id,
            file_path=pdf_path,
            doc_id=doc_id,
            filename=filename,
            document_type=doc_type,
            tags=tags or [],
            categories=categories or [],
            reprocess=True
        )
        
        print("=" * 80)
        print(f"✅ Reprocessing complete!")
        return True
    
    except Exception as e:
        print(f"❌ Error during reprocessing: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        db.conn.close()


def main():
    """Main reprocessing workflow."""
    print("=" * 80)
    print("PHASE 2: Reprocess Document with Topic Tagging")
    print("=" * 80)
    
    # Find test document
    doc_id = "video_hV9-1RgkTk8"  # System Database TridiumTalk
    
    print(f"\n🔍 Looking for PDF for document: {doc_id}")
    pdf_path = find_pdf_for_document(doc_id)
    
    if not pdf_path:
        print(f"❌ PDF file not found for document {doc_id}")
        print(f"   Please ensure the file is in uploads/ or transcripts/")
        return False
    
    print(f"✅ Found PDF: {pdf_path}")
    
    # Trigger reprocessing
    success = trigger_reprocess(doc_id, pdf_path)
    
    if success:
        # Verify topics
        print(f"\n📊 Verifying topic tagging...")
        from test_phase2_reprocess import verify_topics
        verify_topics(doc_id)
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
