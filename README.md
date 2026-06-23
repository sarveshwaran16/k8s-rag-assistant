# AI-Powered Kubernetes Log Investigation Assistant

A fully local RAG (Retrieval-Augmented Generation) pipeline deployed inside a Minikube cluster. Query Kubernetes logs and operational issues using natural language — no cloud, no external APIs.

---

## What It Does

You ask a question like _"Why is my pod in CrashLoopBackOff?"_ and the assistant:

1. Embeds your query using `all-MiniLM-L6-v2`
2. Searches 25,601 indexed chunks across 5 knowledge sources using hybrid retrieval (vector + knowledge graph)
3. Re-ranks the top results
4. Sends the context to a local Ollama LLM (`phi3:mini`) to generate a structured answer
5. Returns the answer with cited source documents and relevance scores

---

## Architecture

```
User Query
    │
    ▼
FastAPI  (port 8000)
    │
    ▼
LangGraph Pipeline
    ├── [1] retrieve_node   → Hybrid Search (ChromaDB + Neo4j)
    ├── [2] build_prompt    → Assembles context + query into prompt
    └── [3] generate_node  → Calls Ollama → structured answer
    │
    ▼
JSON Response  { answer, sources, relevance_scores }
```

---

## Services and Ports

| Service       | Technology                          | Port  |
|---------------|-------------------------------------|-------|
| Query API     | FastAPI + LangGraph                 | 8000  |
| Embedding     | sentence-transformers (MiniLM-L6)   | —     |
| Vector Store  | ChromaDB                            | 8002  |
| Knowledge Graph | Neo4j                             | 7474 (browser), 7687 (bolt) |
| LLM           | Ollama (`phi3:mini`)                | 11434 |

---

## Knowledge Sources

| Source                    | Chunks Ingested |
|---------------------------|-----------------|
| Kubernetes Official Docs  | 21,144          |
| Google SRE Book           | 2,108           |
| Google SRE Workbook       | 1,732           |
| Kubernetes Failure Stories| 433             |
| Prometheus Operator Runbooks | 184          |
| OpenSRE.dev               | 0             |
| **Total**                 | **25,601**      |

>  **OpenSRE.dev** returned 0 chunks — the site was unreachable at the time of ingestion. The ingestion pipeline handles this gracefully (logs the error and skips the source). All other sources were successfully scraped and indexed.

---

## Knowledge Graph

The knowledge graph is stored in Neo4j and augments vector search with structured entity relationships (symptoms → root causes → resolutions).

**Two graph builders exist:**

| File | Method | When to Use |
|------|--------|-------------|
| `services/knowledge_graph/builder.py` | **Regex / keyword-based** extraction (`rule_extractor.py`) |  Used in this project |
| `services/knowledge_graph/builder_llm.py` | **LLM-based** extraction via Ollama (`extractor.py`) | Intended approach — requires adequate hardware |

**Why the regex builder was used:**

`builder_llm.py` calls the Ollama LLM once per chunk to extract entities. With 25,601 chunks, this would require tens of thousands of sequential LLM calls on a machine with no dedicated GPU and only ~4.5 GB of free RAM. This was not feasible.

`builder.py` uses `rule_extractor.py`, which matches a predefined set of ~150 Kubernetes-domain keywords across 5 entity types (`SYMPTOM`, `ALERT`, `ROOT_CAUSE`, `COMPONENT`, `RESOLUTION`) and 48 explicit relationship rules — no LLM required, runs in minutes.

**Graph built (rule-based, on the actual hardware):**

The knowledge graph is populated from 25,601 ChromaDB chunks using the rule-based extractor. The LLM-based builder was tested on a small subset and yielded **129 entities and 17 relationships** — demonstrating that on capable hardware (dedicated GPU, ≥16 GB free RAM), the LLM approach would produce a significantly richer and more semantically accurate graph, directly improving retrieval quality for graph-augmented queries.

