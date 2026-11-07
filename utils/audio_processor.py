import os 
import re
import wave
import subprocess
import shutil
import json
import base64
import tempfile
import concurrent.futures
import requests
import yt_dlp
from pydub import AudioSegment


def get_download_dir() -> str:
    """
    Returns a valid, writable directory for temporary media downloads and audio chunks.
    On Render, containers, or POSIX systems, /tmp is always writable.
    """
    configured = os.getenv("DOWNLOAD_DIR")
    if configured:
        os.makedirs(configured, exist_ok=True)
        return configured
    if os.name != "nt" or os.getenv("RENDER") or os.getenv("ENVIRONMENT") == "production":
        d = "/tmp/downloads"
    else:
        d = os.path.join(os.getcwd(), "downloads")
    os.makedirs(d, exist_ok=True)
    return d


DOWNLOAD_DIR = get_download_dir()


def ensure_ffmpeg() -> tuple[str, str]:
    """
    Ensures that ffmpeg and ffprobe are available, executable, and in PATH.
    Configures pydub and returns (ffmpeg_path, ffprobe_path).
    Supports Docker, Render native Python, Linux, macOS, and Windows.
    """
    # 1. Try static_ffmpeg package if installed (auto-downloads binaries for current OS)
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except Exception:
        pass

    # 2. Check and prepend standard Render and Linux binary directories
    search_dirs = [
        os.path.join(os.getenv("RENDER_PROJECT_DIR", "/opt/render/project"), ".render", "bin"),
        "/opt/render/project/.render/bin",
        "/tmp/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/opt/homebrew/bin"
    ]
    cur_path = os.environ.get("PATH", "")
    for d in search_dirs:
        if os.path.isdir(d) and d not in cur_path:
            os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]

    ffmpeg_bin = shutil.which("ffmpeg")
    ffprobe_bin = shutil.which("ffprobe")

    # 3. If either binary is missing, attempt imageio_ffmpeg fallback with shim wrappers
    if not (ffmpeg_bin and ffprobe_bin):
        try:
            import imageio_ffmpeg
            img_exe = imageio_ffmpeg.get_ffmpeg_exe()
            if img_exe and os.path.exists(img_exe):
                if os.name != "nt":
                    try:
                        st = os.stat(img_exe)
                        os.chmod(img_exe, st.st_mode | 0o111)
                    except Exception:
                        pass

                shim_dir = os.path.join(tempfile.gettempdir(), "kuchu_bin")
                os.makedirs(shim_dir, exist_ok=True)
                ext = ".exe" if os.name == "nt" else ""
                shim_ffmpeg = os.path.join(shim_dir, "ffmpeg" + ext)
                shim_ffprobe = os.path.join(shim_dir, "ffprobe" + ext)

                if not os.path.exists(shim_ffmpeg):
                    try:
                        if hasattr(os, "symlink") and os.name != "nt":
                            os.symlink(img_exe, shim_ffmpeg)
                        else:
                            shutil.copy2(img_exe, shim_ffmpeg)
                    except Exception:
                        pass

                if not os.path.exists(shim_ffprobe):
                    try:
                        if hasattr(os, "symlink") and os.name != "nt":
                            os.symlink(img_exe, shim_ffprobe)
                        else:
                            shutil.copy2(img_exe, shim_ffprobe)
                    except Exception:
                        pass

                if shim_dir not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = shim_dir + os.pathsep + os.environ.get("PATH", "")

                if not ffmpeg_bin:
                    ffmpeg_bin = shutil.which("ffmpeg") or shim_ffmpeg
                if not ffprobe_bin:
                    ffprobe_bin = shutil.which("ffprobe") or shim_ffprobe
        except Exception as e:
            print(f"[audio_processor] Notice during imageio_ffmpeg discovery: {e}")

    # Fallback strings if still unresolved
    if not ffmpeg_bin:
        ffmpeg_bin = "ffmpeg"
    if not ffprobe_bin:
        ffprobe_bin = "ffprobe"

    # Configure pydub global settings
    AudioSegment.converter = ffmpeg_bin
    AudioSegment.ffmpeg = ffmpeg_bin
    AudioSegment.prober = ffprobe_bin

    return ffmpeg_bin, ffprobe_bin


