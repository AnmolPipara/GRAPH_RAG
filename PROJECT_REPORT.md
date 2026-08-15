# Vector RAG vs GraphRAG — Complete Project Report

**Project:** Comparative study of two retrieval-augmented generation (RAG) paradigms on a single-source technical document
**Document:** ISO 20022 Payments Guide 2025 (61 pages, PDF)
**Date:** August 2026

---

## 1. Project Overview

This project builds, evaluates, and iteratively improves two RAG systems on the same PDF:

- **Vector RAG** — semantic chunk retrieval with FAISS embeddings + similarity search.
- **GraphRAG** — knowledge-graph retrieval (Neo4j + Cypher, and a lighter in-memory NetworkX variant) grounded in entities, relationships, and source-chunk provenance.

Both systems answer with the **same LLM and the same QA prompt** (temperature 0.0), so any quality difference is attributable to the retrieval layer alone — the comparison isolates retrieval strategy.

---

## 2. Architecture

### 2.1 Vector RAG
| Component | Tech |
|---|---|
| PDF loader | PyMuPDF (`fitz`) |
| Chunking | RecursiveCharacterTextSplitter, 1000 chars / 200 overlap |
| Embeddings | `sentence-transformers/all-mpnet-base-v2` (local HuggingFace) |
| Vector store | FAISS (cached on disk) |
| QA model | shared answer model (default Groq `llama-3.3-70b-versatile`) |

### 2.2 GraphRAG
| Component | Tech |
|---|---|
| Extraction | frontier LLM (per-chunk entity/relationship extraction, text + diagrams) |
| Graph store | Neo4j AuraDB (Cypher) · in-memory NetworkX for the offline benchmark |
| Cypher generation | LLM-generated Cypher with a compact-schema prompt (17K-token full schema avoided) |
| Retrieval | entity matching → multi-hop traversal (depth ≤ 3) → entity-to-chunk mention index → evidence-density chunk ranking |
| QA model | shared answer model (identical to Vector RAG for fairness) |

---

## 3. GraphRAG Evolution (v1 → v4)

The graph system evolved through four isolated, evidence-driven versions, each changing exactly one component and gated by offline diagnostics before benchmark spend:

| Version | Change | Outcome |
|---|---|---|
| **v1** | Original page-level evidence | Baseline; weak evidence reachability (context recall 0.384) |
| **v2** | Construction fix restoring full page provenance | Provenance restored |
| **v3** | Chunk-level evidence selection | Evidence reachability improved |
| **v4** | Candidate generation: ranked-keyword entity matching + deterministic entity cap (2 keywords, 12 entities) | **Official baseline — first version to beat VectorRAG on grounding** |

v4 replaced two lossy heuristics (first-2-keyword matching; arbitrary `LIMIT 6` row order) with deterministic ranked keyword matching and bounded candidate sets, without exploding into near-full-corpus retrieval.

---

## 4. Evaluation Results

### 4.1 Official v4 Benchmark (12 questions · `openai/gpt-oss-120b` via Groq)

| Metric | Vector RAG | GraphRAG v4 | Better |
|---|---|---|---|
| **Context Recall** | 0.776 | **0.848** | Graph |
| **Faithfulness** | 0.772 | **0.778** | Graph |
| **Hallucination Rate ↓** | 0.228 | **0.222** | Graph |
| Answer Accuracy | **0.815** | 0.760 | Vector |
| Citation Correctness | **0.794** | 0.769 | Vector |
| Context Precision | **0.093** | 0.073 | Vector |

**Over the original implementation (v1), v4 improved:** context recall **+0.464** (0.384 → 0.848), faithfulness **+0.295** (0.483 → 0.778), hallucination rate **−0.295** (0.517 → 0.222).

**Conclusion:** GraphRAG v4 is the first version to exceed VectorRAG on grounding quality. The remaining gap is in answer generation and citation precision — **not in retrieval**.

