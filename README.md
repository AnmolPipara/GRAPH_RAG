# Vector RAG vs GraphRAG — Comparative RAG Study (ISO 20022 Payments Guide)

A research-grade, reproducible comparison of two retrieval-augmented generation (RAG) paradigms on the **same single-source document** — the *ISO 20022 Payments Guide 2025* (61 pages, PDF):

1. **Vector RAG** — classic semantic chunk retrieval with FAISS embeddings.
2. **GraphRAG** — knowledge-graph retrieval over Neo4j (Cypher) grounded in entities, relationships, and source-chunk provenance.

Both systems answer with the **same LLM and the same QA prompt** (temperature 0.0), so any quality difference is attributable to the retrieval layer alone.

---

## 🧠 Model Stack (final / official runs)

| Role | Model | Provider |
|---|---|---|
| QA (answer generation, shared by both systems) | `openai/gpt-oss-120b` | Groq (temperature 0.0) |
| Cypher generation (GraphRAG) | `openai/gpt-oss-120b` | Groq |
| Embeddings (Vector RAG) | `sentence-transformers/all-mpnet-base-v2` | local HuggingFace |
| Graph extraction / refinement | frontier LLM (≥70B) | configurable (`groq` / `openrouter` / `huggingface`) |

> The QA model is **identical for both systems** (enforced by the harness) so the comparison isolates retrieval strategy. `llama-3.3-70b-versatile` (also via Groq) remains the default fallback in `config/settings.py` for free-tier runs; the official v4 benchmark results in this repo were produced with `openai/gpt-oss-120b` via Groq.

---

## 🏗️ Architecture

### Vector RAG
- **PDF loader**: PyMuPDF (`fitz`)
- **Chunking**: `RecursiveCharacterTextSplitter` (1000 chars, 200 overlap)
- **Embeddings**: `sentence-transformers/all-mpnet-base-v2` (local)
- **Vector store**: FAISS (cached on disk)
- **QA model**: shared answer model (`openai/gpt-oss-120b` via Groq)

### GraphRAG
- **Knowledge extraction**: per-chunk LLM extraction (text + diagrams), cached in `data/`
- **Graph store**: Neo4j AuraDB (Cypher) · in-memory NetworkX for the offline benchmark
- **Cypher generation**: LLM-generated Cypher with a compact-schema prompt
- **Retrieval (v4)**: ranked-keyword entity matching → multi-hop traversal (depth ≤ 3) → entity-to-chunk mention index → evidence-density chunk ranking
- **QA model**: shared answer model (identical to Vector RAG for fairness)

---

## 📈 GraphRAG Evolution (v1 → v4)

The graph system evolved through four isolated, evidence-driven versions — each changing exactly one component:

| Version | Change | Outcome |
|---|---|---|
| **v1** | Original page-level evidence | Baseline; weak evidence reachability (context recall 0.384) |
| **v2** | Construction fix restoring full page provenance | Provenance restored |
| **v3** | Chunk-level evidence selection | Evidence reachability improved |
| **v4** | Candidate generation: ranked-keyword entity matching + deterministic entity cap | **Official baseline — first version to beat VectorRAG on grounding** |

---

## 📊 Official v4 Benchmark (12 questions · `openai/gpt-oss-120b` via Groq)

| Metric | Vector RAG | GraphRAG v4 | Better |
|---|---|---|---|
| **Context Recall** | 0.776 | **0.848** | Graph |
| **Faithfulness** | 0.772 | **0.778** | Graph |
| **Hallucination Rate ↓** | 0.228 | **0.222** | Graph |
| Answer Accuracy | **0.815** | 0.760 | Vector |
| Citation Correctness | **0.794** | 0.769 | Vector |
| Context Precision | **0.093** | 0.073 | Vector |

**Over the original implementation (v1), v4 improved:** context recall **+0.464** (0.384 → 0.848), faithfulness **+0.295** (0.483 → 0.778), hallucination rate **−0.295** (0.517 → 0.222).

**Conclusion:** GraphRAG v4 is the first version to exceed VectorRAG on grounding quality; the remaining gap is in answer generation and citation precision — **not in retrieval**.

Graph RAG's advantage is most visible on **multi-hop, code-anchored questions** (e.g., Q4 `UltimateCreditor` element, Q9 `pain.002.001.10` / `ACTC`) where entity identity and provenance beat lexical similarity. See `docs/Final_Project_Report.pdf` and `PROJECT_REPORT.md` for the full analysis.

---

## 📂 Project Structure

```text
GraphRAG/
├── benchmark_compare/     # multi-hop benchmark harness + results + FAISS cache
├── config/                # Pydantic settings (models, providers, Neo4j)
├── data/                  # extracted text, chunks, merged/refined knowledge graphs
├── docs/                  # Final_Project_Report.* (md / pdf / docx) + diagrams
├── evaluation/            # metrics_v2, evaluators, per-version summary JSONs, plots
├── experiments/           # ablation logs, checkpoints, diagnostics
├── graph_rag/             # extraction + Neo4j Cypher retriever (v4 candidate generation)
├── streamlit_app/         # side-by-side chat + evaluation UI
├── utils/                 # LLM factory, visualizer
├── vector_rag/            # FAISS vector pipeline
├── iso-20022-payments-guide-2025-en.pdf   # source document
├── PROJECT_REPORT.md      # complete project report (markdown)
└── README.md              # you are here
```

---

## 🚀 How to Run

### Setup
1. Create `.env` in this directory with your API keys (see `config/settings.py`):
   ```env
   GROQ_API_KEY=your_key            # required (QA / Cypher)
   OPENROUTER_API_KEY=your_key      # optional (extraction providers)
   NEO4J_URI=neo4j+s://<db_id>.databases.neo4j.io   # GraphRAG retriever
   NEO4J_USERNAME=neo4j
   NEO4J_PASSWORD=your_password
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Launch the Streamlit app (chat comparison + evaluation metrics)
```bash
streamlit run streamlit_app/app.py
```
Three tabs: **Vector RAG**, **Graph RAG**, and **Evaluation Metrics** (loads the official `benchmark_v2*_summary.json` results and plots the radar chart).

### Run the multi-hop benchmark
```bash
# Merged graph (default)
python benchmark_compare/benchmark_compare.py

# Sibling graph (denser, 602 nodes)
GRAPH_DATA=sibling python benchmark_compare/benchmark_compare.py
```

### Run the GraphRAG interactive retriever (requires Neo4j)
```bash
python graph_rag/retriever.py
```

---

## 📄 Reports

- **`docs/Final_Project_Report.{md,pdf,docx}`** — the final formatted deliverable (title page, TOC, diagrams).
- **`PROJECT_REPORT.md`** — complete technical report: overview, architecture, evolution, benchmark results, and the two questions where Graph RAG clearly beats Vector RAG.
- **`docs/`** — full documentation and diagrams.
