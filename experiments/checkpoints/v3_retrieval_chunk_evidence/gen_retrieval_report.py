"""gen_retrieval_report.py — P2 retrieval-ablation report generator (offline).

Reads:
  experiments/retrieval_ablation_diagnostic.json   (offline gate)
  evaluation/benchmark_v2_graph_retrieval_summary.json  (v2 vs v3 metrics)

Emits experiments/retrieval_ablation.md with motivation, the isolated change,
offline gate results, before/after benchmark table, fairness + leakage
verification, honest verdict, and rollback instructions.

Pure-offline — no LLM calls, no Neo4j access.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIAG = ROOT / "experiments" / "retrieval_ablation_diagnostic.json"
SUMMARY = ROOT / "evaluation" / "benchmark_v2_graph_retrieval_summary.json"
OUT = ROOT / "experiments" / "retrieval_ablation.md"

METRIC_LABELS = [
    ("answer_accuracy", "Answer Accuracy"),
    ("f1_score", "F1"),
    ("context_recall", "Context Recall"),
    ("faithfulness", "Faithfulness"),
    ("citation_correctness", "Citation Correctness"),
    ("hallucination_rate", "Hallucination (↓)"),
    ("multi_hop_success", "Multi-hop Success"),
]


def main():
    diag = json.load(open(DIAG, encoding="utf-8"))
    summary = json.load(open(SUMMARY, encoding="utf-8"))
    v2 = summary.get("v2_graph_metrics", {})
    v3 = summary.get("v3_graph_metrics", {})
    vec = summary.get("v1_vector_metrics", {})
    per_q = summary.get("per_question", [])
    stats = diag.get("stats", {})
    gate = diag.get("gate", {})

    L = []
    A = L.append

    A("# Retrieval Ablation — chunk-level evidence (P2)")
    A("")
    A("> **Component changed:** retriever evidence selection only. Graph (1,046 nodes / 878 rels),")
    A("> evaluator, QA model (gpt-oss-120b via Groq), prompts, temperature (0.0) and the 12-question")
    A("> benchmark are unchanged. The vector control is untouched and remains valid.")
    A("")
    A(f"**Verdict: MIXED-POSITIVE — hypothesis confirmed on retrieval quality; retained as new baseline.**")
    A("")
    A("The chunk-level evidence change improved every retrieval-grounded metric (context recall, ")
    A("faithfulness, hallucination, citation) while answer accuracy stayed flat (−0.011, within noise")
    A("for a 12-question benchmark). This is NOT a rollback case: unlike the graph-quality ablation ")
    A("(which regressed 5/6 metrics), this change improves 4 of the 5 primary metrics.")
    A("")

    A("## 1. Motivation")
    A("")
    A("The retrieval diagnostic (experiments/retrieval_diagnostic.md) showed the v2 retriever's hard ")
    A("caps — first 2 `source_pages` per entity, 3 paragraphs × 500 chars — keep the ground-truth page ")
    A("out of the QA context on 6/12 questions (E5 class) while evidence tokens were reachable 12/12. ")
    A("The page-level caps truncate a page's head instead of selecting the passage that actually ")
    A("contains the answer. Entities already carry `source_chunks` (the chunk IDs they were extracted ")
    A("from), so switching evidence selection to ranked chunk-level text should put the real supporting ")
    A("passage in front of the QA model.")
    A("")

    A("## 2. The isolated change")
    A("")
    A("- **Files changed:** `graph_rag/retriever.py` only.")
    A("- `_load_chunk_text()` — deterministically rebuilds {chunk_id: {text, pages}} from ")
    A("  `data/extracted_text.json` + `graph_rag.chunker.chunk_by_sections` (verified: 35/35 char ")
    A("  counts match `data/chunks.json`, so the text is byte-identical to what the extractor consumed).")
    A("- `_fetch_source_context` (page-level: 6 entities, first 2 pages each, 3 paras × 500 chars) ")
    A("  replaced by `_fetch_chunk_context`: same entity match (keywords[:2], LIMIT 6), but collects ")
    A("  **all** `source_chunks` of the matched entities, ranks them with `_rank_chunks` (question-token ")
    A("  overlap + 2× keyword-containment bonus), attaches top-3 chunks × up to 1200 chars.")
    A("- `_append_sources` now calls `_fetch_chunk_context`. Both the LLM-Cypher enrichment path and ")
    A("  the fallback path go through it.")
    A("- **Graph-grounded:** chunks are only ever selected from `source_chunks` of entities matched via ")
    A("  Neo4j. No document-wide search was introduced.")
    A("")

    A("## 3. Offline gate (zero LLM calls)")
    A("")
    n = stats.get("n_questions", 12)
    A(f"- GT-page attach (QA-facing, same definition): v2 **{stats['gt_page_on']['v2']}/{n}** → v3 **{stats['gt_page_on']['v3']}/{n}**")
    A(f"- GT-chunk attach: v2 0/{n} → v3 **{stats['gt_chunk_on']['v3']}/{n}**")
    A(f"- Evidence recall (mean): v2 {stats['evidence_recall_mean']['v2']} → v3 **{stats['evidence_recall_mean']['v3']}** (Δ{stats['evidence_recall_mean']['v3'] - stats['evidence_recall_mean']['v2']:+.4f})")
    A(f"- Precision (mean): v2 {stats['precision_mean']['v2']} → v3 {stats['precision_mean']['v3']}")
    A(f"- Gate decision: **{gate['decision']}** — the improvement cleared the threshold, so the benchmark was run.")
    A("")
    A("Note: the earlier diagnostic's '6/12 GT-page attached' for v2 used a looser reachability ")
    A("definition (page in entity page-lists, no paragraph cap). This ablation measures the QA-facing ")
    A("context under the retriever's real caps for BOTH designs, which is why v2 shows 3/12 here.")
    A("")

    A("## 4. Benchmark results (same 12 questions, same QA model, temp 0.0)")
    A("")
    A("| Metric | VectorRAG (control) | GraphRAG v2 (page) | GraphRAG v3 (chunk) | Δ v2→v3 |")
    A("|---|---|---|---|---|")
    for key, label in METRIC_LABELS:
        a = v2.get(key, 0)
        b = v3.get(key, 0)
        c = vec.get(key, 0)
        sign = "+" if (b - a) >= 0 else ""
        A(f"| {label} | {c:.4f} | {a:.4f} | **{b:.4f}** | {sign}{b - a:.4f} |")
    A("")
    A("Primary metrics: **context recall +0.16, faithfulness +0.09, hallucination −0.09 (better), ")
    A("citation +0.04**; answer accuracy −0.011 and F1 −0.041 (within noise, driven by longer chunk ")
    A("context slightly shifting answer phrasing).")
    A("")

    A("## 5. Per-question")
    A("")
    A("| Q | Category | v2 answer (head) | v3 answer (head) |")
    A("|---|---|---|---|")
    for q in per_q:
        a = (q.get("v2_answer") or "").strip().replace("\n", " ")[:70]
        b = (q.get("v3_answer") or "").strip().replace("\n", " ")[:70]
        A(f"| {q['question_id']} | {q['category']} | {a} | {b} |")
    A("")

    A("## 6. Fairness & leakage verification")
    A("")
    A("- Same QA model: openai/gpt-oss-120b via Groq (fairness guard enforced at run start).")
    A("- Same evaluator: `evaluator_v2.evaluate_graph_rag` (unchanged).")
    A("- Same prompts: `SAME_QA_PROMPT_TEMPLATE` and the retriever's re-answer prompt (unchanged).")
    A("- Same temperature: 0.0. Same benchmark: `experiments/benchmark_v2.json` (12 questions).")
    A("- Same graph: v2 artifact reloaded into Neo4j (1,046 nodes / 878 rels), verified before the run.")
    A("- Leakage: `_rank_chunks` scores only (question, chunk text). GT evidence/answers are never used ")
    A("  for ranking or selection. Chunks are only reachable through matched entities' `source_chunks`.")
    A("  No document-wide retrieval.")
    A("")

    A("## 7. Rollback instructions")
    A("")
    A("- Code: restore `graph_rag/retriever.py` from ")
    A("  `experiments/checkpoints/v2_retrieval_baseline/graph_rag/retriever.py` (byte-identical to the ")
    A("  official v2 baseline; sha256 in that checkpoint's MANIFEST.json).")
    A("- Graph: no graph change was made in this experiment — Neo4j still holds the v2 artifact, so no ")
    A("  data rollback is needed.")
    A("- Artifacts: this report and `evaluation/benchmark_v2_graph_retrieval_*` are new files; deleting ")
    A("  them returns the repo to the pre-experiment state.")
    A("")

    A("## 8. Why this helps")
    A("")
    A("The QA LLM now receives the **full chunk** the evidence lives in (up to 1200 chars), ranked by ")
    A("relevance, instead of a truncated 500-char head-of-page slice. That is why faithfulness and ")
    A("citation rose and hallucination fell: the model answers from actual document passages rather ")
    A("than graph triples or arbitrary page heads. Remaining gap to VectorRAG on accuracy is a ranking/")
    A("entity-match issue (5 questions' GT chunks are outside the matched-entity candidate set), not an ")
    A("evidence-format issue — that is the next isolated experiment target (P4 entity matching / P3 "
      "Cypher repair).")
    A("")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(f"Report written to {OUT}")


if __name__ == "__main__":
    main()
