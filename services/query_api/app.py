import os
import httpx
import chromadb
from chromadb.config import Settings
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", 8002))
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "k8s_rag")
EMBED_SERVICE_URL = os.getenv("EMBED_SERVICE_URL", "http://localhost:8001")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:8b-instruct-q4_0")
TOP_K = int(os.getenv("TOP_K", 5))

app = FastAPI(title="K8s RAG Query API", version="1.0")


class QueryRequest(BaseModel):
    query: str


class Source(BaseModel):
    title: str
    source_url: str
    source: str


class QueryResponse(BaseModel):
    query: str
    answer: str
    sources: list[Source]


def get_collection():
    client = chromadb.HttpClient(
        host=CHROMA_HOST,
        port=CHROMA_PORT,
        settings=Settings(anonymized_telemetry=False)
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )


def get_embedding(text: str) -> list[float]:
    resp = httpx.post(
        f"{EMBED_SERVICE_URL}/embed",
        json={"text": text},
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()["vector"]


def retrieve_chunks(query: str) -> list[dict]:
    vector = get_embedding(query)
    collection = get_collection()
    results = collection.query(
        query_embeddings=[vector],
        n_results=TOP_K,
        include=["documents", "metadatas"]
    )
    chunks = []
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        chunks.append({"text": doc, "metadata": meta})
    return chunks


def build_prompt(query: str, chunks: list[dict]) -> str:
    context = "\n\n".join([
        f"Source: {c['metadata']['title']}\n{c['text']}"
        for c in chunks
    ])
    return f"""You are a Kubernetes SRE assistant. Answer the question using only the context below.
Always include: root causes, remediation steps, and source references.

Context:
{context}

Question: {query}

Answer:"""


def generate_answer(prompt: str) -> str:
    resp = httpx.post(
        f"{OLLAMA_HOST}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False
        },
        timeout=120
    )
    resp.raise_for_status()
    return resp.json()["response"]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query cannot be empty")

    chunks = retrieve_chunks(req.query)
    if not chunks:
        raise HTTPException(status_code=404, detail="No relevant chunks found")

    prompt = build_prompt(req.query, chunks)
    answer = generate_answer(prompt)

    sources = [
        Source(
            title=c["metadata"]["title"],
            source_url=c["metadata"]["source_url"],
            source=c["metadata"]["source"]
        )
        for c in chunks
    ]

    return QueryResponse(query=req.query, answer=answer, sources=sources)