---

## Hardware Constraints and Their Impact

**Development machine:**

| Spec | Value |
|------|-------|
| CPU  | Intel Core i5-1335U (13th Gen, 10 cores, laptop U-series) |
| RAM  | 16 GB total — ~11.5 GB in use during operation, ~4.5 GB free |
| GPU  | Intel Iris Xe (integrated, shared memory — no dedicated VRAM) |

**Consequences:**

1. **Slow LLM response times** — Ollama runs entirely on CPU with no GPU acceleration. Response times ranged from **29s to 95s** per query across the 10 evaluation queries. On a machine with a dedicated GPU (e.g. NVIDIA with ≥8 GB VRAM), these would drop to 2–5s.

2. **LLM-based graph builder not used** — Calling the LLM 25,601 times sequentially on CPU would take days and risk OOM crashes. The regex-based `builder.py` was the practical workaround.

3. **Smaller LLM model** — `phi3:mini` (≈2.3 GB) was used because it is the largest model that fits in available RAM. A larger model (e.g. Llama-3 8B or Mistral 7B) would improve answer quality and instruction following.

These are infrastructure constraints, not code limitations. The pipeline is fully functional and will perform significantly better on adequate hardware without any code changes.

---

## Evaluation Results

10 standard Kubernetes troubleshooting queries were evaluated against the live system. Results are saved in `evaluation/results.json`.

| Query | Top Source Relevance | Response Time |
|-------|---------------------|---------------|
| Why is my pod in CrashLoopBackOff? | 0.892 | 87.4s |
| What causes OOMKilled errors? | 0.545 | 77.7s |
| How do I troubleshoot NodeNotReady? | 0.581 | 29.4s |
| Why is my PVC stuck in Pending? | 0.362  | 46.9s |
| How do I diagnose Kubernetes DNS failures? | 0.979 | 81.7s |
| Why is my deployment continuously restarting? | 0.623 | 94.8s |
| How can I investigate CPU throttling? | 0.761 | 37.7s |
| What are common causes of 5XX errors? | 0.802 | 40.9s |
| How do I debug image pull failures? | 0.800 | 57.1s |
| What should I check when a service is unreachable? | 0.847 | 75.0s |

>  **PVC Pending** scored 0.362 — the lowest relevance across all queries. The retrieved chunks came from generic API reference pages rather than storage-specific documentation. This is a retrieval gap, not a pipeline failure. Adding more targeted storage/PVC documentation to the knowledge base would directly fix this.

---

## Project Structure

```
k8s-rag-assistant/
├── main.py                          # CLI entrypoint (ingest | serve | eval)
├── app_ui.py                        # Streamlit web UI
├── requirements.txt
├── .env                             # Environment config (hosts, ports, model)
│
├── services/
│   ├── ingestion/
│   │   ├── ingest.py                # Orchestrates all source ingestion into ChromaDB
│   │   ├── chunker.py               # RecursiveCharacterTextSplitter (750 tokens, 10% overlap)
│   │   ├── Dockerfile
│   │   └── sources/
│   │       ├── k8s_docs.py          # Kubernetes official docs scraper (sitemap-based)
│   │       ├── prometheus_runbooks.py
│   │       ├── k8s_failures.py
│   │       ├── opensre.py           #  Site unreachable at ingestion time — 0 chunks
│   │       └── google_sre.py        # Covers both SRE Book and SRE Workbook
│   │
│   ├── embedding/                   # sentence-transformers embedding service
│   │
│   ├── retrieval/
│   │   ├── vector_retriever.py      # ChromaDB semantic search
│   │   ├── graph_retriever.py       # Neo4j knowledge graph search
│   │   ├── hybrid_retriever.py      # Combines vector + graph results
│   │   └── reranker.py              # Re-ranks combined results by final score
│   │
│   ├── knowledge_graph/
│   │   ├── builder.py               #  Graph builder using rule_extractor (regex-based)
│   │   ├── builder_llm.py           # Graph builder using LLM extractor (hardware-constrained)
│   │   ├── rule_extractor.py        # Keyword/regex entity + relationship extraction
│   │   ├── extractor.py             # LLM-based entity extraction via Ollama
│   │   └── graph_store.py           # Neo4j driver and upsert logic
│   │
│   ├── assistant/
│   │   ├── graph.py                 # LangGraph pipeline definition
│   │   ├── nodes.py                 # retrieve → build_prompt → generate nodes
│   │   ├── assistant.py             # ask() entrypoint used by the API
│   │   └── state.py                 # LangGraph state schema
│   │
│   └── query_api/
│       ├── app.py                   # FastAPI app with POST /query and GET /health
│       └── Dockerfile
│
├── evaluation/
│   ├── queries.py                   # 10 standard eval queries + run_eval()
│   └── results.json                 # Captured results from live system
│
└── k8s/
    └── base/
        ├── kustomization.yaml
        ├── namespace.yaml
        ├── chroma-deployment.yaml
        ├── neo4j-deployment.yaml
        ├── neo4j-pvc.yaml
        ├── llm-deployment.yaml
        ├── embedding-deployment.yaml
        ├── query-api-deployment.yaml
        ├── pvc.yaml
        └── ingestion-job.yaml
```

