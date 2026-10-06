# Actionable items, decisions, questions, and MCQ quiz

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
import os 
import re
from dotenv import load_dotenv

load_dotenv()

_extractor_llm_instance = None

def get_llm():
    global _extractor_llm_instance
    if _extractor_llm_instance is None:
        _extractor_llm_instance = ChatGroq(
            model="openai/gpt-oss-120b",
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=0.2
        )
    return _extractor_llm_instance


def build_chain(system_prompt: str):
    llm = get_llm()
    escaped_prompt = system_prompt.replace("{", "{{").replace("}", "}}")
    return (
        RunnablePassthrough() | RunnableLambda(lambda x: {"text": x}) | ChatPromptTemplate.from_messages([
            ("system", escaped_prompt),
            ("human", "{text}"),
        ]) | llm | StrOutputParser()
    )


def extract_all_takeaways(transcript: str) -> tuple:
    """
    Unified extraction: extracts Action Items, Key Decisions, and Open Questions
    in a SINGLE LLM roundtrip instead of 3 separate calls.
    Returns (action_items, key_decisions, open_questions).
    """
    if not transcript or not transcript.strip():
        return (
            "No action items found.",
            "No key decisions found.",
            "No open questions found."
        )

    system_prompt = (
        "You are an expert meeting and lecture analyst. Based on the transcript, extract key takeaways "
        "into the following THREE sections with their exact markdown headings:\n\n"
        "### ACTION ITEMS\n"
        "Extract all action items. For each provide:\n"
        "- Task description\n"
        "- Owner (who is responsible)\n"
        "- Deadline (if mentioned, else write 'Not specified')\n"
        "Format as a numbered list. If none found say 'No action items found.'\n\n"
        "### KEY DECISIONS\n"
        "Extract all key decisions made. Format as a numbered list. If none found say 'No key decisions found.'\n\n"
        "### OPEN QUESTIONS\n"
        "Extract all unresolved questions or topics needing follow-up. Format as a numbered list. If none found say 'No open questions found.'\n\n"
        "Output ONLY these three sections with their headers."
    )

    chain = build_chain(system_prompt)
    raw_response = chain.invoke(transcript)

    action_items = "No action items extracted."
    key_decisions = "No key decisions recorded."
    open_questions = "No open questions found."

    parts = re.split(r'###\s*', raw_response)
    for part in parts:
        part_clean = part.strip()
        if not part_clean:
            continue
        lines = part_clean.split('\n', 1)
        header = lines[0].strip().upper()
        content = lines[1].strip() if len(lines) > 1 else ""
        if "ACTION" in header:
            action_items = content or action_items
        elif "DECISION" in header:
            key_decisions = content or key_decisions
        elif "QUESTION" in header:
            open_questions = content or open_questions

    return action_items, key_decisions, open_questions


def extract_action_items(transcript: str) -> str:
    chain = build_chain(
        "You are an expert meeting analyst. From the meeting transcript, "
        "extract all action items. For each provide:\n"
        "- Task description\n"
        "- Owner (who is responsible)\n"
        "- Deadline (if mentioned, else write 'Not specified')\n\n"
        "Format as a numbered list. If none found say 'No action items found.'"
    )
    return chain.invoke(transcript)


def extract_key_decisions(transcript: str) -> str:
    chain = build_chain(
        "You are an expert meeting analyst. From the meeting transcript, "
        "extract all key decisions made. Format as a numbered list. "
        "If none found say 'No key decisions found.'"
    )
    return chain.invoke(transcript)


def extract_questions(transcript: str) -> str:
    chain = build_chain(
        "From the meeting transcript, extract all unresolved questions "
        "or topics needing follow-up. Format as a numbered list. "
        "If none found say 'No open questions found.'"
    )
    return chain.invoke(transcript)


def generate_mcq_quiz(transcript: str, num_questions: int = 5) -> str:
    chain = build_chain(
        f"You are an expert educator. Based on the transcript, create exactly {num_questions} multiple-choice questions. "
        "You must output ONLY a raw JSON array of objects. Do not include markdown blocks like ```json or any other text. "
        "Each object must have this exact structure:\n"
        '{{"question": "Question text?", "options": ["A", "B", "C", "D"], "answer": "Exact text of the correct option", "explanation": "Why this is correct"}}'
    )
    return chain.invoke(transcript)