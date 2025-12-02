"""Celery task for YouTube video ingestion - mirrors PDF ingestion pipeline."""
import os
import sys
import time
import traceback
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from app.tasks.celery_app import celery_app
from database.db_client import DatabaseClient
from ingestion.youtube_processor import YouTubeProcessor
from ingestion.image_processor import ImageProcessor  # REUSE!
from ingestion.document_summarizer import DocumentSummarizer  # REUSE!
from utils.embeddings import EmbeddingGenerator  # REUSE!


def update_job_progress(db: DatabaseClient, job_id: str, progress: int, current_step: str):
    """Update job progress in database."""
    try:
        with db.conn.cursor() as cur:
            cur.execute("""
                UPDATE jobs
                SET progress = %s, current_step = %s, updated_at = NOW()
                WHERE id = %s
            """, (progress, current_step, job_id))
            db.conn.commit()
    except Exception as e:
        print(f"⚠️  Failed to update progress: {e}")


@celery_app.task(bind=True, name='app.tasks.ingest_youtube.process_youtube_video')
def process_youtube_video(
    self,
    job_id: str,
    url: str,
    video_id: str,
    tags: list = None,
    categories: list = None
):
    """
    Process YouTube video through ingestion pipeline.

    Mirrors process_document() but for videos.

    Args:
        job_id: Job ID in database
        url: YouTube video URL
        video_id: Generated video ID (video_<youtube_id>)
        tags: List of tags
        categories: List of categories
    """
    start_time = time.time()
    worker_id = os.getenv('WORKER_ID', 'unknown')

    db = DatabaseClient()
    yt_processor = YouTubeProcessor()
    image_processor = ImageProcessor()  # Reuse for screenshots!
    summarizer = DocumentSummarizer()
    embedding_gen = EmbeddingGenerator()

    # Manual cost tracking (CostTracker is for queries, not ingestion)
    total_cost = 0.0
    total_tokens = 0

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

        print(f"\n{'='*60}")
        print(f"🎬 PROCESSING YOUTUBE VIDEO")
        print(f"{'='*60}")
        print(f"Job ID: {job_id}")
        print(f"Video ID: {video_id}")
        print(f"URL: {url}")
        print(f"Worker: {worker_id}")
        print(f"{'='*60}\n")

        # ============================================================
        # STEP 1: Download video and extract metadata (10%)
        # ============================================================
        update_job_progress(db, job_id, 10, 'Downloading video')
        print(f"[STEP 1/10] Downloading video...")

        metadata = yt_processor.download_video(url)

        # Create document index entry
        db.create_document_index(
            doc_id=video_id,
            title=metadata['title'],
            filename=f"{metadata['youtube_id']}.mp4",
            file_hash=metadata['youtube_id'],  # Use YouTube ID as hash
            file_size_bytes=0,
            document_type='video',
            tags=tags,
            categories=categories
        )

        # Update with YouTube-specific metadata
        with db.conn.cursor() as cur:
            cur.execute("""
                UPDATE document_index
                SET source_type = 'youtube',
                    source_url = %s,
                    youtube_id = %s,
                    channel_name = %s,
                    duration_seconds = %s,
                    summary = %s
                WHERE id = %s
            """, (
                url,
                metadata['youtube_id'],
                metadata['channel'],
                metadata['duration'],
                metadata['description'][:500] if metadata['description'] else None,
                video_id
            ))
            db.conn.commit()

        print(f"✓ Video downloaded: {metadata['title']}")
        print(f"  Duration: {metadata['duration']}s ({metadata['duration']/60:.1f} min)")
        print(f"  Channel: {metadata['channel']}")

        # ============================================================
        # STEP 2: Extract audio (20%)
        # ============================================================
        update_job_progress(db, job_id, 20, 'Extracting audio')
        print(f"\n[STEP 2/10] Extracting audio...")

        audio_path = yt_processor.extract_audio(metadata['filepath'])
        print(f"✓ Audio extracted: {audio_path}")

        # ============================================================
        # STEP 3: Transcribe with Whisper (40%)
        # ============================================================
        update_job_progress(db, job_id, 40, 'Transcribing audio')
        print(f"\n[STEP 3/10] Transcribing with Whisper API...")

        segments = yt_processor.transcribe(audio_path, metadata['youtube_id'])
        print(f"✓ Transcribed {len(segments)} segments")

        # Track Whisper API cost ($0.006 per minute)
        audio_duration_minutes = metadata['duration'] / 60
        whisper_cost = audio_duration_minutes * 0.006
        total_cost += whisper_cost
        print(f"  Transcription cost: ${whisper_cost:.4f}")

        # ============================================================
        # STEP 4: Extract screenshots (55%)
        # ============================================================
        update_job_progress(db, job_id, 55, 'Extracting screenshots')
        print(f"\n[STEP 4/10] Extracting screenshots...")

        # Use hybrid method for best coverage
        screenshots = yt_processor.extract_screenshots(
            metadata['filepath'],
            metadata['youtube_id'],
            method='hybrid'  # Scene changes + interval
        )
        print(f"✓ Extracted {len(screenshots)} screenshots")

        # ============================================================
        # STEP 5: Detect chapters (60%)
        # ============================================================
        update_job_progress(db, job_id, 60, 'Detecting chapters')
        print(f"\n[STEP 5/10] Detecting chapters with LLM...")

        chapters = yt_processor.detect_chapters(segments, metadata['title'])
        print(f"✓ Detected {len(chapters)} chapters")

        # ============================================================
        # STEP 6: Convert to PDF-like format (65%)
        # ============================================================
        update_job_progress(db, job_id, 65, 'Converting to unified format')
        print(f"\n[STEP 6/10] Converting to unified format...")

        video_data = yt_processor.convert_to_pdf_format(
            metadata, segments, screenshots, chapters
        )
        print(f"✓ Converted to {len(video_data['pages'])} time-based pages")

        # ============================================================
        # STEP 7: Process screenshots (REUSE ImageProcessor!) (75%)
        # ============================================================
        update_job_progress(db, job_id, 75, 'Processing screenshots')
        print(f"\n[STEP 7/10] Processing screenshots...")

        processed_screenshots = 0
        screenshot_data = []  # Collect processed screenshots for chunk linking

        for idx, screenshot in enumerate(screenshots):
            try:
                # Process exactly like PDF images!
                image_id = image_processor.process_and_save_image(
                    image_path=screenshot['filepath'],
                    doc_id=video_id,
                    page_number=screenshot.get('page_no', int(screenshot['timestamp'] / 60)),
                    image_type='screenshot',
                    timestamp=screenshot['timestamp'],  # Add timestamp!
                    image_index=idx  # Add image_index for S3 upload
                )
                processed_screenshots += 1

                # Store screenshot data for chunk linking
                screenshot_data.append({
                    'timestamp': screenshot['timestamp'],
                    'image_id': image_id
                })

                # Update progress
                progress = 75 + int((processed_screenshots / len(screenshots)) * 10)
                update_job_progress(
                    db, job_id, progress,
                    f'Processing screenshots ({processed_screenshots}/{len(screenshots)})'
                )

            except Exception as e:
                print(f"⚠️  Failed to process screenshot at {screenshot['timestamp']}s: {e}")
                import traceback
                traceback.print_exc()

        print(f"✓ Processed {processed_screenshots}/{len(screenshots)} screenshots")

        # ============================================================
        # STEP 8: Create chunks from transcript (85%)
        # ============================================================
        update_job_progress(db, job_id, 85, 'Creating transcript chunks')
        print(f"\n[STEP 8/10] Creating chunks from transcript...")

        # Combine segments into ~60-second chunks
        chunks = []
        current_chunk = []
        current_duration = 0
        chunk_duration_target = 60  # 60 seconds per chunk

        for segment in segments:
            duration = segment['end_time'] - segment['start_time']

            if current_duration + duration > chunk_duration_target and current_chunk:
                # Finalize current chunk
                chunk_start = current_chunk[0]['start_time']
                chunk_end = current_chunk[-1]['end_time']
                chunk_text = ' '.join([s['text'] for s in current_chunk])
                chunk_page = int(chunk_start / 60)

                # Assign to chapter
                chunk_chapter = None
                for chapter in chapters:
                    if chapter['start_time'] <= chunk_start < chapter['end_time']:
                        chunk_chapter = chapter['title']
                        break

                chunks.append({
                    'content': chunk_text,
                    'page_number': chunk_page,
                    'timestamp_start': chunk_start,
                    'timestamp_end': chunk_end,
                    'video_url_with_timestamp': f"{url}&t={int(chunk_start)}s",
                    'section_path': [chunk_chapter] if chunk_chapter else ['Untitled'],
                    'metadata': {
                        'chapter': chunk_chapter,
                        'segment_count': len(current_chunk)
                    }
                })

                current_chunk = []
                current_duration = 0

            current_chunk.append(segment)
            current_duration += duration

        # Add last chunk
        if current_chunk:
            chunk_start = current_chunk[0]['start_time']
            chunk_end = current_chunk[-1]['end_time']
            chunk_text = ' '.join([s['text'] for s in current_chunk])
            chunk_page = int(chunk_start / 60)

            chunk_chapter = None
            for chapter in chapters:
                if chapter['start_time'] <= chunk_start < chapter['end_time']:
                    chunk_chapter = chapter['title']
                    break

            chunks.append({
                'content': chunk_text,
                'page_number': chunk_page,
                'timestamp_start': chunk_start,
                'timestamp_end': chunk_end,
                'video_url_with_timestamp': f"{url}&t={int(chunk_start)}s",
                'section_path': [chunk_chapter] if chunk_chapter else ['Untitled'],
                'metadata': {
                    'chapter': chunk_chapter,
                    'segment_count': len(current_chunk)
                }
            })

        print(f"✓ Created {len(chunks)} chunks")

        # ============================================================
        # STEP 9: Generate embeddings (90%)
        # ============================================================
        update_job_progress(db, job_id, 90, 'Generating embeddings')
        print(f"\n[STEP 9/10] Generating embeddings...")

        chunk_texts = [chunk['content'] for chunk in chunks]
        embeddings = embedding_gen.generate_embeddings(chunk_texts)

        # Attach embeddings
        for chunk, embedding in zip(chunks, embeddings):
            chunk['embedding'] = embedding

        print(f"✓ Generated {len(embeddings)} embeddings")

        # Track embedding cost (text-embedding-3-small: $0.02 per 1M tokens)
        # Estimate ~100 tokens per chunk on average
        estimated_embedding_tokens = len(chunks) * 100
        embedding_cost = (estimated_embedding_tokens / 1_000_000) * 0.02
        total_cost += embedding_cost
        total_tokens += estimated_embedding_tokens
        print(f"  Embedding cost: ${embedding_cost:.4f} (~{estimated_embedding_tokens:,} tokens)")

        # ============================================================
        # STEP 10: Save to database (95%)
        # ============================================================
        update_job_progress(db, job_id, 95, 'Saving to database')
        print(f"\n[STEP 10/10] Saving to database...")

        # Save chunks
        chunk_count = 0
        for i, chunk in enumerate(chunks):
            chunk_id = f"{video_id}_chunk_{i:06d}"

            with db.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chunks (
                        id, doc_id, content, embedding,
                        page_number, timestamp_start, timestamp_end,
                        video_url_with_timestamp, section_path, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    chunk_id,
                    video_id,
                    chunk['content'],
                    chunk['embedding'],
                    chunk['page_number'],
                    chunk['timestamp_start'],
                    chunk['timestamp_end'],
                    chunk['video_url_with_timestamp'],
                    chunk['section_path'],  # Pass as list (Postgres array type)
                    json.dumps(chunk.get('metadata', {}))  # Convert dict to JSON
                ))
                db.conn.commit()
                chunk_count += 1

        print(f"✓ Saved {chunk_count} chunks")

        # Link screenshots to chunks by timestamp (NEW - enable multimodal RAG!)
        print(f"🔗 Linking screenshots to chunks...")
        linked_count = 0

        for screenshot in screenshot_data:
            timestamp = screenshot['timestamp']
            image_id = screenshot['image_id']

            # Find chunk(s) that overlap with this timestamp
            for i, chunk in enumerate(chunks):
                if chunk['timestamp_start'] <= timestamp <= chunk['timestamp_end']:
                    chunk_id = f"{video_id}_chunk_{i:06d}"

                    # Link this screenshot to the chunk
                    try:
                        with db.conn.cursor() as cur:
                            cur.execute("""
                                UPDATE images
                                SET chunk_id = %s
                                WHERE id = %s
                            """, (chunk_id, image_id))
                            db.conn.commit()
                        linked_count += 1
                    except Exception as e:
                        print(f"  WARNING: Failed to link screenshot {image_id}: {e}")
                    break  # Only link to first matching chunk

        print(f"OK Linked {linked_count}/{len(screenshot_data)} screenshots to chunks (multimodal context enabled!)")


        # Save hierarchy
        with db.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO document_hierarchy (doc_id, hierarchy)
                VALUES (%s, %s)
                ON CONFLICT (doc_id) DO UPDATE
                SET hierarchy = EXCLUDED.hierarchy
            """, (video_id, json.dumps(video_data['hierarchy'])))  # Convert dict to JSON
            db.conn.commit()

        print(f"✓ Saved hierarchy with {len(chapters)} chapters")

        # Generate document summary
        print(f"\n📝 Generating document summary...")

        # Create a simple doc structure for the summarizer
        doc_structure = {
            'pages': video_data['pages'],
            'pictures': video_data['pictures']
        }
        summary, summary_tokens = summarizer.generate_document_summary(doc_structure, metadata['title'])

        # Track summarization cost (gpt-4o-mini: ~$0.15/1M tokens)
        summary_cost = (summary_tokens / 1_000_000) * 0.15
        total_cost += summary_cost
        total_tokens += summary_tokens
        print(f"  Summary cost: ${summary_cost:.4f} (~{summary_tokens} tokens)")

        # Track chapter detection cost (gpt-4o-mini)
        # Estimate ~1000 tokens for chapter detection
        chapter_tokens = 1000
        chapter_cost = (chapter_tokens / 1_000_000) * 0.15
        total_cost += chapter_cost
        total_tokens += chapter_tokens

        # Update document status
        processing_duration = time.time() - start_time

        db.update_document_status(
            doc_id=video_id,
            status='completed',
            summary=summary,
            total_pages=len(video_data['pages']),
            total_chunks=len(chunks),
            total_sections=len(chapters),
            total_images=processed_screenshots,
            total_tables=0,  # Videos don't have tables (yet)
            processing_duration=processing_duration,
            ingestion_cost=total_cost,
            tokens_used=total_tokens
        )

        # Update job to completed
        with db.conn.cursor() as cur:
            cur.execute("""
                UPDATE jobs
                SET status = 'completed',
                    progress = 100,
                    current_step = 'Completed',
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
            """, (job_id,))
            db.conn.commit()

        # Cleanup temporary files
        print(f"\n🧹 Cleaning up...")
        yt_processor.cleanup(metadata['youtube_id'])

        print(f"\n{'='*60}")
        print(f"✅ VIDEO PROCESSING COMPLETE")
        print(f"{'='*60}")
        print(f"Video ID: {video_id}")
        print(f"Title: {metadata['title']}")
        print(f"Duration: {metadata['duration']/60:.1f} minutes")
        print(f"Chunks: {len(chunks)}")
        print(f"Screenshots: {processed_screenshots}")
        print(f"Chapters: {len(chapters)}")
        print(f"Processing time: {processing_duration:.1f}s")
        print(f"Total cost: ${total_cost:.4f}")
        print(f"Total tokens: {total_tokens:,}")
        print(f"{'='*60}\n")

        return {
            'status': 'completed',
            'video_id': video_id,
            'title': metadata['title'],
            'duration': metadata['duration'],
            'chunks': len(chunks),
            'screenshots': processed_screenshots,
            'chapters': len(chapters),
            'processing_time': processing_duration,
            'total_cost': total_cost,
            'total_tokens': total_tokens
        }

    except Exception as e:
        import traceback as tb
        error_msg = str(e)
        print(f"\n❌ ERROR: {error_msg}")
        print(tb.format_exc())

        # Update job status
        with db.conn.cursor() as cur:
            cur.execute("""
                UPDATE jobs
                SET status = 'failed',
                    error_message = %s,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
            """, (error_msg, job_id))
            db.conn.commit()

        # Update document status
        db.update_document_status(
            doc_id=video_id,
            status='failed',
            error_message=error_msg
        )

        raise

    finally:
        db.conn.close()
