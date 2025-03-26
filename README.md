
# Enhanced Docling PDF Extraction for n8n

A comprehensive solution for extracting rich content from PDF documents and integrating with n8n workflows. This project consists of two main components:

1. **Enhanced Docling API** - A FastAPI service that wraps your sophisticated DocumentProcessor
2. **Docling n8n Node** - A custom n8n node that integrates with the API

## Features

- **Comprehensive PDF Processing**
  - Extract markdown content with preserved structure
  - Detect and extract tables with headers, rows, and captions
  - Extract images with metadata
  - Identify technical terms and domain-specific vocabulary
  - Extract procedures, steps, and parameters
  - Build concept networks with relationships
  - Generate multi-level chunks for vector storage

- **Specialized Output Formats**
  - Qdrant-ready format for vector database integration
  - MongoDB-ready format for document database integration
  - Customizable chunking for optimal embedding

- **n8n Integration**
  - Seamless workflow integration with the custom n8n node
  - Support for various extraction options
  - Multiple output format options

## Architecture

The solution follows a modular architecture:

1. **API Layer** - FastAPI service exposing the PDF processing capabilities
2. **Processing Layer** - Enhanced DocumentProcessor adapted for API use
3. **n8n Integration Layer** - Custom n8n node for workflow integration

## Setup and Installation

### 1. API Service

#### Prerequisites
- Python 3.11+
- Tesseract OCR
- Poppler
- OpenAI API key

#### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/docling-n8n-integration.git
   cd docling-n8n-integration/api
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set environment variables:
   ```bash
   export OPENAI_API_KEY=your_openai_api_key
   export API_KEY=your_optional_api_key  # for security
   export OUTPUT_DIR=path/to/output/dir  # optional
   ```

4. Run the API:
   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8000
   ```

#### Docker

Build and run using Docker:

```bash
docker build -t docling-n8n-api .
docker run -p 8000:8000 -e OPENAI_API_KEY=your_openai_api_key -e API_KEY=your_api_key docling-n8n-api
```

### 2. n8n Node

#### Prerequisites
- n8n (version 0.214.0 or later)
- Node.js (version 16+)

#### Installation

1. Navigate to the n8n node directory:
   ```bash
   cd docling-n8n-integration/node
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Build the node:
   ```bash
   npm run build
   ```

4. Link to your n8n installation:
   ```bash
   npm link
   cd ~/.n8n
   npm link n8n-nodes-docling
   ```

5. Restart n8n

## API Endpoints

### Main Extraction Endpoints

#### POST /api/extract
Extract content from a PDF document.

**Parameters:**
- `pdf_id` (form field, optional): Identifier for the PDF
- `file` (file upload): PDF file to process
- `extract_technical_terms` (form field, optional): Whether to extract technical terms
- `extract_procedures` (form field, optional): Whether to extract procedures
- `extract_relationships` (form field, optional): Whether to extract relationships
- `process_images` (form field, optional): Whether to process images
- `process_tables` (form field, optional): Whether to process tables
- `chunk_size` (form field, optional): Size of text chunks (default: 500)
- `chunk_overlap` (form field, optional): Overlap between chunks (default: 100)
- `api_key` (form field, optional): API key for authentication

#### POST /api/extract-qdrant-ready
Extract content and format for Qdrant ingestion.

#### POST /api/extract-mongodb-ready
Extract content and format for MongoDB ingestion.

### Status and Results Endpoints

#### GET /api/status/{pdf_id}
Get processing status for a document.

#### GET /api/results/{pdf_id}
Get processing results for a completed job.

## n8n Node Usage

After installation, the "Docling Extractor" node will be available in n8n under the "Transform" category.

### Operations

1. **Standard Extraction** - Extract content from PDF document
2. **Qdrant Ready** - Extract and format for Qdrant vector database
3. **MongoDB Ready** - Extract and format for MongoDB document database
4. **Get Processing Status** - Check status of a processing job
5. **Get Results** - Get results of a completed processing job

### Configuration Options

- **Docling API URL** - URL of the Docling extraction API
- **API Key** - Optional API key for authentication
- **PDF Document** - Binary property containing the PDF file
- **PDF ID** - Optional identifier for the PDF
- **Advanced Options** - Extraction configuration options
- **Output Format** - How the extracted data should be returned:
  - Combined Object: All data in a single object
  - Separate Items: Separate items for different content types

## Using in n8n Workflow

### Example Workflow

1. Upload PDF document using a Trigger node (e.g., Form Trigger, HTTP Request)
2. Connect to Docling Extractor node
3. Configure extraction options
4. Choose combined or separate output format
5. Process results:
   - Store in a vector database (e.g., Qdrant)
   - Use in a chat system
   - Visualize content

## License

MIT
