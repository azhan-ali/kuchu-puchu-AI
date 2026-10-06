from dotenv import load_dotenv
from utils.audio_processor import process_input
from core.transcriber import transcribe_all
from core.summarizer import summarize, generate_title
from core.extractor import (
    extract_action_items, extract_key_decisions, extract_questions,
    extract_all_takeaways, generate_mcq_quiz
)
from core.diagram_generator import generate_mind_map, generate_flowchart
from core.rag_engine import build_rag_chain, ask_question
from concurrent.futures import ThreadPoolExecutor

load_dotenv()

import time

def run_pipeline(source: str, language: str = "english") -> dict:
    print("Starting AI Video Assistant...")

    chunks = process_input(source)
    transcript = transcribe_all(chunks, language)
    print(f"Raw transcription (first 300 characters):\n{transcript[:300]}...\n")

    print("Generating summaries, mind map, flowchart, quiz, and RAG index concurrently...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        f_title = executor.submit(generate_title, transcript)
        f_summary = executor.submit(summarize, transcript)
        f_takeaways = executor.submit(extract_all_takeaways, transcript)
        f_mcq = executor.submit(generate_mcq_quiz, transcript)
        f_mindmap = executor.submit(generate_mind_map, transcript)
        f_flowchart = executor.submit(generate_flowchart, transcript)
        f_rag = executor.submit(build_rag_chain, transcript)

        title = f_title.result()
        summary = f_summary.result()
        action_item, decisions, questions = f_takeaways.result()
        mcq_quiz = f_mcq.result()
        mind_map = f_mindmap.result()
        flowchart = f_flowchart.result()
        rag_chain = f_rag.result()

    return {
        "title": title,
        "transcript": transcript,
        "summary": summary,
        "action_items": action_item,
        "key_decisions": decisions,
        "open_questions": questions,
        "mcq_quiz": mcq_quiz,
        "mind_map": mind_map,
        "flowchart": flowchart,
        "rag_chain": rag_chain,
    }

if __name__ == "__main__":
    # CLI entry point
    source = input("Enter YouTube URL or local file path: ").strip()
    language = input("Language (english/hinglish): ").strip() or "english"
    result = run_pipeline(source, language)

    print("\n" + "=" * 60)
    print(f"📌 Title: {result['title']}")
    print(f"\n📋 Summary:\n{result['summary']}")
    print(f"\n✅ Action Items:\n{result['action_items']}")
    print(f"\n🔑 Key Decisions:\n{result['key_decisions']}")
    print(f"\n❓ Open Questions:\n{result['open_questions']}")
    print(f"\n📝 MCQ Quiz (JSON):\n{result['mcq_quiz']}")
    print(f"\n🧠 Mind Map (Mermaid):\n{result['mind_map']}")
    print(f"\n📊 Flowchart (Mermaid):\n{result['flowchart']}")
    print("=" * 60)

    # Phase 2 — Chat with your meeting via RAG
    print("\n💬 Chat with your meeting (type 'exit' to quit)\n")
    rag_chain = result["rag_chain"]
    while True:
        question = input("You: ").strip()
        if question.lower() in ["exit", "quit", "q"]:
            print("👋 Goodbye!")
            break
        if not question:
            continue
        answer = ask_question(rag_chain, question)
        print(f"\n🤖 Assistant: {answer}\n")