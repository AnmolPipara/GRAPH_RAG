"""
rebuild_graph_v2.py — Rebuild the knowledge graph with corrected page provenance.

CONSTRUCTION ABLATION: re-attributes every cached extraction's source_pages to
the FULL chunk page range (fixing the construction bug where only page_start was
stamped), re-runs the deterministic refinement, and reloads Neo4j. ZERO LLM
calls, no re-extraction, no retrieval/evaluator/prompt/model changes.

Stages (deterministic, mirrors the fixed pipeline):
  1. Reconstruct full_text from data/extracted_text.json (as pdf_extractor does).
  2. Run the FIXED chunker (position-based page ranges, no collapse to page 1).
     Boundaries are verified identical to data/chunks.json (char_count match).
  3. Load data/raw_extractions.json (35 cached extraction results).
  4. For each extraction result, re-stamp every entity/relationship source_pages
     with list(range(chunk.page_start, chunk.page_end + 1)).
  5. Re-run graph_refiner.refine_graph(use_llm=False) — deterministic merge.
  6. Snapshot BEFORE statistics from the never-overwritten v1 artifact
     (data/refined_graph.json), so re-runs can never corrupt the comparison.
  7. Load the corrected graph into Neo4j (clears + reloads, same schema/loader).
  8. Snapshot AFTER statistics from the in-memory v2 graph + post-load topology.

Outputs:
  data/refined_graph_v2_construction.json   (corrected refined graph)
  experiments/construction_stats_before.json
  experiments/construction_stats_after.json
"""

import json
import logging
import sys
from collections import Counter
from pathlib import Path

logging.disable(logging.CRITICAL)

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402
from graph_rag.chunker import chunk_by_sections  # noqa: E402
from graph_rag.knowledge_extractor import ExtractionResult  # noqa: E402
from graph_rag.graph_refiner import refine_graph  # noqa: E402
from utils.neo4j_loader import Neo4jLoader  # noqa: E402


def load_json(rel):
    with open(ROOT / rel, encoding="utf-8") as f:
        return json.load(f)


def build_full_text(page_texts):
    parts = [f"[PAGE {r['page']}]\n{r['text']}" for r in page_texts if r["text"]]
    return "\n\n".join(parts)


def stats_from_artifact(entities, relationships):
    """Per-page attribution stats derived from a refined-graph artifact.

    Deterministic and immune to Neo4j's mutable state, so before/after
    comparisons survive any number of rebuild re-runs.
    """
    nodes_per_page = Counter()
    for e in entities:
        for p in (e.get("source_pages") or []):
            nodes_per_page[int(p)] += 1
    rels_per_page = Counter()
    for r in relationships:
        for p in (r.get("source_pages") or []):
            rels_per_page[int(p)] += 1
    return {
        "total_nodes_artifact": len(entities),
        "total_rels_artifact": len(relationships),
        "pages_linked": len(nodes_per_page),
        "nodes_per_page": dict(sorted(nodes_per_page.items())),
        "rels_per_page": dict(sorted(rels_per_page.items())),
    }


def probe_neo4j_topology():
    """Graph-level topology counts from the live graph (node/rel/isolated counts).

    The construction fix changes ONLY page attribution, so topology (total nodes,
    total relationships, isolated nodes, empty source_pages) is identical before
    and after — read once from the live graph for both.
    """
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_username, settings.neo4j_password)
    )
    try:
        with driver.session() as s:
            return {
                "total_nodes": s.run("MATCH (n:Entity) RETURN count(n) AS c").single()["c"],
                "total_rels": s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"],
                "isolated_nodes": s.run(
                    "MATCH (n:Entity) WHERE NOT (n)--() RETURN count(n) AS c").single()["c"],
                "empty_source_pages": s.run(
                    "MATCH (n:Entity) WHERE n.source_pages IS NULL OR size(n.source_pages)=0 "
                    "RETURN count(n) AS c").single()["c"],
            }
    finally:
        driver.close()


