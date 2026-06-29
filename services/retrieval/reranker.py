SOURCE_WEIGHTS = {
    "kubernetes_docs": 1.0,
    "prometheus_runbooks": 1.0,
    "k8s_failures": 0.9,
    "knowledge_graph": 0.85,
    "sre_book": 0.6,
    "sre_workbook": 0.6,
}


def rerank(chunks: list[dict], query: str) -> list[dict]:
    """
    Reranks the candidate pool using three signals:
    1. Base similarity/graph score from retrieval
    2. Keyword overlap boost (query terms appearing in the chunk)
    3. Source weight — prioritizes Kubernetes-specific sources (docs, runbooks,
       failure stories) over general SRE-theory sources (sre_book/workbook),
       which are relevant but less precise for K8s-specific troubleshooting.
    """
    query_terms = query.lower().split()

    for chunk in chunks:
        text_lower = chunk["text"].lower()
        keyword_hits = sum(1 for term in query_terms if term in text_lower)
        boost = keyword_hits * 0.05

        source = chunk["metadata"].get("source", "")
        weight = SOURCE_WEIGHTS.get(source, 0.7)

        base_score = chunk.get("score", 0.5)
        chunk["final_score"] = (base_score + boost) * weight

    return sorted(chunks, key=lambda x: x["final_score"], reverse=True)