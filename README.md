# VectifyAI-Inspired RAG Pipeline with Docling

Production-ready RAG system for technical documentation with document-level indexing, PageIndex navigation, and cost-optimized multimodal support.

## ✨ Key Features

- 🗂️ **Document Catalog** - Version control, deduplication, metadata tagging
- 📑 **PageIndex** - VectifyAI-inspired page-level navigation
- 🌳 **Hierarchical Context** - No artificial chunking, preserves document structure
- 🖼️ **S3 Image Storage** - 99.98% smaller database, 95% cost savings
- 📊 **Table Insights** - LLM-extracted key insights from tables
- 🔍 **Traceable Citations** - Document → Section → Page → BBox

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.10+
- PostgreSQL with pgvector (Supabase)
- AWS S3 bucket
- OpenAI API key
- Docling server (Docker)

### 2. Setup

```bash
# Start Docling server
docker-compose -f docker-compose.docling.yml up -d

# Install dependencies
pip install -r requirements.txt

# Apply database schema
python apply_schema.py

# Verify setup
python test_setup.py
```

### 3. Ingest Document

```bash
python ingest.py path/to/document.pdf doc_id --type manual --tags tag1,tag2
```

### 4. Check Status

```bash
python test_setup.py
```

## 📁 Project Structure

```
docling-n8n/
├── src/
│   ├── database/          # Schema, models, DB client
│   ├── ingestion/         # Docling parser, hierarchy builder, processors
│   ├── storage/           # S3 client
│   └── utils/             # Embeddings, helpers
├── docker-compose.docling.yml  # Docling server
├── ingest.py              # Main ingestion CLI
├── test_setup.py          # Verification script
└── requirements.txt       # Python dependencies
```

## 💰 Cost Estimates

**100-page document with 20 images:**
- Ingestion: ~$0.02
- Text query: ~$0.0003
- Query with images: ~$0.0015

## 📖 Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - Get started in 5 minutes
- **[SETUP.md](SETUP.md)** - Detailed setup guide
- **[VECTIFY_ARCHITECTURE.md](VECTIFY_ARCHITECTURE.md)** - Architecture deep-dive
- **[IMAGE_COST_OPTIMIZATION.md](IMAGE_COST_OPTIMIZATION.md)** - Cost optimization
- **[SUMMARY.md](SUMMARY.md)** - Complete overview

## 🎯 Architecture Highlights

### VectifyAI-Inspired Two-Level Retrieval

```
Query → Document Filter (SQL) → PageIndex Navigation → Vector Search → Context Expansion
```

### No Artificial Chunking

Preserves natural document boundaries with full section hierarchy:
```
Document → Pages → Sections → Chunks (with section paths)
```

### Cost-Optimized Images

- Upload to S3 (not base64 in DB)
- Batch processing (5 images per API call)
- Tiered descriptions (caption → basic → detailed)
- Generate detailed descriptions on-demand only

## 🔧 Environment Variables

Required in `.env`:

```bash
# OpenAI
OPENAI_API_KEY=...
EMBEDDING_MODEL=text-embedding-3-small
DOC_SUMMARY_MODEL=gpt-4o-mini

# Database
DATABASE_URL=postgresql://...

# S3 Storage
S3_BUCKET=...
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_PUBLIC_BASE=https://...

# Docling
DOCLING_SERVER_URL=http://localhost:5001
```

## 🏗️ System Status

✅ **Ingestion Pipeline** - Fully operational  
⏳ **Query System** - In development  
⏳ **API Layer** - Planned  
⏳ **UI Dashboard** - Planned  

## 🤝 Contributing

This is a production system for technical documentation RAG. Focus areas:
- Query system with context expansion
- Citation generation
- API endpoints
- UI dashboard

## 📝 License

Internal project for AME Inc.

## 🆘 Support

See [QUICKSTART.md](QUICKSTART.md) for troubleshooting and common issues.

---

**Built with:** Docling • PostgreSQL • pgvector • OpenAI • AWS S3 • VectifyAI concepts

# V2 Document RAG Pipeline - Clean Implementation

## Architecture

```
Docling JSON → Page-Based Hierarchy → Chunk with References → Vector DB → ID-Based Retrieval
```

## Core Principles

1. **Preserve Structure**: Never use markdown, always use Docling's native JSON
2. **Page-First Organization**: VectifyAI approach - organize by pages, then sections
3. **Reference-Based**: Store chunk IDs in hierarchy, not ranges
4. **Clean Separation**: Ingestion, storage, and retrieval are separate modules

## Directory Structure

```
v2/
├── src/
│   ├── ingestion/
│   │   ├── docling_parser.py      # Parse PDF with Docling
│   │   ├── hierarchy_builder.py   # Build page+section hierarchy
│   │   └── chunk_creator.py       # Create chunks with references
│   ├── retrieval/
│   │   ├── vector_search.py       # Vector similarity search
│   │   ├── context_expander.py    # Expand using hierarchy IDs
│   │   └── answer_generator.py    # LLM answer generation
│   └── database/
│       ├── schema.sql              # Database schema
│       ├── db_client.py            # Database operations
│       └── models.py               # Data models
├── tests/
│   └── test_pipeline.py           # End-to-end tests
└── ingest.py                       # CLI for ingestion
└── query.py                        # CLI for queries
```

## Data Flow

### Ingestion
```
PDF → Docling JSON → Elements[] → 
  → Pages[] (with chunk_ids) 
  → Sections[] (with chunk_ids, parent_id)
  → Chunks[] (with section_id, page)
  → Embeddings[]
  → Database
```

### Retrieval
```
Query → Embedding → Vector Search → Golden Chunk ID →
  → Lookup section_id from chunk →
  → Get section['chunk_ids'] from hierarchy →
  → Fetch all section chunks by IDs →
  → (Optional) Expand to parent section →
  → Assemble context with pages →
  → LLM answer
```

## Key Features

- ✅ Preserves page numbers
- ✅ Preserves bounding boxes
- ✅ Proper section hierarchy
- ✅ Direct ID lookups (no range arithmetic)
- ✅ Efficient context expansion
- ✅ PageIndex section summaries
- ✅ Image handling