def main():
    # ── 1. Reconstruct + chunk with the FIXED chunker ────────────────────
    et = load_json("data/extracted_text.json")
    chunks_saved = load_json("data/chunks.json")
    full_text = build_full_text(et)
    chunks = chunk_by_sections(full_text)

    assert len(chunks) == len(chunks_saved), f"chunk count changed: {len(chunks)} vs {len(chunks_saved)}"
    boundary_mismatch = sum(
        1 for c, s in zip(chunks, chunks_saved) if c.char_count != s["char_count"]
    )
    assert boundary_mismatch == 0, f"chunk boundaries changed: {boundary_mismatch} mismatches"
    print(f"Chunking reproduced: {len(chunks)} chunks, {boundary_mismatch} boundary mismatches")

    chunk_ranges = {c.chunk_id: (c.page_start, c.page_end) for c in chunks}

    # ── 2. Re-attribute cached extractions to full chunk ranges ─────────
    raw = load_json("data/raw_extractions.json")
    assert len(raw["extractions"]) == len(chunks), \
        f"extraction results {len(raw['extractions'])} != chunks {len(chunks)}"
    results = []
    for r in raw["extractions"]:
        ents, rels = r.get("entities", []), r.get("relationships", [])
        # chunk_id from the first entity OR relationship's source_chunks (results
        # are chunk-ordered; entities always present in this corpus, but checking
        # relationships too makes the guard airtight for entity-less results).
        cid = None
        for e in ents + rels:
            sc = e.get("source_chunks") or []
            if sc and sc[0] >= 0:
                cid = sc[0]
                break
        if cid is None or cid not in chunk_ranges:
            # Image extractions carry chunk_id=-1 with their own single-page
            # attribution ([page_num]) — that attribution is already correct, so
            # keep it. (Also catches any text result whose cid lookup failed.)
            results.append(ExtractionResult(entities=ents, relationships=rels))
            continue
        ps, pe = chunk_ranges[cid]
        pages = list(range(ps, pe + 1))
        for e in ents:
            e["source_pages"] = pages
            e["source_chunks"] = [cid]
        for rel in rels:
            rel["source_pages"] = pages
            rel["source_chunks"] = [cid]
        results.append(ExtractionResult(entities=ents, relationships=rels))

    # ── 3. Deterministic refinement (no LLM) ────────────────────────────
    merged = refine_graph(results, use_llm=False)
    print(f"Refined graph: {len(merged.entities)} entities, {len(merged.relationships)} relationships")

    # corrected page coverage
    ent_pages = Counter()
    for e in merged.entities:
        for p in (e.source_pages or []):
            ent_pages[p] += 1
    print(f"Distinct pages in corrected entity source_pages: {len(ent_pages)}/61")

    # ── 4. Before stats (from the v1 artifact — deterministic, re-run safe) ─
    # The v1 artifact data/refined_graph.json is NEVER overwritten by this
    # script, so deriving "before" from it is correct on every run (unlike
    # snapshotting the live graph, which the first load already replaced).
    print("Capturing BEFORE construction statistics (from v1 artifact)...")
    v1_artifact = load_json("data/refined_graph.json")
    topology = probe_neo4j_topology()
    before = {**stats_from_artifact(v1_artifact.get("entities", []),
                                    v1_artifact.get("relationships", [])), **topology}
    (ROOT / "experiments" / "construction_stats_before.json").write_text(
        json.dumps(before, indent=2), encoding="utf-8")

    # ── 5. Load corrected graph into Neo4j (clear + reload, same loader) ─
    print("Loading corrected graph into Neo4j (clears current graph)...")
    loader = Neo4jLoader(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password)
    try:
        loader.load_all(merged, settings.ENTITY_TYPES)
        loader.validate()
    finally:
        loader.close()

    # ── 6. After stats (from the in-memory v2 graph, identical to the v2
    #    artifact persisted in step 7, + LIVE topology re-probed post-load) ─
    # The topology is re-probed AFTER load_all so the self-validation assert
    # checks the actual post-load state, not the pre-load count.
    after_topology = probe_neo4j_topology()
    after = {**stats_from_artifact(
        [e.model_dump() for e in merged.entities],
        [r.model_dump() for r in merged.relationships]), **after_topology}
    assert after["total_nodes"] == len(merged.entities), \
        f"Neo4j nodes {after['total_nodes']} != merged entities {len(merged.entities)}"
    assert after["total_rels"] == topology["total_rels"], \
        f"Neo4j rels {after['total_rels']} changed vs pre-load {topology['total_rels']} (topology should be invariant)"
    (ROOT / "experiments" / "construction_stats_after.json").write_text(
        json.dumps(after, indent=2), encoding="utf-8")

    # ── 7. Save corrected refined graph for reproducibility ─────────────
    (ROOT / "data" / "refined_graph_v2_construction.json").write_text(
        json.dumps(merged.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Report ──────────────────────────────────────────────────────────
    print("\n=== CONSTRUCTION STATS: BEFORE vs AFTER ===")
    for k in ("total_nodes", "total_rels", "isolated_nodes", "empty_source_pages", "pages_linked"):
        print(f"  {k:22s}: {before[k]} -> {after[k]}")
    print("  pages_linked_detail:")
    print(f"    before: {sorted(before['nodes_per_page'].keys())}")
    print(f"    after : {sorted(after['nodes_per_page'].keys())}")
    print("  node distribution top 8 pages:")
    print(f"    before: {sorted(before['nodes_per_page'].items(), key=lambda x: -x[1])[:8]}")
    print(f"    after : {sorted(after['nodes_per_page'].items(), key=lambda x: -x[1])[:8]}")


if __name__ == "__main__":
    main()
