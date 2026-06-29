import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import requests
from dotenv import load_dotenv
from retrieval.hybrid_retriever import hybrid_search

load_dotenv()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3:mini")
TOP_K = int(os.getenv("TOP_K", 5))


def retrieve_node(state: dict) -> dict:
    """Retrieve relevant chunks using hybrid search."""
    print(f"[retrieve] Searching for: {state['query']}")
    chunks = hybrid_search(state["query"], top_k=TOP_K)
    print(f"[retrieve] Found {len(chunks)} chunks")
    return {"retrieved_chunks": chunks}


def build_prompt_node(state: dict) -> dict:
    """Build the prompt from retrieved chunks."""
    chunks = state["retrieved_chunks"]
    query = state["query"]
    context_parts = []
    sources = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(f"{chunk['metadata'].get('title', '')}: {chunk['text'][:250]}")
        sources.append({
            "title": chunk["metadata"].get("title", "Unknown"),
            "source_url": chunk["metadata"].get("source_url", ""),
            "source": chunk["metadata"].get("source", ""),
            "relevance_score": round(chunk.get("final_score", 0), 3)
        })
    context = "\n\n".join(context_parts)
    source_titles = [s["title"] for s in sources]
    prompt = f"""Context: {context}

Using ONLY the information in the context above, answer this question. Do not add facts, field names, or details that are not present in the context. If the context doesn't fully answer the question, say so rather than guessing.

After every factual statement, add a citation tag in the format [source:<title>], using one of these exact titles: {', '.join(source_titles)}. If you cannot cite a source for a statement, omit that statement.

Question: {query}

Give a short answer covering: cause, fix. Max 100 words."""
    return {"prompt": prompt, "sources": sources}


def generate_node(state: dict) -> dict:
    """Generate answer using Ollama."""
    print(f"[generate] Calling Ollama...")
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": state["prompt"],
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_ctx": 1024,
                    "num_predict": 200
                }
            },
            timeout=480
        )
        resp.raise_for_status()
        answer = resp.json()["response"].strip()
    except Exception as e:
        answer = f"Error generating answer: {e}"

    print(f"[generate] Done!")
    return {"answer": answer}