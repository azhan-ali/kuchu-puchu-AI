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
    DEBIAN_FRONTEND=noninteractive \
    DOWNLOAD_DIR=/tmp/downloads \
    CHROMA_PERSIST_DIR=/tmp/vector_db \
    PATH="/tmp/bin:/usr/local/bin:$PATH"

WORKDIR /app

# Install system dependencies (FFmpeg for video/audio extraction, Deno & Node.js as JS runtimes for yt-dlp, curl, unzip)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    unzip \
    nodejs \
    ca-certificates \
    && (which node > /dev/null 2>&1 || ln -s /usr/bin/nodejs /usr/bin/node || true) \
    && curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh \
    && (which deno > /dev/null 2>&1 || ln -s /usr/local/bin/deno /usr/bin/deno || true) \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and packaging tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Pre-install CPU-only PyTorch and torchaudio to prevent pulling multi-GB CUDA binaries
RUN pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# Install project Python dependencies and ensure the latest release of yt-dlp is always installed
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --upgrade --force-reinstall "yt-dlp[default]" yt-dlp-ejs static-ffmpeg

# Verify FFmpeg and FFprobe system executables
RUN ffmpeg -version && ffprobe -version

# Copy application source code
COPY . .

# Create persistent/runtime directories in workspace and temporary storage
RUN mkdir -p /tmp/downloads /tmp/vector_db /tmp/bin downloads vector_db \
    && chmod -R 777 /tmp/downloads /tmp/vector_db /tmp/bin || true

# Expose default port
EXPOSE 8000

# Docker Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Start Uvicorn with single worker, proxy headers, and generous keep-alive for streaming
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --timeout-keep-alive 120"]


