# Video RAG System - Deployment & Usage Guide

**Date:** 2025-11-26
**Status:** Production-Ready (Documents), Video Features Complete

---

## Quick Start

### 1. Prerequisites

```bash
# Required
- Docker & Docker Compose
- Python 3.11+
- Node.js 18+
- PostgreSQL with pgvector extension (or Supabase account)
- AWS S3 bucket for image storage
- OpenAI API key

# Optional
- Google Drive API credentials (for auto-upload)
```

### 2. Environment Setup

```bash
# 1. Clone and navigate
cd docling-n8n

# 2. Copy environment file
cp .env.docker.example .env.docker

# 3. Configure environment variables
nano .env.docker
```

**Critical Variables:**
```bash
# OpenAI
OPENAI_API_KEY=sk-proj-...

# Database (Supabase)
DATABASE_URL=postgresql://...
SUPABASE_URL=https://....supabase.co
SUPABASE_API_KEY=eyJhbGci...

# S3 Storage
S3_BUCKET=your-bucket-name
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1

# Optional: Google Drive
ENABLE_GDRIVE_UPLOAD=true
GDRIVE_CREDENTIALS_PATH=/app/service-account-key.json
GDRIVE_FOLDER_ID=...
```

### 3. Start Services

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f backend
```

**Services Running:**
- Backend API: http://localhost:8000
- Frontend: http://localhost:3000
- Docling Server: http://localhost:5001
- Redis: localhost:6379

### 4. Initialize Database

```bash
# Run migrations
bash apply-migration.sh

# Or manually
psql $DATABASE_URL -f migrations/001_initial_schema.sql
psql $DATABASE_URL -f migrations/012_add_youtube_support.sql
# ... (run all migrations)
```

---

## Features Overview

### ✅ Document Processing (Production-Ready)

**Capabilities:**
- PDF upload with drag-drop interface
- Automatic Docling parsing with native image extraction
- Hierarchical structure detection (TOC + bookmarks)
- Table extraction with markdown conversion
- S3-optimized image storage (95% cost savings)
- Document deduplication via SHA256 hashing
- Checkpoint-based resumable processing
- Google Drive auto-upload integration

**Cost:** ~$0.50-$1.00 per 100-page document

### ✅ Video Processing (Complete)

**Capabilities:**
- YouTube URL ingestion
- Whisper API transcription ($0.006/minute)
- Screenshot extraction (scene detection + interval)
- Chapter detection with LLM
- Timestamp-based chunking (~60s chunks)
- Video chat with side-by-side player
- Clickable timestamp citations
- Transcript navigation

**Cost:** ~$0.20-$0.30 per 10-minute video

### ✅ Chat RAG System (Production-Ready)

**Text-Only Chat** (`/api/chat/`)
- Model: GPT-4o-mini
- Cost: ~$0.0002/query
- Hybrid search (semantic + keyword)
- Conversation memory (4 messages)
- Citation with page numbers

**Multimodal Chat** (`/api/chat/multimodal/`)
- Model: GPT-4o with vision
- Cost: ~$0.015/query
- Golden chunk + context expansion strategy
- Images from S3 included
- Tables in markdown
- Rich citations

**Unified Search** (`/api/chat/unified/`)
- Searches PDFs + Videos simultaneously
- Type-specific citations (page vs timestamp)
- Video thumbnails in results
- Cross-modal reasoning

---

## Usage Guide

### Uploading Documents

#### Via Web Interface:
1. Navigate to http://localhost:3000/upload
2. Drag & drop PDF or paste YouTube URL
3. Add metadata (tags, categories, document type)
4. Click "Upload"
5. Monitor progress at /queue

#### Via API:
```bash
# Upload PDF
curl -X POST http://localhost:8000/api/upload/single \
  -F "file=@document.pdf" \
  -F "tags=technical,manual" \
  -F "categories=documentation"

# Upload YouTube video
curl -X POST http://localhost:8000/api/chat/unified/ \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=VIDEO_ID",
    "tags": ["tutorial"],
    "categories": ["education"]
  }'
```

### Chatting with Content

#### Document Chat:
```bash
curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "doc_id": "docProvisioning_c0a072cb",
    "question": "How do I configure authentication?",
    "chat_history": []
  }'
```

#### Video Chat (with timestamps):
```bash
curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "doc_id": "video_dQw4w9WgXcQ",
    "question": "What is discussed at the beginning?",
    "chat_history": []
  }'
```

#### Unified Search (PDFs + Videos):
```bash
curl -X POST http://localhost:8000/api/chat/unified/ \
  -H "Content-Type: application/json" \
  -d '{
    "question": "How does deployment work?",
    "source_types": ["all"],
    "top_k_per_source": 5
  }'
