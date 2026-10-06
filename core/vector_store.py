import os 
import torch
from dotenv import load_dotenv

load_dotenv()

# Set HF_TOKEN if available to avoid unauthenticated download throttling
hf_key = os.getenv("HUGGINGFACE_API_KEY")
if hf_key and "HF_TOKEN" not in os.environ:
    os.environ["HF_TOKEN"] = hf_key

from langchain_chroma import Chroma 
try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceEmbeddings

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

CHROMA_DIR = "vector_db"
COLLECTION_NAME = "meeting_transcript"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

_embeddings_instance = None

def get_embeddings():
    global _embeddings_instance
    if _embeddings_instance is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _embeddings_instance = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": device},
            encode_kwargs={"batch_size": 32, "normalize_embeddings": True}
        )
    return _embeddings_instance

def build_vector_store(transcript: str) -> Chroma:
    print("Building vector store...")

    # Optimal semantic chunks: 750 chars (~110 words) provides complete thoughts,
    # cuts number of embedding calls in half, and significantly improves RAG accuracy.
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=750,
        chunk_overlap=75
    )

    chunks = splitter.split_text(transcript)

    docs = [
        Document(page_content=chunk, metadata={'chunk_index': i})
        for i, chunk in enumerate(chunks)
    ]

    embeddings = get_embeddings()
    try:
        vector_store = Chroma.from_documents(
            documents=docs,
            embedding=embeddings,
            collection_name=COLLECTION_NAME,
            persist_directory=CHROMA_DIR
        )
    except Exception:
        vector_store = Chroma.from_documents(
            documents=docs,
            embedding=embeddings
        )

    print(f"Vector store indexed with {len(docs)} semantic chunks.")
    return vector_store


def load_vector_store() -> Chroma:
    embeddings = get_embeddings()
    vector_store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=CHROMA_DIR
    )
    return vector_store

def get_retriever(vector_store: Chroma, k: int = 4):
    return vector_store.as_retriever(
        search_type='similarity',
        search_kwargs={"k": k}
    )