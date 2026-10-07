import os 
import time
import requests
import torch
from pydub import AudioSegment
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

load_dotenv()

# Sarvam's sync STT-translate API rejects audio longer than 30s.
SARVAM_PIECE_SECONDS = 25
SARVAM_STT_TRANSLATE_URL = "https://api.sarvam.ai/speech-to-text-translate"

_local_whisper_model = None

def get_stt_engine_name(language: str = "english") -> str:
    """Returns human-friendly name of the engine that will be used."""
    groq_key = os.getenv("GROQ_API_KEY")
    sarvam_key = os.getenv("SARVAM_API_KEY")
    
    if language and language.lower() == "hinglish" and sarvam_key:
        return "Sarvam AI"
    elif groq_key:
        return "Whisper (Groq Cloud Turbo)"
    else:
        return "Whisper (Local CPU)"

def load_local_whisper_model():
    """Lazy-load local Whisper model with memory-safe default ('base' instead of heavy 'small')."""
    global _local_whisper_model

    if _local_whisper_model is None:
        import whisper
        # In cloud environments, 'base' or 'tiny' uses <150MB RAM vs >500MB for 'small'
        model_name = os.getenv("WHISPER_MODEL", "base")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[transcriber] Loading local Whisper fallback model: {model_name} on device: {device}...")
        _local_whisper_model = whisper.load_model(model_name, device=device)
        print(f"[transcriber] Local Whisper model ({model_name}) loaded successfully.")

    return _local_whisper_model

def transcribe_chunk_groq(chunk_path: str, language: str = "english") -> str:
    """Fast Groq cloud Whisper transcription (runs in 1-3 seconds, 0MB server RAM)."""
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        raise ValueError("GROQ_API_KEY not configured.")

    from groq import Groq
    client = Groq(api_key=groq_key)
    model = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")

    # Groq accepts maximum 25 MB file size
    file_size_mb = os.path.getsize(chunk_path) / (1024 * 1024)
    if file_size_mb > 24.0:
        print(f"[transcriber] Chunk {chunk_path} is {file_size_mb:.1f}MB (>24MB). Compressing for Groq...")
        compressed_path = chunk_path + "_groq.mp3"
        try:
            audio = AudioSegment.from_file(chunk_path)
            audio.export(compressed_path, format="mp3", bitrate="64k")
            target_file = compressed_path
        except Exception as e:
            print(f"[transcriber] MP3 compression failed: {e}, using original chunk")
            target_file = chunk_path
    else:
        target_file = chunk_path
        compressed_path = None

    try:
        with open(target_file, "rb") as f:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(target_file), f),
                model=model,
                response_format="text",
                language="en" if language and language.lower() == "english" else None,
                temperature=0.0
            )
            result_text = transcription if isinstance(transcription, str) else transcription.text
            return result_text.strip()
    finally:
        if compressed_path and os.path.exists(compressed_path):
            try:
                os.remove(compressed_path)
            except Exception:
                pass

def transcribe_chunk_whisper(chunk_path: str, language: str = "english") -> str:
    """Local Whisper fallback if cloud APIs are unavailable."""
    model = load_local_whisper_model()
    is_cuda = torch.cuda.is_available()

    transcribe_kwargs = {
        "task": "transcribe",
        "beam_size": 1,
        "best_of": 1,
        "temperature": 0.0,
        "condition_on_previous_text": False,
        "fp16": is_cuda
    }
    if language and language.lower() == "english":
        transcribe_kwargs["language"] = "en"

    result = model.transcribe(chunk_path, **transcribe_kwargs)
    return result.get("text", "")

def _send_to_sarvam(piece_path: str) -> str:
    """Send one ≤30s WAV file to Sarvam and return the English transcript."""
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        raise RuntimeError("SARVAM_API_KEY is not set in environment variables.")
    sarvam_model = os.getenv("SARVAM_STT_MODEL", "saaras:v2.5")
    headers = {"api-subscription-key": api_key}

    with open(piece_path, "rb") as f:
        files = {"file": (os.path.basename(piece_path), f, "audio/wav")}
        data = {"model": sarvam_model, "with_diarization": "false"}
        response = requests.post(
            SARVAM_STT_TRANSLATE_URL,
            headers=headers,
            files=files,
            data=data,
            timeout=120,
        )

    if not response.ok:
        print(f"\n❌ Sarvam returned {response.status_code}: {response.text}\n")
        response.raise_for_status()

    return response.json().get("transcript", "")

