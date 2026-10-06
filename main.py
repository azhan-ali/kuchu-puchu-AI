from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
import sys
import os
import time
import shutil
import uuid
from pydantic import BaseModel

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# core imports
from utils.audio_processor import process_input
from core.transcriber import transcribe_all
from core.summarizer import summarize, generate_title
from core.extractor import (
    extract_action_items, extract_key_decisions, extract_questions,
    extract_all_takeaways, generate_mcq_quiz
)
from core.diagram_generator import generate_mind_map, generate_flowchart, sanitize_mindmap, sanitize_flowchart
from core.rag_engine import build_rag_chain, load_rag_chain, create_rag_chain_from_vector_store, ask_question
from dotenv import load_dotenv

load_dotenv()

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Kuchu Puchu AI")

# Configure CORS for flexible deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.get("/health")
@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "Kuchu Puchu AI",
        "version": "1.0.0",
        "environment": os.environ.get("ENVIRONMENT", "production")
    }


# In-memory store for RAG chains
rag_chains = {}

class ChatRequest(BaseModel):
    session_id: str
    question: str

@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

import json
import asyncio
from fastapi.responses import JSONResponse, StreamingResponse
from core.vector_store import build_vector_store, get_retriever
from core.rag_engine import get_llm as get_rag_llm, format_docs, ask_question
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda

STAGE_TITLES = {
    "audio": "Processing audio/video",
    "whisper": "Transcribing with Whisper",
    "summary": "Creating the summary",
    "embedding": "Splitting & embedding content",
    "mindmap": "Building the Mind Map",
    "flowchart": "Building the Process Flowchart",
    "mcq": "Generating MCQs",
    "rag": "Preparing the RAG chatbot",
    "final": "Finalizing results"
}

