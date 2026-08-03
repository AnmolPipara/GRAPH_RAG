# Final Cleanup Report — GraphRAG

**Date:** August 3, 2026
**Scope:** Removal of superseded *documentation* only. The project is frozen (v4 candidate generation is the official baseline).
**Principle:** Delete ONLY documentation files that have been replaced by the single official report (`Final_Project_Report.md` / `.pdf` / `.docx`). Keep every source file, evaluation JSON, benchmark output, checkpoint, plot, dataset, experiment artifact, and diagnostic file.

---

## A. Files removed (all superseded documentation)

| # | File | Reason for removal | Replacement document |
|---|---|---|---|
| 1 | `cleanup_report.md` | Previous cleanup audit (Aug 2) — superseded by this report | `final_cleanup_report.md` |
| 2 | `docs/Final_Report.md` | Old final report (covered only v1/v2; predates v3/v4) | `docs/Final_Project_Report.md` |
| 3 | `docs/Final_Report.pdf` | Old final report PDF (v1/v2 only) | `docs/Final_Project_Report.pdf` |
| 4 | `docs/Final_Report.docx` | Old final report DOCX (v1/v2 only) | `docs/Final_Project_Report.docx` |
| 5 | `docs/project_report.html` | Interim progress report (Jul 31) | `docs/Final_Project_Report.*` |
| 6 | `docs/project_report.pdf` | Interim progress report PDF (Jul 31) | `docs/Final_Project_Report.pdf` |
| 7 | `experiments/ABLATION_PROTOCOL.md` | Intermediate methodology draft | Final report §6 (Evolution) |
| 8 | `experiments/ABLATION_REPORT.md` | Intermediate ablation write-up | Final report §6, §8 |
| 9 | `experiments/benchmark_comparison.md` | Early comparison draft | Final report §8 (Evaluation) |
| 10 | `experiments/construction_ablation.md` | v2 experiment report (already archived in `checkpoints/v2_construction_baseline/` and `checkpoints/v2_retrieval_baseline/`) | Final report §6.2 |
| 11 | `experiments/quality_ablation.md` | v3-quality (rejected) experiment report; archived in `checkpoints/v3_retrieval_chunk_evidence/` | Final report §6 (rejected experiments) |
| 12 | `experiments/retrieval_ablation.md` | v3 retrieval experiment report (archived in `checkpoints/v3_retrieval_baseline/` and `checkpoints/v3_retrieval_chunk_evidence/`) | Final report §6.3 |
| 13 | `experiments/candidate_gen_ablation.md` | v4 experiment report; per-question data remains in `evaluation/benchmark_v2_graph_candidategen_results.json` | Final report §6.4, §8 |
| 14 | `experiments/FINAL_EVALUATION_REPORT.md` | Pre-v4 evaluation report | Final report §8 |
| 15 | `experiments/final_cross_version_comparison.md` | Cross-version comparison (Aug 3) — superseded by the final report's consolidated evaluation | Final report §8 |
| 16 | `experiments/improvements_roadmap.md` | Roadmap draft | Final report §11 (Future Work) |

**Deletion totals:** 16 files — all documentation. Zero source, data, checkpoint, plot, or artifact files deleted.

---

## B. Files reviewed and KEPT (not deletable under the freeze)

| Category | Examples | Why kept |
|---|---|---|
| Source code | `graph_rag/*.py`, `vector_rag/*.py`, `evaluation/*.py`, `utils/*.py`, `config/`, `streamlit_app/`, `rebuild_graph_v2.py`, `requirements.txt` | The frozen system |
| Final metrics | `evaluation/benchmark_v2_summary.json`, `benchmark_v2_graph_construction_summary.json`, `benchmark_v2_graph_retrieval_summary.json`, `benchmark_v2_graph_candidategen_summary.json` (+ per-question `*_results.json`, vector results, `evaluation_results.json`, `graph_rag_results.json`) | Required to reproduce the final report tables |
| Benchmarks & logs | `experiments/benchmark_v2.json`, `benchmark_audit_data.json`, all `*.log` run traces | Evidence of config fairness |
| Checkpoints | `experiments/checkpoints/**` (incl. archived `construction_ablation.md`, `retrieval_ablation.md`, `retrieval_diagnostic.md` inside checkpoint dirs) | Frozen baselines with SHA manifests; also preserve copies of the removed reports |
| Plots | `evaluation/plots/*.png` | Result visualizations |
| Datasets & graph data | `iso-20022-payments-guide-2025-en.pdf`, `data/*.json`, `data/cache/chunk_*.json`, `vector_rag/db/faiss/` | Source document, graph artifacts, vector DB |
| Diagnostics & audits | `experiments/root_cause_analysis.md`, `retrieval_analysis.md`, `retrieval_diagnostic.md`, `retrieval_ablation_diagnostic.md`, `graph_construction_audit.md`, `graph_quality_audit.md`, `benchmark_validation_report.md` + all `.py` audit scripts and `.json` diagnostics | Diagnostic evidence — explicitly protected |
| Archives | `evaluation/previous_*`, `poisoned_quota/`, `stale_network_report/` | Historical run archives preserved for the paper |

---

## C. Verification notes

- **No** source file, evaluation JSON, benchmark output, checkpoint, plot, dataset, or diagnostic was deleted.
- The removed experiment reports remain available inside their checkpoint archives (`checkpoints/v2_construction_baseline/`, `checkpoints/v2_retrieval_baseline/`, `checkpoints/v3_retrieval_baseline/`, `checkpoints/v3_retrieval_chunk_evidence/`).
- All metric values cited in the new final report are read directly from the retained summary JSONs listed in section B; no benchmarks were re-run.
- The new report set `docs/Final_Project_Report.{md,pdf,docx}` and `docs/diagrams/` are the only additions.

**Conclusion:** 16 unambiguous documentation deletions. The repository is frozen with GraphRAG v4 (Candidate Generation) as the official baseline and `Final_Project_Report.*` as the single official project documentation.
