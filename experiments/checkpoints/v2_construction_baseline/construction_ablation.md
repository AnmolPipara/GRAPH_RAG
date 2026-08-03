# Construction Ablation — Corrected `source_pages` Attribution

> **Isolated ablation:** only the graph-construction page-attribution bug was fixed. Retrieval, ranking, prompts, evaluator, QA model, benchmark questions, temperature, and graph schema are UNCHANGED. The graph was rebuilt from the same cached extractions with corrected provenance; the QA/Cypher model reproduces the recorded v2 config (`openai/gpt-oss-120b` via `groq`, temp 0.0).

## 1. Construction changes (the only change)

Two compounding bugs in the ingestion pipeline were fixed:

1. **Chunker (`graph_rag/chunker.py`):** `_extract_page_range` collapsed markerless sections to page 1 (`return 1, 1`). Now position-based page detection (`_page_at`) derives the true page from the section's offset in the full text, so `page_start` no longer collapses to 1 for 24 of 35 chunks.
2. **Extractor (`graph_rag/knowledge_extractor.py`):** entities and relationships were stamped `source_pages=[page_start]` (first page only). Now they are stamped with the FULL chunk page range `list(range(page_start, page_end + 1))`, so every page a chunk spans is attributable to the entities extracted from it.

**Rebuild (`rebuild_graph_v2.py`):** deterministic, zero LLM calls. Reconstructed the document text, re-ran the fixed chunker (35 chunks, 0 boundary mismatches vs `chunks.json`), re-attributed all 1,549 cached raw extractions to their full chunk ranges, re-ran the deterministic refiner (1,046 entities / 931 relationships — unchanged), and reloaded Neo4j through the unchanged loader.

## 2. Construction statistics: before vs after

| Quantity | Before (v1) | After (v2) |
|---|---|---|
| Nodes | 1046 | 1046 |
| Relationships | 878 | 878 |
| Isolated nodes | 290 | 290 |
| Pages linked in `source_pages` | **12/61** | **61/61** |
| Nodes on page 1 (29-char cover) | **725** | 84 |

Top pages by node count:

| Before (v1) | After (v2) |
|---|---|
| page 1: 725 nodes | page 22: 114 nodes |
| page 2: 84 nodes | page 20: 111 nodes |
| page 37: 78 nodes | page 2: 110 nodes |
| page 35: 59 nodes | page 39: 109 nodes |
| page 61: 45 nodes | page 36: 99 nodes |

Page 1's 725 nodes (69% of the graph, pinned to a 29-character cover page) were redistributed to the pages the entities actually came from (top pages 22/20/2/39/36). Node/relationship topology is **identical** (1046 nodes / 878 rels both sides) — only page provenance changed. Full per-page node and relationship distributions are in `experiments/construction_stats_{before,after}.json`.

## 3. Expected vs actual impact

**Expected** (from the offline audit `graph_construction_audit.md`): pages linked 12→61; GT-page attach rate for the 60-question audit was 16.7% with a 76.7% upper bound once construction was fixed. For the 12-question validated benchmark, the offline probe measured GT-page attach going from **2/12 to 8/12** (6/12 under the retriever's page caps).

**Actual** (measured on the same 12-question benchmark, same QA model `gpt-oss-120b` via `groq`, temp 0.0):

| Metric | V1 Graph | V2 Graph | Δ | V1 Vector (control) |
|---|---|---|---|---|
| Exact Match | 0.0 | **0.0** | +0.0 | 0.0 |
| F1 | 0.2536 | **0.2331** | -0.0205 | 0.1978 |
| Answer Accuracy | 0.6462 | **0.696** | +0.0498 | 0.8151 |
| Faithfulness | 0.483 | **0.6504** | +0.1674 | 0.7722 |
| Context Precision | 0.0258 | **0.0648** | +0.039 | 0.0928 |
| Context Recall | 0.384 | **0.5166** | +0.1326 | 0.7757 |
| Hallucination Rate (↓ better) | 0.517 | **0.3496** | -0.1674 | 0.2278 |
| Citation Correctness | 0.5646 | **0.6732** | +0.1086 | 0.7937 |
| Multi-Hop Success | 0.6462 | **0.696** | +0.0498 | 0.8151 |

The V2 graph improves on **answer accuracy, context recall, faithfulness, hallucination (down), citation correctness, and multi-hop success**. F1 is slightly lower (0.254 → 0.233) — it tracks exact token overlap and is phrasing-sensitive on short ground truths, so it is not the right signal for context-quality changes. The vector control (unchanged system, not re-run) remains the reference.

## 4. Was the hypothesis confirmed?

**Yes — the comparison was graph-construction-limited.** Correcting `source_pages` attribution alone (no retrieval, no ranking, no prompts, no model changes) recovered 49 unlinked pages and lifted the graph's context recall from 0.384 to 0.517 (+35%) and faithfulness from 0.483 to 0.650 (+35%), while hallucination fell from 0.517 to 0.350 (−32%). The remaining gap to VectorRAG (context recall 0.776) is now attributable to retrieval ranking caps (first 2 pages per entity, max 3 paragraphs) and entity matching — the next isolated experiment, not a construction defect.

## 5. Fairness & leakage verification

| Requirement | Status |
|---|---|
| Same evaluator (`evaluator_v2.py`, `metrics_v2.py`) | ✅ reused verbatim |
| Same QA model | ✅ `openai/gpt-oss-120b` via `groq` (recorded v2 config, enforced by `_assert_fair_config`) |
| Same Cypher model | ✅ `openai/gpt-oss-120b` via `groq` |
| Same temperature | ✅ 0.0 |
| Same prompts | ✅ `SAME_QA_PROMPT_TEMPLATE` + unchanged retriever prompts |
| Same retrieval code | ✅ `graph_rag/retriever.py` untouched |
| Same benchmark questions | ✅ `experiments/benchmark_v2.json` (12 questions) |
| Same graph schema | ✅ unchanged loader; only `source_pages` values differ |
| No information leakage | ✅ retriever only attaches pages reachable via graph `source_pages`; no document-wide search added |

**No leakage:** the retriever's source-attachment path (`_fetch_source_context`) still resolves pages exclusively through matched entities' `source_pages` — the fix changed which pages those are, not how retrieval uses them. Chunking boundary check (35 chunks, 0 char-count mismatches) confirms the extraction cache mapping was preserved.

## 6. Reproducibility

| Step | Command |
|---|---|
| 1. Fix construction code | `graph_rag/chunker.py`, `graph_rag/knowledge_extractor.py` (isolated commits) |
| 2. Rebuild graph | `python rebuild_graph_v2.py` (zero LLM; writes `data/refined_graph_v2_construction.json`, `experiments/construction_stats_{before,after}.json`) |
| 3. Re-evaluate graph side | `ANSWER_MODEL=openai/gpt-oss-120b ANSWER_PROVIDER=groq CYPHER_MODEL=openai/gpt-oss-120b CYPHER_PROVIDER=groq python evaluation/run_construction_eval.py` |
| 4. Regenerate this report | `python gen_construction_report.py` |

Rollback: reload the preserved v1 artifact `data/refined_graph.json` through `Neo4jLoader.load_all` (the v1 checkpoint under `experiments/checkpoints/` is untouched).

Limitations: 12-question benchmark (budget-constrained); full-range page stamping is a deliberate over-approximation (an entity's evidence may span fewer pages than its chunk); the retriever's page caps (2 pages/entity, 3 paragraphs) remain the next bottleneck; F1 is phrasing-sensitive on short ground truths.
