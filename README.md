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
    ├── [1] retrieve_node
    │       ├── vector_search  → ChromaDB  (candidate pool: 15 chunks)
    │       ├── graph_search   → Neo4j     (top_k graph nodes)
    │       └── rerank         → weighted score → top 5 returned
    ├── [2] build_prompt    → Assembles context + query into prompt
    └── [3] generate_node  → Calls Ollama → structured answer
    │
    ▼
JSON Response  { answer, sources, relevance_scores }
```

---

## Retrieval Pipeline

Hybrid retrieval runs two searches in parallel and merges them before passing context to the LLM.

### Step 1 — Candidate pool (vector search)

`vector_search` queries ChromaDB with `candidate_pool=15` — fetching **15 chunks** instead of the final `TOP_K=5`. This wider pool gives the reranker real material to work with; without it, re-ranking on only 5 chunks would have little effect.

### Step 2 — Graph augmentation

`graph_search` queries Neo4j for entities matching keywords extracted from the query, returning up to `top_k` additional nodes (with a fixed graph score). Graph results are appended to the vector pool before re-ranking.

### Step 3 — Weighted re-ranking

`rerank()` scores every chunk in the combined pool using **three signals**, then sorts descending and returns the top `TOP_K=5`:

| Signal | How it works |
|--------|--------------|
| **Base score** | Raw similarity score from ChromaDB (cosine distance) or fixed graph score from Neo4j |
| **Keyword overlap boost** | +0.05 per query term found verbatim in the chunk text — rewards chunks that directly contain the user's exact words |
| **Source weight** | Multiplies the boosted score — prioritises operationally precise sources over general theory |

**Source weights (`reranker.py`):**

| Source | Weight | Rationale |
|--------|--------|-----------|
| `kubernetes_docs` | 1.0 | Primary reference — highest precision for K8s-specific facts |
| `prometheus_runbooks` | 1.0 | Operational runbooks — directly actionable, K8s-specific |
| `k8s_failures` | 0.9 | Real failure post-mortems — highly relevant, slightly noisier |
| `knowledge_graph` | 0.85 | Graph nodes add structure but are extracted, not verbatim source text |
| `sre_book` | 0.6 | Valuable SRE theory but not K8s-specific — down-weighted |
| `sre_workbook` | 0.6 | Same as SRE Book |

**Final score formula:**
```
final_score = (base_score + keyword_boost) × source_weight
```

### Why this matters

Vector similarity alone ranks chunks by semantic closeness to the query embedding. The reranker corrects for two known weaknesses of `all-MiniLM-L6-v2` on this corpus: it tends to surface SRE theory content (high semantic similarity) when K8s-specific runbook content (lower raw score, but operationally correct) is more useful, and it can miss chunks that share the user's exact technical terms without being semantically close in embedding space. The keyword boost and source weights compensate for both.

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

## Guardrails & Grounding

Three independent layers were implemented to reduce hallucination and limit the assistant to its intended domain. Each layer is operative in the production pipeline; the LLM-based variant is preserved as a documented, swappable experiment.

---

### 1. Input Guardrail — Scope Check (`guardrail.py`)

A deterministic keyword gate that runs as the **first node** in the LangGraph pipeline, before any retrieval or LLM call.

- Matches the query against a curated list of 100+ Kubernetes/SRE terms spanning core objects (`pod`, `deployment`, `pvc` …), failure states (`crashloopbackoff`, `oomkilled`, `imagepullbackoff` …), infra vocabulary (`dns`, `rbac`, `storageclass` …), and common troubleshooting phrases (`debug`, `stuck`, `keeps restarting` …).
- If no keyword matches, the pipeline **short-circuits to `END` instantly** — zero retrieval calls, zero LLM calls — and returns a structured rejection message pointing the user toward a valid K8s question.
- Tested and confirmed working in both directions: correctly rejects `"What is the capital of France?"` and correctly accepts `"How do I debug image pull failures?"`. The keyword list was expanded after a real miss caught during eval testing.
- **Known limitation:** purely lexical — can both false-block legitimate questions phrased without K8s jargon, and false-allow off-topic questions that happen to contain an ambiguous common word from the list (e.g. `"scale"`, `"image"`, `"error"`).

---

### 2. Grounding (Faithfulness) — Three Layered Attempts

#### Layer 1 — Prompt Instruction (`nodes.py`)

Added explicit negative constraints to the LLM prompt:

> *"Using ONLY the information in the context above, answer this question. Do not add facts, field names, or details that are not present in the context. If the context doesn't fully answer the question, say so rather than guessing."*

**Result:** Measurably reduced fabricated details (eliminated invented field names like `retryAfterSeconds`). Did not eliminate all hallucination — the model still occasionally introduced vague, unsupported framing.

#### Layer 2 — Citation Tags + Safety Check (`nodes.py` + `safety.py`) — **Production default**

The prompt now requires the model to append a `[source:<title>]` citation tag after every factual statement, drawn exclusively from the retrieved source titles. A post-generation `safety_check_node` then:

1. Extracts all citation tags and validates each against the actual set of retrieved source titles — flags any citation that references a source not in the retrieved set.
2. Extracts all `kubectl <verb>` commands from the answer and checks each one verbatim against the raw text of the retrieved chunks.
3. Any command that cannot be verified is **replaced in-place** with `<command omitted — '...' could not be verified against retrieved sources>` and a note is appended to the answer.

**Result:** Zero extra latency (pure Python, no LLM call). Caught the specific "real-but-misapplied command" failure mode seen in earlier testing (`kubectl autoscale` suggested for a quota issue where the source never mentioned it in that context).

#### Layer 3 — LLM-Based Faithfulness Check (`grounding_llm.py` + `graph_llm_grounding.py`) — **Experiment only, not production**

Built as an explicitly swappable alternative (same architectural pattern as `builder.py` / `builder_llm.py`): a second Ollama call asks the model directly whether the answer contains any claim unsupported by the retrieved context.

**Parsing problem encountered and documented:** `phi3:mini` does not reliably emit a clean YES/NO verdict. In testing on two known cases:

- **Case 1 (fabricated claim):** The model replied `"NO — The provided information does not include details about retryAfterSeconds field; hence it cannot be confirmed as supported based on the given context."` — formally answers NO, but its own reasoning states the claim is unsupported (correct answer: YES). The model's reasoning is right; its chosen format is not.
- **Case 2 (faithful answer):** The model replied `"NO — The provided answer does not contain any claims that are not supported by the given context."` — correct verdict, correct reasoning.

Two parsing fixes were each tried:
1. **Trust only the first word** — Case 1 wrongly passes as grounded (model said "NO" first despite meaning the opposite).
2. **Scan full text for unsupported-claim signals** (`"not supported"`, `"cannot be confirmed"` …) — fixes Case 1 but breaks Case 2, because Case 2's sentence also contains `"not supported"` inside a double negative (`"does not contain claims that are not supported"`), which simple string matching cannot distinguish from an actual unsupported-claim signal.

**Honest conclusion:** The LLM-based check is the only approach capable of true semantic judgment, but on this model and hardware it is not reliable enough to trust as an automated gate. Its value in this project is as a real, tested experiment demonstrating exactly *why* the simpler citation/safety-check approach is the pragmatic production choice — not a missed opportunity. It will behave correctly on a larger model or when structured output / JSON mode is available.

#### How to switch between the two pipelines

The entire pipeline is wired through a single import in [`assistant.py`](file:///d:/rag-assistant/k8s-rag-assistant/services/assistant/assistant.py). One line controls which graph runs:

**Currently active (production default — citation + command safety check, no second LLM call):**
```python
# services/assistant/assistant.py  line 6
from assistant.graph import assistant_graph
```

**To switch to LLM-based faithfulness check (adds a second Ollama call after safety check):**
```python
# services/assistant/assistant.py  line 6
from assistant.graph_llm_grounding import assistant_graph_llm_grounding as assistant_graph
```

That single import swap is the only change needed — the `ask()` function and everything above it stay identical. The LLM grounding pipeline adds one extra node (`run_llm_grounding`) after `run_safety_check` before reaching `END`, as defined in [`graph_llm_grounding.py`](file:///d:/rag-assistant/k8s-rag-assistant/services/assistant/graph_llm_grounding.py).

> **When to use LLM grounding:** Only on hardware with a dedicated GPU and a larger model (Llama-3 8B / Mistral 7B with JSON/structured output mode). On `phi3:mini` + CPU, it roughly doubles latency and the YES/NO verdict parsing is unreliable — see the parsing problem documented above.

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

### 5. NodeNotReady — Right Document Existed, Nothing Retrieved It

**Query:** *"How do I troubleshoot NodeNotReady?"* — a standard PRD evaluation question.

**What happened:** The assistant correctly declined to answer rather than guess. Tracing the failure revealed the cause was not a content gap:

- **The content exists.** A direct text search across all 25,601 chunks confirms a chunk titled `"KubeNodeNotReady#"` from the Prometheus runbooks, opening with *"the KubeNodeNotReady alert is fired when a Kubernetes node is not in Ready state"* — almost a perfect match for the question's wording.
- **Vector search missed it.** Even with the candidate pool widened to 15 chunks, this exact chunk never appeared. `all-MiniLM-L6-v2` scored adjacent node-health content (`NodeClockSkewDetected`, `NodeNetworkReceiveErrs`) similarly to or higher than the directly relevant chunk — the embedding model's similarity judgment did not capture the closeness a human reader would see between the query phrasing and this specific technical term.
- **Graph search was correctly designed but had nothing to find.** The keyword-extraction logic in `graph_retriever.py` correctly identified `"nodenotready"` as the entity to search for in Neo4j. But a direct query against the graph confirms zero entities contain that string — the rule-based extractor's keyword dictionary never created a node for this specific term, despite the source text containing it.
- **Grounding then did exactly what it was built to do.** With neither retrieval path returning genuinely relevant content, the model — instructed to acknowledge gaps rather than guess — correctly declined. This is safe behaviour, but it is still a retrieval failure, not a success.

**Root cause:** Two layers upstream — the embedding model's similarity judgment, and a gap in the rule-based knowledge graph's coverage. Every individual component behaved correctly given its inputs; the failure sits in what was fed to them. A richer knowledge graph (the kind `builder_llm.py` was designed to produce) would very plausibly have caught this specific case by having a properly-linked `NodeNotReady` entity for graph search to find even when vector search came up short — exactly the complementary strength hybrid retrieval is supposed to provide.

---

### 6. PVC Stuck in Pending — Fabricated Claim Dressed in a Real Citation

**Query:** *"Why is my PVC stuck in Pending?"*

**What happened:** The answer included two `[source:...]` citation tags, both pointing to genuinely retrieved documents — on the surface, a sign of grounding working. But the actual claim was fabricated: the answer described Kubernetes API pagination behaviour (the `continue` parameter, used for paging through list results) as the cause of PVCs getting stuck in Pending. This is a real Kubernetes concept, but entirely unrelated to PVC provisioning — invented and then wrapped in a citation that passed the `validate_citations` check without issue.

**Why the citation check didn't catch it:** The citation system only verifies that a named source exists in the retrieved set. It has no way to check whether the specific claim attached to that citation is actually what the source says — only that the source was retrieved. This is a known, specific limit of the current implementation.

**Root cause:** The same upstream weakness as Problem 5 — weak retrieval. All three retrieved sources scored an unusually low, suspiciously identical `0.362` similarity, meaning vector search effectively had nothing genuinely relevant and surfaced its least-bad options. This time, instead of declining (as in the NodeNotReady case), the model filled the gap with an invented mechanism and attached a real citation to it — which is arguably more dangerous than an uncited fabrication, because the citation makes the answer appear grounded and credible.

**What this reveals about grounding consistency:** The model's response to weak retrieval is not consistent. Sometimes the grounding instruction succeeds in making it decline; sometimes it doesn't. Citations alone cannot reliably distinguish between those two outcomes after the fact. The deeper fix is better retrieval — not stronger post-generation checks.

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
