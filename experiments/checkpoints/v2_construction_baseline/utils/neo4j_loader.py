"""
Neo4j Knowledge Graph Loader — Enhanced.

Handles connecting to Neo4j, setting up schema, clearing graphs,
and loading entities and relationships with full attribute support.

Enhanced from the original to support:
- Entity aliases (stored as list property)
- Entity attributes (stored as node properties)
- Entity descriptions
- Full-text search indexes for entity names
- Batch operations using UNWIND for performance
- Per-entity/relationship error logging
"""

import logging
from collections import defaultdict
from typing import List

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)


class Neo4jLoader:
    """Manages Neo4j connections and knowledge graph persistence.
    
    Args:
        uri: Neo4j connection URI (bolt:// or neo4j+s://).
        user: Database username.
        password: Database password.
    """

    def __init__(self, uri: str, user: str, password: str):
        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            self.driver.verify_connectivity()
            logger.info("Connected to Neo4j successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise

    # ── Schema Setup ────────────────────────────────────────────────────

    def setup_schema(self, entity_types: List[str]):
        """Create constraints, indexes, and full-text search indexes."""
        try:
            with self.driver.session() as session:
                # Uniqueness constraint on Entity.id
                try:
                    session.run("DROP CONSTRAINT entity_name IF EXISTS")
                except Exception:
                    pass

                try:
                    session.run(
                        "CREATE CONSTRAINT entity_id IF NOT EXISTS "
                        "FOR (e:Entity) REQUIRE e.id IS UNIQUE"
                    )
                except Exception as e:
                    logger.warning(f"Constraint may already exist: {e}")

                # Indexes for specific entity types
                for label in entity_types:
                    safe_label = label.replace(" ", "")
                    try:
                        session.run(
                            f"CREATE INDEX idx_{safe_label.lower()}_id IF NOT EXISTS "
                            f"FOR (n:{safe_label}) ON (n.id)"
                        )
                    except Exception:
                        pass

                # Full-text search index on entity names and descriptions
                try:
                    session.run(
                        "CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS "
                        "FOR (n:Entity) ON EACH [n.name, n.canonical_name, n.description]"
                    )
                except Exception as e:
                    logger.warning(f"Full-text index may already exist: {e}")

            logger.info("Schema constraints and indexes verified/created")
        except Exception as e:
            logger.error(f"Failed to setup schema: {e}")

    # ── Graph Operations ────────────────────────────────────────────────

    def clear_graph(self):
        """Delete all nodes and relationships from the graph."""
        try:
            with self.driver.session() as session:
                # Delete in batches to avoid memory issues on large graphs
                while True:
                    result = session.run(
                        "MATCH (n) WITH n LIMIT 10000 DETACH DELETE n "
                        "RETURN count(*) AS deleted"
                    )
                    record = result.single()
                    deleted = record["deleted"] if record else 0
                    if deleted == 0:
                        break
                    logger.debug(f"Deleted batch of {deleted} nodes")
            logger.info("Graph cleared")
        except Exception as e:
            logger.error(f"Failed to clear graph: {e}")

    # ── Entity Loading ──────────────────────────────────────────────────

    def load_entities(self, entities: list):
        """Load entities into Neo4j with full attribute support.
        
        Each entity gets:
        - Labels: Entity + its type (e.g., Entity:Organization)
        - Properties: name, type, description, confidence, source_text,
                      page_start, page_end, aliases (list), plus any
                      key-value pairs from the attributes dict.
        """
        entity_dicts = []
        for e in entities:
            d = e.model_dump() if hasattr(e, 'model_dump') else e
            # Flatten attributes into top-level properties with 'attr_' prefix
            attrs = d.pop("attributes", {}) or {}
            for k, v in attrs.items():
                # Only store serializable values
                if isinstance(v, (str, int, float, bool)):
                    d[f"attr_{k}"] = v
            # Ensure aliases is a list
            if "aliases" not in d or d["aliases"] is None:
                d["aliases"] = []
            entity_dicts.append(d)

        try:
            with self.driver.session() as session:
                # Group entities by type for efficient MERGE with labels
                type_groups = defaultdict(list)
                for ed in entity_dicts:
                    type_groups[ed.get("type", "Entity")].append(ed)

                for e_type, group in type_groups.items():
                    label = e_type.replace(" ", "")

                    # Build SET clause dynamically for each group
                    # Core properties always set
                    query = (
                        "UNWIND $entities AS entity "
                        f"MERGE (n:Entity:{label} {{id: entity.id}}) "
                        "SET n.canonical_name = entity.canonical_name, "
                        "    n.name = entity.name, "
                        "    n.type = entity.type, "
                        "    n.description = entity.description, "
                        "    n.confidence = entity.confidence, "
                        "    n.evidence = entity.evidence, "
                        "    n.frequency = entity.frequency, "
                        "    n.source_pages = entity.source_pages, "
                        "    n.source_chunks = entity.source_chunks, "
                        "    n.aliases = entity.aliases"
                    )

                    # Add attribute properties if any entity in this group has them
                    attr_keys = set()
                    for ed in group:
                        attr_keys.update(
                            k for k in ed.keys()
                            if k.startswith("attr_")
                        )

                    for attr_key in sorted(attr_keys):
                        query += f", n.{attr_key} = entity.{attr_key}"

                    session.run(query, entities=group)
                    logger.info(f"Loaded {len(group)} {label} nodes")

        except Exception as e:
            logger.error(f"Failed to load entities: {e}")
            raise

    # ── Relationship Loading ────────────────────────────────────────────

    def load_relationships(self, relationships: list):
        """Load relationships into Neo4j.
        
        Each relationship connects two Entity nodes and carries:
        - Properties: confidence, source_text, description, page_start,
                      page_end, is_implicit
        """
        rel_type_groups = defaultdict(list)
        for rel in relationships:
            rd = rel.model_dump() if hasattr(rel, 'model_dump') else rel
            rel_type_groups[rd.get("relation", "RELATED_TO")].append(rd)

        try:
            with self.driver.session() as session:
                for rel_type, rel_list in rel_type_groups.items():
                    # Sanitize relationship type for Cypher
                    sanitized = (
                        rel_type.replace(" ", "_")
                        .replace("-", "_")
                        .replace(".", "_")
                        .upper()
                    )

                    query = (
                        "UNWIND $rels AS rel "
                        "MATCH (a:Entity {id: rel.source}) "
                        "MATCH (b:Entity {id: rel.target}) "
                        f"MERGE (a)-[r:{sanitized}]->(b) "
                        "SET r.confidence = rel.confidence, "
                        "    r.evidence = rel.evidence, "
                        "    r.description = rel.description, "
                        "    r.implicit = rel.implicit, "
                        "    r.frequency = rel.frequency, "
                        "    r.source_pages = rel.source_pages, "
                        "    r.source_chunks = rel.source_chunks"
                    )

                    session.run(query, rels=rel_list)
                    logger.info(
                        f"Loaded {len(rel_list)} {sanitized} relationships"
                    )
        except Exception as e:
            logger.error(f"Failed to load relationships: {e}")
            raise

    # ── Orchestration ───────────────────────────────────────────────────

    def load_all(
        self,
        extraction_result,
        entity_types: List[str],
        clear_first: bool = True,
    ):
        """Load a complete extraction result into Neo4j.
        
        Args:
            extraction_result: ExtractionResult with entities and relationships.
            entity_types: List of entity type labels for index creation.
            clear_first: Whether to clear existing graph data before loading.
        """
        self.setup_schema(entity_types)

        if clear_first:
            self.clear_graph()

        logger.info("Loading entities into Neo4j...")
        self.load_entities(extraction_result.entities)

        logger.info("Loading relationships into Neo4j...")
        self.load_relationships(extraction_result.relationships)

        logger.info(
            f"Knowledge Graph loaded: "
            f"{len(extraction_result.entities)} nodes, "
            f"{len(extraction_result.relationships)} edges"
        )

    # ── Validation ──────────────────────────────────────────────────────

    def validate(self):
        """Run validation queries and log results."""
        queries = {
            "Total Nodes": "MATCH (n) RETURN count(n) AS count",
            "Nodes by Type": (
                "MATCH (n:Entity) RETURN n.type AS type, count(n) AS count "
                "ORDER BY count DESC"
            ),
            "Total Relationships": "MATCH ()-[r]->() RETURN count(r) AS count",
            "Relationship Types": (
                "MATCH ()-[r]->() RETURN type(r) AS rel_type, count(r) AS count "
                "ORDER BY count DESC LIMIT 20"
            ),
            "Entities with Aliases": (
                "MATCH (n:Entity) WHERE size(n.aliases) > 0 "
                "RETURN count(n) AS count"
            ),
            "Entities with Description": (
                "MATCH (n:Entity) WHERE n.description IS NOT NULL "
                "AND n.description <> '' RETURN count(n) AS count"
            ),
        }

        with self.driver.session() as session:
            for title, query in queries.items():
                logger.info(f"Validation [{title}]:")
                try:
                    result = session.run(query)
                    records = list(result)
                    if records:
                        for record in records:
                            logger.info(f"  -> {dict(record)}")
                    else:
                        logger.info("  -> (no results)")
                except Exception as e:
                    logger.error(f"Query failed: {e}")

    # ── Full-Text Search ────────────────────────────────────────────────

    def search_entities(self, query: str, limit: int = 10) -> list:
        """Search entities using the full-text index.
        
        Args:
            query: Search query string.
            limit: Maximum number of results.
            
        Returns:
            List of matching entity records.
        """
        try:
            with self.driver.session() as session:
                result = session.run(
                    "CALL db.index.fulltext.queryNodes("
                    "'entity_fulltext', $query) "
                    "YIELD node, score "
                    "RETURN node.name AS name, node.type AS type, "
                    "       node.description AS description, score "
                    "ORDER BY score DESC LIMIT $limit",
                    query=query,
                    limit=limit,
                )
                return [dict(r) for r in result]
        except Exception as e:
            logger.error(f"Full-text search failed: {e}")
            return []

    # ── Get Neighborhood ────────────────────────────────────────────────

    def get_entity_neighborhood(
        self, entity_name: str, hops: int = 2, limit: int = 50
    ) -> dict:
        """Get the multi-hop neighborhood of an entity.
        
        Args:
            entity_name: Name of the center entity.
            hops: Number of relationship hops (1-3).
            limit: Maximum number of paths to return.
            
        Returns:
            Dict with 'entities' and 'relationships' in the neighborhood.
        """
        hops = min(max(hops, 1), 3)  # Clamp to 1-3

        try:
            with self.driver.session() as session:
                result = session.run(
                    f"MATCH (center:Entity {{name: $name}}) "
                    f"MATCH path = (center)-[*1..{hops}]-(neighbor) "
                    f"WITH neighbor, relationships(path) AS rels "
                    f"LIMIT $limit "
                    f"RETURN neighbor.name AS name, neighbor.type AS type, "
                    f"       neighbor.description AS description",
                    name=entity_name,
                    limit=limit,
                )
                entities = [dict(r) for r in result]

                # Get relationships in the neighborhood
                result2 = session.run(
                    f"MATCH (center:Entity {{name: $name}}) "
                    f"MATCH (center)-[r*1..{hops}]-(neighbor) "
                    f"WITH center, neighbor "
                    f"MATCH (center)-[r]->(neighbor) "
                    f"RETURN center.name AS source, type(r) AS relation, "
                    f"       neighbor.name AS target "
                    f"LIMIT $limit",
                    name=entity_name,
                    limit=limit,
                )
                relationships = [dict(r) for r in result2]

                return {
                    "center": entity_name,
                    "entities": entities,
                    "relationships": relationships,
                }
        except Exception as e:
            logger.error(f"Neighborhood query failed: {e}")
            return {"center": entity_name, "entities": [], "relationships": []}

    # ── Cleanup ─────────────────────────────────────────────────────────

    def close(self):
        """Close the Neo4j driver connection."""
        self.driver.close()
        logger.info("Neo4j connection closed")
