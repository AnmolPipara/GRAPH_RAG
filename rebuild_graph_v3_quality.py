"""
rebuild_graph_v3_quality.py — PRIORITY 1 graph-quality ablation: entity dedup.

Isolated, deterministic, ZERO-LLM graph-construction fix on top of the v2
construction-fixed graph (data/refined_graph_v2_construction.json):

  1. MERGE DUPLICATE ENTITIES — entities with the same normalized canonical
     name but different IDs (the extractor emitted one concept under several
     type-guesses: "Group Header" as BusinessComponent AND XMLElement, etc.)
     are collapsed into a single survivor node that unions aliases,
     source_pages, source_chunks, evidence, frequency, and attributes.
     Exact-name merging is unambiguous (same name = same concept); the
     semantic alias pairs (Seller<->Creditor, Payer<->Debtor) are NOT merged
     here to keep the ablation conservative and attributable.

  2. REWIRE RELATIONSHIPS — every relationship endpoint that pointed at a
     merged-away ID is re-pointed at the survivor ID; collapsed duplicates
     (same source/relation/target) are merged and self-loops dropped.

  3. RESOLVE DANGLING ENDPOINTS — the 42 `-cross-chunk` IDs the refiner
     failed to resolve (53 rels silently dropped by the loader) are matched
     against entity canonical names by alphanumeric collapse where possible;
     rels with unresolvable endpoints are dropped explicitly so the artifact
     and the database agree.

Retrieval, ranking, prompts, evaluator, QA model, benchmark questions, and
temperature are NOT touched (verified by git diff of the retrieval code).

Outputs:
  data/refined_graph_v3_quality.json      (deduped graph artifact)
  experiments/quality_stats_before.json   (v2 baseline statistics)
  experiments/quality_stats_after.json    (v3 deduped statistics)
  experiments/quality_merge_log.json      (merge groups + rewiring decisions)
"""

import json
import logging
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

logging.disable(logging.CRITICAL)

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402
from utils.neo4j_loader import Neo4jLoader  # noqa: E402

V2_ARTIFACT = ROOT / "data" / "refined_graph_v2_construction.json"
V3_ARTIFACT = ROOT / "data" / "refined_graph_v3_quality.json"
BEFORE_STATS = ROOT / "experiments" / "quality_stats_before.json"
AFTER_STATS = ROOT / "experiments" / "quality_stats_after.json"
MERGE_LOG = ROOT / "experiments" / "quality_merge_log.json"


# ── Normalization helpers ─────────────────────────────────────────────

