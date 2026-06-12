import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import hashlib
from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings

from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from sources import k8s_docs, prometheus_runbooks, k8s_failures, opensre, google_sre
from chunker import chunk_document

load_dotenv()

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", 8002))
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "k8s_rag")


def get_chroma_collection():
    """Connect to ChromaDB and return the collection."""
    ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    client = chromadb.HttpClient(
        host=CHROMA_HOST,
        port=CHROMA_PORT,
        settings=Settings(anonymized_telemetry=False)
    )
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
        embedding_function=ef
    )
    return collection


def make_doc_id(text: str, source_url: str, chunk_index: int) -> str:
    """Generate a stable unique ID for a chunk."""
    raw = f"{source_url}::{chunk_index}::{text[:100]}"
    return hashlib.md5(raw.encode()).hexdigest()


def ingest_source(source_name: str, generator, collection):
    """Fetch, chunk and upsert all docs from a single source."""
    print(f"\n{'='*50}")
    print(f"Ingesting: {source_name}")
    print(f"{'='*50}")
    total_chunks = 0
    skipped = 0
    try:
        for doc in generator:
            chunks = chunk_document(doc)
            ids = []
            texts = []
            metadatas = []
            for chunk in chunks:
                doc_id = make_doc_id(
                    chunk["text"],
                    chunk["metadata"]["source_url"],
                    chunk["metadata"]["chunk_index"]
                )
                ids.append(doc_id)
                texts.append(chunk["text"])
                metadatas.append(chunk["metadata"])
            if not ids:
                skipped += 1
                continue
            batch_size = 100
            for i in range(0, len(ids), batch_size):
                collection.upsert(
                    ids=ids[i:i+batch_size],
                    documents=texts[i:i+batch_size],
                    metadatas=metadatas[i:i+batch_size]
                )
            total_chunks += len(ids)
    except Exception as e:
        print(f"[{source_name}] Error — skipping source: {e}")
    print(f"[{source_name}] Done — {total_chunks} chunks ingested, {skipped} docs skipped")


def run():
    print("Connecting to ChromaDB...")
    collection = get_chroma_collection()
    print(f"Connected — collection: {COLLECTION_NAME}")

    sources = [
        #("k8s_docs",             k8s_docs.fetch_all()),
        ("prometheus_runbooks",  prometheus_runbooks.fetch_all()),
        #("k8s_failures",         k8s_failures.fetch_all()),
        ("opensre",              opensre.fetch_all()),
        ("google_sre",           google_sre.fetch_all()),
    ]

    for source_name, generator in sources:
        ingest_source(source_name, generator, collection)

    total = collection.count()
    print(f"\n✅ Ingestion complete — {total} total chunks in ChromaDB")


if __name__ == "__main__":
    run()