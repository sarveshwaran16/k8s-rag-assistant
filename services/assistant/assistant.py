import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
from assistant.graph import assistant_graph

load_dotenv()


def ask(query: str) -> dict:
    """Run the assistant pipeline for a given query."""
    initial_state = {
        "query": query,
        "retrieved_chunks": [],
        "prompt": "",
        "answer": "",
        "sources": [],
        "messages": []
    }

    result = assistant_graph.invoke(initial_state)

    return {
        "query": query,
        "answer": result["answer"],
        "sources": result["sources"]
    }


if __name__ == "__main__":
    import json
    query = "Why is my pod in CrashLoopBackOff?"
    print(f"\nQuery: {query}\n")
    result = ask(query)
    print(f"Answer:\n{result['answer']}\n")
    print(f"Sources:")
    for s in result["sources"]:
        print(f"  - {s['title']} ({s['source']}) — score: {s['relevance_score']}")