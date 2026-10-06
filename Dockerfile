# ========================================================
# Kuchu Puchu AI — Production Dockerfile
# Optimized for Railway, Render, and Container Environments
# ========================================================

FROM python:3.11-slim

# Prevent Python from buffering stdout/stderr and writing .pyc files
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    HOST=0.0.0.0 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system dependencies (FFmpeg for video/audio extraction, curl for health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Pre-install CPU-only PyTorch and torchaudio to prevent pulling multi-GB CUDA binaries
RUN pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# Install project Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Create persistent/runtime directories
RUN mkdir -p downloads vector_db

# Expose default port
EXPOSE 8000

# Docker Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Start Uvicorn with single worker to preserve in-memory RAG sessions and optimize memory usage
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
