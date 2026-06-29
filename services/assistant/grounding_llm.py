import os
import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3:mini")

VERIFICATION_PROMPT = """Context:
{context}

Answer:
{answer}

Does the answer contain any claim that is NOT supported by the context above? Respond with exactly one word, YES or NO, followed by a colon and a brief quote of the unsupported part if YES. If NO, just respond NO."""


def check_grounding_llm(answer: str, chunks: list[dict]) -> dict:
    """
    LLM-based faithfulness check. Unlike the lexical-overlap or citation-based
    checks, this asks the model directly whether the answer's claims are
    supported by the retrieved context — a semantic judgment that keyword
    matching cannot make. Requires a second Ollama call, roughly doubling
    per-query latency on CPU-only inference; on GPU hardware this cost is
    small relative to generation itself.

    Parsing note: phi3:mini does not reliably lead with a strict "YES"/"NO"
    token as instructed — in testing it sometimes opens with "NO" while its
    own reasoning text clearly states the claim is unsupported. Rather than
    trusting only the first word, this checks the full verdict text for
    explicit unsupported-claim language. This is still a heuristic over an
    unreliable model output, not a guaranteed-correct parse.
    """
    context_text = "\n\n".join(c["text"][:300] for c in chunks)
    prompt = VERIFICATION_PROMPT.format(context=context_text, answer=answer)

    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.0, "num_ctx": 1024, "num_predict": 100}
            },
            timeout=480
        )
        resp.raise_for_status()
        verdict = resp.json()["response"].strip()
    except Exception as e:
        return {"grounded": None, "verdict_raw": f"ERROR: {e}", "checked": False}

    verdict_lower = verdict.lower()
    unsupported_signals = [
        "not supported", "not mentioned", "unsupported", "cannot be confirmed",
        "does not include", "does not mention", "not present in", "not found in",
        "no mention of", "not contained in"
    ]
    is_grounded = not any(signal in verdict_lower for signal in unsupported_signals)

    return {"grounded": is_grounded, "verdict_raw": verdict, "checked": True}


def grounding_llm_node(state: dict) -> dict:
    """LangGraph node — LLM-based faithfulness check, swappable alternative
    to the lexical/citation-based safety_check_node."""
    result = check_grounding_llm(state["answer"], state["retrieved_chunks"])
    answer = state["answer"]
    if result["checked"] and not result["grounded"]:
        answer += f"\n\n_LLM faithfulness check flagged this answer: {result['verdict_raw']}_"
    return {"answer": answer, "grounding_llm": result}