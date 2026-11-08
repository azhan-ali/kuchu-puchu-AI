#!/usr/bin/env bash
# ========================================================
# Kuchu Puchu AI — Render Build Script
# Ensures FFmpeg, FFprobe, and Python dependencies on Render
# ========================================================
set -o errexit

echo "=== [render-build] Starting Kuchu Puchu AI Build on Render ==="

# 1. Setup persistent storage/bin directory for static binaries
BIN_DIR="${RENDER_PROJECT_DIR:-/opt/render/project}/.render/bin"
mkdir -p "$BIN_DIR"
mkdir -p /tmp/downloads /tmp/vector_db /tmp/chroma /tmp/bin
chmod -R 777 /tmp/downloads /tmp/vector_db /tmp/chroma /tmp/bin || true

# 2. Check if ffmpeg & ffprobe exist on PATH or in BIN_DIR
if ! command -v ffmpeg &> /dev/null || ! command -v ffprobe &> /dev/null; then
    if [ ! -f "$BIN_DIR/ffmpeg" ] || [ ! -f "$BIN_DIR/ffprobe" ]; then
        echo "[render-build] System FFmpeg not found. Downloading static FFmpeg release..."
        FFMPEG_ARCHIVE="/tmp/ffmpeg-release.tar.xz"
        curl -fsSL -o "$FFMPEG_ARCHIVE" "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz" || true
        
        if [ -f "$FFMPEG_ARCHIVE" ] && [ -s "$FFMPEG_ARCHIVE" ]; then
            EXTRACT_DIR="/tmp/ffmpeg_extracted"
            mkdir -p "$EXTRACT_DIR"
            tar -xf "$FFMPEG_ARCHIVE" -C "$EXTRACT_DIR" --strip-components 1
            cp "$EXTRACT_DIR/ffmpeg" "$BIN_DIR/ffmpeg"
            cp "$EXTRACT_DIR/ffprobe" "$BIN_DIR/ffprobe"
            chmod +x "$BIN_DIR/ffmpeg" "$BIN_DIR/ffprobe"
            rm -rf "$FFMPEG_ARCHIVE" "$EXTRACT_DIR"
            echo "[render-build] Successfully installed static FFmpeg & FFprobe to $BIN_DIR"
        else
            echo "[render-build] Notice: Direct tarball download skipped or unavailable; static-ffmpeg Python package will provide binaries."
        fi
    fi
fi

export PATH="$BIN_DIR:/tmp/bin:$PATH"

# 3. Upgrade pip and build tools
python -m pip install --no-cache-dir --upgrade pip setuptools wheel

# 4. Install PyTorch CPU-only wheel
python -m pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# 5. Install project dependencies and ensure latest release of yt-dlp is installed
python -m pip install --no-cache-dir -r requirements.txt
python -m pip install --no-cache-dir --upgrade --force-reinstall "yt-dlp[default]" yt-dlp-ejs static-ffmpeg

echo "=== [render-build] Build Complete ==="

