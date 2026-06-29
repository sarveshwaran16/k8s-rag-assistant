import os
import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from dotenv import load_dotenv

load_dotenv()

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", 8002))
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "k8s_rag")
TOP_K = int(os.getenv("TOP_K", 5))


def get_collection():
    ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    client = chromadb.HttpClient(
        host=CHROMA_HOST,
        port=CHROMA_PORT,
        settings=Settings(anonymized_telemetry=False)
    )
    return client.get_collection(COLLECTION_NAME, embedding_function=ef)


def vector_search(query: str, top_k: int = TOP_K, candidate_pool: int = 15) -> list[dict]:
    """
    Search ChromaDB for semantically similar chunks. Retrieves a wider candidate
    pool than top_k so the reranker has real material to reorder — otherwise a
    chunk ranked 6th by raw similarity never gets a chance to surface even if
    it's a better match once source-weighting is applied.
    """
    collection = get_collection()
    results = collection.query(
        query_texts=[query],
        n_results=candidate_pool,
        include=["documents", "metadatas", "distances"]
    )

    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0]
    ):
        chunks.append({
            "text": doc,
            "metadata": meta,
            "score": 1 - dist,  # convert distance to similarity score
            "source": "vector"
        })

    return chunks