import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "rag-assistant")


def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def create_indexes(driver):
    """Create indexes for faster lookups."""
    with driver.session() as session:
        session.run("CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)")
        session.run("CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type)")
    print("[graph_store] Indexes created")


def upsert_entities(driver, extracted: dict):
    """Insert or update entities and relationships into Neo4j."""
    with driver.session() as session:
        for entity in extracted.get("entities", []):
            if not entity.get("name"):
                continue
            session.run("""
                MERGE (e:Entity {name: $name})
                SET e.type = $type,
                    e.description = $description,
                    e.source_url = $source_url,
                    e.source = $source
            """, name=entity["name"],
                type=entity.get("type", "CONCEPT"),
                description=entity.get("description", ""),
                source_url=extracted.get("source_url", ""),
                source=extracted.get("source", ""))

        for rel in extracted.get("relationships", []):
            session.run("""
                MATCH (a:Entity {name: $source})
                MATCH (b:Entity {name: $target})
                MERGE (a)-[r:RELATED {type: $type}]->(b)
            """, source=rel["source"],
                target=rel["target"],
                type=rel["type"])


def get_related_entities(driver, query_entities: list[str], limit: int = 10) -> list[dict]:
    """Retrieve entities related to the query entities from the graph."""
    with driver.session() as session:
        result = session.run("""
            MATCH (e:Entity)
            WHERE e.name IN $names
            OPTIONAL MATCH (e)-[r:RELATED]->(related:Entity)
            RETURN e.name as name, e.type as type, e.description as description,
                   e.source_url as source_url, collect(related.name) as related
            LIMIT $limit
        """, names=query_entities, limit=limit)
        return [dict(record) for record in result]


def count_entities(driver) -> int:
    with driver.session() as session:
        result = session.run("MATCH (e:Entity) RETURN count(e) as count")
        return result.single()["count"]