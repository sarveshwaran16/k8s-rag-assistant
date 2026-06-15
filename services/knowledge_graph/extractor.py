import json
import requests
import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3:mini")

EXTRACTION_PROMPT = """You are a JSON generator. Output only valid JSON, nothing else.

Extract entities from this Kubernetes text:
{text}

Output this exact JSON structure:
{{"entities": [{{"name": "entity_name", "type": "SYMPTOM", "description": "what it is"}}], "relationships": [{{"source": "entity1", "target": "entity2", "type": "CAUSES"}}]}}

JSON output:"""
def extract_entities(chunk: dict) -> dict:
    """Extract entities and relationships from a single chunk using Ollama."""
    text = chunk["text"][:500]
    prompt = EXTRACTION_PROMPT.format(text=text)

    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.0}
            },
            timeout=300
        )
        resp.raise_for_status()
        raw = resp.json()["response"].strip()
        

        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        parsed = json.loads(raw)
        normalized_rels = []
        for rel in parsed.get("relationships", []):
            normalized_rels.append({
                "source": rel.get("source") or rel.get("sourceEntity", ""),
                "target": rel.get("target") or rel.get("targetConditionStatus", ""),
                "type": rel.get("type", "RELATED")
            })
        parsed["relationships"] = normalized_rels
        parsed["source_url"] = chunk["metadata"]["source_url"]
        parsed["title"] = chunk["metadata"]["title"]
        parsed["source"] = chunk["metadata"]["source"]  
        return parsed

    except Exception as e:
        print(f"[extractor] Failed on chunk: {e}")
        return {"entities": [], "relationships": [],
                "source_url": chunk["metadata"].get("source_url", ""),
                "title": chunk["metadata"].get("title", ""),
                "source": chunk["metadata"].get("source", "")}