FROM python:3.11-slim

WORKDIR /app

# Set PYTHONPATH so imports like `from document_processor` work inside /app/api
ENV PYTHONPATH="/app/api"

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    tesseract-ocr \
    libtesseract-dev \
    poppler-utils \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install spaCy model
RUN python -m spacy download en_core_web_sm


# Copy application code
COPY ./api /app/api

# Create output directory
RUN mkdir -p /app/output

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
