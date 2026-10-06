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
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is missing. Please set it in your Railway/Render environment.")
    primary_llm = ChatGroq(
        model="openai/gpt-oss-120b",
        api_key=api_key,
        temperature=0.3,
    )
    fallback_llm = ChatGroq(
        model="openai/gpt-oss-20b",
        api_key=api_key,
        temperature=0.3,
    )
    return primary_llm.with_fallbacks([fallback_llm])

def format_docs(docs):
    return "\n\n".join([doc.page_content for doc in docs])

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
    retriever = get_retriever(vector_store)

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

    rag_chain = (
        {
            "context":  retriever| RunnableLambda(format_docs),
            "question": RunnablePassthrough(),
        }
        | prompt
        | llm
        | StrOutputParser()
    )

    return rag_chain


def ask_question(rag_chain, question:str) -> str:
    try:
        safe_q = question.encode("ascii", errors="backslashreplace").decode("ascii")
        print(f"Question : {safe_q}")
    except Exception:
        pass

    answer = rag_chain.invoke(question)

    if not isinstance(answer, str):
        answer = str(answer)

    try:
        safe_a = answer.encode("ascii", errors="backslashreplace").decode("ascii")
        print(f"answer :{safe_a}")
    except Exception:
        pass

    return answer