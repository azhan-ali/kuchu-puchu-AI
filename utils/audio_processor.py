import os 
import wave
import subprocess
import shutil
import yt_dlp
from pydub import AudioSegment

# Configurable downloads directory
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def get_ffmpeg_binary() -> str:
    """Find FFmpeg executable from PATH, imageio_ffmpeg, or common system locations."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    for p in ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg"]:
        if os.path.exists(p):
            return p
    return "ffmpeg"

# Ensure pydub uses the resolved FFmpeg binary
ffmpeg_exe = get_ffmpeg_binary()
if ffmpeg_exe and ffmpeg_exe != "ffmpeg":
    AudioSegment.converter = ffmpeg_exe

## function that download the audio from youtube link 
def download_youtube_audio(url: str) -> str:
    output_template = os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web", "ios"]
            }
        },
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }
        ],
        "postprocessor_args": [
            "-ar", "16000",
            "-ac", "1"
        ],
        "quiet": False,
        "no_warnings": False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"[audio_processor] Extracting audio from YouTube: {url}")
            info = ydl.extract_info(url, download=True)
            if "entries" in info and info["entries"]:
                info = info["entries"][0]
            prep = ydl.prepare_filename(info)
            base = os.path.splitext(prep)[0]
            filename = base + ".wav"
            
            if not os.path.exists(filename) or os.path.getsize(filename) == 0:
                vid_id = info.get("id", "")
                found = None
                for f in os.listdir(DOWNLOAD_DIR):
                    f_path = os.path.join(DOWNLOAD_DIR, f)
                    if (vid_id in f or os.path.basename(base) in f) and os.path.getsize(f_path) > 0:
                        if f.endswith(".wav"):
                            found = f_path
                            break
                        elif f.endswith((".webm", ".m4a", ".mp4", ".opus", ".mp3")):
                            print(f"[audio_processor] Converting downloaded raw stream {f} to WAV...")
                            found = convert_to_wav(f_path)
                            break
                if found and os.path.exists(found) and os.path.getsize(found) > 0:
                    filename = found
                else:
                    raise FileNotFoundError(f"Could not locate extracted WAV file for YouTube ID: {vid_id}")

            print(f"[audio_processor] YouTube audio successfully downloaded: {filename}")
            return filename
            
    except yt_dlp.utils.DownloadError as de:
        err_msg = str(de)
        print(f"[audio_processor] YouTube download error: {err_msg}")
        if "Sign in to confirm you're not a bot" in err_msg or "blocked" in err_msg.lower() or "403" in err_msg:
            raise RuntimeError(
                "YouTube has restricted downloads from cloud datacenter servers. "
                "Please download the video or audio locally and upload the file directly using the 'Upload Audio / Video' option."
            )
        elif "Private video" in err_msg or "Video unavailable" in err_msg:
            raise RuntimeError(f"YouTube video is unavailable or private: {err_msg}")
        raise RuntimeError(f"YouTube extraction failed: {err_msg}")
    except Exception as e:
        print(f"[audio_processor] Unexpected YouTube download error: {e}")
        raise RuntimeError(f"Failed to process YouTube audio: {str(e)}")


## Convert audio/video to 16kHz mono WAV format efficiently
def convert_to_wav(input_path: str) -> str:
    """Convert any audio/video file to 16kHz mono WAV using direct FFmpeg with pydub fallback."""
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")
        
    output_path = os.path.splitext(input_path)[0] + "_converted.wav"
    bin_path = get_ffmpeg_binary()
    
    # Fast path: use ffmpeg directly (bypasses Python memory overhead and runs in <1s)
    try:
        cmd = [
            bin_path, "-y", "-v", "error",
            "-i", input_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            output_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"[audio_processor] Direct FFmpeg conversion succeeded: {output_path}")
            return output_path
    except Exception as e:
        print(f"[audio_processor] Direct FFmpeg conversion notice: {e}, falling back to pydub...")

    # Fallback to pydub if direct ffmpeg fails
    audio = AudioSegment.from_file(input_path)
    audio = audio.set_channels(1).set_frame_rate(16000)
    audio.export(output_path, format="wav")
    return output_path


def get_audio_duration_seconds(wav_path: str) -> float:
    """Fast duration lookup using standard wave module (0ms, no decoding)."""
    try:
        with wave.open(wav_path, 'rb') as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate)
    except Exception:
        pass
    try:
        audio = AudioSegment.from_file(wav_path)
        return len(audio) / 1000.0
    except Exception:
        return 0.0


def chunk_audio(wav_path: str, chunk_minutes: int = 10) -> list:
    """
    Chunk audio if it exceeds the chunk limit (default 10 min ~18MB to ensure safe <24MB API payloads);
    otherwise return original file.
    """
    duration_sec = get_audio_duration_seconds(wav_path)
    chunk_limit_sec = chunk_minutes * 60

    # If within chunk limit and file size is safe (<24MB), return original file
    file_size_mb = os.path.getsize(wav_path) / (1024 * 1024) if os.path.exists(wav_path) else 0
    if duration_sec > 0 and duration_sec <= chunk_limit_sec and file_size_mb < 24.0:
        print(f"[audio_processor] Audio duration is {duration_sec:.1f}s, size {file_size_mb:.1f}MB. Single chunk used.")
        return [wav_path]

    print(f"[audio_processor] Audio duration is {duration_sec:.1f}s ({file_size_mb:.1f}MB). Slicing into {chunk_minutes}-min chunks...")
    audio = AudioSegment.from_wav(wav_path)
    chunk_ms = chunk_minutes * 60 * 1000

    chunks = []
    for i, start in enumerate(range(0, len(audio), chunk_ms)):
        chunk = audio[start: start + chunk_ms]
        chunk_path = f"{wav_path}_chunk_{i}.wav"
        chunk.export(chunk_path, format="wav")
        chunks.append(chunk_path)

    return chunks


def process_input(source: str) -> list:
    if source.startswith("http://") or source.startswith("https://"):
        print(f"[audio_processor] Processing remote URL source: {source}")
        wav_path = download_youtube_audio(source)
    else:
        print(f"[audio_processor] Processing local media upload: {source}")
        wav_path = convert_to_wav(source)

    print("[audio_processor] Checking audio duration and chunk limits...")
    chunks = chunk_audio(wav_path, chunk_minutes=10)
    print(f"[audio_processor] Audio ready — {len(chunks)} chunk(s) prepared.")
    return chunks