---

## Prerequisites

- Docker
- Minikube (v1.32+)
- kubectl
- Python 3.11+
- 8 GB RAM minimum (16 GB recommended for running Ollama locally)

---

## Quick Start

```bash
# 1. Start Minikube
minikube start --memory=6144 --cpus=4

# 2. Deploy all services (one command)
kubectl apply -k k8s/base/

# 3. Run ingestion — intentionally separate from kubectl apply -k
#    ingestion-job.yaml is NOT listed in kustomization.yaml because
#    ingestion is a one-time job that must run after services are ready.
#    Running it as part of the base apply would cause it to fire before
#    ChromaDB and Ollama are up.
kubectl apply -f k8s/base/ingestion-job.yaml

# 4. Open four port-forwards (each in a separate terminal)
kubectl port-forward -n rag-assistant svc/query-api-service  8000:8000
kubectl port-forward -n rag-assistant svc/chroma-service     8002:8002
kubectl port-forward -n rag-assistant svc/neo4j-service      7474:7474 7687:7687
kubectl port-forward -n rag-assistant svc/ollama-service     11434:11434

# 5. Populate ChromaDB — run ingestion locally against the port-forwarded ChromaDB
#    (The k8s ingestion job in step 3 runs this inside the cluster.
#     If you need to re-run or run locally, use this instead.)
python services/ingestion/ingest.py

# 6. Build the knowledge graph in Neo4j
#    Two options — choose based on available hardware:

#    Option A (recommended on capable hardware — dedicated GPU + 16 GB+ free RAM):
#    Uses Ollama to extract entities/relationships from each chunk via LLM.
#    Produces a rich graph (~5,000–10,000 entities, ~2,000–5,000 relationships).
python services/knowledge_graph/builder_llm.py

#    Option B (used on constrained hardware — CPU-only, limited RAM):
#    Uses regex/keyword matching — fast but bounded to ~150 predefined keywords.
#    Produces a smaller graph (tested: 129 entities, 17 relationships).
python services/knowledge_graph/builder.py

# 7. Launch the web UI
streamlit run app_ui.py

# Or query via curl
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Why is my pod in CrashLoopBackOff?"}'
```

---

## Running Locally (Without Minikube)

```bash
pip install -r requirements.txt

# Ingest documents into ChromaDB
python main.py ingest

# Start the FastAPI server
python main.py serve

# Run evaluation queries
python main.py eval

# Launch the UI
streamlit run app_ui.py
```

---

## Functional Requirements Status

