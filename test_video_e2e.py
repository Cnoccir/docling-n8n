"""
End-to-End Test Script for Video RAG System
Tests YouTube video ingestion, chat, and timestamp navigation
"""
import os
import sys
import time
import requests
import json
from typing import Optional

API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:8000/api')
TEST_VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Short test video
DATABASE_URL = os.getenv('DATABASE_URL')

# Colors for output
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
NC = '\033[0m'  # No Color


def print_result(success: bool, message: str):
    """Print test result with color"""
    if success:
        print(f"{GREEN}✓ {message}{NC}")
    else:
        print(f"{RED}✗ {message}{NC}")
        sys.exit(1)


def print_warning(message: str):
    """Print warning message"""
    print(f"{YELLOW}⚠ {message}{NC}")


def test_health_check():
    """Test 1: API Health Check"""
    print("\nTest 1: API Health Check")
    try:
        response = requests.get(f"{API_BASE_URL}/../health")
        if response.status_code == 200:
            print_result(True, "API is healthy")
            return True
        else:
            print_result(False, f"API health check failed (HTTP {response.status_code})")
            return False
    except Exception as e:
        print_result(False, f"API health check failed: {e}")
        return False


def test_upload_video():
    """Test 2: Upload YouTube Video"""
    print(f"\nTest 2: Upload YouTube Video")
    print(f"URL: {TEST_VIDEO_URL}")

    try:
        response = requests.post(
            f"{API_BASE_URL}/youtube/upload",
            json={
                "url": TEST_VIDEO_URL,
                "tags": ["test", "e2e"],
                "categories": ["demo"]
            }
        )

        if response.status_code == 200:
            data = response.json()
            video_id = data.get('video_id')
            job_id = data.get('job_id')

            if video_id and job_id:
                print_result(True, f"Video upload initiated (video_id: {video_id}, job_id: {job_id})")
                return video_id, job_id
            else:
                print_result(False, "Failed to get video_id or job_id from response")
                return None, None
        else:
            print_result(False, f"Upload failed (HTTP {response.status_code}): {response.text}")
            return None, None
    except Exception as e:
        print_result(False, f"Upload failed: {e}")
        return None, None


def test_monitor_job(job_id: str):
    """Test 3: Monitor Job Progress"""
    print("\nTest 3: Monitor Job Progress")
    print("Waiting for video processing to complete...")

    max_wait = 600  # 10 minutes max
    waited = 0
    job_status = "pending"

    while job_status != "completed" and waited < max_wait:
        time.sleep(10)
        waited += 10

        try:
            response = requests.get(f"{API_BASE_URL}/jobs/{job_id}")
            data = response.json()

            job_status = data.get('status', 'unknown')
            progress = data.get('progress', 0)
            current_step = data.get('current_step', 'unknown')

            print(f"  Progress: {progress}% - {current_step}")

            if job_status == "failed":
                error_message = data.get('error_message', 'Unknown error')
                print_result(False, f"Job failed: {error_message}")
                return False

        except Exception as e:
            print(f"  Error checking job status: {e}")

    if job_status == "completed":
        print_result(True, f"Video processing completed in {waited}s")
        return True
    else:
        print_result(False, f"Video processing timed out after {max_wait}s")
        return False


def test_video_query(video_id: str):
    """Test 4: Query Video Details via API"""
    print("\nTest 4: Query Video Details via API")

    try:
        response = requests.get(f"{API_BASE_URL}/youtube/{video_id}")
        if response.status_code == 200:
            data = response.json()
            video = data.get('video', {})

            video_title = video.get('title', '')
            total_chunks = video.get('total_chunks', 0)
            duration = video.get('duration_seconds', 0)

            if video_title:
                print_result(True, "Video details retrieved")
                print(f"  Title: {video_title}")
                print(f"  Duration: {duration}s ({duration/60:.1f}min)")
                print(f"  Chunks: {total_chunks}")
                return total_chunks
            else:
                print_result(False, "Failed to retrieve video details")
                return 0
        else:
            print_result(False, f"Failed to query video (HTTP {response.status_code})")
            return 0
    except Exception as e:
        print_result(False, f"Video query failed: {e}")
        return 0


def test_chat(video_id: str):
    """Test 5: Chat with Video"""
    print("\nTest 5: Chat with Video (Text-only)")

    try:
        response = requests.post(
            f"{API_BASE_URL}/chat/",
            json={
                "doc_id": video_id,
                "question": "What is this video about?",
                "chat_history": []
            }
        )

        if response.status_code == 200:
            data = response.json()
            answer = data.get('answer', '')
            citations = data.get('citations', [])

            if answer and len(citations) > 0:
                print_result(True, f"Chat response generated with {len(citations)} citations")
                print(f"  Answer preview: {answer[:100]}...")
                return citations
            else:
                print_result(False, "Chat response failed - no answer or citations")
                return []
        else:
            print_result(False, f"Chat failed (HTTP {response.status_code}): {response.text}")
            return []
    except Exception as e:
        print_result(False, f"Chat failed: {e}")
        return []


def test_timestamp_citations(citations: list):
    """Test 6: Verify Timestamp Citations"""
    print("\nTest 6: Verify Timestamp Citations")

    if not citations:
        print_result(False, "No citations to verify")
        return

    first_citation = citations[0]
    timestamp = first_citation.get('timestamp')
    video_url = first_citation.get('video_url', '')

    if timestamp is not None:
        print_result(True, f"Timestamp citation found: {timestamp}s")
    else:
        print_result(False, "Timestamp missing in citation")

    if '&t=' in video_url:
        print_result(True, "Video URL includes timestamp parameter")
    else:
        print_result(False, "Video URL missing timestamp parameter")


def test_unified_search():
    """Test 7: Unified Search (Cross-Source)"""
    print("\nTest 7: Unified Search (Cross-Source)")

    try:
        response = requests.post(
            f"{API_BASE_URL}/chat/unified/",
            json={
                "question": "What is this about?",
                "source_types": ["all"],
                "top_k_per_source": 5
            }
        )

        if response.status_code == 200:
            data = response.json()
            sources_searched = ', '.join(data.get('sources_searched', []))
            total_sources = data.get('total_sources_found', 0)

            if sources_searched:
                print_result(True, f"Unified search working (searched: {sources_searched}, found: {total_sources} sources)")
            else:
                print_result(False, "Unified search failed - no sources searched")
        else:
            print_result(False, f"Unified search failed (HTTP {response.status_code})")
    except Exception as e:
        print_result(False, f"Unified search failed: {e}")


def main():
    """Run all tests"""
    print("=" * 40)
    print("🎬 VIDEO RAG SYSTEM E2E TEST")
    print("=" * 40)

    # Run tests
    if not test_health_check():
        return

    video_id, job_id = test_upload_video()
    if not video_id or not job_id:
        return

    if not test_monitor_job(job_id):
        return

    total_chunks = test_video_query(video_id)
    citations = test_chat(video_id)
    test_timestamp_citations(citations)
    test_unified_search()

    # Summary
    print("\n" + "=" * 40)
    print("✅ ALL TESTS PASSED!")
    print("=" * 40)
    print(f"\nSummary:")
    print(f"  Video ID: {video_id}")
    print(f"  Job ID: {job_id}")
    print(f"  Total Chunks: {total_chunks}")
    print(f"\nNext steps:")
    print(f"  1. Test frontend at http://localhost:3000/videos/{video_id}")
    print(f"  2. Verify timestamp navigation in chat tab")
    print(f"  3. Test transcript tab clickable timestamps")
    print()


if __name__ == "__main__":
    main()
