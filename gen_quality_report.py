"""gen_quality_report.py — P1 Graph-Quality Ablation Report Generator.

Reads the saved evaluation summary (benchmark_v2_graph_quality_summary.json),
the quality stats (quality_stats_{before,after}.json), and writes
experiments/quality_ablation.md.

Pure offline (no LLM calls). Reproducible:
    python gen_quality_report.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

EVAL = ROOT / "evaluation"
SUMMARY = EVAL / "benchmark_v2_graph_quality_summary.json"
BEFORE = ROOT / "experiments" / "quality_stats_before.json"
AFTER = ROOT / "experiments" / "quality_stats_after.json"
OUT = ROOT / "experiments" / "quality_ablation.md"

METRIC_LABELS = [
    ("exact_match", "Exact Match"),
    ("f1_score", "F1"),
    ("answer_accuracy", "Answer Accuracy"),
    ("faithfulness", "Faithfulness"),
    ("context_precision", "Context Precision"),
    ("context_recall", "Context Recall"),
    ("hallucination_rate", "Hallucination Rate (↓ better)"),
    ("citation_correctness", "Citation Correctness"),
    ("multi_hop_success", "Multi-Hop Success"),
]

STAT_ROWS = [
    ("entities", "Entities"),
    ("relationships", "Relationships"),
    ("isolated_nodes", "Isolated nodes"),
    ("mean_degree", "Mean total degree"),
    ("max_degree", "Max degree"),
    ("wcc_count", "Weakly-connected components"),
    ("largest_wcc", "Largest component"),
    ("dup_groups", "Duplicate-name groups"),
    ("dup_entities", "Entities in duplicate groups"),
    ("pages_linked", "Pages linked in `source_pages`"),
    ("n_with_alias", "Entities with ≥1 alias"),
    ("n_with_desc", "Entities with description"),
]


def main():
    s = json.load(open(SUMMARY, encoding="utf-8"))
    before = json.load(open(BEFORE, encoding="utf-8"))
    after = json.load(open(AFTER, encoding="utf-8"))

    v1 = s.get("v1_graph_metrics", {})
    v2 = s.get("v2_graph_metrics", {})
    v3 = s.get("v3_graph_metrics", {})
    vec = s.get("v1_vector_metrics", {})

    # Deltas computed from the stats so prose never drifts from the data
    d_isolated = (after.get("isolated_nodes", 0) or 0) - (before.get("isolated_nodes", 0) or 0)
    d_wcc = (after.get("wcc_count", 0) or 0) - (before.get("wcc_count", 0) or 0)
    d_degree = round(
        (after.get("mean_degree", 0) or 0) - (before.get("mean_degree", 0) or 0), 3)
    n_dropped_rels = (before.get("relationships", 0) or 0) - (after.get("relationships", 0) or 0)
    n_merged_entities = (before.get("entities", 0) or 0) - (after.get("entities", 0) or 0)

    L = []
    A = L.append

    A("# P1 Graph-Quality Ablation — Entity Deduplication (v2 → v3)")
    A("")
    A("> **Isolated ablation:** only the graph-construction defect set was changed: "
      "duplicate entities merged by normalized canonical name, relationships rewired "
      "to survivor IDs, dangling `-cross-chunk` endpoints resolved, collapsed "
      "duplicates and self-loops dropped. Retrieval, ranking, prompts, evaluator, QA "
      "model, benchmark questions, temperature, and graph schema are UNCHANGED "
      "(byte-verified against the `v2_construction_baseline` checkpoint). The graph "
      "was rebuilt deterministically with zero LLM calls and reloaded through the "
      "same loader (post-load assert: 100% of rels landed). QA/Cypher model "
      "reproduces the recorded v2 config (`openai/gpt-oss-120b` via `groq`, temp 0.0).")
    A("")
    A("> **Result: NEGATIVE — v3 NOT adopted; Neo4j reloaded to v2 "
      "(1046 nodes / 878 rels / 290 isolated); v2 remains the official baseline. "
      "See the verdict in §5.**")
    A("")

    # ── 1. Motivation & audit evidence ──
    A("## 1. Motivation: what the offline audit found")
    A("")
    A("The offline audit (`graph_quality_audit.md`) of the v2 graph showed the "
      "dominant construction defect is **entity fragmentation**:")
    A("")
    A("| Defect | v2 count |")
    A("|---|---|")
    A(f"| Exact-name duplicate groups (same canonical name, different IDs) | **{before.get('dup_groups')}** groups / **{before.get('dup_entities')}** entities |")
    A(f"| Name↔alias collisions (entity name equals another entity's alias) | 225 (audit) |")
    A(f"| Dangling `-cross-chunk` relationship endpoints (silently dropped by loader) | 42 unique / 53 rels (audit) |")
    A(f"| Isolated nodes (degree 0) | **{before.get('isolated_nodes')}** |")
    A(f"| Weakly-connected components | **{before.get('wcc_count')}** (largest {before.get('largest_wcc')}) |")
    A("")
    A("Examples of duplicated concepts extracted under multiple type-guesses:")
    A("")
    A("- `Group Header` → `BusinessComponent` (19 pages) **and** `XMLElement` (3 pages)")
    A("- `Payment Information` → `BusinessComponent` (26 pages) **and** `BusinessConcept` (4 pages)")
    A("- `Message root` → three nodes (`BusinessComponent`, `TechnicalConcept`, `XMLElement`)")
    A("- `Credit transfer` → four nodes (`PaymentScheme`, `PaymentType`, `BusinessComponent`, `BusinessConcept`)")
    A("")
    A("**Why this hurts retrieval:** every fragment carries only its own `source_pages` "
      "and only its own neighborhood. Whichever fragment the retriever matches, it "
      "attaches fewer source paragraphs (lower context recall) and sees a thinner "
      "1-hop neighborhood (weaker fallback retrieval and multi-hop evidence). "
      "Fragments also live in different weakly-connected components, so merging them "
      "connects components that the document actually relates.")
    A("")

    # ── 2. The isolated change ──
    A("## 2. The isolated change (construction only)")
    A("")
    A("1. **Entity dedup (`rebuild_graph_v3_quality.py`):** entities sharing a "
      "normalized canonical name (case/punctuation-insensitive) are merged into a "
      "single survivor (most-extracted fragment wins; ties by description length). "
      "Aliases, `source_pages`, `source_chunks`, evidence, frequency, confidence "
      "(max) and attributes are unioned. **Only exact-name merging** was applied — "
      "semantic alias pairs (`Seller`↔`Creditor`, `Payer`↔`Debtor`) were deliberately "
      "left untouched to keep the ablation conservative and attributable.")
    A("2. **Relationship rewiring:** every endpoint that pointed at a merged-away ID "
      "is re-pointed at its survivor; collapsed duplicates (same source/relation/"
      "target) are merged with evidence concatenated; self-loops dropped.")
    A("3. **Dangling-endpoint resolution:** `-cross-chunk` IDs the refiner failed to "
      "resolve are matched against entity canonical names by alphanumeric collapse "
      "where possible; rels with unresolvable endpoints are dropped explicitly so the "
      "artifact and the database agree (46 dropped, 7 resolved).")
    A("")
    A("Retrieval code, evaluator, prompts, QA model, benchmark, temperature: "
      "**untouched** (byte-identical to the `v2_construction_baseline` checkpoint).")
    A("")

    # ── 3. Graph statistics before vs after ──
    A("## 3. Graph statistics: before (v2) vs after (v3)")
    A("")
    A("| Quantity | Before (v2) | After (v3) |")
    A("|---|---|---|")
    for key, label in STAT_ROWS:
        A(f"| {label} | {before.get(key)} | **{after.get(key)}** |")
    A("")
    A(f"Duplicate-name groups: **{before.get('dup_groups')} → {after.get('dup_groups')}**. "
      f"{n_merged_entities} entities merged ({n_dropped_rels} relationships net "
      f"change: collapsed duplicates, self-loops, and unresolvable rels). "
      f"Isolated nodes {d_isolated:+,d}, WCCs {d_wcc:+,d}, mean degree "
      f"{d_degree:+.2f} — the graph is denser and better connected, with identical "
      f"page coverage ({after.get('pages_linked')}/61). The post-load assert "
      f"confirmed **{after.get('entities')}/{after.get('entities')} nodes and "
      f"{after.get('relationships')}/{after.get('relationships')} rels** landed in "
      f"Neo4j (in the v2 graph, 53 rels had been silently dropped by the loader).")
    A("")

    # ── 4. Benchmark results ──
    A("## 4. Benchmark results (same 12 questions, same harness)")
    A("")
    A("| Metric | V1 Graph | V2 Graph | V3 Graph | Δ v2→v3 | V1 Vector (control) |")
    A("|---|---|---|---|---|---|")
    for key, label in METRIC_LABELS:
        b = v1.get(key, 0)
        c = v2.get(key, 0)
        a = v3.get(key, 0)
        d = a - c
        sign = "+" if d >= 0 else ""
        vecv = vec.get(key, 0)
        A(f"| {label} | {round(b, 4)} | {round(c, 4)} | **{round(a, 4)}** | {sign}{round(d, 4)} | {round(vecv, 4)} |")
    A("")
    A("Per-question v2→v3 answer comparison is in the summary JSON "
      "(`evaluation/benchmark_v2_graph_quality_summary.json` → `per_question`).")
    A("")

    # ── 5. Verdict (negative result, rolled back) ──
    A("## 5. Verdict: hypothesis NOT confirmed — negative result, rolled back")
    A("")
    A("**The entity-dedup experiment did not improve GraphRAG and slightly hurt "
      "answer quality. Per the protocol it was rolled back — v3 was NOT adopted and "
      "Neo4j was reloaded to the preserved v2 artifact (verified: 1046 nodes / 878 "
      "rels / 290 isolated, the v2 baseline). v2 remains the official baseline.**")
    A("")
    A("| Metric | V2 | V3 | Δ |")
    A("|---|---|---|---|")
    for key, label in METRIC_LABELS:
        b = v2.get(key, 0)
        a = v3.get(key, 0)
        d = a - b
        sign = "+" if d >= 0 else ""
        # For hallucination_rate, a positive delta means WORSE (▼), not better.
        flag = ""
        if key == "hallucination_rate" and d > 0:
            flag = " ▼ (worse)"
        elif key == "hallucination_rate" and d < 0:
            flag = " ▼ (better)"
        A(f"| {label} | {round(b, 4)} | **{round(a, 4)}** | {sign}{round(d, 4)}{flag} |")
    A("")
    A("Only **context recall** improved (0.517 → 0.556). Answer accuracy, "
      "faithfulness, citation correctness, multi-hop success and hallucination all "
      "regressed; Q8 and Q27 collapsed from substantive answers to \"I don't know\".")
    A("")
    A("**Why it regressed (verified offline, zero LLM calls):** an offline probe of "
      "the retriever's page selection (`pages[:2]` per matched entity, 6 entities, 3 "
      "paragraphs) shows the page lists are **identical** between v2 and v3 for the "
      "benchmark questions (e.g. Q8/Q27/Q45/Q49 both yield `[1, 2]`, GT page never "
      "within the cap) — so page-list reordering was NOT the cause. The real driver "
      "is neighborhood densification: dedup raised mean degree 1.728 → 1.918 and "
      "merged WCCs, so the **fallback retrieval** (which fires on 8 of 12 questions "
      "when the LLM Cypher returns empty) returned richer but *different* triple "
      "context (28 rows for Q45/Q49/Q51 in v3 vs 9–11 in v2). Richer context raised "
      "context recall, but the QA re-answered from a changed, noisier context and "
      "lost precision.")
    A("")
    A("**Implication for the next experiment:** fragmentation was not the binding "
      "bottleneck. The dominant defect is that the **LLM-generated Cypher path "
      "returns empty context on most questions** (fallback fired on 8/12), and the "
      "retriever's page caps (2 pages/entity, 3 paragraphs) keep the GT page out of "
      "context. The next isolated experiment should therefore target **Priority 2/3** "
      "(chunk-level evidence selection and retrieval ranking), not more graph "
      "construction.")
    A("")

    # ── 6. Fairness & leakage verification ──
    A("## 6. Fairness & leakage verification")
    A("")
    A("| Requirement | Status |")
    A("|---|---|")
    A("| Same evaluator (`evaluator_v2.py`, `metrics_v2.py`) | ✅ reused verbatim |")
    A(f"| Same QA model | ✅ `{s['config']['model']}` via `{s['config']['provider']}` (enforced by `_assert_fair_config`) |")
    A(f"| Same Cypher model | ✅ `{s['config'].get('cypher_model')}` via `{s['config'].get('cypher_provider')}` |")
    A(f"| Same temperature | ✅ {s['config']['temperature']} |")
    A("| Same prompts | ✅ `SAME_QA_PROMPT_TEMPLATE` + unchanged retriever prompts |")
    A("| Same retrieval code | ✅ `graph_rag/retriever.py` untouched (cmp vs checkpoint) |")
    A("| Same benchmark questions | ✅ `experiments/benchmark_v2.json` (12 questions) |")
    A("| Same graph schema | ✅ unchanged loader; only node/rel sets changed |")
    A("| No information leakage | ✅ retriever only attaches pages reachable via graph `source_pages`; no document-wide search added |")
    A("")
    A("**No leakage:** the retriever's source-attachment path "
      "(`_fetch_source_context`) still resolves pages exclusively through matched "
      "entities' `source_pages`. Dedup changed which nodes carry those pages — not "
      "how retrieval uses them. The v2 artifact (`data/refined_graph_v2_construction"
      ".json`) was never overwritten; rollback = reload it through `Neo4jLoader`.")
    A("")

    # ── 7. Reproducibility ──
    A("## 7. Reproducibility")
    A("")
    A("| Step | Command |")
    A("|---|---|")
    A("| 1. Audit | `python graph_quality_audit.py` (zero LLM) |")
    A("| 2. Rebuild (dedup) | `python rebuild_graph_v3_quality.py` (zero LLM; writes `data/refined_graph_v3_quality.json`, `experiments/quality_stats_{before,after}.json`) |")
    A("| 3. Re-evaluate graph side | `ANSWER_MODEL=openai/gpt-oss-120b ANSWER_PROVIDER=groq CYPHER_MODEL=openai/gpt-oss-120b CYPHER_PROVIDER=groq python evaluation/run_quality_eval.py` |")
    A("| 4. Regenerate this report | `python gen_quality_report.py` |")
    A("")
    A("Rollback: reload the preserved v2 artifact "
      "`data/refined_graph_v2_construction.json` through `Neo4jLoader.load_all` "
      "(checkpoint `experiments/checkpoints/v2_construction_baseline/` is untouched).")
    A("")
    A("Limitations: 12-question benchmark (budget-constrained); exact-name merging "
      "only (semantic alias pairs deferred); retriever page caps (2 pages/entity, 3 "
      "paragraphs) still bound context recall; F1 is phrasing-sensitive on short "
      "ground truths.")

    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"WROTE {OUT}")
    print(f"v3: {json.dumps(v3)}")


if __name__ == "__main__":
    main()
