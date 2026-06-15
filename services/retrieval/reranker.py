def rerank(chunks: list[dict], query: str) -> list[dict]:
    """
    Simple keyword-based reranker.
    Boosts score if query terms appear in the chunk text.
    """
    query_terms = query.lower().split()

    for chunk in chunks:
        text_lower = chunk["text"].lower()
        keyword_hits = sum(1 for term in query_terms if term in text_lower)
        boost = keyword_hits * 0.05
        chunk["final_score"] = chunk.get("score", 0.5) + boost

    return sorted(chunks, key=lambda x: x["final_score"], reverse=True)