def get_ffmpeg_binary() -> str:
    """Find FFmpeg executable via ensure_ffmpeg()."""
    ffmpeg_bin, _ = ensure_ffmpeg()
    return ffmpeg_bin


# Initialize and resolve binaries at module import
ffmpeg_exe, ffprobe_exe = ensure_ffmpeg()


def get_js_runtimes() -> dict:
    """
    Detect available JavaScript runtimes for yt-dlp (Deno, Node.js).
    Deno is yt-dlp's primary, default-supported EJS challenge solver.
    """
    runtimes = {}
    # 1. Deno (primary & default for yt-dlp EJS challenge solver)
    for p in [shutil.which("deno"), "/usr/local/bin/deno", "/usr/bin/deno", os.path.expanduser("~/.deno/bin/deno")]:
        if p and (os.path.exists(p) or shutil.which(p)):
            runtimes["deno"] = {"path": p}
            break

    # 2. Node.js (secondary fallback)
    for p in [shutil.which("node"), shutil.which("nodejs"), "/usr/local/bin/node", "/usr/bin/node", "/usr/bin/nodejs"]:
        if p and (os.path.exists(p) or shutil.which(p)):
            runtimes["node"] = {"path": p}
            break

    return runtimes


def normalize_cookie_text(content: str) -> str:
    """
    Normalizes cookies from raw text, escaped newlines, or JSON arrays (from Chrome extensions like
    Cookie-Editor / EditThisCookie) into standard Netscape HTTP Cookie File format.
    """
    content = content.strip()
    if (content.startswith('"') and content.endswith('"')) or (content.startswith("'") and content.endswith("'")):
        content = content[1:-1].strip()

    # Unescape literal \n and \t if standard newlines are missing (common in single-line env vars)
    if "\\n" in content and "\n" not in content:
        content = content.replace("\\n", "\n").replace("\\r", "").replace("\\t", "\t")
    else:
        content = content.replace("\r\n", "\n").replace("\r", "\n")

    # Handle JSON array of cookies exported by browser extensions
    if content.startswith("[") and content.endswith("]"):
        try:
            data = json.loads(content)
            if isinstance(data, list):
                lines = [
                    "# Netscape HTTP Cookie File",
                    "# This file was generated by Kuchu Puchu AI from JSON export",
                    ""
                ]
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    domain = item.get("domain", "")
                    include_sub = "TRUE" if domain.startswith(".") else "FALSE"
                    path = item.get("path", "/")
                    secure = "TRUE" if item.get("secure", False) else "FALSE"
                    expiry = str(int(item.get("expirationDate", item.get("expiry", 0))))
                    name = item.get("name", "")
                    value = item.get("value", "")
                    if domain and name:
                        lines.append(f"{domain}\t{include_sub}\t{path}\t{secure}\t{expiry}\t{name}\t{value}")
                return "\n".join(lines) + "\n"
        except Exception as e:
            print(f"[audio_processor] Notice: JSON cookie parse attempt: {e}")

    # Ensure valid Netscape header
    if not content.startswith("# Netscape HTTP Cookie File"):
        content = "# Netscape HTTP Cookie File\n# This file was generated by Kuchu Puchu AI\n\n" + content

    return content


