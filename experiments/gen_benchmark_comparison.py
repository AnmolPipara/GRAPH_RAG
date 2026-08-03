"""Generate experiments/benchmark_comparison.md (Original vs Validated).

Data-driven from evaluation/benchmark_v2_summary.json (produced by
evaluation/run_v2_eval.py). Kept as a permanent artifact so the Phase-3
comparison document is reproducible from the run summary alone.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.metrics_v2 import answer_accuracy

summary = json.load(open(str(ROOT / "evaluation" / "benchmark_v2_summary.json"), encoding="utf-8"))

vec_m = summary["vector_rag_metrics"]
graph_m = summary["graph_rag_metrics"]
overlap = summary["overlap_original_vs_corrected"]


def esc(x, n=40):
    """Escape pipes/newlines so table cells cannot break; truncate."""
    s = str(x).replace("|", "\\|").replace("\n", " ")
    return s[:n] + ("…" if len(s) > n else "")


L = []
A = L.append
A("# Benchmark Comparison — Original vs Validated (Phase 3)")
A("")
A(f"Corrected benchmark: **{summary['config']['n_questions']} questions** "
  f"(`experiments/benchmark_v2.json`) · QA model `{summary['config']['model']}` via "
  f"`{summary['config']['provider']}`, temperature 0.0 · same evaluator, prompt template, "
  "retrieval, and graph as the official v1 run (only the question set changed).")
A("")
A("## Corrected-benchmark aggregates (12 questions)")
A("")
A("| Metric | VectorRAG | GraphRAG |")
A("|---|---|---|")
for k in ("answer_accuracy", "f1_score", "context_recall", "context_precision",
          "faithfulness", "citation_correctness", "hallucination_rate", "multi_hop_success"):
    A(f"| {k} | {vec_m.get(k, 0)} | {graph_m.get(k, 0)} |")
A("")
A("## Original vs corrected — overlap questions (were in the 10-question smoke)")
A("")
A("| ID | Original GT | Graph answer (orig) | Graph acc (orig) | Vector acc (orig) | Corrected GT | Graph answer (corr) | Graph acc (corr) | Vector acc (corr) |")
A("|---|---|---|---|---|---|---|---|---|")
for o in overlap:
    if o["original_question"] is None:
        continue
    orig_acc = answer_accuracy(o.get("original_answer") or "", o.get("original_ground_truth") or "")
    corr_acc = answer_accuracy(o.get("corrected_answer") or "", o.get("corrected_ground_truth") or "")
    ov_acc = answer_accuracy(o.get("original_vector_answer") or "", o.get("original_ground_truth") or "")
    cv_acc = answer_accuracy(o.get("corrected_vector_answer") or "", o.get("corrected_ground_truth") or "")
    A(f"| {o['question_id']} | {esc(o['original_ground_truth'])} | {esc(o.get('original_answer') or '', 32)} | "
      f"{orig_acc:.2f} | {ov_acc:.2f} | {esc(o['corrected_ground_truth'])} | "
      f"{esc(o.get('corrected_answer') or '', 32)} | {corr_acc:.2f} | {cv_acc:.2f} |")
A("")
A("Original questions for the overlap IDs (from the v1 smoke benchmark):")
A("")
for o in overlap:
    if o["original_question"] is None:
        continue
    A(f"- **Q{o['question_id']}:** {esc(o['original_question'], 200)}")
A("")
A("## Per-corrected-question records")
A("")
A("> All 12 questions in `benchmark_v2.json` are Phase-1 **UNSUPPORTED** by construction:")
A("> each was repaired precisely because its original ground truth was not derivable from")
A("> the corpus (see `experiments/benchmark_validation_report.md`). The status column is")
A("> therefore constant across rows.")
A("")
A("| ID | Category | Corrected question | Corrected GT | Graph answer | Vector answer | Phase-1 status |")
A("|---|---|---|---|---|---|---|")
for o in overlap:
    qid = o["question_id"]
    A(f"| {qid} | {o['category']} | {esc(o['corrected_question'], 46)} | {esc(o['corrected_ground_truth'], 36)} | "
      f"{esc(o.get('corrected_answer') or '', 42)} | {esc(o.get('corrected_vector_answer') or '', 42)} | "
      "UNSUPPORTED (repaired) |")
A("")
A("## What this comparison shows")
A("")
A("- **Q2, Q5, Q7, Q8** were in the original smoke: their ground truths were wrong or")
A("  unanswerable (Phase-1 audit). The same systems were scored against both the original and")
A("  the corrected ground truths — e.g. Q2 the system already answered `+358 20 793 4200`")
A("  (the corpus-consistent number) but scored 0.75 against the wrong GT and 1.00 against the")
A("  corrected one; Q5/Q7 flipped from 0.00 (\"I don't know\") to 1.00 once the GT existed.")
A("- **Q27, Q34, Q45, Q46, Q48, Q49, Q51, Q53** had **no original benchmark record** (they were")
A("  never run) — they are new validated questions replacing unsupported ones.")
A("")
A("## Known limitations (documented)")
A("")
A("- **Workflow-category redundancy:** the corrected Q45, Q46, Q48, Q51 are all re-grounded in")
A("  the same customer-to-bank (C2B) / VOP flow from page 53 — the guide's only detailed")
A("  workflow. Categories and difficulty are preserved, but topic variety in the workflow")
A("  category is reduced vs the original intent. A reviewer should not read these as")
A("  independent test items.")
A("- The corrected set is 12 questions; per-category aggregates are small (workflow n=4).")
A("- Corrected-benchmark aggregates (12 questions) are NOT directly comparable to the v1")
A("  smoke aggregates (10 questions, different question set).")

open(str(ROOT / "experiments" / "benchmark_comparison.md"), "w", encoding="utf-8").write("\n".join(L))
print("WROTE experiments/benchmark_comparison.md")
print("VEC:", json.dumps(vec_m))
print("GRAPH:", json.dumps(graph_m))
