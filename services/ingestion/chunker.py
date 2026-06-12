from langchain.text_splitter import RecursiveCharacterTextSplitter
from typing import List

CHUNK_SIZE = 750
CHUNK_OVERLAP = 75


def chunk_document(doc: dict) -> List[dict]:
    """
    Takes a parsed document dict with 'text' and 'metadata',
    splits into chunks, returns list of chunk dicts.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " ", ""],
    )

    chunks = splitter.split_text(doc["text"])

    result = []
    for i, chunk in enumerate(chunks):
        if len(chunk.strip()) < 50:
            continue
        result.append({
            "text": chunk.strip(),
            "metadata": {
                **doc["metadata"],
                "chunk_index": i,
                "chunk_total": len(chunks),
            }
        })

    return result


def chunk_documents(docs: list[dict]) -> list[dict]:
    """
    Process a list of documents, return all chunks across all docs.
    """
    all_chunks = []
    for doc in docs:
        chunks = chunk_document(doc)
        all_chunks.extend(chunks)

    return all_chunks