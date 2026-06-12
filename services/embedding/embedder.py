import os
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")

# Load model once at module level — reused across all calls
_model = None


def get_model() -> SentenceTransformer:
    """Lazy load the embedding model."""
    global _model
    if _model is None:
        print(f"[embedder] Loading model: {EMBED_MODEL}")
        _model = SentenceTransformer(EMBED_MODEL)
        print(f"[embedder] Model loaded")
    return _model


def embed_text(text: str) -> list[float]:
    """Embed a single string, returns a vector."""
    model = get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings, returns list of vectors."""
    model = get_model()
    vectors = model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=True)
    return vectors.tolist()