def get_youtube_cookiefile() -> str | None:
    """
    Safely resolves YouTube cookies for yt-dlp authentication from:
    1. Render Secret Files: /etc/secrets/cookies.txt, /etc/secrets/youtube_cookies.txt
    2. YOUTUBE_COOKIES_FILE or YOUTUBE_COOKIES_PATH env var
    3. Local cookies.txt, yt_cookies.txt, or youtube_cookies.txt in workspace root
    4. YOUTUBE_COOKIES_BASE64 env var (base64-encoded Netscape cookies text)
    5. YOUTUBE_COOKIES env var (raw Netscape cookies text or JSON array from Cookie-Editor)
    Returns the path to the verified cookie file or None.
    """
    # 1. Render Secret Files (/etc/secrets)
    secret_paths = [
        "/etc/secrets/cookies.txt",
        "/etc/secrets/youtube_cookies.txt",
        "/etc/secrets/yt_cookies.txt"
    ]
    for sp in secret_paths:
        if os.path.exists(sp) and os.path.getsize(sp) > 0:
            print(f"[audio_processor] Using Render Secret File cookies: {sp}")
            return sp

    # 2. Explicit environment variables for file paths
    for env_var in ["YOUTUBE_COOKIES_FILE", "YOUTUBE_COOKIES_PATH"]:
        file_env = os.getenv(env_var)
        if file_env and os.path.exists(file_env) and os.path.getsize(file_env) > 0:
            print(f"[audio_processor] Using cookies file from {env_var}: {file_env}")
            return file_env

    # 3. Workspace cookies files
    for local_name in ["cookies.txt", "yt_cookies.txt", "youtube_cookies.txt"]:
        local_cookie = os.path.join(os.getcwd(), local_name)
        if os.path.exists(local_cookie) and os.path.getsize(local_cookie) > 0:
            print(f"[audio_processor] Using workspace cookies file: {local_cookie}")
            return local_cookie

    # 4. Base64 encoded cookies environment variable
    b64_cookies = os.getenv("YOUTUBE_COOKIES_BASE64")
    if b64_cookies and b64_cookies.strip():
        try:
            decoded = base64.b64decode(b64_cookies.strip()).decode("utf-8", errors="replace")
            norm_content = normalize_cookie_text(decoded)
            tmp_path = os.path.join(get_download_dir(), "yt_cookies.txt")
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(norm_content)
            print(f"[audio_processor] Decoded YOUTUBE_COOKIES_BASE64 to {tmp_path}")
            return tmp_path
        except Exception as e:
            print(f"[audio_processor] Warning: Failed to decode YOUTUBE_COOKIES_BASE64: {e}")

    # 5. Raw text or JSON cookies environment variable
    raw_cookies = os.getenv("YOUTUBE_COOKIES")
    if raw_cookies and raw_cookies.strip():
        try:
            norm_content = normalize_cookie_text(raw_cookies)
            tmp_path = os.path.join(get_download_dir(), "yt_cookies.txt")
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(norm_content)
            print(f"[audio_processor] Prepared YOUTUBE_COOKIES to {tmp_path}")
            return tmp_path
        except Exception as e:
            print(f"[audio_processor] Warning: Failed to process YOUTUBE_COOKIES: {e}")

    return None


