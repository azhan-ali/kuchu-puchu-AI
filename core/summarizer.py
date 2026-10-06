from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.runnables import RunnablePassthrough, RunnableLambda

import os 
from dotenv import load_dotenv

load_dotenv()

_llm_instance = None

def get_llm():
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = ChatGroq(
            model="openai/gpt-oss-120b",
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=0.3
        )
    return _llm_instance


def split_transcript(transcript: str, chunk_size: int = 12000, chunk_overlap: int = 600) -> list:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )
    return splitter.split_text(transcript)


SUMMARY_SYSTEM_PROMPT = (
    "You are an expert analyst. Generate ONE universal, comprehensive summary based only on the "
    "provided video or meeting transcript. The summary must be clear, well-structured, and detailed "
    "enough that someone can fully understand the complete discussion and topics without watching or listening to it.\n\n"
    "Requirements:\n"
    "- Cover the main topic, key ideas, important details, explanations, decisions, conclusions, and relevant context.\n"
    "- Do NOT include audience-specific perspectives (strictly exclude sections like 'Why It Matters for Students' "
    "or 'Why It Matters for Working Professionals').\n"
    "- Remove repetition, filler words, and unnecessary fluff.\n"
    "- Keep the summary accurate, concise, easy to read, and logically organized using clear markdown headings and bullet points."
)

CHUNK_SYSTEM_PROMPT = (
    "Summarize this segment of the transcript thoroughly and objectively. "
    "Capture all key topics, explanations, important details, decisions, and relevant context without any filler. "
    "Do NOT include audience-specific perspectives (e.g., student vs. professional sections)."
)

COMBINED_SYSTEM_PROMPT = (
    "You are an expert analyst. Combine the following segment summaries into ONE universal, comprehensive summary.\n\n"
    "Requirements:\n"
    "- The summary must be clear, well-structured, and detailed enough that someone can understand the entire video or meeting "
    "without watching or listening to it.\n"
    "- Cover the main topic, key ideas, important details, explanations, decisions, conclusions, and relevant context.\n"
    "- Strictly remove audience-specific perspectives (do NOT generate sections like 'Why It Matters for Students' "
    "or 'Why It Matters for Working Professionals').\n"
    "- Eliminate repetition and synthesize the points into a coherent, organized markdown document with clear headings and bullet points."
)


def summarize(transcript: str) -> str:
    if not transcript or not transcript.strip():
        return "No transcript content detected to summarize."

    llm = get_llm()

    # Fast & high quality: if transcript fits comfortably in LLM context (<=15k chars ~ 2,500 words / ~20 mins),
    # process in a single pass to preserve complete narrative coherence and eliminate 4+ extra round-trips.
    if len(transcript) <= 15000:
        single_prompt = ChatPromptTemplate.from_messages([
            ("system", SUMMARY_SYSTEM_PROMPT),
            ("human", "{text}"),
        ])
        single_chain = single_prompt | llm | StrOutputParser()
        return single_chain.invoke({"text": transcript})

    # For very long transcripts (>15k chars), split into large chunks and summarize concurrently
    chunks = split_transcript(transcript, chunk_size=12000, chunk_overlap=600)
    chunk_prompt = ChatPromptTemplate.from_messages([
        ("system", CHUNK_SYSTEM_PROMPT),
        ("human", "{text}"),
    ])
    chunk_chain = chunk_prompt | llm | StrOutputParser()

    # Parallel chunk summarization via LangChain batch
    chunk_inputs = [{"text": c} for c in chunks]
    chunk_summaries = chunk_chain.batch(chunk_inputs)

    combined = "\n\n".join(chunk_summaries)

    combined_prompt = ChatPromptTemplate.from_messages([
        ("system", COMBINED_SYSTEM_PROMPT),
        ("human", "{text}"),
    ])
    combined_chain = combined_prompt | llm | StrOutputParser()
    return combined_chain.invoke({"text": combined})


def generate_title(transcript: str) -> str:
    if not transcript or not transcript.strip():
        return "Audio/Meeting Notes"

    llm = get_llm()

    title_chain = (
        RunnablePassthrough() | RunnableLambda(lambda x: {"text": x}) | 
        ChatPromptTemplate.from_messages([
             (
                "system",
                "Based on the meeting transcript, generate a short professional meeting title "
                "(max 8 words). Only return the title, nothing else.",
            ),
            ("human", "{text}"),
        ])
        | llm
        | StrOutputParser()
    )

    return title_chain.invoke(transcript[:2000]).strip(' "\'')