@app.post("/api/process")
async def process_media(
    request: Request,
    source_type: str = Form(...),
    url: str = Form(None),
    file: UploadFile = File(None),
    language: str = Form("english")
):
    source = ""
    if source_type == "url" and url:
        source = url
    elif source_type == "file" and file:
        downloads_dir = os.environ.get("DOWNLOAD_DIR", "downloads")
        os.makedirs(downloads_dir, exist_ok=True)
        safe_name = os.path.basename(file.filename or "uploaded_media").replace(" ", "_")
        file_path = os.path.join(downloads_dir, f"{uuid.uuid4().hex[:8]}_{safe_name}")
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        source = file_path
    else:
        raise HTTPException(status_code=400, detail="Invalid source")

    accept_header = request.headers.get("accept", "")
    is_streaming = "text/event-stream" in accept_header or request.query_params.get("stream") == "true"

    if is_streaming:
        async def event_generator():
            try:
                # 1. Processing audio/video (fast FFmpeg extraction)
                yield f"data: {json.dumps({'stage_index': 1, 'stage_id': 'audio', 'status': 'processing', 'title': STAGE_TITLES['audio'], 'detail': 'Extracting 16kHz audio tracks and preparing chunks...', 'progress': 11})}\n\n"
                chunks = await asyncio.to_thread(process_input, source)
                yield f"data: {json.dumps({'stage_index': 1, 'stage_id': 'audio', 'status': 'completed', 'title': STAGE_TITLES['audio'], 'detail': f'Audio prepared with {len(chunks)} chunk(s)!', 'progress': 11})}\n\n"

                # 2. Transcribing with Whisper (fast greedy decoding, beam_size=1)
                stt_engine = "Sarvam AI" if language.lower() == "hinglish" else "Whisper"
                yield f"data: {json.dumps({'stage_index': 2, 'stage_id': 'whisper', 'status': 'processing', 'title': STAGE_TITLES['whisper'], 'detail': f'Transcribing audio chunks using {stt_engine}...', 'progress': 22})}\n\n"
                transcript = await asyncio.to_thread(transcribe_all, chunks, language)
                word_count = len(transcript.split()) if transcript else 0
                yield f"data: {json.dumps({'stage_index': 2, 'stage_id': 'whisper', 'status': 'completed', 'title': STAGE_TITLES['whisper'], 'detail': f'Transcription complete ({word_count:,} words)!', 'progress': 22})}\n\n"

                # Setup event queue and shared state for concurrent post-transcription execution
                event_queue = asyncio.Queue()
                completed_count = 2  # audio (1) and whisper (2) done
                state_lock = asyncio.Lock()

                title = ""
                summary = ""
                vector_store = None
                mind_map = ""
                flowchart = ""
                mcq_quiz = "[]"
                action_items = "No action items extracted."
                decisions = "No key decisions recorded."
                questions = "No open questions found."
                session_id = str(uuid.uuid4())

                # Announce active processing status for independent stages to start the bus journey
                for s_id, s_idx, d_text in [
                    ("summary", 3, "Taking notes! Synthesizing key takeaways & lecture title..."),
                    ("embedding", 4, "Building semantic chunks & indexing vector store..."),
                    ("mindmap", 5, "Synthesizing concept taxonomy into Mermaid Mind Map..."),
                    ("flowchart", 6, "Mapping workflow & procedural logic flowchart..."),
                    ("mcq", 7, "Drafting practice quiz MCQs & action takeaways...")
                ]:
                    await event_queue.put({
                        "stage_index": s_idx,
                        "stage_id": s_id,
                        "status": "processing",
                        "title": STAGE_TITLES[s_id],
                        "detail": d_text,
                        "progress": 22
                    })

                async def emit_completion(stage_id: str, stage_idx: int, detail: str):
                    nonlocal completed_count
                    async with state_lock:
                        completed_count += 1
                        pct = int((completed_count / 9.0) * 100)
                    await event_queue.put({
                        "stage_index": stage_idx,
                        "stage_id": stage_id,
                        "status": "completed",
                        "title": STAGE_TITLES[stage_id],
                        "detail": detail,
                        "progress": pct
                    })

                # Task: Summary and Title
                async def run_summary_worker():
                    nonlocal title, summary
                    try:
                        title_task = asyncio.to_thread(generate_title, transcript)
                        summary_task = asyncio.to_thread(summarize, transcript)
                        title, summary = await asyncio.gather(title_task, summary_task)
                    except Exception as e:
                        print(f"Summary error: {e}")
                        title = "Lecture Notes"
                        summary = "Could not generate summary."
                    await emit_completion("summary", 3, f'Summary created: "{title}"')

                # Task: Embedding and RAG Chain
                async def run_embedding_and_rag_worker():
                    nonlocal vector_store
                    try:
                        vector_store = await asyncio.to_thread(build_vector_store, transcript)
                    except Exception as e:
                        print(f"Embedding error: {e}")
                    await emit_completion("embedding", 4, "Vector embeddings indexed & ready!")

                    # Immediately initialize RAG chatbot once vector store is ready
                    nonlocal completed_count
                    pct_now = int((completed_count / 9.0) * 100)
                    await event_queue.put({
                        "stage_index": 8,
                        "stage_id": "rag",
                        "status": "processing",
                        "title": STAGE_TITLES["rag"],
                        "detail": "Connecting vector store to conversational study buddy...",
                        "progress": pct_now
                    })
                    try:
                        if vector_store:
                            chain = await asyncio.to_thread(create_rag_chain_from_vector_store, vector_store)
                        else:
                            chain = await asyncio.to_thread(build_rag_chain, transcript)
                        rag_chains[session_id] = chain
                        rag_chains["latest"] = chain
                    except Exception as e:
                        print(f"RAG initialization error: {e}")
                    await emit_completion("rag", 8, "Study Buddy chatbot online & ready!")

                # Task: Mermaid Mind Map
                async def run_mindmap_worker():
                    nonlocal mind_map
                    try:
                        mind_map = await asyncio.to_thread(generate_mind_map, transcript)
                    except Exception as e:
                        print(f"Mind map error: {e}")
                        mind_map = sanitize_mindmap("", fallback_topic=title or "Summary")
                    await emit_completion("mindmap", 5, "Interactive Mermaid Mind Map generated!")

                # Task: Mermaid Process Flowchart
                async def run_flowchart_worker():
                    nonlocal flowchart
                    try:
                        flowchart = await asyncio.to_thread(generate_flowchart, transcript)
                    except Exception as e:
                        print(f"Flowchart error: {e}")
                        flowchart = sanitize_flowchart("", fallback_topic=title or "Workflow")
                    await emit_completion("flowchart", 6, "Process flowchart constructed!")

                # Task: MCQs and Takeaways (unified single LLM call for action items, decisions, questions)
                async def run_mcq_and_takeaways_worker():
                    nonlocal mcq_quiz, action_items, decisions, questions
                    try:
                        mcq_task = asyncio.to_thread(generate_mcq_quiz, transcript)
                        takeaways_task = asyncio.to_thread(extract_all_takeaways, transcript)
                        mcq_quiz, (action_items, decisions, questions) = await asyncio.gather(mcq_task, takeaways_task)
                    except Exception as e:
                        print(f"MCQ & takeaways error: {e}")
                        mcq_quiz = "[]"
                        action_items = "No action items extracted."
                        decisions = "No key decisions recorded."
                        questions = "No open questions found."
                    await emit_completion("mcq", 7, "MCQs and study takeaways generated!")

                # Run all independent stages concurrently
                workers = asyncio.gather(
                    run_summary_worker(),
                    run_embedding_and_rag_worker(),
                    run_mindmap_worker(),
                    run_flowchart_worker(),
                    run_mcq_and_takeaways_worker()
                )

                # Stream out events as each worker completes in real time
                while not workers.done() or not event_queue.empty():
                    try:
                        event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
                        yield f"data: {json.dumps(event)}\n\n"
                    except asyncio.TimeoutError:
                        pass

                await workers

                while not event_queue.empty():
                    event = await event_queue.get()
                    yield f"data: {json.dumps(event)}\n\n"

                # 9. Finalizing results
                yield f"data: {json.dumps({'stage_index': 9, 'stage_id': 'final', 'status': 'processing', 'title': STAGE_TITLES['final'], 'detail': 'Packing study notes & assembling complete folio...', 'progress': 95})}\n\n"

                final_data = {
                    "title": title or "Lecture Notes",
                    "transcript": transcript,
                    "summary": summary,
                    "action_items": action_items,
                    "key_decisions": decisions,
                    "open_questions": questions,
                    "mcq_quiz": mcq_quiz,
                    "mind_map": mind_map,
                    "flowchart": flowchart,
                    "session_id": session_id
                }

                yield f"data: {json.dumps({'stage_index': 9, 'stage_id': 'final', 'status': 'completed', 'title': STAGE_TITLES['final'], 'detail': 'All stops completed! Kuchu Puchu Study Bus has arrived!', 'progress': 100, 'data': final_data})}\n\n"

            except Exception as e:
                import traceback
                traceback.print_exc()
                yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    # Fallback non-streaming synchronous execution (also parallelized for maximum speed)
    try:
        chunks = await asyncio.to_thread(process_input, source)
        transcript = await asyncio.to_thread(transcribe_all, chunks, language)

        summary_task = asyncio.gather(
            asyncio.to_thread(generate_title, transcript),
            asyncio.to_thread(summarize, transcript)
        )
        vector_task = asyncio.to_thread(build_vector_store, transcript)
        mindmap_task = asyncio.to_thread(generate_mind_map, transcript)
        flowchart_task = asyncio.to_thread(generate_flowchart, transcript)
        mcq_task = asyncio.gather(
            asyncio.to_thread(generate_mcq_quiz, transcript),
            asyncio.to_thread(extract_all_takeaways, transcript)
        )

        (title, summary), vector_store, mind_map, flowchart, (mcq_quiz, (action_items, decisions, questions)) = await asyncio.gather(
            summary_task,
            vector_task,
            mindmap_task,
            flowchart_task,
            mcq_task
        )

        rag_chain = create_rag_chain_from_vector_store(vector_store)
        session_id = str(uuid.uuid4())
        rag_chains[session_id] = rag_chain
        rag_chains["latest"] = rag_chain

        return JSONResponse({
            "title": title,
            "transcript": transcript,
            "summary": summary,
            "action_items": action_items,
            "key_decisions": decisions,
            "open_questions": questions,
            "mcq_quiz": mcq_quiz,
            "mind_map": mind_map,
            "flowchart": flowchart,
            "session_id": session_id
        })
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def chat(req: ChatRequest):
    target_chain = rag_chains.get(req.session_id)
    if not target_chain and rag_chains:
        # Fallback to the latest initialized chain
        target_chain = rag_chains.get("latest") or list(rag_chains.values())[-1]

    if not target_chain:
        try:
            target_chain = load_rag_chain()
            if req.session_id:
                rag_chains[req.session_id] = target_chain
            rag_chains["latest"] = target_chain
        except Exception as e:
            print(f"Could not load persisted vector store: {e}")

    if not target_chain:
        return {"answer": "No active meeting session found. Please analyze a video or file first to enable the chat co-pilot."}

    try:
        answer = ask_question(target_chain, req.question)
        return {"answer": answer}
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        return {"answer": f"Sorry, I encountered an issue retrieving the answer: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    is_dev = os.environ.get("ENVIRONMENT", "").lower() == "development"
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=is_dev,
        reload_dirs=["app", "core", "utils"] if is_dev else None
    )