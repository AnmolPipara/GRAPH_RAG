# benchmark_compare — Vector RAG vs Graph RAG (Multi-Hop QA Benchmark)

Self-contained benchmark harness comparing **Vector RAG** (FAISS + embeddings) against **Graph RAG**
(in-memory NetworkX graph with entity→chunk mention indexing and depth-3 traversal) on a 10-question
multi-hop QA benchmark built from the ISO 20022 Payments Guide 2025.

This module was consolidated into `GraphRAG/` from the legacy sibling `Graph Rag/` workspace
(previously a separate git repo). All artifacts now live here.

## Layout

```text
benchmark_compare/
├── benchmark_compare.py   # the harness (Vector RAG + Graph RAG + LLM-judge + metrics)
├── benchmark_run.log      # last full run trace
├── data/
│   ├── extracted_text.json            # page-per-entry text extraction of the 61-page guide
│   ├── graph_rag_questions.json       # 10 multi-hop questions (3 easy / 4 medium / 3 hard) + reference answers
│   ├── merged_knowledge.json          # this benchmark's 300-entity / 373-edge graph extraction
│   ├── raw_extractions.json           # raw SLM/VLM extractions behind the merged graph
│   ├── faiss_index/                   # cached FAISS index (skips rebuild on re-run)
│   ├── benchmark_results.json         # merged-graph run (Groq 8B)
│   ├── benchmark_progress.json        # checkpoint for the above (resumable)
│   ├── benchmark_results_sibling_8b.json   # sibling-graph run (Groq 8B)
│   ├── benchmark_progress_sibling_8b.json  # checkpoint for the above
│   ├── benchmark_comparison.md        # generated report for the latest sibling run
│   ├── sibling_vs_merged_8b.md        # merged-vs-sibling graph comparison write-up
│   └── final_report.pdf               # 📄 THE FINAL REPORT (3 pages, Aug 2026)
```

## Running

```bash
# merged graph (default, 300 nodes)
python benchmark_compare.py

# sibling graph (the main GraphRAG 673-entity extraction, normalized to 602 nodes / 401 edges)
GRAPH_DATA=sibling python benchmark_compare.py
```

Requires an API key in `../.env` (`GROQ_API_KEY` / `OPENROUTER_API_KEY` / `OPENAI_API_KEY` —
provider chosen via `ANSWER_PROVIDER`, default `groq`). Dependencies (faiss-cpu, networkx,
langchain-community, langchain-huggingface, sentence-transformers, python-dotenv) are already in
`GraphRAG/requirements.txt`. Results resume from `data/benchmark_progress.json` if interrupted.

## Headline result

Same LLM for both systems, only retrieval differs. Across graph stores and models the stable picture is:
**Graph RAG equals or beats Vector RAG, and the denser graph widens the gap.**

| Run | Vector RAG | Graph RAG |
|-----|-----------|-----------|
| Merged graph (300 nodes) — Groq 70B | 0.80 | 0.80 |
| Merged graph (300 nodes) — Groq 8B | 0.70 | 0.80 |
| Sibling graph (602 nodes) — Groq 8B (best) | 0.70 | 0.85 |

See `data/final_report.pdf` for the full report and `data/sibling_vs_merged_8b.md` for the
merged-vs-sibling comparison.
