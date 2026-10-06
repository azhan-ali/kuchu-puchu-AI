import os 
import whisper
import requests
import torch
from pydub import AudioSegment
from concurrent.futures import ThreadPoolExecutor

# Sarvam's sync STT-translate API rejects audio longer than 30s.
# We slice each chunk into 25s pieces (with a 5s safety margin) before sending.
SARVAM_PIECE_SECONDS = 25

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_STT_TRANSLATE_URL = "https://api.sarvam.ai/speech-to-text-translate"
SARVAM_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v2.5")

_model = None

def load_model():
    global _model

    if _model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading Whisper model: {WHISPER_MODEL} on device: {device} ...")
        _model = whisper.load_model(WHISPER_MODEL, device=device)
        print("Whisper model loaded.")

    return _model

def transcribe_chunk_whisper(chunk_path: str, language: str = "english") -> str:
    model = load_model()
    is_cuda = torch.cuda.is_available()

    # Fast decoding options: beam_size=1 (greedy) is 3-4x faster than beam_size=5
    # condition_on_previous_text=False prevents repetition hallucinations and fallback loops
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
    headers = {"api-subscription-key": SARVAM_API_KEY}

    with open(piece_path, "rb") as f:
        files = {"file": (os.path.basename(piece_path), f, "audio/wav")}
        data = {"model": SARVAM_MODEL, "with_diarization": "false"}
        response = requests.post(
            SARVAM_STT_TRANSLATE_URL,
            headers=headers,
            files=files,
            data=data,
            timeout=120,
        )

    if not response.ok:
        print(f"\n❌ Sarvam returned {response.status_code}")
        print(f"Response body: {response.text}\n")
        response.raise_for_status()

    return response.json().get("transcript", "")

## chunking of sarvam api key with parallel execution
def transcribe_chunk_sarvam(chunk_path: str) -> str:
    """
    Sarvam sync API only accepts ≤30s audio. We split this chunk into
    25-second pieces, send each concurrently, and join the transcripts in order.
    """
    if not SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY is not set in environment / .env")

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
            print(f"  → Sarvam piece {idx + 1}/{total_pieces} ...")
            text = _send_to_sarvam(p_path)
            return (idx, text)
        finally:
            if os.path.exists(p_path):
                try:
                    os.remove(p_path)
                except Exception:
                    pass

    # Concurrently send pieces (4-6 workers)
    max_workers = min(6, len(pieces_info)) if pieces_info else 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(_process_piece, pieces_info))

    results.sort(key=lambda x: x[0])
    return " ".join(r[1] for r in results if r[1]).strip()

## Transcribe the chunks 
def transcribe_chunk(chunk_path: str, language: str = "english") -> str:
    """
    Route one chunk to Whisper or Sarvam depending on language choice.
    - english  → Whisper (local model)
    - hinglish → Sarvam (translates to English while transcribing)
    """
    if language.lower() == "hinglish":
        return transcribe_chunk_sarvam(chunk_path)
    else:
        return transcribe_chunk_whisper(chunk_path, language=language)

## transcribe whole audio 
def transcribe_all(chunks: list, language: str = "english") -> str:
    full_transcript = ""
    engine = "Sarvam AI" if language.lower() == "hinglish" else "Whisper"
    print(f"Using {engine} for transcription of {len(chunks)} chunk(s)...")

    for i, chunk in enumerate(chunks):
        print(f"Transcribing chunk {i+1}/{len(chunks)}...")
        text = transcribe_chunk(chunk, language=language)
        full_transcript += text + " "

    print("Transcription complete.")
    return full_transcript.strip()
    