```

### Frontend Features

**Dashboard** (`/`)
- System statistics
- Recent documents
- Queue status
- Cost analytics

**Upload** (`/upload`)
- PDF drag-drop
- YouTube URL input
- Metadata editor
- Bulk upload support

**Queue Manager** (`/queue`)
- Real-time job monitoring (WebSocket)
- Progress tracking
- Job retry/cancel/resume
- Worker monitoring

**Documents** (`/documents`)
- Document library
- Search & filters
- Status tracking
- Click to view details

**Document Detail** (`/documents/:docId`)
- Full document view
- Chat interface
- Image gallery
- Table viewer
- Metadata display

**Videos** (`/videos`)
- Video library
- Duration & stats
- Channel information
- Search & filters

**Video Detail** (`/videos/:videoId`)
- **Overview Tab:** Video player + summary
- **Chat Tab:** Side-by-side (video + chat)
  - Timestamp jump on citation click
  - Current time tracking
- **Transcript Tab:** Full transcript with clickable timestamps

**Unified Search** (`/search`)
- Cross-source search UI
- PDF + Video filters
- Rich results display
- Video thumbnails
- Direct navigation to sources

---

## Video Chat Features

### Timestamp Navigation

**How it works:**
1. User asks question about video
2. RAG returns citations with timestamps
3. Citations display timestamp badges (e.g., "▶ 2:35")
4. Clicking citation jumps video to that timestamp
5. Video auto-plays from citation point

**Implementation:**
- Uses YouTube IFrame API
- Timestamps stored in database (`chunks.timestamp_start`)
- Video URLs include `&t=XXs` parameter
- `jumpToTimestamp()` function in VideoDetail.tsx

**Example Citation:**
```json
{
  "source_type": "youtube",
  "timestamp": 155,
  "timestamp_formatted": "2:35",
  "video_url": "https://www.youtube.com/watch?v=VIDEO_ID&t=155s",
  "content": "At this point, we discuss authentication..."
}
```

### Transcript Features

- **Clickable Timestamps:** Click any timestamp to jump to that point
- **Auto-Scroll:** Transcript auto-scrolls to current time
- **Chapter Navigation:** LLM-detected chapters shown in timeline
- **Search:** Find specific words in transcript

---

## Cost Optimization

### Current Costs (Per Operation)

| Operation | Model | Cost | Notes |
|-----------|-------|------|-------|
| Text Chat | gpt-4o-mini | $0.0002 | 95% of queries |
| Multimodal Chat | gpt-4o | $0.015 | When images needed |
| Document Summary | gpt-4o-mini | $0.10 | Per document |
| Video Transcription | Whisper | $0.006/min | Audio processing |
| Embeddings | text-embedding-3-small | $0.02/1M | All chunks |
| Image Storage | S3 | $0.023/GB/mo | 95% cheaper than base64 |

### Monthly Cost Projections

**Small Team (10 users, 100 docs, 20 videos):**
- Ingestion: $80 (one-time)
- Queries: $0.94/month (1000 queries)
- Storage: $10.22/month
- **Total: ~$11/month**

**Medium Team (100 users, 1000 docs, 200 videos):**
- Ingestion: $800 (one-time)
- Queries: $18.80/month (20,000 queries)
- Storage: $30.69/month
- **Total: ~$50/month**

### Optimization Tips

1. **Use Text Chat by Default**
   - Only use multimodal when images are essential
   - Saves 75x cost per query

2. **Batch Process Documents**
   - Process during off-hours
   - Use bulk upload endpoint

3. **Cache Frequent Queries**
   - Redis caching for common questions
   - 60% query reduction

4. **Optimize Video Processing**
   - Use scene detection for screenshots (not interval)
   - Cache YouTube transcripts if available
   - Skip screenshots for audio-only content

---

## Troubleshooting

### Common Issues

#### 1. "Docling server not responding"
```bash
# Check Docling health
curl http://localhost:5001/health

# Restart Docling
docker-compose restart docling-server

# Check memory (needs 4-8GB)
docker stats docling-server
```

#### 2. "Database connection failed"
```bash
# Test connection
psql $DATABASE_URL -c "SELECT 1;"

# Check pgvector extension
psql $DATABASE_URL -c "SELECT * FROM pg_extension WHERE extname='vector';"

# Reinstall extension
psql $DATABASE_URL -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

#### 3. "S3 upload failed"
```bash
# Test S3 credentials
aws s3 ls s3://$S3_BUCKET --profile default

# Check CORS configuration
aws s3api get-bucket-cors --bucket $S3_BUCKET

# Fix CORS if needed
aws s3api put-bucket-cors --bucket $S3_BUCKET --cors-configuration file://s3-cors.json
```