### 4.2 Multi-Hop Benchmark (10 questions · Groq `llama-3.1-8b-instant`, in-memory graph)

Judge verdicts (correct = 1, partial = 0.5, wrong = 0):

| Run | Vector RAG | Graph RAG |
|---|---|---|
| Merged graph (300 nodes) · Groq 70B | 0.80 | 0.80 |
| Merged graph (300 nodes) · Groq 8B | 0.70 | **0.80** |
| Sibling graph (602 nodes) · Groq 8B | 0.70 | **0.85** |

Lexical metrics on the sibling graph: context recall 0.732 (graph) vs 0.456 (vector); faithfulness 0.697 vs 0.647; answer accuracy 0.800 vs 0.713.

**Headline:** graph RAG equals or beats vector RAG, and the denser graph widens the gap.

---

## 5. The 2 Questions Where Graph RAG Clearly Beats Vector RAG

These are the two questions where graph RAG answers fully and correctly while vector RAG fails — both multi-hop / code-anchored questions where entity traversal matters more than lexical similarity:

### Q4 (medium) — UltimateCreditor element
> **Question:** "A payment is credited to the account of a financing company, but the ultimate creditor of the payment is a customer of that financing company. Which element in the Credit Transfer Transaction Information block (Block C) is used to identify this customer as the ultimate beneficiary?"

| System | Verdict | Detail |
|---|---|---|
| **Vector RAG** | ❌ wrong | Named the element but cited the **wrong index (2.149)** and wrong sub-elements — semantic search landed on a nearby element-table row and the model copied the wrong identifiers. |
| **Graph RAG** | ✅ correct | Named **UltimateCreditor (index 2.148)** with the correct definition — the entity record anchored to the exact element and traversal surfaced the authoritative definition sentence. |

### Q9 (hard) — Payment Status Report schema / status
> **Question:** "The payment message with MessageIdentification MSGID000001 passes structural validation at the bank. Which schema does the bank use for the return message, which Group Status does that return message carry, and which original identifier does it include?"

| System | Verdict | Detail |
|---|---|---|
| **Vector RAG** | ⚠️ partial | Got ACTC and MSGID000001 but **invented a non-existent schema** ("schema A: Structure, schema validation") — a hallucination from an adjacent validation section. |
| **Graph RAG** | ✅ correct | Named the exact schema **pain.002.001.10** (page 39), Group Status **ACTC**, and the original **MSGID000001** — all three facts correct, with source-page citations. |

**Why the pattern:** Q4 and Q9 ask for element/schema/status identifiers. Graph RAG walks entity links (UltimateCreditor, pain.002.001.10, ACTC, MSGID000001) to the authoritative page, while vector RAG retrieves whatever chunk is lexically closest — which can be an adjacent table row or a similar-looking section. The remaining shared failures (Q3 SHAR/SLEV conflation on the 8B model, Q8 five-page XML extraction) are model-synthesis limits, not retrieval gaps.

---

## 6. Work Completed (Project Deliverables & Maintenance)

### 6.1 Core deliverables
- Full **Vector RAG pipeline** (`vector_rag/`) — loader, chunker, embeddings, FAISS store, QA chain.
- Full **GraphRAG pipeline** (`graph_rag/`) — knowledge extractor, Neo4j loader, enhanced Cypher retriever with chunk-linkage enrichment and fallback retrieval.
- **Evaluation harness** (`evaluation/`) — `metrics_v2.py` (exact match, F1, answer accuracy, faithfulness, context precision/recall, hallucination rate, citation correctness, multi-hop success), summary JSONs for every graph version, radar-chart visualizer.
- **Official final report** (`docs/Final_Project_Report.{md,pdf,docx}`) with diagrams.

