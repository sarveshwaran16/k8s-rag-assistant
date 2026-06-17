import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

from assistant.assistant import ask

load_dotenv()

app = FastAPI(title="K8s RAG Query API", version="1.0")


class QueryRequest(BaseModel):
    query: str


class Source(BaseModel):
    title: str
    source_url: str
    source: str
    relevance_score: float


class QueryResponse(BaseModel):
    query: str
    answer: str
    sources: list[Source]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query cannot be empty")

    try:
        result = ask(req.query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return QueryResponse(
        query=result["query"],
        answer=result["answer"],
        sources=[Source(**s) for s in result["sources"]]
    )