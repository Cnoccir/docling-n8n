# Use Python 3.11 as the base image
FROM python:3.11-slim

# Set up environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    git \
    tesseract-ocr \
    libtesseract-dev \
    poppler-utils \
    libmagic1 \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ./enhanced_document_fetcher.py /app/
COPY ./enhanced_types.py /app/
COPY ./app.py /app/

# Copy the core document processing libraries
# Assuming your app code is in a directory called "app"
RUN mkdir -p /app/app/chat/utils
COPY ./app /app/app/

# Create output directory
RUN mkdir -p /app/output && \
    chmod -R 777 /app/output

# Expose port
EXPOSE 8000

# Define health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Set up a non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Run the application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