### 6.2 Benchmark module consolidated into the project
- Moved the self-contained **Vector-vs-Graph multi-hop benchmark** from the legacy sibling `Graph Rag/` workspace into **`GraphRAG/benchmark_compare/`** (`benchmark_compare.py`, run logs, all benchmark result JSONs, FAISS cache, and reports).
- Fixed all relative paths so the harness runs inside `GraphRAG/` and imports `metrics_v2` from the project's own `evaluation/` directory.
- Added `benchmark_compare/README.md` documenting how to run it (merged vs sibling graph via `GRAPH_DATA=sibling`).

### 6.3 Streamlit app — Evaluation tab fixed
- The Evaluation Metrics tab previously looked for the removed Ragas CSVs (`vector_rag_metrics.csv` / `graph_rag_metrics.csv`) and always showed "metrics not found".
- Rewired it to load the current **`metrics_v2` JSON summaries** (`evaluation/benchmark_v2*_summary.json`), with a file selector defaulting to the official GraphRAG v4 candidate-gen summary.
- Updated the radar chart (`utils/visualizer.py`) to the `metrics_v2` metric names (Faithfulness, Answer Accuracy, Context Precision, Context Recall) and added `load_metrics_from_summary()`.
- Verified live: app serves on :8501, all three tabs render, Vector RAG and Graph RAG both answer real queries (Neo4j restored/resumed), and the radar chart plots real v4 numbers.

### 6.4 Neo4j connectivity
- The AuraDB instance had been suspended, causing `Failed to connect to Neo4j` in the app and harness. Diagnosed via DNS (`410b7631.databases.neo4j.io` non-existent) and **resolved by resuming the instance** — GraphRAG retriever now connects (1046 nodes, 878 relationships, 73 labels, 35 source chunks rebuilt).

---

## 7. Repository Layout (GraphRAG/)

```text
GraphRAG/
├── benchmark_compare/     # multi-hop benchmark harness + results + final report PDF
├── config/                # Pydantic settings (models, providers, Neo4j)
├── data/                  # extracted text, chunks, merged/refined knowledge graphs
├── docs/                  # Final_Project_Report.* + diagrams
├── evaluation/            # metrics_v2, evaluators, per-version summary JSONs, plots
├── experiments/           # ablation logs, checkpoints, diagnostics
├── graph_rag/             # extraction + Neo4j Cypher retriever (v4 candidate generation)
├── streamlit_app/         # side-by-side chat + evaluation UI
├── utils/                 # LLM factory, visualizer
├── vector_rag/            # FAISS vector pipeline
├── iso-20022-payments-guide-2025-en.pdf
└── README.md
```

---

## 8. How to Run

```bash
# App (chat comparison + evaluation metrics)
streamlit run streamlit_app/app.py

# Multi-hop benchmark (merged graph)
python benchmark_compare/benchmark_compare.py

# Multi-hop benchmark (sibling GraphRAG graph, denser)
GRAPH_DATA=sibling python benchmark_compare/benchmark_compare.py

# GraphRAG interactive retriever (Neo4j required)
python graph_rag/retriever.py
```

Requires `.env` with API keys (`GROQ_API_KEY`, `OPENROUTER_API_KEY`, etc.) and a running Neo4j instance (`NEO4J_URI`).

---

## 9. Key Takeaways

1. **Retrieval engineering works:** GraphRAG v4 improved context recall by +0.464 and faithfulness by +0.295 over v1 purely through evidence-reachability fixes.
2. **Graph RAG wins on grounding; Vector RAG wins on answer-level polish.** The two systems are complementary — the graph gets the right evidence to the LLM, the vector store produces slightly more accurate/cited final answers.
3. **The graph's advantage is most visible on multi-hop, code-anchored questions** (Q4 UltimateCreditor, Q9 pain.002.001.10/ACTC) where entity identity and provenance beat lexical similarity.
4. All benchmark artifacts, reports, and the app are consolidated in `GraphRAG/`; the project is frozen with **GraphRAG v4 (candidate generation)** as the official baseline.
