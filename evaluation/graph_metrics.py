"""
graph_metrics.py - Graph Quality Analysis for Knowledge Graphs.

Computes: node/entity statistics, relationship statistics, graph density,
connected components, average degree, confidence stats.
"""

import json
import logging
from typing import Dict, List, Any
from pathlib import Path

logger = logging.getLogger(__name__)


def load_refined_graph(path: str = None) -> Dict:
    """Load the refined graph JSON file."""
    if path is None:
        path = Path(__file__).parent.parent / "data" / "refined_graph.json"
    path = Path(path)
    if not path.exists():
        logger.warning(f"Refined graph not found at {path}")
        return {"entities": [], "relationships": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_graph_statistics(graph: Dict = None) -> Dict:
    """Compute comprehensive graph statistics."""
    if graph is None:
        graph = load_refined_graph()

    entities = graph.get("entities", [])
    relationships = graph.get("relationships", [])

    stats = {}

    # Entity type distribution
    entity_types = {}
    for e in entities:
        etype = e.get("type", e.get("entity_type", "Unknown"))
        entity_types[etype] = entity_types.get(etype, 0) + 1

    # Relationship type distribution
    rel_types = {}
    for r in relationships:
        rtype = r.get("type", r.get("relationship_type", r.get("relation", "Unknown")))
        rel_types[rtype] = rel_types.get(rtype, 0) + 1

    # Build adjacency for degree computation
    adj = {}
    for r in relationships:
        source = r.get("source", r.get("source_id", ""))
        target = r.get("target", r.get("target_id", ""))
        for node in [source, target]:
            if node:
                adj.setdefault(node, set())
        if source and target:
            adj[source].add(target)
            adj[target].add(source)

    degrees = [len(neighbors) for neighbors in adj.values()]
    avg_degree = sum(degrees) / len(degrees) if degrees else 0.0
    max_degree = max(degrees) if degrees else 0

    # Node degree distribution
    degree_dist = {}
    for d in degrees:
        degree_dist[d] = degree_dist.get(d, 0) + 1

    # Graph density
    n = len(entities)
    m = len(relationships)
    max_possible = n * (n - 1) / 2 if n > 1 else 1
    density = m / max_possible if max_possible > 0 else 0.0

    # Connected components (simple union-find)
    parent = {}
    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x
    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for r in relationships:
        src = r.get("source", r.get("source_id", ""))
        tgt = r.get("target", r.get("target_id", ""))
        if src and tgt:
            parent.setdefault(src, src)
            parent.setdefault(tgt, tgt)
            union(src, tgt)

    components = {}
    for node in parent:
        root = find(node)
        components.setdefault(root, set()).add(node)

    component_sizes = [len(c) for c in components.values()]
    num_components = len(components)
    largest_component = max(component_sizes) if component_sizes else 0

    # Entity confidence statistics
    confidences = [e.get("confidence", 1.0) for e in entities if "confidence" in e]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 1.0

    # Top connected entities
    entity_degrees = {}
    for e in entities:
        eid = e.get("id", e.get("name", ""))
        if eid in adj:
            entity_degrees[e.get("name", eid)] = len(adj[eid])

    top_connected = sorted(entity_degrees.items(), key=lambda x: -x[1])[:10]

    # Entity frequency statistics
    entity_name_counts = {}
    for e in entities:
        name = e.get("name", e.get("canonical_name", "Unknown"))
        entity_name_counts[name] = entity_name_counts.get(name, 0) + 1

    # Relationship frequency statistics
    rel_name_counts = {}
    for r in relationships:
        rtype = r.get("type", r.get("relationship_type", r.get("relation", "Unknown")))
        rel_name_counts[rtype] = rel_name_counts.get(rtype, 0) + 1

    stats = {
        "total_unique_entities": len(entities),
        "total_unique_relationships": len(relationships),
        "entity_type_distribution": dict(sorted(entity_types.items(), key=lambda x: -x[1])),
        "relationship_type_distribution": dict(sorted(rel_types.items(), key=lambda x: -x[1])),
        "average_node_degree": round(avg_degree, 3),
        "max_node_degree": max_degree,
        "top_connected_entities": top_connected,
        "graph_density": round(density, 6),
        "num_connected_components": num_components,
        "largest_component_size": largest_component,
        "average_confidence": round(avg_confidence, 3),
        "degree_distribution": dict(sorted(degree_dist.items())),
        "entity_frequency": dict(sorted(entity_name_counts.items(), key=lambda x: -x[1])[:20]),
        "relationship_frequency": dict(sorted(rel_name_counts.items(), key=lambda x: -x[1])),
    }

    return stats


def print_graph_stats(stats: Dict):
    """Pretty-print graph statistics."""
    print("=" * 60)
    print("KNOWLEDGE GRAPH QUALITY REPORT")
    print("=" * 60)
    print(f"  Total Unique Entities   : {stats['total_unique_entities']}")
    print(f"  Total Unique Rels       : {stats['total_unique_relationships']}")
    print(f"  Average Node Degree     : {stats['average_node_degree']}")
    print(f"  Max Node Degree         : {stats['max_node_degree']}")
    print(f"  Graph Density           : {stats['graph_density']}")
    print(f"  Connected Components    : {stats['num_connected_components']}")
    print(f"  Largest Component       : {stats['largest_component_size']}")
    print(f"  Average Confidence      : {stats['average_confidence']}")
    print()
    print("  Top Entity Types:")
    for etype, count in list(stats['entity_type_distribution'].items())[:10]:
        print(f"    {etype}: {count}")
    print()
    print("  Top Relationship Types:")
    for rtype, count in list(stats['relationship_type_distribution'].items())[:10]:
        print(f"    {rtype}: {count}")
    print()
    print("  Top Connected Entities:")
    for name, degree in stats['top_connected_entities'][:5]:
        print(f"    {name}: {degree} connections")
    print("=" * 60)


if __name__ == "__main__":
    stats = compute_graph_statistics()
    print_graph_stats(stats)
