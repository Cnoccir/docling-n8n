#!/bin/bash

# End-to-End Test Script for Video RAG System
# Tests YouTube video ingestion, chat, and timestamp navigation

set -e  # Exit on error

API_BASE_URL="${API_BASE_URL:-http://localhost:8000/api}"
TEST_VIDEO_URL="https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Short test video
DATABASE_URL="${DATABASE_URL}"

echo "========================================"
echo "🎬 VIDEO RAG SYSTEM E2E TEST"
echo "========================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print test results
print_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ $2${NC}"
    else
        echo -e "${RED}✗ $2${NC}"
        exit 1
    fi
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Test 1: Health Check
echo "Test 1: API Health Check"
response=$(curl -s -o /dev/null -w "%{http_code}" ${API_BASE_URL}/../health)
if [ "$response" = "200" ]; then
    print_result 0 "API is healthy"
else
    print_result 1 "API health check failed (HTTP $response)"
fi
echo ""

# Test 2: Upload YouTube Video
echo "Test 2: Upload YouTube Video"
echo "URL: $TEST_VIDEO_URL"
upload_response=$(curl -s -X POST "${API_BASE_URL}/youtube/upload" \
    -H "Content-Type: application/json" \
    -d "{
        \"url\": \"$TEST_VIDEO_URL\",
        \"tags\": [\"test\", \"e2e\"],
        \"categories\": [\"demo\"]
    }")

video_id=$(echo $upload_response | jq -r '.video_id // empty')
job_id=$(echo $upload_response | jq -r '.job_id // empty')

if [ -n "$video_id" ] && [ -n "$job_id" ]; then
    print_result 0 "Video upload initiated (video_id: $video_id, job_id: $job_id)"
else
    echo "Response: $upload_response"
    print_result 1 "Failed to initiate video upload"
fi
echo ""

# Test 3: Monitor Job Progress
echo "Test 3: Monitor Job Progress"
echo "Waiting for video processing to complete..."
max_wait=600  # 10 minutes max
waited=0
job_status="pending"

while [ "$job_status" != "completed" ] && [ $waited -lt $max_wait ]; do
    sleep 10
    waited=$((waited + 10))

    job_response=$(curl -s "${API_BASE_URL}/jobs/$job_id")
    job_status=$(echo $job_response | jq -r '.status // empty')
    progress=$(echo $job_response | jq -r '.progress // 0')
    current_step=$(echo $job_response | jq -r '.current_step // "unknown"')

    echo "  Progress: ${progress}% - $current_step"

    if [ "$job_status" = "failed" ]; then
        error_message=$(echo $job_response | jq -r '.error_message // "Unknown error"')
        print_result 1 "Job failed: $error_message"
    fi
done

if [ "$job_status" = "completed" ]; then
    print_result 0 "Video processing completed in ${waited}s"
else
    print_result 1 "Video processing timed out after ${max_wait}s"
fi
echo ""

# Test 4: Verify Database Entries
echo "Test 4: Verify Database Entries"

if [ -z "$DATABASE_URL" ]; then
    print_warning "DATABASE_URL not set, skipping database verification"
else
    # Check document_index
    doc_count=$(psql "$DATABASE_URL" -t -c "SELECT COUNT(*) FROM document_index WHERE id='$video_id' AND source_type='youtube';" | xargs)
    if [ "$doc_count" = "1" ]; then
        print_result 0 "Document index entry created"
    else
        print_result 1 "Document index entry not found"
    fi

    # Check chunks
    chunk_count=$(psql "$DATABASE_URL" -t -c "SELECT COUNT(*) FROM chunks WHERE doc_id='$video_id';" | xargs)
    if [ "$chunk_count" -gt "0" ]; then
        print_result 0 "Chunks created: $chunk_count"
    else
        print_result 1 "No chunks found"
    fi

    # Check timestamp fields
    timestamp_count=$(psql "$DATABASE_URL" -t -c "SELECT COUNT(*) FROM chunks WHERE doc_id='$video_id' AND timestamp_start IS NOT NULL;" | xargs)
    if [ "$timestamp_count" -gt "0" ]; then
        print_result 0 "Timestamps populated: $timestamp_count chunks"
    else
        print_result 1 "No timestamps found"
    fi

    # Check images/screenshots
    screenshot_count=$(psql "$DATABASE_URL" -t -c "SELECT COUNT(*) FROM images WHERE doc_id='$video_id' AND timestamp IS NOT NULL;" | xargs)
    if [ "$screenshot_count" -gt "0" ]; then
        print_result 0 "Screenshots extracted: $screenshot_count"
    else
        print_warning "No screenshots found (this may be OK for short videos)"
    fi
