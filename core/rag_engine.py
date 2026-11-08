import os
import sys

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

from dotenv import load_dotenv

load_dotenv()
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from core.vector_store import build_vector_store, load_vector_store, get_retriever

def get_llm():
    """
    Returns an LLM for conversational RAG.
    Supports Groq (primary) and Google Gemini (fallback or alternative).
    """
    api_key = os.getenv("GROQ_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    fallbacks = []

    # Optional Gemini fallback
    if gemini_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            gemini_llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                api_key=gemini_key,
                temperature=0.3
            )
            fallbacks.append(gemini_llm)
        except Exception as e:
            print(f"[rag_engine] Notice: Gemini LLM fallback unavailable: {e}")

    if api_key:
        primary_llm = ChatGroq(
            model="openai/gpt-oss-120b",
            api_key=api_key,
            temperature=0.3,
        )
        secondary_llm = ChatGroq(
            model="openai/gpt-oss-20b",
            api_key=api_key,
            temperature=0.3,
        )
        all_fallbacks = [secondary_llm] + fallbacks
        return primary_llm.with_fallbacks(all_fallbacks)

    if fallbacks:
        print("[rag_engine] GROQ_API_KEY not configured. Using Gemini LLM for RAG chatbot...")
        return fallbacks[0]

    raise ValueError("Neither GROQ_API_KEY nor GEMINI_API_KEY environment variable is configured.")

def format_docs(docs):
    if not docs:
        return "No specific excerpt found in transcript."
    return "\n\n".join([getattr(doc, "page_content", str(doc)) for doc in docs])

def create_rag_chain_from_vector_store(vector_store):
    retriever = get_retriever(vector_store, k=4)
    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """You are an expert meeting assistant. Answer the user's question 
based ONLY on the meeting transcript context provided below.

If the answer is not found in the context, say: 
"I could not find this information in the meeting transcript."

Always be concise and precise. If quoting someone, mention it clearly.

Context from meeting transcript:
{context}""",
        ),
        ("human", "{question}"),
    ])
    return (
        {"context": retriever | RunnableLambda(format_docs), "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )


def build_rag_chain(transcript: str):
    vector_store = build_vector_store(transcript)
    return create_rag_chain_from_vector_store(vector_store)


def load_rag_chain():
    vector_store = load_vector_store()
    return create_rag_chain_from_vector_store(vector_store)


def ask_question(rag_chain, question: str) -> str:
    try:
        safe_q = question.encode("ascii", errors="backslashreplace").decode("ascii")
        print(f"Question : {safe_q}")
    except Exception:
        pass

    try:
        if hasattr(rag_chain, "invoke"):
            answer = rag_chain.invoke(question)
        elif callable(rag_chain):
            answer = rag_chain(question)
        else:
            answer = str(rag_chain)
    except Exception as e:
        print(f"[rag_engine] Error in RAG chain invocation: {e}")
        return f"I had trouble retrieving the answer from the transcript context: {str(e)}"

    if not isinstance(answer, str):
        answer = str(answer)

    try:
        safe_a = answer.encode("ascii", errors="backslashreplace").decode("ascii")
        print(f"answer :{safe_a}")
    except Exception:
        pass

    return answer
