"""Celery task for document ingestion."""
import os
import sys
import time
import traceback
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Add src to path for ingestion code
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from app.tasks.celery_app import celery_app
from app.utils.checkpoint import ProcessingCheckpoint
from database.db_client import DatabaseClient
from ingestion.docling_parser_sdk import DoclingSDKParser
from ingestion.hierarchy_builder_v2 import HierarchyBuilderV2
from ingestion.image_processor import ImageProcessor
from ingestion.table_processor import TableProcessor
from ingestion.document_summarizer import DocumentSummarizer
from utils.embeddings import EmbeddingGenerator
from gdrive_uploader import GDriveUploader
import hashlib


def compute_file_hash(file_path: str) -> str:
    """Compute SHA256 hash of file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for block in iter(lambda: f.read(4096), b''):
            sha256.update(block)
    return sha256.hexdigest()


def update_job_progress(db: DatabaseClient, job_id: str, progress: int, current_step: str):
    """Update job progress in database with fresh connection per update."""
    try:
        # Use a fresh cursor for each update to avoid connection timeouts
        with db.conn.cursor() as cur:
            cur.execute("""
                UPDATE jobs
                SET progress = %s, current_step = %s, updated_at = NOW()
                WHERE id = %s
            """, (progress, current_step, job_id))
            db.conn.commit()
    except Exception as e:
        print(f"⚠️  Failed to update progress: {e}")
        # Don't fail the entire task if progress update fails
        pass


@celery_app.task(bind=True, name='app.tasks.ingest.process_document')
def process_document(self, job_id: str, file_path: str, doc_id: str, filename: str,
                    document_type: str = None, tags: list = None, categories: list = None,
                    reprocess: bool = False):
    """
    Process a document through the ingestion pipeline.

    Args:
        job_id: Job ID in database
        file_path: Path to uploaded PDF
        doc_id: Document ID
        filename: Original filename
        document_type: Type of document
        tags: List of tags
        categories: List of categories
        reprocess: Allow reprocessing if document exists (creates new version)
    """
    start_time = time.time()
    worker_id = os.getenv('WORKER_ID', 'unknown')

    # Initialize checkpoint manager
    checkpoint = ProcessingCheckpoint(job_id)

    # Check if resuming from checkpoint
    resuming = checkpoint.exists()
    if resuming:
        print(f"🔄 RESUMING from checkpoint:")
        print(checkpoint.get_state_summary())

    db = DatabaseClient()

    try:
        # Update job status to processing
        with db.conn.cursor() as cur:
            cur.execute("""
                UPDATE jobs
                SET status = 'processing',
                    started_at = NOW(),
                    task_id = %s,
                    worker_id = %s
                WHERE id = %s
            """, (self.request.id, worker_id, job_id))
            db.conn.commit()
        
        # Validate file
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_size = os.path.getsize(file_path)
        file_hash = compute_file_hash(file_path)
        
        # Check for duplicates
        existing = db.check_document_exists(file_hash)
        if existing and not reprocess:
            raise ValueError(f"Document already exists: {existing['id']}. Use reprocess=true to delete and reprocess.")

        # If reprocessing, DELETE the old document and all related data
        if existing and reprocess:
            old_doc_id = existing['id']
            print(f"🗑️  Deleting old document: {old_doc_id}")

            # Delete all related data (chunks, images, tables, hierarchy)
            with db.conn.cursor() as cur:
                # Delete chunks
                cur.execute("DELETE FROM chunks WHERE doc_id = %s", (old_doc_id,))
                chunks_deleted = cur.rowcount
                print(f"   ✓ Deleted {chunks_deleted} chunks")

                # Delete images
                cur.execute("DELETE FROM images WHERE doc_id = %s", (old_doc_id,))
                images_deleted = cur.rowcount
                print(f"   ✓ Deleted {images_deleted} images")

                # Delete tables
                cur.execute("DELETE FROM document_tables WHERE doc_id = %s", (old_doc_id,))
                tables_deleted = cur.rowcount
                print(f"   ✓ Deleted {tables_deleted} tables")

                # Delete hierarchy
                cur.execute("DELETE FROM document_hierarchy WHERE doc_id = %s", (old_doc_id,))
                print(f"   ✓ Deleted hierarchy")

                # Delete document index (with version)
                cur.execute("DELETE FROM document_index WHERE id = %s", (old_doc_id,))
                print(f"   ✓ Deleted document index")

                db.conn.commit()

            print(f"✅ Old document deleted, reprocessing as fresh document")
            # Use same document ID to maintain consistency
            doc_id = old_doc_id
        
        # Initialize components
        parser = DoclingSDKParser()
        hierarchy_builder = HierarchyBuilderV2()
        image_processor = ImageProcessor()
        table_processor = TableProcessor()
        summarizer = DocumentSummarizer()
        embedding_gen = EmbeddingGenerator()

        # Step 1: Parse PDF (0-15%) - CHECKPOINT
        doc_json = checkpoint.get_parsed_doc()
        if doc_json:
            print("✓ Using cached parsed document (saved parsing time)")
            update_job_progress(db, job_id, 15, "parsing")
        else:
            update_job_progress(db, job_id, 5, "parsing")
            doc_json = parser.parse_pdf(file_path)
            checkpoint.save_parsed_doc(doc_json)  # Save to checkpoint
            update_job_progress(db, job_id, 15, "parsing")

        # Define title from filename (used for summary and Google Drive)
        title = os.path.splitext(filename)[0]

        # Step 2: Generate summary (15-25%) - CHECKPOINT
        cached_summary = checkpoint.get_summary()
        if cached_summary:
            summary, summary_tokens = cached_summary
            print(f"✓ Using cached summary (saved {summary_tokens} tokens)")
            update_job_progress(db, job_id, 25, "summarizing")
        else:
            update_job_progress(db, job_id, 15, "summarizing")
            summary, summary_tokens = summarizer.generate_document_summary(doc_json, title)
            checkpoint.save_summary(summary, summary_tokens)  # Save to checkpoint
            update_job_progress(db, job_id, 25, "summarizing")

        # Step 2.5: Upload to Google Drive (if enabled)
        gdrive_info = None
        if os.getenv('ENABLE_GDRIVE_UPLOAD', 'false').lower() == 'true':
            try:
                print(f"\n☁️  Uploading to Google Drive...")
                gdrive = GDriveUploader()
                gdrive_info = gdrive.upload_pdf(
                    pdf_path=file_path,
                    doc_title=title,
                    doc_id=doc_id
                )
                print(f"   ✅ Uploaded to Google Drive")
                print(f"   📁 File ID: {gdrive_info['file_id']}")
                print(f"   🔗 Link: {gdrive_info['link']}")
            except Exception as e:
                print(f"   ⚠️  Google Drive upload failed: {e}")
                print(f"   Continuing without Google Drive link...")
                traceback.print_exc()  # Print full traceback for debugging
                gdrive_info = None

        # Create document index with Google Drive info
        db.create_document_index(
            doc_id=doc_id,
            title=title,
            filename=filename,
            file_hash=file_hash,
            file_size_bytes=file_size,
            document_type=document_type,
            summary=summary,
            tags=tags or [],
            categories=categories or [],
            gdrive_file_id=gdrive_info['file_id'] if gdrive_info else None,
            gdrive_link=gdrive_info['link'] if gdrive_info else None,
            gdrive_folder_id=gdrive_info.get('folder_id') if gdrive_info else None
        )
        update_job_progress(db, job_id, 25, "summarizing")
        
        # Step 3: Build hierarchy (25-40%) - CHECKPOINT
        if checkpoint.is_hierarchy_built():
            print("✓ Hierarchy already built (skipping)")
            hierarchy, chunks, page_index, asset_index = hierarchy_builder.build(doc_json, doc_id, pdf_path=file_path)
            update_job_progress(db, job_id, 40, "building_hierarchy")
        else:
            update_job_progress(db, job_id, 25, "building_hierarchy")
            hierarchy, chunks, page_index, asset_index = hierarchy_builder.build(doc_json, doc_id, pdf_path=file_path)
            checkpoint.save_hierarchy()
            update_job_progress(db, job_id, 40, "building_hierarchy")

        # Step 4: Process images (40-60%) - CHECKPOINT WITH GRANULAR PROGRESS
        update_job_progress(db, job_id, 40, "processing_images")

        # Get already processed images from checkpoint
        processed_image_indices, processed_images_data = checkpoint.get_processed_images()

        # Progress callback for granular updates
        def image_progress_callback(current, total, step_name):
            # Calculate sub-progress within 40-60% range
            base_progress = 40
            progress_range = 20
            sub_progress = (current / max(total, 1)) * progress_range
            new_progress = int(base_progress + sub_progress)
            update_job_progress(db, job_id, new_progress, step_name)

        # Process images (will skip already processed ones)
        new_images = image_processor.process_images(
            doc_json,
            doc_id,
            skip_indices=processed_image_indices,
            progress_callback=image_progress_callback
        )

        # Save each new image to checkpoint
        for img in new_images:
            img_idx = int(img.id.split('_')[-1])  # Extract index from ID
            checkpoint.save_image_result(img_idx, {
                's3_url': img.s3_url,
                'summary': img.basic_summary,
                'image_type': img.image_type,
                'tokens': img.tokens_used,
                'page_number': img.page_number,
                'bbox': img.bbox,
                'caption': img.caption
            })

        # Reconstruct full images list from checkpoint + new images
        if processed_images_data:
            print(f"✓ Restored {len(processed_images_data)} previously processed images")
            # Combine cached images with new ones
            from ingestion.image_processor import ImageReference
            all_images = []

            # Add cached images
            for idx_str, img_data in processed_images_data.items():
                img_ref = ImageReference(
                    id=f"{doc_id}_img_{img_data['page_number']}_{int(idx_str):02d}",
                    doc_id=doc_id,
                    page_number=img_data['page_number'],
                    bbox=img_data.get('bbox'),
                    s3_url=img_data['s3_url'],
                    caption=img_data.get('caption'),
                    image_type=img_data.get('image_type'),
                    basic_summary=img_data.get('summary'),
                    tokens_used=img_data.get('tokens', 0)
                )
                all_images.append(img_ref)

            # Add new images
            all_images.extend(new_images)
            images = all_images
        else:
            images = new_images

        update_job_progress(db, job_id, 60, "processing_images")
        
        # Step 5: Process tables (60-70%)
        update_job_progress(db, job_id, 60, "processing_tables")
        tables = table_processor.process_tables(doc_json, doc_id)
        update_job_progress(db, job_id, 70, "processing_tables")
        
        # Step 6: Generate embeddings (70-85%)
        update_job_progress(db, job_id, 70, "generating_embeddings")
        chunk_texts = [c.content for c in chunks]
        embeddings = embedding_gen.generate_embeddings(chunk_texts)
        update_job_progress(db, job_id, 85, "generating_embeddings")
        
        # Step 7: Save to database (85-100%)
        update_job_progress(db, job_id, 85, "saving_to_database")
        
        # Save hierarchy
        db.save_hierarchy(hierarchy, page_index, asset_index)
        
        # Save chunks with embeddings
        db.save_chunks(chunks, embeddings)
        
        # Save images with section_id from asset_index
        if images:
            image_dicts = []
            for img in images:
                # Extract section_id from asset_index
                section_id = None
                if asset_index and 'images' in asset_index:
                    img_asset = asset_index['images'].get(img.id, {})
                    section_id = img_asset.get('section_id')

                image_dicts.append({
                    'id': img.id,
                    'doc_id': img.doc_id,
                    'page_number': img.page_number,
                    'bbox': img.bbox,
                    's3_url': img.s3_url,
                    'caption': img.caption,
                    'ocr_text': img.ocr_text,
                    'image_type': img.image_type,
                    'basic_summary': img.basic_summary,
                    'detailed_description': img.detailed_description,
                    'tokens_used': img.tokens_used,
                    'description_generated': img.description_generated,
                    'section_id': section_id  # NEW: Map from asset_index
                })
            db.save_images(image_dicts)
        
        # Save tables with section_id from asset_index
        if tables:
            table_dicts = []
            for tbl in tables:
                # Extract section_id from asset_index
                section_id = None
                if asset_index and 'tables' in asset_index:
                    tbl_asset = asset_index['tables'].get(tbl['id'], {})
                    section_id = tbl_asset.get('section_id')

                # Add section_id to table dict
                tbl_with_section = dict(tbl)  # Create copy
                tbl_with_section['section_id'] = section_id  # NEW: Map from asset_index
                table_dicts.append(tbl_with_section)

            db.save_tables(table_dicts)
        
        # Calculate metrics
        processing_duration = time.time() - start_time
        image_tokens = sum(img.tokens_used for img in images)
        embedding_tokens = len(chunks) * 10
        tokens_used = summary_tokens + image_tokens + embedding_tokens
        ingestion_cost = (tokens_used * 0.00000015)
        
        # Update document status
        db.update_document_status(
            doc_id=doc_id,
            status='completed',
            summary=summary,
            total_pages=len(hierarchy.pages),
            total_chunks=len(chunks),
            total_sections=len(hierarchy.sections),
            total_images=len(images),
            total_tables=len(tables),
            processing_duration=processing_duration,
            ingestion_cost=ingestion_cost,
            tokens_used=tokens_used
        )
        
        # Update job to completed
        with db.conn.cursor() as cur:
            cur.execute("""
                UPDATE jobs 
                SET status = 'completed',
                    progress = 100,
                    completed_at = NOW(),
                    doc_id = %s,
                    total_pages = %s,
                    total_chunks = %s,
                    total_images = %s,
                    total_tables = %s,
                    tokens_used = %s,
                    ingestion_cost_usd = %s
                WHERE id = %s
            """, (doc_id, len(hierarchy.pages), len(chunks), len(images), 
                  len(tables), tokens_used, ingestion_cost, job_id))
            db.conn.commit()
        
        # Clean up temp file
        try:
            os.remove(file_path)
        except:
            pass

        # Delete checkpoint on successful completion
        checkpoint.delete()
        print("✅ Checkpoint deleted (processing completed successfully)")

        update_job_progress(db, job_id, 100, "completed")

        return {
            "status": "completed",
            "doc_id": doc_id,
            "pages": len(hierarchy.pages),
            "chunks": len(chunks),
            "images": len(images),
            "tables": len(tables),
            "duration": processing_duration,
            "cost": ingestion_cost
        }
    
    except Exception as e:
        error_message = str(e)
        error_traceback = traceback.format_exc()
        
        # Update job to failed
        with db.conn.cursor() as cur:
            cur.execute("""
                UPDATE jobs 
                SET status = 'failed',
                    completed_at = NOW(),
                    error_message = %s,
                    error_traceback = %s
                WHERE id = %s
            """, (error_message, error_traceback, job_id))
            db.conn.commit()
        
        # Update document status if it was created
        try:
            db.update_document_status(
                doc_id=doc_id,
                status='failed',
                error_message=error_message
            )
        except:
            pass
        
        # Clean up temp file
        try:
            os.remove(file_path)
        except:
            pass
        
        raise