def transcribe_chunk_sarvam(chunk_path: str) -> str:
    """
    Sarvam sync API only accepts ≤30s audio. Splits chunk into
    25-second pieces, sends each concurrently, and joins the transcripts in order.
    """
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        print("[transcriber] SARVAM_API_KEY not configured. Falling back to Groq/Whisper...")
        return transcribe_chunk_groq_or_whisper(chunk_path, language="hinglish")

    audio = AudioSegment.from_wav(chunk_path)
    piece_ms = SARVAM_PIECE_SECONDS * 1000

    total_pieces = (len(audio) + piece_ms - 1) // piece_ms
    pieces_info = []

    for i, start in enumerate(range(0, len(audio), piece_ms)):
        piece = audio[start: start + piece_ms]
        piece_path = f"{chunk_path}_sv_{i}.wav"
        piece.export(piece_path, format="wav")
        pieces_info.append((i, piece_path))

    def _process_piece(item):
        idx, p_path = item
        try:
            print(f"  → Sarvam piece {idx + 1}/{total_pieces}...")
            text = _send_to_sarvam(p_path)
            return (idx, text)
        finally:
            if os.path.exists(p_path):
                try:
                    os.remove(p_path)
                except Exception:
                    pass

    max_workers = min(6, len(pieces_info)) if pieces_info else 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(_process_piece, pieces_info))

    results.sort(key=lambda x: x[0])
    return " ".join(r[1] for r in results if r[1]).strip()

def transcribe_chunk_groq_or_whisper(chunk_path: str, language: str = "english") -> str:
    """Try Groq cloud Whisper first; fallback to local Whisper if Groq fails or is not configured."""
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            print(f"[transcriber] Transcribing chunk via Groq Whisper ({os.path.basename(chunk_path)})...")
            t0 = time.time()
            text = transcribe_chunk_groq(chunk_path, language=language)
            print(f"[transcriber] Groq transcription completed in {time.time() - t0:.2f}s.")
            return text
        except Exception as e:
            print(f"[transcriber] Groq Whisper failed ({e}). Falling back to local Whisper...")
    
    print(f"[transcriber] Using local Whisper for chunk {os.path.basename(chunk_path)}...")
    t0 = time.time()
    text = transcribe_chunk_whisper(chunk_path, language=language)
    print(f"[transcriber] Local Whisper completed in {time.time() - t0:.2f}s.")
    return text

def transcribe_chunk(chunk_path: str, language: str = "english") -> str:
    """
    Route audio chunk to appropriate engine:
    - hinglish with SARVAM_API_KEY → Sarvam AI
    - english or general → Groq Whisper Turbo (with local Whisper fallback)
    """
    if language and language.lower() == "hinglish" and os.getenv("SARVAM_API_KEY"):
        return transcribe_chunk_sarvam(chunk_path)
    else:
        return transcribe_chunk_groq_or_whisper(chunk_path, language=language)

def transcribe_all(chunks: list, language: str = "english", progress_callback=None) -> str:
    """
    Transcribes all audio chunks. Supports optional progress_callback(chunk_idx, total_chunks, partial_text).
    """
    if not chunks:
        return ""

    # Direct transcript fallback support
    if len(chunks) == 1 and str(chunks[0]).endswith(".txt") and os.path.exists(chunks[0]):
        print(f"[transcriber] Pre-extracted transcript provided via {chunks[0]}. Reading directly...")
        try:
            with open(chunks[0], "r", encoding="utf-8") as f:
                content = f.read().strip()
            word_count = len(content.split())
            print(f"[transcriber] Direct transcript loaded ({word_count} words).")
            if progress_callback:
                try:
                    progress_callback(1, 1, content)
                except Exception:
                    pass
            return content
        except Exception as e:
            print(f"[transcriber] Notice: Could not read direct transcript file: {e}")

    engine_name = get_stt_engine_name(language)
    total = len(chunks)
    print(f"[transcriber] Using {engine_name} for transcription of {total} chunk(s)...")

    # If using Groq and multiple chunks, transcribe concurrently for even faster results
    groq_key = os.getenv("GROQ_API_KEY")
    can_parallel = bool(groq_key and total > 1 and not (language.lower() == "hinglish" and os.getenv("SARVAM_API_KEY")))

    if can_parallel:
        print(f"[transcriber] Transcribing {total} chunks concurrently with Groq...")
        def _worker(item):
            idx, c_path = item
            txt = transcribe_chunk_groq_or_whisper(c_path, language=language)
            if progress_callback:
                try:
                    progress_callback(idx + 1, total, txt)
                except Exception:
                    pass
            return (idx, txt)

        items = list(enumerate(chunks))
        with ThreadPoolExecutor(max_workers=min(4, total)) as executor:
            results = list(executor.map(_worker, items))
        results.sort(key=lambda x: x[0])
        full_transcript = " ".join(r[1] for r in results if r[1]).strip()
    else:
        full_transcript_parts = []
        for i, chunk in enumerate(chunks):
            print(f"[transcriber] Transcribing chunk {i + 1}/{total}...")
            text = transcribe_chunk(chunk, language=language)
            full_transcript_parts.append(text)
            if progress_callback:
                try:
                    progress_callback(i + 1, total, text)
                except Exception:
                    pass
        full_transcript = " ".join(full_transcript_parts).strip()

    print(f"[transcriber] Full transcription complete ({len(full_transcript.split())} words).")
    return full_transcript

    
