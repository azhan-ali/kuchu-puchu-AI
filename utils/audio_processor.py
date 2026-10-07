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

def get_youtube_cookiefile() -> str | None:
    """
    Safely resolves YouTube cookies for yt-dlp authentication from:
    1. YOUTUBE_COOKIES_FILE env var (absolute or relative path to cookies file)
    2. Local cookies.txt file in workspace root
    3. YOUTUBE_COOKIES_BASE64 env var (base64-encoded Netscape cookies text)
    4. YOUTUBE_COOKIES env var (raw Netscape cookies text)
    Returns the path to the cookie file or None.
    """
    file_env = os.getenv("YOUTUBE_COOKIES_FILE")
    if file_env and os.path.exists(file_env) and os.path.getsize(file_env) > 0:
        return file_env

    local_cookie = os.path.join(os.getcwd(), "cookies.txt")
    if os.path.exists(local_cookie) and os.path.getsize(local_cookie) > 0:
        return local_cookie

    b64_cookies = os.getenv("YOUTUBE_COOKIES_BASE64")
    if b64_cookies and b64_cookies.strip():
        try:
            import base64
            decoded = base64.b64decode(b64_cookies.strip()).decode("utf-8", errors="replace")
            tmp_path = os.path.join(DOWNLOAD_DIR, "yt_cookies.txt")
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(decoded)
            return tmp_path
        except Exception as e:
            print(f"[audio_processor] Warning: Failed to decode YOUTUBE_COOKIES_BASE64: {e}")

    raw_cookies = os.getenv("YOUTUBE_COOKIES")
    if raw_cookies and raw_cookies.strip():
        tmp_path = os.path.join(DOWNLOAD_DIR, "yt_cookies.txt")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(raw_cookies.strip())
        return tmp_path

    return None


def _build_ydl_opts(output_template: str, player_clients: list, cookie_file: str | None = None) -> dict:
    opts = {
        "format": "bestaudio/best[ext=m4a]/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "extractor_args": {
            "youtube": {
                "player_client": player_clients
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
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        }
    }
    if cookie_file and os.path.exists(cookie_file):
        opts["cookiefile"] = cookie_file
    return opts


## function that download the audio from youtube link 
def download_youtube_audio(url: str) -> str:
    output_template = os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s")
    cookie_file = get_youtube_cookiefile()
    if cookie_file:
        print("[audio_processor] Authenticated YouTube session detected (cookiefile enabled).")

    # Client strategies: android + web_safari avoids bot challenges; pure android as backup
    client_strategies = [
        ["android", "web_safari"],
        ["android"],
        ["tv", "android"]
    ]

    last_error = None

    for attempt_idx, clients in enumerate(client_strategies):
        print(f"[audio_processor] Attempting YouTube extraction using clients: {clients} (attempt {attempt_idx + 1}/{len(client_strategies)})...")
        ydl_opts = _build_ydl_opts(output_template, clients, cookie_file)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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
            last_error = str(de)
            print(f"[audio_processor] Client strategy {clients} failed: {last_error}")
            # If not last attempt, continue to next client strategy
            if attempt_idx < len(client_strategies) - 1:
                continue
        except Exception as e:
            last_error = str(e)
            print(f"[audio_processor] Strategy error: {last_error}")
            if attempt_idx < len(client_strategies) - 1:
                continue

    # If all client strategies were exhausted
    err_lower = (last_error or "").lower()
    if "sign in to confirm you're not a bot" in err_lower or "bot" in err_lower or "403" in err_lower:
        raise RuntimeError(
            "YouTube has flagged this datacenter IP for bot verification. "
            "To solve this: 1) Add your YouTube cookies to Railway via the YOUTUBE_COOKIES environment variable (see .env.example), "
            "or 2) Upload your video/audio file directly via 'Upload Audio / Video'."
        )
    elif "private video" in err_lower or "video unavailable" in err_lower:
        raise RuntimeError(f"YouTube video is private or unavailable: {last_error}")
    raise RuntimeError(f"YouTube extraction failed: {last_error}")


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