def norm(s: str) -> str:
    """Case/punct-insensitive key (for duplicate grouping)."""
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def alnum(s: str) -> str:
    """Alphanumeric collapse (for cross-chunk endpoint resolution)."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def stats(entities, relationships):
    """Graph-quality statistics for a merged entity/relationship pair."""
    ids = {e["id"] for e in entities}
    out_deg = Counter(); in_deg = Counter()
    rel_by_type = Counter()
    for r in relationships:
        out_deg[r["source"]] += 1
        in_deg[r["target"]] += 1
        rel_by_type[r["relation"]] += 1
    total_deg = {i: out_deg[i] + in_deg[i] for i in ids}
    # WCC (undirected)
    parent = {i: i for i in ids}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    for r in relationships:
        if r["source"] in parent and r["target"] in parent:
            union(r["source"], r["target"])
    comp = defaultdict(list)
    for i in ids:
        comp[find(i)].append(i)
    sizes = sorted((len(v) for v in comp.values()), reverse=True)
    # duplicates
    by_name = defaultdict(list)
    for e in entities:
        by_name[norm(e["canonical_name"])].append(e)
    dup_groups = [v for v in by_name.values() if len(v) > 1]
    # benchmark reach: pages reachable from entities matching each question
    bench = json.loads((ROOT / "experiments" / "benchmark_v2.json").read_text(encoding="utf-8"))
    reach = []
    for q in bench:
        toks = set(norm(q["question"]).split())
        toks = {t for t in toks if len(t) > 2}
        pages = set()
        matched = 0
        for e in entities:
            name_toks = set(norm(e["canonical_name"]).split())
            alias_toks = set(norm(" ".join(e.get("aliases") or [])).split())
            if toks & (name_toks | alias_toks):
                matched += 1
                pages.update(e.get("source_pages") or [])
        reach.append({"id": q["id"], "matched": matched,
                      "reachable_pages": sorted(pages),
                      "n_pages": len(pages),
                      "gt_page": q.get("evidence_page")})
    return {
        "entities": len(entities),
        "relationships": len(relationships),
        "isolated_nodes": sum(1 for d in total_deg.values() if d == 0),
        "mean_degree": round(sum(total_deg.values()) / len(total_deg), 3) if total_deg else 0.0,
        "max_degree": max(total_deg.values()) if total_deg else 0,
        "wcc_count": len(comp),
        "largest_wcc": sizes[0] if sizes else 0,
        "dup_groups": len(dup_groups),
        "dup_entities": sum(len(v) for v in dup_groups),
        "pages_linked": len({p for e in entities for p in (e.get("source_pages") or [])}),
        "n_with_alias": sum(1 for e in entities if e.get("aliases")),
        "n_with_desc": sum(1 for e in entities if (e.get("description") or "").strip()),
        "benchmark_reach": reach,
    }


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ── Merge logic ───────────────────────────────────────────────────────

def pick_survivor(group):
    """Deterministic survivor: max frequency, then longest description.
    (IDs are unique per group by construction; frequency is the extraction
    count so the most-extracted fragment wins, with description length as a
    stable tie-break.)"""
    return max(
        group, key=lambda e: (e.get("frequency", 1), len(e.get("description") or ""))
    )["id"]


def merge_entities(entities):
    """Merge entities sharing a normalized canonical name.

    Returns (merged_entities, old_id -> survivor_id map, merge_groups).
    """
    groups = defaultdict(list)
    for e in entities:
        groups[norm(e["canonical_name"])].append(e)

    merged = []
    id_map = {}
    merge_groups = []
    for name, group in groups.items():
        if len(group) == 1:
            merged.append(group[0])
            id_map[group[0]["id"]] = group[0]["id"]
            continue
        survivor_id = pick_survivor(group)
        survivor = next(e for e in group if e["id"] == survivor_id)
        for e in group:
            id_map[e["id"]] = survivor_id
        merge_groups.append({
            "canonical_name": survivor["canonical_name"],
            "survivor": survivor_id,
            "merged": [{"id": e["id"], "type": e["type"],
                        "pages": sorted(set(e.get("source_pages") or [])),
                        "freq": e.get("frequency", 1)} for e in group],
        })
        # Union fields into survivor
        aliases = []
        for e in group:
            for a in (e.get("aliases") or []):
                if a and a not in aliases:
                    aliases.append(a)
        survivor["aliases"] = aliases
        survivor["source_pages"] = sorted(set(
            p for e in group for p in (e.get("source_pages") or [])))
        survivor["source_chunks"] = sorted(set(
            c for e in group for c in (e.get("source_chunks") or [])))
        survivor["frequency"] = sum(e.get("frequency", 1) for e in group)
        survivor["confidence"] = max(e.get("confidence", 0.0) for e in group)
        descs = sorted({e.get("description", "") for e in group if e.get("description")},
                       key=len, reverse=True)
        if descs:
            survivor["description"] = descs[0]
        ev = [e.get("evidence", "") for e in group if e.get("evidence")]
        survivor["evidence"] = "\n".join(dict.fromkeys(ev)) if ev else survivor.get("evidence")
        attrs = {}
        for e in sorted(group, key=lambda x: x["id"]):
            attrs.update(e.get("attributes") or {})
        survivor["attributes"] = attrs
        merged.append(survivor)
    return merged, id_map, merge_groups


def rewire_relationships(relationships, id_map, entities):
    """Re-point merged-away endpoints at survivors, resolve dangling
    cross-chunk IDs via alnum collapse, drop unresolvable rels and self-loops,
    and merge collapsed duplicates. Returns (rewired_rels, dropped, resolved)."""
    ids = {e["id"] for e in entities}
    alnum_to_ids = defaultdict(list)
    for e in entities:
        alnum_to_ids[alnum(e["canonical_name"])].append(e["id"])

    rewired = []
    dropped = {"unresolvable": 0, "self_loop": 0, "duplicate": 0}
    resolved = []

    for r in relationships:
        src = id_map.get(r["source"], r["source"])
        tgt = id_map.get(r["target"], r["target"])
        if src not in ids:
            cands = alnum_to_ids.get(alnum(src.replace("-cross-chunk", "")), [])
            if cands:
                new_id = sorted(cands)[0]
                resolved.append({"old": r["source"], "new": new_id,
                                 "relation": r["relation"]})
                src = new_id
            else:
                dropped["unresolvable"] += 1
                continue
        if tgt not in ids:
            cands = alnum_to_ids.get(alnum(tgt.replace("-cross-chunk", "")), [])
            if cands:
                new_id = sorted(cands)[0]
                resolved.append({"old": r["target"], "new": new_id,
                                 "relation": r["relation"]})
                tgt = new_id
            else:
                dropped["unresolvable"] += 1
                continue
        if src == tgt:
            dropped["self_loop"] += 1
            continue
        r["source"], r["target"] = src, tgt
        rewired.append(r)

    # Merge collapsed duplicates (same source/relation/target)
    by_key = {}
    for r in rewired:
        key = (r["source"], r["relation"], r["target"])
        if key in by_key:
            prev = by_key[key]
            prev["source_pages"] = sorted(set(
                (prev.get("source_pages") or []) + (r.get("source_pages") or [])))
            prev["source_chunks"] = sorted(set(
                (prev.get("source_chunks") or []) + (r.get("source_chunks") or [])))
            prev["frequency"] = prev.get("frequency", 1) + r.get("frequency", 1)
            prev["confidence"] = max(prev.get("confidence", 0.0), r.get("confidence", 0.0))
            if len(r.get("description", "")) > len(prev.get("description", "")):
                prev["description"] = r["description"]
            # Preserve provenance: concatenate evidence (like graph_refiner).
            if r.get("evidence") and r["evidence"] not in (prev.get("evidence") or ""):
                if prev.get("evidence"):
                    prev["evidence"] += "\n" + r["evidence"]
                else:
                    prev["evidence"] = r["evidence"]
            dropped["duplicate"] += 1
        else:
            by_key[key] = r
    return list(by_key.values()), dropped, resolved


# ── Main ──────────────────────────────────────────────────────────────

def main():
    v2 = load_json(V2_ARTIFACT)
    v2_entities = v2["entities"]
    v2_rels = v2["relationships"]

    before = stats(v2_entities, v2_rels)
    BEFORE_STATS.parent.mkdir(parents=True, exist_ok=True)
    BEFORE_STATS.write_text(json.dumps(before, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"BEFORE: {before['entities']} entities, {before['relationships']} rels, "
          f"{before['isolated_nodes']} isolated, {before['dup_groups']} dup groups")

    merged_entities, id_map, merge_groups = merge_entities(v2_entities)
    merged_rels, dropped, resolved = rewire_relationships(v2_rels, id_map, merged_entities)

    after = stats(merged_entities, merged_rels)
    AFTER_STATS.write_text(json.dumps(after, indent=2, ensure_ascii=False), encoding="utf-8")

    log = {
        "entities_before": len(v2_entities),
        "entities_after": len(merged_entities),
        "rels_before": len(v2_rels),
        "rels_after": len(merged_rels),
        "merge_groups": merge_groups,
        "dropped": dropped,
        "resolved_dangling": resolved,
    }
    MERGE_LOG.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"AFTER : {after['entities']} entities, {after['relationships']} rels, "
          f"{after['isolated_nodes']} isolated, {after['dup_groups']} dup groups")
    print(f"MERGED: {len(v2_entities) - len(merged_entities)} entities, "
          f"{len(v2_rels) - len(merged_rels)} rels net change")
    print(f"DROPPED: {dropped}  RESOLVED: {len(resolved)} dangling endpoints")

    # ── Persist v3 artifact ───────────────────────────────────────────
    v3 = {"entities": merged_entities, "relationships": merged_rels}
    V3_ARTIFACT.write_text(json.dumps(v3, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Load into Neo4j (same loader, same schema) ────────────────────
    print("Loading deduped graph into Neo4j (clears current graph)...")
    loader = Neo4jLoader(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password)
    try:
        from graph_rag.knowledge_extractor import ExtractionResult
        result = ExtractionResult(entities=merged_entities, relationships=merged_rels)
        loader.load_all(result, settings.ENTITY_TYPES)
        loader.validate()
    finally:
        loader.close()

    # ── Post-load topology assert (the bug class we are fixing: the loader
    #    silently dropped 53 rels before; the deduped graph must load 100%) ─
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(settings.neo4j_uri,
                                  auth=(settings.neo4j_username, settings.neo4j_password))
    try:
        with driver.session() as s:
            live_nodes = s.run("MATCH (n:Entity) RETURN count(n) AS c").single()["c"]
            live_rels = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    finally:
        driver.close()
    assert live_nodes == len(merged_entities), \
        f"Neo4j nodes {live_nodes} != merged entities {len(merged_entities)}"
    assert live_rels == len(merged_rels), \
        f"Neo4j rels {live_rels} != merged rels {len(merged_rels)} (loader dropped some!)"
    print(f"Post-load assert OK: {live_nodes} nodes, {live_rels} rels (100% loaded)")

    # ── Report ────────────────────────────────────────────────────────
    print("\n=== GRAPH-QUALITY STATS: BEFORE (v2) vs AFTER (v3) ===")
    for k in ("entities", "relationships", "isolated_nodes", "mean_degree",
              "max_degree", "wcc_count", "largest_wcc", "dup_groups",
              "dup_entities", "pages_linked", "n_with_alias", "n_with_desc"):
        print(f"  {k:16s}: {before[k]} -> {after[k]}")
    print("\nBenchmark entity reach (pages reachable from matched entities):")
    for b, a in zip(before["benchmark_reach"], after["benchmark_reach"]):
        gt = a["gt_page"]
        hit_b = "Y" if gt in b["reachable_pages"] else "N"
        hit_a = "Y" if gt in a["reachable_pages"] else "N"
        print(f"  Q{a['id']:<3} matched {b['matched']:>3}->{a['matched']:<3} "
              f"pages {b['n_pages']:>2}->{a['n_pages']:<2} "
              f"GT-page({gt:>2}) {hit_b}->{hit_a}")


if __name__ == "__main__":
    main()