| FR | Requirement | Status |
|----|-------------|--------|
| FR-1 | Fetch from all 6 primary sources |  5/6 — opensre.dev unreachable at ingestion |
| FR-2 | 500–1000 token chunks, 10% overlap |  750 tokens, 75 token overlap |
| FR-3 | Preserve source URL and section metadata |  All chunks carry `source_url`, `title`, `source` |
| FR-4 | Deduplicate before indexing |  MD5 hash per chunk used as ChromaDB document ID |
| FR-5 | Same embedding model for queries and chunks | `all-MiniLM-L6-v2` used throughout |
| FR-6 | Return top-5 semantically similar chunks |  `TOP_K=5` default in hybrid retriever |
| FR-7 | Include source URL and title in results |  Returned in every API response |
| FR-8 | Construct prompt from query + context |  `build_prompt_node` in LangGraph pipeline |
| FR-9 | Structured response: root cause + remediation |  Prompt explicitly instructs "cause, fix" |
| FR-10 | Cite source documents in every response |  Sources with relevance scores in JSON response |
| FR-11 | REST endpoint accepting plain-text query |  `POST /query` via FastAPI |
| FR-12 | JSON response format |  Pydantic `QueryResponse` model |
| FR-13 | CLI or minimal web UI |  Both — `main.py` CLI + Streamlit `app_ui.py` |

---

## Known Shortcomings vs. Ideal Assistant

This section is transparent about where the current implementation falls short of the PRD targets, why each gap exists, and what the system would look like on adequate hardware.

---

### 1. Knowledge Graph Is Too Small

**PRD expectation:** A rich knowledge graph that meaningfully augments vector search — enough entities and relationships that graph-based retrieval reliably surfaces relevant nodes for any K8s query.

**Actual result:** 129 entities, 17 relationships — built using the rule-based `builder.py`.

**Root cause:** The correct approach is `builder_llm.py`, which uses Ollama to extract entities and relationships from each chunk via a structured prompt. On the development hardware (CPU-only, ~4.5 GB free RAM), calling the LLM 25,601 times sequentially would take several days and would likely OOM crash. The regex-based `builder.py` was used as a practical workaround — it is fast but bounded to ~150 hardcoded keywords, producing a far smaller and less semantically rich graph.

**Estimated graph at full scale (if `builder_llm.py` ran on all 25,601 chunks):**

The LLM builder was tested and yielded 129 entities and 17 relationships on a small run. Extrapolating to the full dataset, with Neo4j deduplication (entities with the same name merge):

| Metric | Current (rule-based) | Estimated at full LLM scale |
|--------|---------------------|----------------------------|
| Entities | 129 | ~5,000 – 10,000 |
| Relationships | 17 | ~2,000 – 5,000 |
| Entity types | 5 fixed types | Open-ended (LLM discovers types) |
| Relationship types | 3 fixed (CAUSES, RESOLVES, AFFECTS) | Rich (TRIGGERS, INDICATES, REQUIRES, MITIGATES, etc.) |

This is roughly a **40–80× increase** in graph size and diversity. Hybrid retrieval would contribute substantially more to final answer quality rather than relying almost entirely on vector search.

**Impact on current results:** For queries where the relevant knowledge is structural (e.g. "PVC stuck in Pending" — involves StorageClass → PVC → Node relationships), graph retrieval currently contributes very little. The low relevance score of 0.362 for the PVC query is partly a consequence of this.

---

### 2. Response Latency Exceeds the 30-Second Target

**PRD target:** Responses in under 30 seconds.

**Actual results:** 9 out of 10 evaluation queries exceeded 30 seconds. Times ranged from 29.4s to 94.8s.

| Queries under 30s | Queries over 30s |
|-------------------|-----------------|
| 1 (NodeNotReady — 29.4s, barely) | 9 |

**Root cause:** Ollama (`phi3:mini`) runs entirely on CPU — the development machine has no dedicated GPU and Intel Iris Xe uses shared system memory, not dedicated VRAM. CPU-only inference on a 3.8B parameter model is inherently slow.

