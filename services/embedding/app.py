import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from embedder import embed_text, embed_batch
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Embedding Service", version="1.0")


class EmbedRequest(BaseModel):
    text: str


class EmbedBatchRequest(BaseModel):
    texts: list[str]


class EmbedResponse(BaseModel):
    vector: list[float]
    model: str


class EmbedBatchResponse(BaseModel):
    vectors: list[list[float]]
    model: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text cannot be empty")
    vector = embed_text(req.text)
    return EmbedResponse(vector=vector, model=os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2"))


@app.post("/embed/batch", response_model=EmbedBatchResponse)
def embed_batch_endpoint(req: EmbedBatchRequest):
    if not req.texts:
        raise HTTPException(status_code=400, detail="texts cannot be empty")
    vectors = embed_batch(req.texts)
    return EmbedBatchResponse(vectors=vectors, model=os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2"))