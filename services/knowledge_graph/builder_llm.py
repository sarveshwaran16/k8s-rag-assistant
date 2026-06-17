import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from dotenv import load_dotenv
from tqdm import tqdm

from knowledge_graph.extractor import extract_entities
from knowledge_graph.graph_store import get_driver, create_indexes, upsert_entities, count_entities

load_dotenv()

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", 8002))
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "k8s_rag")
BATCH_SIZE = 50


def get_chunks(limit: int = None) -> list[dict]:
    """Fetch all chunks from ChromaDB."""
    ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    client = chromadb.HttpClient(
        host=CHROMA_HOST,
        port=CHROMA_PORT,
        settings=Settings(anonymized_telemetry=False)
    )
    collection = client.get_collection(COLLECTION_NAME, embedding_function=ef)
    total = collection.count()
    fetch_limit = limit if limit else total
    print(f"[builder] Fetching {fetch_limit} chunks from ChromaDB...")
    results = collection.get(limit=fetch_limit, include=["documents", "metadatas"])
    chunks = []
    for doc, meta in zip(results["documents"], results["metadatas"]):
        chunks.append({"text": doc, "metadata": meta})
    return chunks


def build_graph(limit: int = None):
    """Main runner — fetch chunks, extract entities, store in Neo4j."""
    print("Connecting to Neo4j...")
    driver = get_driver()
    driver.verify_connectivity()
    print("Connected to Neo4j!")

    create_indexes(driver)

    chunks = get_chunks(limit=limit)
    print(f"[builder] Processing {len(chunks)} chunks...")

    success = 0
    failed = 0

    for i, chunk in enumerate(tqdm(chunks)):
        extracted = extract_entities(chunk)
        if extracted["entities"]:
            upsert_entities(driver, extracted)
            success += 1
        else:
            failed += 1

        if i % BATCH_SIZE == 0 and i > 0:
            total = count_entities(driver)
            print(f"[builder] Progress {i}/{len(chunks)} — {total} entities in Neo4j")

    total = count_entities(driver)
    print(f"\n✅ Graph build complete!")
    print(f"   Chunks processed: {len(chunks)}")
    print(f"   Successful extractions: {success}")
    print(f"   Failed: {failed}")
    print(f"   Total entities in Neo4j: {total}")
    driver.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Limit chunks to process")
    args = parser.parse_args()
    build_graph(limit=args.limit)