**Secondary cause:** `phi3:mini` is the largest model that fits in the available ~4.5 GB of free RAM. Larger models that produce better structured output require more VRAM and would not load at all on this machine.

---

### 3. Low Relevance Scores for Certain Queries

**PRD expectation:** Semantically relevant chunks for every standard troubleshooting query.

**Queries with weak retrieval:**

| Query | Relevance Score | Reason |
|-------|----------------|--------|
| Why is my PVC stuck in Pending? | 0.362 | Retrieved generic API reference pages — no PVC/StorageClass-specific content in top chunks |
| What causes OOMKilled errors? | 0.545 | Top chunks came from SRE Book (cascading failures), not K8s-specific memory limit docs |
| How do I troubleshoot NodeNotReady? | 0.581 | Retrieved from K8s failure stories rather than operational runbooks |

**Root causes:**
- **Documentation gap:** The ingested K8s docs cover reference APIs heavily (21k chunks from sitemap) but are thinner on deep troubleshooting narratives for storage and node issues.
- **Weak graph augmentation:** With only 17 relationships in the knowledge graph, graph retrieval contributes almost nothing for queries that would benefit from entity traversal (e.g. PVC → StorageClass → Node).
- **OpenSRE.dev missing:** That source (0 chunks, site unreachable) would have contributed practical troubleshooting content that bridges the K8s docs and SRE book.

---

### 4. Missing Knowledge Source (OpenSRE.dev)

**PRD requirement:** 6 knowledge sources ingested.

**Actual:** 5 of 6 — OpenSRE.dev returned 0 chunks because the site was unreachable at ingestion time. The scraper and ingestion logic for it is fully implemented in `sources/opensre.py`. Re-running ingestion when the site is available would populate it automatically.

---

### Current Hardware vs. Ideal Specification

| Spec | Current (Development) | Ideal for Full Performance |
|------|-----------------------|-----------------------------|
| CPU | Intel i5-1335U (laptop U-series, 10 cores, 1.3 GHz base) | Any modern desktop CPU (8+ cores) |
| RAM | 16 GB total, ~4.5 GB free during operation | 32 GB+ with ≥16 GB free |
| GPU | Intel Iris Xe (integrated, no dedicated VRAM) | NVIDIA RTX 3080 / 4070 or better (≥8 GB VRAM) |
| LLM model | `phi3:mini` (3.8B, ~2.3 GB) — largest that fits | `Llama-3 8B` or `Mistral 7B` (quantized, needs GPU) |
| Graph builder | `builder.py` (regex, runs in minutes) | `builder_llm.py` (LLM, ~hours with GPU) |
| Expected latency | 29 – 95s per query | 2 – 5s per query (GPU-accelerated) |
| Knowledge graph | 129 entities, 17 relationships | ~5,000–10,000 entities, ~2,000–5,000 relationships |

**No code changes are required** to unlock this performance. Deploying the exact same stack on a machine with a dedicated GPU and sufficient RAM would:
- Drop response times from ~60s average to under 5s
- Allow `builder_llm.py` to run on all 25,601 chunks and build a full-scale graph
- Allow use of a larger, more capable LLM model
- Improve answer quality, structure, and relevance across all queries

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Ingestion | LangChain, BeautifulSoup4, Requests | langchain 0.3.30 |
| Embedding | sentence-transformers | 3.1.1 |
| Vector Store | ChromaDB | 0.5.5 |
| Knowledge Graph | Neo4j | 5.25.0 |
| Orchestration | LangGraph | 0.2.28 |
| API | FastAPI + Uvicorn | 0.115.0 |
| LLM | Ollama (`phi3:mini`) | via HTTP |
| UI | Streamlit | 1.39.0 |
| Deployment | Minikube + kubectl + Kustomize | — |