#### 4. "YouTube download failed"
```bash
# Update yt-dlp
pip install --upgrade yt-dlp

# Test manually
yt-dlp "https://www.youtube.com/watch?v=VIDEO_ID"

# Check ffmpeg
ffmpeg -version
```

#### 5. "Job stuck in processing"
```bash
# Check Celery workers
docker-compose logs celery-worker

# Restart workers
docker-compose restart celery-worker

# Resume from checkpoint
curl -X POST http://localhost:8000/api/jobs/{job_id}/resume
```

---

## Testing

### Run End-to-End Tests

```bash
# Python version (recommended for Windows)
python test_video_e2e.py

# Bash version (Linux/Mac)
bash test_video_e2e.sh
```

**Tests Include:**
1. API health check
2. YouTube video upload
3. Job progress monitoring
4. Database verification
5. Video query
6. Chat with timestamps
7. Timestamp citation verification
8. Unified search
9. Cost tracking

### Manual Testing Checklist

- [ ] Upload PDF document
- [ ] Upload YouTube video
- [ ] Monitor job queue
- [ ] Verify document in /documents
- [ ] Verify video in /videos
- [ ] Chat with document
- [ ] Chat with video
- [ ] Click timestamp citation (video should jump)
- [ ] Click transcript timestamp (video should jump)
- [ ] Use unified search
- [ ] Verify costs in analytics

---

## Performance Tuning

### Backend Optimization

```python
# Increase worker concurrency
MAX_WORKERS=4
MAX_CONCURRENT_PROCESSES=2

# Adjust chunk parameters
CHUNK_SIZE=1200  # Larger = fewer chunks, less granular
CHUNK_OVERLAP=200

# Image processing
IMAGE_BATCH_SIZE=5
IMAGE_MAX_SIZE=512  # Resize before upload
```

### Database Optimization

```sql
-- Add indexes for common queries
CREATE INDEX idx_chunks_doc_id ON chunks(doc_id);
CREATE INDEX idx_chunks_embedding ON chunks USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_chunks_content_tsv ON chunks USING gin(content_tsv);

-- Vacuum regularly
VACUUM ANALYZE chunks;
```

### Frontend Optimization

```typescript
// Enable lazy loading
const VideoDetail = lazy(() => import('./pages/VideoDetail'));

// Cache API responses
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
    },
  },
});
```

---

## Production Deployment

### Environment Configuration

```bash
# Use production database
DATABASE_URL=postgresql://prod-user:pass@prod-db:5432/prod

# Enable HTTPS
FRONTEND_URL=https://rag.yourdomain.com
BACKEND_URL=https://api.rag.yourdomain.com

# Set rate limits
RATE_LIMIT_PER_HOUR=100

# Enable monitoring
SENTRY_DSN=https://...
PROMETHEUS_ENABLED=true
```

### Deployment Steps

1. **Build Docker Images**
```bash
docker build -t rag-backend:latest -f Dockerfile .
docker build -t rag-frontend:latest -f frontend/Dockerfile ./frontend
```

2. **Push to Registry**
```bash
docker tag rag-backend:latest your-registry/rag-backend:latest
docker push your-registry/rag-backend:latest
```

3. **Deploy with Docker Compose**
```bash
docker-compose -f docker-compose.prod.yml up -d
```

4. **Configure Reverse Proxy (Nginx)**
```nginx
server {
    listen 443 ssl;
    server_name rag.yourdomain.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /ws {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

5. **Set Up Monitoring**
```bash
# Prometheus + Grafana
docker-compose -f docker-compose.monitoring.yml up -d

# Access Grafana
open http://localhost:3001
```

6. **Configure Backups**
```bash
# Database backup script
pg_dump $DATABASE_URL | gzip > backups/db-$(date +%Y%m%d).sql.gz

# S3 sync
aws s3 sync s3://$S3_BUCKET backups/s3/ --storage-class GLACIER
```

---

## Security Considerations

1. **API Authentication**
   - Add JWT tokens for API access
   - Rate limit per user/IP
   - Use API keys for external access

2. **Database Security**
   - Use SSL for database connections
   - Rotate credentials regularly
   - Enable row-level security (RLS)

3. **S3 Security**
   - Enable versioning
   - Set bucket policies
   - Use signed URLs for temporary access

4. **Secrets Management**
   - Use environment variables
   - Never commit `.env` files
   - Use AWS Secrets Manager or Vault

---

## Support & Resources

- **Documentation:** [PROJECT_AUDIT_AND_ROADMAP.md](PROJECT_AUDIT_AND_ROADMAP.md)
- **GitHub Issues:** https://github.com/your-repo/docling-n8n/issues
- **API Reference:** http://localhost:8000/docs (when running)

---

**System Status:** ✅ Production-Ready
**Last Updated:** 2025-11-26
**Version:** 2.0 (with Video RAG)
