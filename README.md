# AI-Powered Kubernetes Log Investigation Assistant

A fully local RAG pipeline deployed inside a Minikube cluster. Query Kubernetes logs and operational issues using natural language — no cloud, no external APIs.

## Architecture

```
User Query → FastAPI → Embedding → ChromaDB (top-k) → Ollama LLM → JSON Response
```

| Service | Technology | Port |
|---|---|---|
| Query API | FastAPI | 8000 |
| Embedding | sentence-transformers | 8001 |
| Vector Store | ChromaDB | 8002 |
| LLM | Ollama (Llama-3 4-bit) | 11434 |
| Ingestion | Python / LangChain | — |

## Prerequisites

- Docker
- Minikube (v1.32+)
- kubectl
- Python 3.11+
- 8GB RAM minimum

## Quick Start

```bash
# 1. Start Minikube
minikube start --memory=6144 --cpus=4

# 2. Deploy all services
kubectl apply -k k8s/base/

# 3. Run ingestion (one-time)
kubectl apply -f k8s/base/ingestion-job.yaml

# 4. Query the assistant
curl -X POST http://$(minikube ip):8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Why is my pod in CrashLoopBackOff?"}'
```

## Project Structure

```
k8s-rag-assistant/
├── services/
│   ├── ingestion/       # Fetches & chunks docs from 6 sources
│   ├── embedding/       # sentence-transformers embedding service
│   ├── query_api/       # FastAPI REST endpoint
│   └── llm/             # Ollama model config
├── k8s/
│   ├── base/            # Kubernetes manifests
│   └── overlays/        # Kustomize overlays
├── evaluation/          # 10 standard eval queries + results
├── scripts/             # Helper scripts (setup, teardown)
└── docs/                # Runbook and handoff docs
```

## Milestones

- [x] M1 — Environment Setup
- [ ] M2 — Ingestion Pipeline
- [ ] M3 — Vector Store
- [ ] M4 — LLM Integration
- [ ] M5 — Evaluation
- [ ] M6 — Handoff

## Knowledge Sources

- [Kubernetes Docs](https://kubernetes.io/docs/)
- [Prometheus Operator Runbooks](https://runbooks.prometheus-operator.dev/)
- [K8s Failure Stories](https://k8s.af/)
- [OpenSRE](https://opensre.dev/)
- [Google SRE Book](https://sre.google/sre-book/table-of-contents/)
- [Google SRE Workbook](https://sre.google/workbook/table-of-contents/)