fi
echo ""

# Test 5: Query Video via API
echo "Test 5: Query Video Details via API"
video_response=$(curl -s "${API_BASE_URL}/youtube/$video_id")
video_title=$(echo $video_response | jq -r '.video.title // empty')
total_chunks=$(echo $video_response | jq -r '.video.total_chunks // 0')
duration=$(echo $video_response | jq -r '.video.duration_seconds // 0')

if [ -n "$video_title" ]; then
    print_result 0 "Video details retrieved"
    echo "  Title: $video_title"
    echo "  Duration: ${duration}s ($(echo "scale=1; $duration/60" | bc)min)"
    echo "  Chunks: $total_chunks"
else
    print_result 1 "Failed to retrieve video details"
fi
echo ""

# Test 6: Chat with Video (Text-only)
echo "Test 6: Chat with Video (Text-only)"
chat_response=$(curl -s -X POST "${API_BASE_URL}/chat/" \
    -H "Content-Type: application/json" \
    -d "{
        \"doc_id\": \"$video_id\",
        \"question\": \"What is this video about?\",
        \"chat_history\": []
    }")

answer=$(echo $chat_response | jq -r '.answer // empty')
citation_count=$(echo $chat_response | jq -r '.citations | length // 0')

if [ -n "$answer" ] && [ "$citation_count" -gt "0" ]; then
    print_result 0 "Chat response generated with $citation_count citations"
    echo "  Answer preview: ${answer:0:100}..."
else
    print_result 1 "Chat response failed"
fi
echo ""

# Test 7: Verify Timestamp Citations
echo "Test 7: Verify Timestamp Citations"
first_citation=$(echo $chat_response | jq -r '.citations[0] // empty')
if [ -n "$first_citation" ]; then
    timestamp=$(echo $first_citation | jq -r '.timestamp // empty')
    video_url=$(echo $first_citation | jq -r '.video_url // empty')

    if [ -n "$timestamp" ]; then
        print_result 0 "Timestamp citation found: ${timestamp}s"
    else
        print_result 1 "Timestamp missing in citation"
    fi

    if [[ "$video_url" == *"&t="* ]]; then
        print_result 0 "Video URL includes timestamp parameter"
    else
        print_result 1 "Video URL missing timestamp parameter"
    fi
else
    print_result 1 "No citations found to verify"
fi
echo ""

# Test 8: Unified Search (PDFs + Videos)
echo "Test 8: Unified Search (Cross-Source)"
unified_response=$(curl -s -X POST "${API_BASE_URL}/chat/unified/" \
    -H "Content-Type: application/json" \
    -d "{
        \"question\": \"What is this about?\",
        \"source_types\": [\"all\"],
        \"top_k_per_source\": 5
    }")

sources_searched=$(echo $unified_response | jq -r '.sources_searched | join(", ") // empty')
total_sources=$(echo $unified_response | jq -r '.total_sources_found // 0')

if [ -n "$sources_searched" ]; then
    print_result 0 "Unified search working (searched: $sources_searched, found: $total_sources sources)"
else
    print_result 1 "Unified search failed"
fi
echo ""

# Test 9: Cost Tracking
echo "Test 9: Cost Tracking Verification"
if [ -z "$DATABASE_URL" ]; then
    print_warning "DATABASE_URL not set, skipping cost verification"
else
    ingestion_cost=$(psql "$DATABASE_URL" -t -c "SELECT ingestion_cost_usd FROM document_index WHERE id='$video_id';" | xargs)
    tokens_used=$(psql "$DATABASE_URL" -t -c "SELECT tokens_used FROM document_index WHERE id='$video_id';" | xargs)

    if [ -n "$ingestion_cost" ] && [ "$(echo "$ingestion_cost > 0" | bc)" -eq 1 ]; then
        print_result 0 "Ingestion cost tracked: \$$ingestion_cost ($tokens_used tokens)"
    else
        print_result 1 "Ingestion cost not tracked properly"
    fi
fi
echo ""

# Summary
echo "========================================"
echo "✅ ALL TESTS PASSED!"
echo "========================================"
echo ""
echo "Summary:"
echo "  Video ID: $video_id"
echo "  Job ID: $job_id"
echo "  Processing Time: ${waited}s"
echo "  Total Chunks: $total_chunks"
echo "  Cost: \$$ingestion_cost"
echo ""
echo "Next steps:"
echo "  1. Test frontend at http://localhost:3000/videos/$video_id"
echo "  2. Verify timestamp navigation in chat tab"
echo "  3. Test transcript tab clickable timestamps"
echo ""
