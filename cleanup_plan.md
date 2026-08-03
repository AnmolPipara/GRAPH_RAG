# Repository Cleanup Plan — GraphRAG

**Date:** 2026-08-03
**Status:** Plan approved — deletions below performed only after this report was generated.
**Scope:** `GraphRAG/` (the public-release repo). No source code, evaluation logic, benchmark,
report content, or checkpoint was modified.

---

## Baseline (before cleanup)

- Repository size (excluding `.git`): **21 MB**
- Tracked files: **272** (in git), **295** files on disk excluding `.git`
- Git state: clean on `main` (commit `ebd0dfb`), pushed to `github.com/AnmolPipara/GRAPH_RAG`

---

## A. Logs — REMOVE (16 files)

All regenerable at runtime by the evaluation scripts. None are referenced by code or manifests.

| File | Reason | Reproducible? | Backed up? |
|---|---|---|---|
| `evaluation/benchmark_v2_eval.log` | Run log | Yes (rerun eval) | No |
| `evaluation/construction_ablation_eval.log` | Run log | Yes | No |
| `evaluation/evaluation.log` | Run log | Yes | No |
| `evaluation/fair_run.log` | Run log | Yes | No |
| `evaluation/fair_run2.log` | Run log | Yes | No |
| `evaluation/fair_run3.log` | Run log | Yes | No |
| `evaluation/fair_run4.log` | Run log | Yes | No |
| `evaluation/fair_run5.log` | Run log | Yes | No |
| `evaluation/groq120b_enrich_run.log` | Run log | Yes | No |
| `evaluation/groq120b_fair_run.log` | Run log | Yes | No |
| `evaluation/groq120b_fair_run4.log` | Run log | Yes | No |
| `evaluation/groq70_fair_run.log` | Run log | Yes | No |
| `evaluation/groq70_fair_run2.log` | Run log | Yes | No |
| `evaluation/quality_eval.log` | Run log | Yes | No |
| `evaluation/retrieval_ablation_eval.log` | Run log | Yes | No |
| `evaluation/smoke_run.log` | Run log | Yes | No |

> **Kept (checkpoint-protected):** `experiments/checkpoints/v1_source_evidence/groq120b_enrich_run.log`
> and `experiments/checkpoints/v2_construction_baseline/construction_ablation_eval.log` — these are
> MANIFEST-referenced artifacts of frozen experiment checkpoints, which the instructions require keeping.

---

## B. Debugging / superseded run folders — REMOVE (6 folders)

| Folder | Size | Reason | Reproducible? | Backed up? |
|---|---|---|---|---|
| `evaluation/previous_groq120b_noenrich/` | 80 KB | Superseded model-run results (pre-final benchmark) | Yes (rerun) | Metrics superseded by `benchmark_v2_*` |
| `evaluation/previous_groq70/` | 56 KB | Superseded model-run results | Yes | Superseded by final benchmark |
| `evaluation/previous_groq8b/` | 2.0 MB | Superseded model-run results + plots | Yes | Superseded by final benchmark |
| `evaluation/previous_hf397b/` | 56 KB | Superseded model-run results | Yes | Superseded by final benchmark |
| `evaluation/poisoned_quota/` | 972 KB | Quarantine dir auto-recreated by `run_fair_eval.py` (`qdir.mkdir(exist_ok=True)`) | Yes (auto) | No — regenerable |
| `evaluation/stale_network_report/` | 432 KB | Report of a one-off stale-network incident; superseded | No | Superseded by final benchmark |

> `previous_*` contain their own `plots/` copies; the canonical plots live in
> `evaluation/plots/` (kept). Only one code reference exists: `run_fair_eval.py:116` writes to
> `poisoned_quota/` and recreates it on demand — removal is safe.

---

## C. Temporary report generators — REMOVE (4 files)

Not imported by any module; their generated reports are deleted or superseded.

| File | Generates | Reason | Reproducible? | Backed up? |
|---|---|---|---|---|
| `gen_construction_report.py` | `construction_ablation.md` (root copy already deleted; archived in checkpoint) | Superseded ablation report generator | Yes | Output archived in `checkpoints/v2_construction_baseline/` |
| `gen_quality_report.py` | `quality_ablation.md` (deleted) | Superseded ablation report generator | Yes | Output superseded |
| `gen_retrieval_report.py` | `retrieval_ablation.md` (archived in checkpoints) | Superseded ablation report generator | Yes | Output archived in `checkpoints/v3_retrieval_*` |
| `gen_final_docs.py` | `docs/Final_Report.{pdf,docx}` (old report, deleted) | Cannot regenerate current docs (`Final_Project_Report.*` built by the removed `_tmp_build_report.py`); superseded | Yes | Output superseded by `docs/Final_Project_Report.*` |