def extract_youtube_video_id(url: str) -> str | None:
    """Extract standard 11-char YouTube video ID from various URL formats or raw ID."""
    if not url:
        return None
    url = url.strip()
    if len(url) == 11 and re.match(r'^[A-Za-z0-9_-]{11}$', url):
        return url
    patterns = [
        r'(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/|\/live\/|\/watch\?v=|\/watch\?.+&v=)([^#\&\?]{11})',
        r'youtu\.be\/([^#\&\?]{11})',
        r'youtube\.com\/shorts\/([^#\&\?]{11})',
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


def extract_youtube_subtitles(url: str, cookie_file: str | None = None) -> str | None:
    """
    Fetches official or auto-generated YouTube captions directly.
    1. Primary method: YouTubeTranscriptApi (pure HTTP, zero media download, immune to datacenter blocks)
       Protected with a 10s timeout to prevent hanging on blocked datacenter IPs.
    2. Fallback method: yt-dlp timedtext scraping with fast socket timeouts.
    """
    video_id = extract_youtube_video_id(url)
    
    # ── Strategy 1: YouTubeTranscriptApi (Fastest, pure HTTP) ──
    if video_id:
        def _fetch_transcript():
            from youtube_transcript_api import YouTubeTranscriptApi
            api = YouTubeTranscriptApi()
            transcript_list = api.list(video_id)
            
            transcript = None
            try:
                transcript = transcript_list.find_transcript(['en', 'en-US', 'en-GB', 'hi', 'hi-Latn'])
            except Exception:
                for t in transcript_list:
                    # Prefer translatable to English if available
                    if getattr(t, "is_translatable", False):
                        try:
                            transcript = t.translate('en')
                            break
                        except Exception:
                            pass
                    transcript = t
                    break

            if transcript:
                fetched = transcript.fetch()
                text_snippets = []
                for s in fetched.snippets if hasattr(fetched, 'snippets') else fetched:
                    text_snippets.append(getattr(s, 'text', '') if hasattr(s, 'text') else (s.get('text', '') if isinstance(s, dict) else str(s)))
                full_text = " ".join(text_snippets).strip()
                if full_text:
                    return full_text
            return None

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_fetch_transcript)
                result = future.result(timeout=10.0)
                if result:
                    print(f"[audio_processor] Direct transcript extracted via YouTubeTranscriptApi ({len(result)} chars).")
                    return result
        except concurrent.futures.TimeoutError:
            print("[audio_processor] YouTubeTranscriptApi timed out after 10s, proceeding to fallback.")
        except Exception as e:
            print(f"[audio_processor] YouTubeTranscriptApi notice: {e}")

    # ── Strategy 2: yt-dlp timedtext metadata fallback ──────────────────────
    js_runtimes = get_js_runtimes()
    bin_path, _ = ensure_ffmpeg()

    opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 15,
        "retries": 2,
        "fragment_retries": 2,
        "extractor_args": {
            "youtube": {
                "player_client": ["ios", "android", "web"]
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
        }
    }
    if bin_path and os.path.exists(bin_path):
        opts["ffmpeg_location"] = os.path.dirname(bin_path) or bin_path
    if js_runtimes:
        opts["js_runtimes"] = js_runtimes
    if cookie_file and os.path.exists(cookie_file):
        opts["cookiefile"] = cookie_file

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None

            subs = info.get("subtitles") or {}
            auto_subs = info.get("automatic_captions") or {}

            # Preferred languages in order of preference
            target_entry = None
            for lang in ["en", "en-US", "en-GB", "hi", "hi-Latn"]:
                if lang in subs and subs[lang]:
                    target_entry = subs[lang]
                    break
                if lang in auto_subs and auto_subs[lang]:
                    target_entry = auto_subs[lang]
                    break

            if not target_entry:
                all_subs = {**subs, **auto_subs}
                if all_subs:
                    first_lang = next(iter(all_subs.keys()))
                    target_entry = all_subs[first_lang]

            if not target_entry:
                return None

            # Prioritize json3 format, else first available format
            json_fmt = next((fmt for fmt in target_entry if fmt.get("ext") == "json3"), None)
            if not json_fmt:
                json_fmt = target_entry[0]

            sub_url = json_fmt.get("url")
            if not sub_url:
                return None

            resp = requests.get(sub_url, timeout=10)
            if resp.status_code == 200:
                if json_fmt.get("ext") == "json3":
                    data = resp.json()
                    events = data.get("events", [])
                    text_parts = []
                    for ev in events:
                        for seg in ev.get("segs", []):
                            text_parts.append(seg.get("utf8", ""))
                    full_text = "".join(text_parts).strip()
                    if full_text:
                        print(f"[audio_processor] Direct YouTube transcript extracted via yt-dlp ({len(full_text)} chars).")
                        return full_text
                else:
                    raw_text = resp.text.strip()
                    if raw_text:
                        print(f"[audio_processor] Direct YouTube transcript format {json_fmt.get('ext')} extracted.")
                        return raw_text
    except Exception as e:
        print(f"[audio_processor] YouTube direct caption extraction notice: {e}")

    return None


