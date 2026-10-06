# 🚌 Kuchu Puchu AI — Intelligent Video & Audio Study Buddy

**Kuchu Puchu AI** transforms long lectures, meetings, and YouTube videos into interactive study notes, concept mind maps, procedural flowcharts, self-assessment quizzes, and a conversational RAG-powered study buddy.

---

## ✨ Features

- **Multi-Source Ingestion**: Process YouTube videos directly or upload local audio/video files (`mp4`, `mp3`, `wav`, `m4a`, etc.).
- **High-Performance Speech-to-Text**:
  - Local **OpenAI Whisper** transcription with optimized decoding.
  - Multi-lingual translation & STT via **Sarvam AI** for Hindi / Hinglish content.
- **Concurrent Analysis Pipeline**:
  - **Comprehensive Summary & Title**: Synthesizes key ideas without filler or fluff.
  - **Action Items & Key Decisions**: Structured deliverables, ownership, and open questions.
  - **Mermaid Mind Maps & Flowcharts**: Interactive, visual taxonomy and process diagrams.
  - **Practice MCQ Quizzes**: Instant knowledge check and self-assessment questions.
- **RAG-Powered Chat Co-Pilot**:
  - Semantic vector store using HuggingFace embeddings (`all-MiniLM-L6-v2`) and ChromaDB.
  - Grounded question-answering with fallbacks powered by Groq.
- **Modern Interactive Web UI**: Real-time multi-stage progress tracking ("The Study Bus Journey"), responsive layout, dark theme, and export tools.

---

## 🛠️ Tech Stack

- **Backend**: FastAPI, Uvicorn, Jinja2, Pydantic
- **AI & LLM Orchestration**: LangChain LCEL, Groq, Google Gemini, Mistral AI
- **Speech & Audio**: OpenAI Whisper, PyTorch, PyDub, FFmpeg, yt-dlp, Sarvam AI
- **Vector Search & RAG**: ChromaDB, LangChain-Chroma, Sentence-Transformers, HuggingFace Hub
- **Frontend**: HTML5, Vanilla CSS, JavaScript, Mermaid.js, Marked.js

---

## 🚀 Quick Start Guide

### 1. Prerequisites

- **Python 3.10+**
- **FFmpeg**: Required for audio extraction.
  - **Windows**: `winget install Gyan.FFmpeg` or download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to `PATH`.
  - **macOS**: `brew install ffmpeg`
  - **Ubuntu/Debian**: `sudo apt update && sudo apt install ffmpeg`

### 2. Clone the Repository

```bash
git clone https://github.com/azhan-ali/kuchu-puchu-AI.git
cd kuchu-puchu-AI
```

### 3. Create a Virtual Environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Environment Variables Setup

Copy the example environment configuration file:

```bash
# Windows (PowerShell)
Copy-Item .env.example .env

# Linux / macOS
cp .env.example .env
```

Open `.env` in an editor and fill in your API keys:

```env
# Groq API Key (Required for summary, takeaways, and RAG chat)
GROQ_API_KEY=your_groq_api_key_here

# Google Gemini API Key (Recommended for high-fidelity Mermaid diagrams)
GEMINI_API_KEY=your_gemini_api_key_here

# Mistral AI API Key (Fallback provider)
MISTRAL_API_KEY=your_mistral_api_key_here

# Sarvam AI API Key (Optional: for Hinglish / Indian language speech translation)
SARVAM_API_KEY=your_sarvam_api_key_here

# HuggingFace Token (Optional: prevents download rate-limiting)
HUGGINGFACE_API_KEY=your_huggingface_token_here

# Whisper local model size (tiny, base, small, medium, large-v3)
WHISPER_MODEL=small
```

---

## 🖥️ Running the Application

### Web Application (FastAPI + Interactive UI)

Start the local development server:

```bash
python main.py
```

Or using Uvicorn directly:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser and navigate to:
```
http://localhost:8000
```

### CLI Mode

You can also run the pipeline from the command line:

```bash
python cli.py
```

---

## 📁 Project Structure

```
kuchu-puchu-AI/
├── app/
│   ├── static/
│   │   ├── css/          # Responsive styles and theme
│   │   ├── fonts/        # Web fonts
│   │   ├── img/          # UI assets and logos
│   │   └── js/           # Frontend state, SSE streaming, and Mermaid rendering
│   └── templates/
│       └── index.html    # Single-page web dashboard
├── core/
│   ├── diagram_generator.py # Mermaid mindmap and flowchart generator
│   ├── extractor.py         # Action items, key decisions, and MCQ generator
│   ├── rag_engine.py        # Conversational RAG chain
│   ├── summarizer.py        # Map-reduce and single-pass summarizer
│   ├── transcriber.py       # Whisper and Sarvam AI STT
│   └── vector_store.py      # ChromaDB embeddings and vector retriever
├── utils/
│   └── audio_processor.py   # yt-dlp downloader, FFmpeg conversion, audio chunking
├── cli.py                   # Command-line interface
├── main.py                  # FastAPI server and streaming endpoints
├── requirements.txt         # Project dependencies
├── .env.example             # Safe template for environment configuration
├── .gitignore               # Excludes secrets, virtualenvs, vector db, and caches
└── README.md                # Project documentation
```

---

## 🔒 Security & Privacy

- All sensitive keys are configured strictly via environment variables (`.env`).
- `.env`, local audio downloads (`downloads/`), and generated vector databases (`vector_db/`) are strictly ignored via `.gitignore`.
- No user media or audio chunks are tracked in version control.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
