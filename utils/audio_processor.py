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
                "player_client": ["android", "ios"]
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
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if "entries" in info and info["entries"]:
            info = info["entries"][0]
        prep = ydl.prepare_filename(info)
        base = os.path.splitext(prep)[0]
        filename = base + ".wav"
        if not os.path.exists(filename):
            vid_id = info.get("id", "")
            for f in os.listdir(DOWNLOAD_DIR):
                if f.endswith(".wav") and (vid_id in f or os.path.basename(base) in f):
                    filename = os.path.join(DOWNLOAD_DIR, f)
                    break
    return filename


## Convert audio/video to 16kHz mono WAV format efficiently
def convert_to_wav(input_path: str) -> str:
    """Convert any audio/video file to 16kHz mono WAV using direct FFmpeg with pydub fallback."""
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
            return output_path
    except Exception as e:
        print(f"Direct FFmpeg conversion notice: {e}, falling back to pydub...")

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


def chunk_audio(wav_path: str, chunk_minutes: int = 15) -> list:
    """Chunk audio only if it exceeds the chunk limit; otherwise return original file."""
    duration_sec = get_audio_duration_seconds(wav_path)
    chunk_limit_sec = chunk_minutes * 60

    # If within chunk limit, avoid duplicate re-reading and re-exporting
    if duration_sec > 0 and duration_sec <= chunk_limit_sec:
        print(f"Audio duration is {duration_sec:.1f}s (<= {chunk_limit_sec}s). Single chunk used.")
        return [wav_path]

    print(f"Audio duration is {duration_sec:.1f}s (> {chunk_limit_sec}s). Slicing into {chunk_minutes}-min chunks...")
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
        print("Detected YouTube URL. Downloading audio...")
        wav_path = download_youtube_audio(source)
    else:
        print("Detected local file. Converting to 16kHz WAV...")
        wav_path = convert_to_wav(source)

    print("Checking audio chunks...")
    chunks = chunk_audio(wav_path, chunk_minutes=15)
    print(f"Audio ready — {len(chunks)} chunk(s) prepared.")
    return chunks