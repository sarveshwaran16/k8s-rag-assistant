import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "rag-assistant")


def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def extract_keywords(query: str) -> list[str]:
    """Extract likely entity names from the query."""
    k8s_terms = [
        "crashloopbackoff", "oomkilled", "nodenotready", "pending",
        "evicted", "imagepullbackoff", "dns", "pvc", "cpu", "memory",
        "pod", "node", "deployment", "service", "ingress", "etcd",
        "kubelet", "scheduler", "timeout", "error", "failed"
    ]
    query_lower = query.lower()
    found = [term for term in k8s_terms if term in query_lower]
    return found if found else query.split()[:3]


def graph_search(query: str, limit: int = 5) -> list[dict]:
    """Search Neo4j for entities related to the query."""
    driver = get_driver()
    keywords = extract_keywords(query)

    results = []
    with driver.session() as session:
        for keyword in keywords:
            result = session.run("""
                MATCH (e:Entity)
                WHERE toLower(e.name) CONTAINS toLower($keyword)
                   OR toLower(e.description) CONTAINS toLower($keyword)
                OPTIONAL MATCH (e)-[r:RELATED]->(related:Entity)
                RETURN e.name as name,
                       e.type as type,
                       e.description as description,
                       e.source_url as source_url,
                       collect(related.name) as related_entities
                LIMIT $limit
            """, keyword=keyword, limit=limit)

            for record in result:
                text = f"{record['name']} ({record['type']}): {record['description']}"
                if record['related_entities']:
                    text += f" Related to: {', '.join(record['related_entities'])}"
                results.append({
                    "text": text,
                    "metadata": {
                        "source_url": record["source_url"] or "",
                        "title": record["name"],
                        "source": "knowledge_graph"
                    },
                    "score": 0.7,
                    "source": "graph"
                })

    driver.close()
    # deduplicate
    seen = set()
    unique = []
    for r in results:
        if r["text"] not in seen:
            seen.add(r["text"])
            unique.append(r)

    return unique[:limit]