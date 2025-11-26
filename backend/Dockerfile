# Use full python image (not slim) for better library support
FROM python:3.11

WORKDIR /app

# Set environment variables for Python and pip
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Environment variables for torch and HuggingFace
ENV TORCH_HOME=/tmp/torch \
    HF_HOME=/tmp/huggingface \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1 \
    HF_HUB_DISABLE_SYMLINK_CACHE=1

# Install system dependencies for Docling SDK + YouTube processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build essentials
    gcc \
    g++ \
    make \
    cmake \
    # Database
    libpq-dev \
    # Tesseract OCR (multiple languages)
    tesseract-ocr \
    tesseract-ocr-eng \
    libtesseract-dev \
    # PDF processing
    poppler-utils \
    # OpenCV dependencies
    libgl1 \
    libgl1-mesa-dri \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgeos-dev \
    # Image processing
    libopencv-dev \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    # YouTube video processing
    ffmpeg \
    # Other utilities
    curl \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy unified requirements
COPY requirements-docker.txt /app/requirements.txt

# Install Python dependencies in stages for better caching
# Stage 1: Core dependencies (fast)
RUN pip install --upgrade pip setuptools wheel

# Stage 2: Install torch first (large, benefits from caching)
RUN pip install torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cpu

# Stage 3: Install remaining dependencies
RUN pip install -r requirements.txt

# Copy backend code
COPY backend/app /app/app

# Copy ingestion pipeline
COPY src /app/src

# Create necessary directories (add /tmp/youtube for video processing)
RUN mkdir -p /tmp/uploads /tmp/torch /tmp/huggingface /tmp/youtube

# Expose port for FastAPI
EXPOSE 8000

# Default command (can be overridden in docker-compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