> **Kept:** `experiments/checkpoints/v3_retrieval_chunk_evidence/gen_retrieval_report.py` and
> `experiments/checkpoints/v2_construction_baseline/gen_construction_report.py` — checkpoint copies.

---

## D. Duplicate / legacy evaluation artifacts — REVIEWED, ALL KEPT

Byte-identical scan across all `evaluation/*.json|csv` found **zero duplicates**. Every JSON is
referenced by an evaluation script or a manifest:

| File | Status | Reason |
|---|---|---|
| `benchmark_v2_summary.json` | KEEP | Final v2 summary (written by `run_v2_eval.py`) |
| `benchmark_v2_vector_results.json` | KEEP | Final vector results (written by `run_v2_eval.py`) |
| `benchmark_v2_graph_results.json` | KEEP | Final graph results (written by `run_v2_eval.py`) |
| `benchmark_v2_graph_construction_{results,summary}.json` | KEEP | Final construction ablation (written by `run_construction_eval.py`) |
| `benchmark_v2_graph_quality_{results,summary}.json` | KEEP | Final quality ablation (written by `run_quality_eval.py`) |
| `benchmark_v2_graph_retrieval_{results,summary}.json` | KEEP | Final retrieval ablation (written by `run_retrieval_eval.py`) |
| `benchmark_v2_graph_candidategen_{results,summary}.json` | KEEP | Final v4 candidate-gen results (final baseline) |
| `evaluation_results.json` / `.csv` | KEEP | v1 combined results — read/written by `report.py`, `run_evaluation.py`; archived in `checkpoints/v1_source_evidence/` |
| `graph_rag_results.json` / `vector_rag_results.json` | KEEP | v1 results — read/written by `run_fair_eval.py`, `evaluator_v2.py`, `run_evaluation.py`; archived in `checkpoints/v1_source_evidence/` |
| `questions.json`, `experiments/benchmark_v2.json` | KEEP | Benchmark question sets (datasets — never delete) |

> These fail the "no longer referenced" test, so per the instructions they are retained.

---

## E. Checkpoints — REVIEWED, ALL KEPT (experiment-specific, not full copies)

| Checkpoint | Size | Files | Contents | Recommendation |
|---|---|---|---|---|
| `v1_source_evidence/` | 445 KB | 9 | v1 retriever + eval scripts + v1 results + MANIFEST | KEEP — experiment-specific snapshot |
| `v2_construction_baseline/` | 1.6 MB | 26 | v2 source snapshot (graph_rag/, config/, utils/) + construction results + MANIFEST | KEEP — code snapshot with manifest hashes |
| `v2_retrieval_baseline/` | 1.5 MB | 17 | v2 retriever/chunker + eval results + MANIFEST | KEEP — experiment-specific |
| `v3_retrieval_baseline/` | 357 KB | 6 | v3 retriever + retrieval results + MANIFEST | KEEP — the retained v3 baseline |
| `v3_retrieval_chunk_evidence/` | 464 KB | 14 | v3 chunk-evidence snapshot + results + MANIFEST | KEEP — experiment-specific |

None is an exact full-repository duplicate (each contains only version-specific files with
MANIFEST hashes), so the instructions require keeping them.

---

## F. Everything else — KEPT (unchanged)

`graph_rag/`, `vector_rag/`, `streamlit_app/`, `utils/`, `docs/`, `experiments/`,
`config/`, `data/` (incl. `data/cache` and Neo4j import files), `evaluation/plots/`,
all `run_*.py`, `evaluator.py`, `evaluator_v2.py`, `metrics.py`, `metrics_v2.py`,
`report.py`, `questions_benchmark.py`, `README.md`, `requirements.txt`, `.gitignore`,
`iso-20022-payments-guide-2025-en.pdf` (benchmark PDF), the final report
(`docs/Final_Project_Report.{md,pdf,docx}` + `docs/diagrams/`), and
`final_cleanup_report.md`.

---

## Summary of removals

- **16 log files**
- **6 debugging/superseded folders** (~3.6 MB)
- **4 superseded report generators**

No code, no evaluation logic, no benchmark, no report content, no checkpoint, and no dataset
is modified or deleted.
