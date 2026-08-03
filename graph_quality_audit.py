"""
graph_quality_audit.py — PRIORITY 1 offline graph-quality audit (ZERO LLM calls).

Reads the v2 graph artifact (data/refined_graph_v2_construction.json) and
quantifies graph-quality dimensions that plausibly affect retrieval:

  - node/relationship totals, degree distribution (in/out/total)
  - isolated nodes (degree 0) and near-isolated (degree 1)
  - weakly-connected components (WCC) sizes
  - duplicate-entity candidates (identical / near-identical names with
    different IDs, and name-vs-alias collisions)
  - alias coverage, description coverage
  - relationship-type sparsity and entity-type distribution
  - bidirectional duplicate pairs (A-[R]->B and B-[S]->A where R,S are
    semantically identical inverse types) — direction-quality signal
  - per-benchmark-question entity hit-rate + hit-degree (retrieval reach)

Outputs:
  experiments/graph_quality_stats.json  (machine-readable)
  experiments/graph_quality_audit.md    (paper-ready audit section)

No network calls, no LLM calls, read-only on the artifact.
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARTIFACT = ROOT / "data" / "refined_graph_v2_construction.json"
BENCHMARK = ROOT / "experiments" / "benchmark_v2.json"
STATS_OUT = ROOT / "experiments" / "graph_quality_stats.json"
MD_OUT = ROOT / "experiments" / "graph_quality_audit.md"

# Inverse type pairs whose coexistence (A-[R]->B AND B-[S]->A) is legitimate
# (the graph intentionally stores both directions). Pairs NOT in this set are
# flagged as possible direction mistakes or redundant duplicates.
INVERSE_PAIRS = {
    ("CREATED", "CREATED_BY"),
    ("OWNS", "OWNED_BY"),
    ("PUBLISHES", "PUBLISHED_BY"),
    ("DEVELOPS", "DEVELOPED_BY"),
    ("USES", "USED_BY"),
    ("IMPLEMENTS", "IMPLEMENTED_BY"),
    ("SUPPORTS", "SUPPORTED_BY"),
    ("ENABLES", "ENABLED_BY"),
    ("PROVIDES", "PROVIDED_BY"),
    ("REQUIRES", "REQUIRED_BY"),
    ("REGULATES", "REGULATED_BY"),
    ("VALIDATES", "APPROVED_BY"),
    ("HAS_VERSION", "VERSION_OF"),
    ("REPLACES", "REPLACED_BY"),
    ("PRECEDED_BY", "SUCCEEDS"),
    ("BASED_ON", "DERIVED_FROM"),
    ("COVERS", "COVERED_BY"),
    ("APPLIES_TO", "APPLIED_BY"),
    ("CONTAINS", "PART_OF"),
    ("HAS_COMPONENT", "PART_OF"),
}


def norm(s: str) -> str:
    """Case/punct-normalized key for duplicate detection."""
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    entities = art.get("entities", [])
    relationships = art.get("relationships", [])

    eid2e = {e["id"]: e for e in entities}
    out_deg = Counter()
    in_deg = Counter()
    rel_by_type = Counter()
    bidirectional = []          # (A, R, B, S) where both directions exist

    for r in relationships:
        src, tgt, rel = r["source"], r["target"], r["relation"]
        out_deg[src] += 1
        in_deg[tgt] += 1
        rel_by_type[rel] += 1

    reverse_map = defaultdict(list)
    for r in relationships:
        reverse_map[(r["target"], r["source"])].append(r["relation"])

    for r in relationships:
        src, tgt, rel = r["source"], r["target"], r["relation"]
        for other_rel in reverse_map.get((src, tgt), []):
            pair = (rel, other_rel)
            if pair not in INVERSE_PAIRS and (pair[1], pair[0]) not in INVERSE_PAIRS:
                bidirectional.append({
                    "source": eid2e.get(src, {}).get("canonical_name", src),
                    "target": eid2e.get(tgt, {}).get("canonical_name", tgt),
                    "forward": rel,
                    "reverse": other_rel,
                })

    # Dedupe: each undirected pair is emitted once per direction with swapped
    # roles; count each pair only once so the anomaly count is not 2x inflated.
    seen_bidir = set()
    bidir_unique = []
    for b in bidirectional:
        key = frozenset([(b["source"], b["forward"]), (b["target"], b["reverse"])])
        if key in seen_bidir:
            continue
        seen_bidir.add(key)
        bidir_unique.append(b)
    bidirectional = bidir_unique

    all_ids = set(eid2e)
    total_deg = {i: out_deg[i] + in_deg[i] for i in all_ids}
    isolated = [i for i in all_ids if total_deg[i] == 0]
    near_isolated = [i for i in all_ids if total_deg[i] == 1]
    deg_hist = Counter(total_deg.values())

    # ── WCC (undirected) via union-find ────────────────────────────────
    parent = {i: i for i in all_ids}

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
    for i in all_ids:
        comp[find(i)].append(i)
    wcc_sizes = sorted((len(v) for v in comp.values()), reverse=True)

    # ── Duplicate candidates ───────────────────────────────────────────
    by_norm_name = defaultdict(list)
    for e in entities:
        by_norm_name[norm(e["canonical_name"])].append(e)
    exact_dup_groups = [v for v in by_norm_name.values() if len(v) > 1]

    # name-vs-alias collisions: entity A's name equals entity B's alias or
    # canonical name (B not merged into A during extraction)
    alias_collisions = []
    alias_lookup = {}
    for e in entities:
        for a in (e.get("aliases") or []):
            alias_lookup.setdefault(norm(a), []).append(e)
    seen_pairs = set()
    for e in entities:
        n = norm(e["canonical_name"])
        for other in by_norm_name.get(n, []):
            pass  # handled above
        for other in alias_lookup.get(n, []):
            if other["id"] != e["id"]:
                key = tuple(sorted([e["id"], other["id"]]))
                if key not in seen_pairs:
                    seen_pairs.add(key)
                    alias_collisions.append({
                        "entity": e["canonical_name"],
                        "alias_source": other["canonical_name"],
                    })

    # ── Coverage ───────────────────────────────────────────────────────
    with_alias = sum(1 for e in entities if e.get("aliases"))
    with_desc = sum(1 for e in entities if (e.get("description") or "").strip())
    no_desc = [e["canonical_name"] for e in entities if not (e.get("description") or "").strip()]

    # ── Per-type stats ─────────────────────────────────────────────────
    type_nodes = Counter(e.get("type", "Concept") for e in entities)
    type_rels = Counter()
    for r in relationships:
        type_rels[eid2e.get(r["source"], {}).get("type", "?")] += 1

    # ── Benchmark entity hit-rate ──────────────────────────────────────
    benchmark = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    hits = []
    for q in benchmark:
        qn = norm(q["question"])
        toks = set(qn.split())
        toks = {t for t in toks if len(t) > 2}
        matched = []
        for e in entities:
            name_toks = set(norm(e["canonical_name"]).split())
            alias_toks = set(norm(" ".join(e.get("aliases") or [])).split())
            if toks & (name_toks | alias_toks):
                matched.append(e)
        hits.append({
            "id": q["id"],
            "category": q["category"],
            "question": q["question"],
            "n_matched": len(matched),
            "matched": [(m["canonical_name"], total_deg.get(m["id"], 0)) for m in matched[:6]],
        })

    # ── Assemble stats ─────────────────────────────────────────────────
    stats = {
        "totals": {
            "entities": len(entities),
            "relationships": len(relationships),
            "entities_with_relationship_endpoint": len(set(out_deg) | set(in_deg)),
        },
        "degree": {
            "histogram": dict(sorted(deg_hist.items())),
            "max_total_degree": max(total_deg.values()) if total_deg else 0,
            "mean_total_degree": round(sum(total_deg.values()) / len(total_deg), 3) if total_deg else 0.0,
            "n_degree_0": len(isolated),
            "n_degree_1": len(near_isolated),
        },
        "wcc": {
            "n_components": len(comp),
            "largest_component": wcc_sizes[0] if wcc_sizes else 0,
            "n_singleton_components": sum(1 for s in wcc_sizes if s == 1),
            "component_sizes_top10": wcc_sizes[:10],
        },
        "duplicates": {
            "exact_name_groups": len(exact_dup_groups),
            "entities_in_dup_groups": sum(len(v) for v in exact_dup_groups),
            "name_vs_alias_collisions": len(alias_collisions),
            "sample_exact": [ [e["canonical_name"] for e in g][:5] for g in exact_dup_groups[:8] ],
            "sample_alias_collisions": alias_collisions[:10],
        },
        "coverage": {
            "n_with_alias": with_alias,
            "alias_coverage": round(with_alias / len(entities), 4) if entities else 0.0,
            "n_with_description": with_desc,
            "description_coverage": round(with_desc / len(entities), 4) if entities else 0.0,
            "n_without_description": len(no_desc),
        },
        "sparsity": {
            "relationship_types": len(rel_by_type),
            "rel_type_top15": rel_by_type.most_common(15),
            "entity_type_nodes_top10": type_nodes.most_common(10),
            "entity_type_rels_top10": type_rels.most_common(10),
            "bidirectional_anomaly_pairs": len(bidirectional),
            "bidirectional_sample": bidirectional[:12],
        },
        "benchmark_hits": hits,
    }

    STATS_OUT.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {STATS_OUT.name}")

    # ── Markdown report ────────────────────────────────────────────────
    L = []
    L.append("# Graph Quality Audit — GraphRAG v2 (construction-fixed graph)")
    L.append("")
    L.append("> Offline audit of `data/refined_graph_v2_construction.json`. Zero LLM calls, "
             "read-only, deterministic.")
    L.append("")
    L.append("## 1. Totals")
    L.append("")
    L.append(f"- Entities: **{stats['totals']['entities']}**")
    L.append(f"- Relationships: **{stats['totals']['relationships']}**")
    L.append(f"- Entities with ≥1 relationship endpoint: **{stats['totals']['entities_with_relationship_endpoint']}**")
    L.append("")
    L.append("## 2. Degree distribution")
    L.append("")
    L.append(f"- Mean total degree: **{stats['degree']['mean_total_degree']}**; "
             f"max: **{stats['degree']['max_total_degree']}**")
    L.append(f"- Isolated nodes (degree 0): **{stats['degree']['n_degree_0']}** "
             f"({round(100*stats['degree']['n_degree_0']/stats['totals']['entities'],1)}%)")
    L.append(f"- Near-isolated (degree 1): **{stats['degree']['n_degree_1']}**")
    L.append("")
    L.append("| Total degree | Nodes |")
    L.append("|---|---|")
    for d, c in sorted(deg_hist.items()):
        if d <= 12 or d == stats['degree']['max_total_degree']:
            L.append(f"| {d} | {c} |")
    L.append("")
    L.append("## 3. Weakly-connected components")
    L.append("")
    L.append(f"- Components: **{stats['wcc']['n_components']}**; "
             f"largest: **{stats['wcc']['largest_component']}**; "
             f"singletons: **{stats['wcc']['n_singleton_components']}**")
    L.append(f"- Component sizes (top 10): {stats['wcc']['component_sizes_top10']}")
    L.append("")
    L.append("## 4. Duplicate-entity candidates")
    L.append("")
    L.append(f"- Exact-name groups (same canonical name, different IDs): "
             f"**{stats['duplicates']['exact_name_groups']}** groups / "
             f"**{stats['duplicates']['entities_in_dup_groups']}** entities")
    L.append(f"- Name-vs-alias collisions: **{stats['duplicates']['name_vs_alias_collisions']}**")
    L.append("")
    if exact_dup_groups:
        L.append("Sample exact-name groups:")
        L.append("")
        for g in exact_dup_groups[:8]:
            L.append(f"- `{'` / `'.join(e['canonical_name'] for e in g[:5])}` "
                     f"({', '.join(e['type'] for e in g[:5])})")
        L.append("")
    if alias_collisions:
        L.append("Sample name-vs-alias collisions:")
        L.append("")
        for c in alias_collisions[:10]:
            L.append(f"- `{c['entity']}` ↔ alias of `{c['alias_source']}`")
        L.append("")
    L.append("## 5. Alias & description coverage")
    L.append("")
    L.append(f"- Entities with ≥1 alias: **{stats['coverage']['n_with_alias']}** "
             f"({round(100*stats['coverage']['alias_coverage'],1)}%)")
    L.append(f"- Entities with non-empty description: **{stats['coverage']['n_with_description']}** "
             f"({round(100*stats['coverage']['description_coverage'],1)}%)")
    L.append(f"- Entities with empty description: **{stats['coverage']['n_without_description']}**")
    L.append("")
    L.append("## 6. Sparsity & direction quality")
    L.append("")
    L.append(f"- Relationship types: **{stats['sparsity']['relationship_types']}**")
    L.append("")
    L.append("| Relationship type | Count |")
    L.append("|---|---|")
    for t, c in rel_by_type.most_common(15):
        L.append(f"| {t} | {c} |")
    L.append("")
    L.append(f"- Bidirectional pairs with non-inverse types (possible direction "
             f"errors / redundant duplicates): **{stats['sparsity']['bidirectional_anomaly_pairs']}**")
    for b in bidirectional[:12]:
        L.append(f"  - `{b['source']}` -[{b['forward']}]-> `{b['target']}` "
                 f"and reverse `-[{b['reverse']}]->`")
    L.append("")
    L.append("## 7. Benchmark entity hit-rate")
    L.append("")
    L.append("For each benchmark question, how many graph entities share a "
             "non-stopword token with the question, and their degrees (retrieval reach).")
    L.append("")
    L.append("| Q | Category | Matched | Matched entities (degree) |")
    L.append("|---|---|---|---|")
    for h in hits:
        m = ", ".join(f"`{n}`({d})" for n, d in h["matched"])
        L.append(f"| {h['id']} | {h['category']} | {h['n_matched']} | {m} |")
    L.append("")

    MD_OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"Wrote {MD_OUT.name}")


if __name__ == "__main__":
    main()