def _build_ydl_opts(output_template: str, player_clients: list | None = None, cookie_file: str | None = None) -> dict:
    """
    Constructs robust yt-dlp options with:
    - Fallback player clients: ['ios', 'android', 'web'] to bypass datacenter player response blocks.
    - Custom modern User-Agent headers.
    - Broad format selector: allows 360p/480p MP4 if YouTube omits pure audio URLs (SABR experiment).
    - JavaScript runtime detection (Deno/Node.js) to solve YouTube challenge signatures.
    - Explicit FFmpeg location and extraction to 16kHz mono WAV.
    - Strict network timeouts to prevent hanging on datacenter rate limits.
    """
    js_runtimes = get_js_runtimes()
    bin_path, _ = ensure_ffmpeg()

    target_clients = player_clients if player_clients is not None else ["ios", "android", "web"]

    opts = {
        "format": "bestaudio/ba/b[ext=mp4]/b[height<=480]/18/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
        "file_access_retries": 2,
        "extractor_retries": 3,
        "extractor_args": {
            "youtube": {
                "player_client": target_clients
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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Mode": "navigate"
        }
    }
    if bin_path and os.path.exists(bin_path):
        opts["ffmpeg_location"] = os.path.dirname(bin_path) or bin_path
    if js_runtimes:
        opts["js_runtimes"] = js_runtimes
    if cookie_file and os.path.exists(cookie_file):
        opts["cookiefile"] = cookie_file
    return opts


def download_youtube_audio(url: str, progress_callback=None) -> str:
    """
    Downloads audio from a YouTube URL.
    Cycles through robust client strategies using real Innertube clients:
    1. ios, android, web (iOS player API first, then android & web fallback in single query)
    2. ios, mweb, web (mobile web fallback)
    3. web_embedded, ios (embedded player client)
    4. default yt-dlp selection
    """
    downloads_dir = get_download_dir()
    output_template = os.path.join(downloads_dir, "%(id)s.%(ext)s")
    cookie_file = get_youtube_cookiefile()
    if cookie_file:
        print(f"[audio_processor] Authenticated YouTube session detected ({cookie_file}).")

    client_strategies = [
        ["ios", "android", "web"],       # Primary: iOS player API first, then android & web fallback
        ["ios", "mweb", "web"],          # Mobile web fallback
        ["web_embedded", "ios"],         # Embedded player client
        None                             # Default yt-dlp selection
    ]

    last_error = None

    for attempt_idx, clients in enumerate(client_strategies):
        desc = clients if clients else "default yt-dlp"
        if progress_callback:
            progress_callback(f"Downloading YouTube audio with {desc[0] if isinstance(clients, list) else 'standard'} client...", 11)
        print(f"[audio_processor] Attempting YouTube extraction using clients: {desc} (attempt {attempt_idx + 1}/{len(client_strategies)})...")
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
                    for f in os.listdir(downloads_dir):
                        f_path = os.path.join(downloads_dir, f)
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
            print(f"[audio_processor] Client strategy {desc} failed: {last_error}")
            if attempt_idx < len(client_strategies) - 1:
                continue
        except Exception as e:
            last_error = str(e)
            print(f"[audio_processor] Strategy error: {last_error}")
            if attempt_idx < len(client_strategies) - 1:
                continue

    # If all audio download strategies failed, try direct subtitle/caption extraction fallback
    print("[audio_processor] Audio stream download restricted. Attempting direct YouTube captions fallback...")
    if progress_callback:
        progress_callback("Audio stream restricted. Attempting direct YouTube captions fallback...", 11)
    direct_transcript = extract_youtube_subtitles(url, cookie_file)
    if direct_transcript:
        import hashlib
        h = hashlib.md5(url.encode()).hexdigest()[:8]
        transcript_file = os.path.join(downloads_dir, f"yt_{h}_transcript.txt")
        with open(transcript_file, "w", encoding="utf-8") as f:
            f.write(direct_transcript)
        print(f"[audio_processor] Direct transcript successfully saved to {transcript_file}.")
        return transcript_file

    # If both audio download and captions were blocked
    err_lower = (last_error or "").lower()
    if "sign in to confirm you're not a bot" in err_lower or "bot" in err_lower or "403" in err_lower or "player response" in err_lower:
        raise RuntimeError(
            "YouTube has blocked player response extraction from Render's cloud IP and no public captions were found. "
            "To solve this: 1) Add your YouTube cookies to Render as a Secret File (/etc/secrets/cookies.txt) "
            "or via the YOUTUBE_COOKIES environment variable (see .env.example), "
            "or 2) Upload your video/audio file directly via 'Upload Audio / Video'."
        )
    elif "private video" in err_lower or "video unavailable" in err_lower:
        raise RuntimeError(f"YouTube video is private or unavailable: {last_error}")
    raise RuntimeError(f"YouTube extraction failed: {last_error}")


def convert_to_wav(input_path: str, progress_callback=None) -> str:
    """
    Convert any audio/video file to 16kHz mono WAV using direct FFmpeg with pydub fallback.
    Uses -nostdin and stdin=subprocess.DEVNULL to prevent hangs in headless server environments.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    downloads_dir = get_download_dir()
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    output_path = os.path.join(downloads_dir, f"{base_name}_converted.wav")

    bin_path, _ = ensure_ffmpeg()

    if progress_callback:
        progress_callback("Converting media to 16kHz audio track with FFmpeg...", 11)

    # Fast path: use ffmpeg directly (bypasses Python memory overhead and completes in <1s)
    if bin_path:
        try:
            cmd = [
                bin_path, "-y", "-nostdin", "-v", "error",
                "-i", input_path,
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                output_path
            ]
            subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=120,
                check=True
            )
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                print(f"[audio_processor] Direct FFmpeg conversion succeeded: {output_path}")
                return output_path
        except subprocess.TimeoutExpired:
            print(f"[audio_processor] Direct FFmpeg conversion timed out after 120s for {input_path}")
        except Exception as e:
            print(f"[audio_processor] Direct FFmpeg conversion notice: {e}, falling back to pydub...")

    # Fallback to pydub if direct ffmpeg fails
    try:
        audio = AudioSegment.from_file(input_path)
        audio = audio.set_channels(1).set_frame_rate(16000)
        audio.export(output_path, format="wav")
        return output_path
    except Exception as pe:
        raise RuntimeError(
            f"Failed to convert media file to 16kHz WAV format: {pe}. "
            "Please ensure ffmpeg is installed or upload an uncompressed WAV or standard MP3 file."
        )


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


def chunk_audio(wav_path: str, chunk_minutes: int = 10, progress_callback=None) -> list:
    """
    Chunk audio if it exceeds chunk limit (default 10 min ~18MB for 16kHz mono WAV);
    otherwise return original file.
    Uses fast direct FFmpeg stream copy to avoid memory bloat on 512MB RAM servers.
    """
    duration_sec = get_audio_duration_seconds(wav_path)
    chunk_limit_sec = chunk_minutes * 60

    file_size_mb = os.path.getsize(wav_path) / (1024 * 1024) if os.path.exists(wav_path) else 0
    if duration_sec > 0 and duration_sec <= chunk_limit_sec and file_size_mb < 24.0:
        print(f"[audio_processor] Audio duration is {duration_sec:.1f}s, size {file_size_mb:.1f}MB. Single chunk used.")
        return [wav_path]

    print(f"[audio_processor] Audio duration is {duration_sec:.1f}s ({file_size_mb:.1f}MB). Slicing into {chunk_minutes}-min chunks...")
    if progress_callback:
        progress_callback(f"Audio is {duration_sec / 60:.1f}m long. Slicing into {chunk_minutes}-min chunks...", 11)

    bin_path, _ = ensure_ffmpeg()
    chunk_sec = chunk_minutes * 60
    chunks = []

    # Fast path: use direct FFmpeg stream copy slicing (takes ~0.05s, uses <5MB RAM, safe for Render free tier 512MB RAM)
    if bin_path and duration_sec > 0:
        try:
            num_chunks = int(duration_sec // chunk_sec) + (1 if duration_sec % chunk_sec > 0 else 0)
            for i in range(num_chunks):
                start_s = i * chunk_sec
                c_path = f"{wav_path}_chunk_{i}.wav"
                cmd = [
                    bin_path, "-y", "-nostdin", "-v", "error",
                    "-ss", str(start_s),
                    "-t", str(chunk_sec),
                    "-i", wav_path,
                    "-c", "copy",
                    c_path
                ]
                subprocess.run(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=60,
                    check=True
                )
                if os.path.exists(c_path) and os.path.getsize(c_path) > 0:
                    chunks.append(c_path)
            if len(chunks) == num_chunks:
                print(f"[audio_processor] Direct FFmpeg chunking created {len(chunks)} chunk(s).")
                return chunks
        except Exception as e:
            print(f"[audio_processor] Direct FFmpeg chunking notice: {e}, falling back to pydub slicing...")
            for c in chunks:
                if os.path.exists(c):
                    try:
                        os.remove(c)
                    except Exception:
                        pass
            chunks = []

    # Fallback to pydub if direct FFmpeg slice wasn't used or failed
    audio = AudioSegment.from_wav(wav_path)
    chunk_ms = chunk_minutes * 60 * 1000

    chunks = []
    for i, start in enumerate(range(0, len(audio), chunk_ms)):
        chunk = audio[start: start + chunk_ms]
        chunk_path = f"{wav_path}_chunk_{i}.wav"
        chunk.export(chunk_path, format="wav")
        chunks.append(chunk_path)

    return chunks


def process_input(source: str, progress_callback=None) -> list:
    """
    Process input source (YouTube URL or uploaded media file).
    For YouTube URLs:
    1. Checks for instant direct captions first (fastest, zero bandwidth, immune to cloud IP blocks)
    2. Falls back to downloading audio and slicing into 16kHz WAV chunks for Whisper
    """
    if source.startswith("http://") or source.startswith("https://"):
        print(f"[audio_processor] Processing remote URL source: {source}")
        if progress_callback:
            progress_callback("Checking for direct YouTube captions / transcript...", 11)

        # Check direct captions first (completes in ~0.5s and bypasses datacenter blocks)
        cookie_file = get_youtube_cookiefile()
        direct_transcript = extract_youtube_subtitles(source, cookie_file)
        if direct_transcript:
            import hashlib
            h = hashlib.md5(source.encode()).hexdigest()[:8]
            transcript_file = os.path.join(get_download_dir(), f"yt_{h}_transcript.txt")
            with open(transcript_file, "w", encoding="utf-8") as f:
                f.write(direct_transcript)
            print(f"[audio_processor] Direct verified transcript saved: {transcript_file}")
            if progress_callback:
                progress_callback("Direct verified captions fetched from YouTube timedtext!", 11)
            return [transcript_file]

        # If direct captions not available, download audio streams
        if progress_callback:
            progress_callback("Downloading YouTube audio tracks with yt-dlp...", 11)
        extracted_path = download_youtube_audio(source, progress_callback)
    else:
        print(f"[audio_processor] Processing local media upload: {source}")
        if progress_callback:
            progress_callback("Extracting 16kHz audio track from uploaded media...", 11)
        extracted_path = convert_to_wav(source, progress_callback)

    # If direct transcript file was returned from timedtext fallback
    if extracted_path.endswith(".txt"):
        print(f"[audio_processor] Direct transcript mode active: {extracted_path}")
        return [extracted_path]

    print("[audio_processor] Checking audio duration and chunk limits...")
    if progress_callback:
        progress_callback("Preparing audio chunks for transcription...", 11)
    chunks = chunk_audio(extracted_path, chunk_minutes=10, progress_callback=progress_callback)
    print(f"[audio_processor] Audio ready — {len(chunks)} chunk(s) prepared.")
    return chunks
