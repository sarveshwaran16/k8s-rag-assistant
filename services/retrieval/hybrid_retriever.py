import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from retrieval.vector_retriever import vector_search
from retrieval.graph_retriever import graph_search
from retrieval.reranker import rerank

TOP_K = int(os.getenv("TOP_K", 5))


def hybrid_search(query: str, top_k: int = TOP_K) -> list[dict]:
    """
    Combine vector search + graph search and rerank results.
    Vector search returns a wider candidate pool than top_k so reranking has
    real material to work with; only the final reranked list is truncated
    to top_k.
    """
    print(f"[hybrid] Running vector search...")
    vector_results = vector_search(query, top_k=top_k, candidate_pool=15)

    print(f"[hybrid] Running graph search...")
    graph_results = graph_search(query, limit=top_k)

    print(f"[hybrid] Vector: {len(vector_results)} | Graph: {len(graph_results)}")

    combined = vector_results + graph_results
    reranked = rerank(combined, query)

    return reranked[:top_k]


if __name__ == "__main__":
    query = "Why is my pod in CrashLoopBackOff?"
    results = hybrid_search(query)
    print(f"\nTop {len(results)} results for: '{query}'\n")
    for i, r in enumerate(results, 1):
        print(f"[{i}] Source: {r['source']} | Score: {r.get('final_score', 0):.3f}")
        print(f"     {r['text'][:200]}")
        print()