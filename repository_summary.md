# Repository Summary — GraphRAG

**Date:** 2026-08-03
**Repo:** `github.com/AnmolPipara/GRAPH_RAG` · branch `main`
**Status:** Cleaned for public release. All 55 file deletions are documented in `cleanup_plan.md`.

---

## Repository structure

```
GraphRAG/
├── config/            Pydantic settings; all secrets come from .env (not committed)
├── data/              Extracted text, chunks, knowledge graph JSONs, cache
│   └── cache/         Chunk cache (regenerable)
├── docs/              FINAL REPORT: Final_Project_Report.{md,pdf,docx} + diagrams/
├── evaluation/        Evaluators, metrics, run_*.py drivers, benchmark results
│   ├── plots/         Canonical evaluation plots
│   └── benchmark_v2_*.json   Final benchmark summaries & results (v1–v4)
├── experiments/       Ablation reports, diagnostics, checkpoints/ (v1–v4 snapshots)
│   └── checkpoints/   Frozen per-version experiment snapshots (MANIFEST-protected)
├── graph_rag/         GraphRAG pipeline: extraction → graph → Neo4j → retrieval
├── vector_rag/        VectorRAG baseline: chunking → embeddings → FAISS → retrieval
├── streamlit_app/     Interactive demo UI
├── utils/             LLM factory, HF client, Neo4j loader, logger, visualizer
├── .gitignore         Excludes .env, caches, editor files
├── README.md
├── requirements.txt
├── iso-20022-payments-guide-2025-en.pdf   Benchmark PDF dataset
└── *.py               Support scripts (checkpointing, rebuild, diagnostics)
```

## Purpose of every top-level folder

| Folder | Purpose |
|---|---|
| `graph_rag/` | The GraphRAG system — entity/relationship extraction, knowledge graph, Neo4j store, candidate generation, chunk retrieval, answer generation |
| `vector_rag/` | The baseline VectorRAG system — chunking, embeddings, FAISS index, dense retrieval |
| `evaluation/` | RAGAS-style evaluation — evaluators, metrics, run drivers, final benchmark JSONs and plots |
| `experiments/` | Evidence trail — ablation reports, offline diagnostics, and frozen checkpoints for every accepted version |
| `docs/` | The single official final report (`Final_Project_Report.{md,pdf,docx}`) and architecture diagrams |
| `streamlit_app/` | Interactive UI to query both systems |
| `utils/` | Shared infrastructure (LLM factory, Neo4j loader, logging, visualization) |
| `config/` | Central settings (secrets via environment, never committed) |
| `data/` | Pipeline data: extracted text, chunks, refined knowledge graphs, cache |

## Files removed in this cleanup

55 files/folders, fully documented in `cleanup_plan.md`:

- **16 run logs** (`evaluation/*.log`) — regenerable; not referenced
- **6 debugging/superseded folders** (`previous_groq120b_noenrich/`, `previous_groq70/`,
  `previous_groq8b/`, `previous_hf397b/`, `poisoned_quota/`, `stale_network_report/`) — superseded
  model-run results; `poisoned_quota/` is auto-recreated by `run_fair_eval.py`
- **4 superseded report generators** (`gen_construction_report.py`, `gen_quality_report.py`,
  `gen_retrieval_report.py`, `gen_final_docs.py`) — their outputs are deleted/archived; cannot
  regenerate the current `Final_Project_Report.*` (built by the removed `_tmp_build_report.py`)

### Reviewed and retained (deliberately)

- **All `benchmark_v2_*.json`** — final benchmark summaries/results, referenced by `run_*_eval.py`
- **Legacy v1 results** (`evaluation_results.json/csv`, `graph_rag_results.json`,
  `vector_rag_results.json`) — still read/written by `report.py`, `run_fair_eval.py`,
  `evaluator_v2.py`, `run_evaluation.py`; archived in `checkpoints/v1_source_evidence/`
- **All 5 checkpoints** — experiment-specific snapshots (MANIFEST-protected), not full repo duplicates
- **`experiments/` diagnostics, plots, question sets, PDF dataset, all source code**

## Repository size

| Metric | Before | After | Delta |
|---|---|---|---|
| Size (excl. `.git`) | 21 MB | 17 MB | −4 MB |
| Files on disk (excl. `.git`) | 295 | 242 | −53 |

## Verification

- ✅ **No code changed** — git diff shows only deletions (`D` entries); zero modifications
- ✅ **No benchmark changed** — all `benchmark_v2_*` JSONs untouched (verified via git status)
- ✅ **No evaluation changed** — evaluators, metrics, run scripts byte-identical
- ✅ **No report content changed** — `docs/Final_Project_Report.*` untouched
- ✅ **No checkpoints modified** — checkpoint files intact
- ✅ **All Python compiles** — 0 compile failures across the repo
- ✅ **Final report opens** — PDF valid, 12 pages, title verified
- ✅ **No broken imports** — generators removed are not imported anywhere
- ✅ **Git status clean** — after commit, working tree clean
