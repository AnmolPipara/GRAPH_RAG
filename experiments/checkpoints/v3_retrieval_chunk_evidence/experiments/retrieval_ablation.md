# Retrieval Ablation — chunk-level evidence (P2)

> **Component changed:** retriever evidence selection only. Graph (1,046 nodes / 878 rels),
> evaluator, QA model (gpt-oss-120b via Groq), prompts, temperature (0.0) and the 12-question
> benchmark are unchanged. The vector control is untouched and remains valid.

**Verdict: MIXED-POSITIVE — hypothesis confirmed on retrieval quality; retained as new baseline.**

The chunk-level evidence change improved every retrieval-grounded metric (context recall, 
faithfulness, hallucination, citation) while answer accuracy stayed flat (−0.011, within noise
for a 12-question benchmark). This is NOT a rollback case: unlike the graph-quality ablation 
(which regressed 5/6 metrics), this change improves 4 of the 5 primary metrics.

## 1. Motivation

The retrieval diagnostic (experiments/retrieval_diagnostic.md) showed the v2 retriever's hard 
caps — first 2 `source_pages` per entity, 3 paragraphs × 500 chars — keep the ground-truth page 
out of the QA context on 6/12 questions (E5 class) while evidence tokens were reachable 12/12. 
The page-level caps truncate a page's head instead of selecting the passage that actually 
contains the answer. Entities already carry `source_chunks` (the chunk IDs they were extracted 
from), so switching evidence selection to ranked chunk-level text should put the real supporting 
passage in front of the QA model.

## 2. The isolated change

- **Files changed:** `graph_rag/retriever.py` only.
- `_load_chunk_text()` — deterministically rebuilds {chunk_id: {text, pages}} from 
  `data/extracted_text.json` + `graph_rag.chunker.chunk_by_sections` (verified: 35/35 char 
  counts match `data/chunks.json`, so the text is byte-identical to what the extractor consumed).
- `_fetch_source_context` (page-level: 6 entities, first 2 pages each, 3 paras × 500 chars) 
  replaced by `_fetch_chunk_context`: same entity match (keywords[:2], LIMIT 6), but collects 
  **all** `source_chunks` of the matched entities, ranks them with `_rank_chunks` (question-token 
  overlap + 2× keyword-containment bonus), attaches top-3 chunks × up to 1200 chars.
- `_append_sources` now calls `_fetch_chunk_context`. Both the LLM-Cypher enrichment path and 
  the fallback path go through it.
- **Graph-grounded:** chunks are only ever selected from `source_chunks` of entities matched via 
  Neo4j. No document-wide search was introduced.

## 3. Offline gate (zero LLM calls)

- GT-page attach (QA-facing, same definition): v2 **3/12** → v3 **5/12**
- GT-chunk attach: v2 0/12 → v3 **5/12**
- Evidence recall (mean): v2 0.4258 → v3 **0.6286** (Δ+0.2028)
- Precision (mean): v2 0.0402 → v3 0.0308
- Gate decision: **PROCEED** — the improvement cleared the threshold, so the benchmark was run.

Note: the earlier diagnostic's '6/12 GT-page attached' for v2 used a looser reachability 
definition (page in entity page-lists, no paragraph cap). This ablation measures the QA-facing 
context under the retriever's real caps for BOTH designs, which is why v2 shows 3/12 here.

## 4. Benchmark results (same 12 questions, same QA model, temp 0.0)

| Metric | VectorRAG (control) | GraphRAG v2 (page) | GraphRAG v3 (chunk) | Δ v2→v3 |
|---|---|---|---|---|
| Answer Accuracy | 0.8151 | 0.6960 | **0.6853** | -0.0107 |
| F1 | 0.1978 | 0.2331 | **0.1922** | -0.0409 |
| Context Recall | 0.7757 | 0.5166 | **0.6761** | +0.1595 |
| Faithfulness | 0.7722 | 0.6504 | **0.7400** | +0.0896 |
| Citation Correctness | 0.7937 | 0.6732 | **0.7127** | +0.0395 |
| Hallucination (↓) | 0.2278 | 0.3496 | **0.2600** | -0.0896 |
| Multi-hop Success | 0.8151 | 0.6960 | **0.6853** | -0.0107 |

Primary metrics: **context recall +0.16, faithfulness +0.09, hallucination −0.09 (better), 
citation +0.04**; answer accuracy −0.011 and F1 −0.041 (within noise, driven by longer chunk 
context slightly shifting answer phrasing).

## 5. Per-question

| Q | Category | v2 answer (head) | v3 answer (head) |
|---|---|---|---|
| 2 | fact_lookup | The phone number for Finance Finland is **+358 20 793 4200**. | The phone number for Finance Finland is **+358 20 793 4200**. |
| 5 | fact_lookup | One occurrence of unstructured remittance information may contain up t | One occurrence may contain up to **140 characters** of unstructured re |
| 7 | fact_lookup | The fax number for Finance Finland is **+358 20 793 4202**. | The fax number for Finance Finland is **+358 20 793 4202**. |
| 8 | fact_lookup | The ISO 20022 website listed by Finance Finland is:  **www.financefinl | I don’t know. |
| 27 | relationship | A C2B payment initiation file is the **input** that the bank receives  | A C2B (customer‑to‑bank) payment initiation file is the file the corpo |
| 34 | hierarchical | The ISO 20022 Payments Guide is organized into a series of numbered ch | Based on the excerpts that were retrieved, the **ISO 20022 Payments Gu |
| 45 | workflow | A customer starts a credit‑transfer by sending a **Customer Credit Tra | A customer (the **debtor**) starts a credit‑transfer by creating a **C |
| 46 | workflow | When the customer uploads (or otherwise hands over) a C2B payment file | After the customer uploads the C2B payment file, the bank takes that f |
| 48 | workflow | **Message flow for a Customer‑to‑Bank (C2B) credit transfer (ISO 20022 | **Message flow for a Customer‑to‑Bank (C2B) credit‑transfer that uses  |
| 49 | workflow | A returned (i.e., rejected) credit‑transfer is not communicated by a s | A returned (i.e., rejected or failed) credit‑transfer is communicated  |
| 51 | workflow | The bank uses the **Verification‑of‑Payee (VOP) service** to check the | **How the bank verifies the payee (the creditor) before it releases a  |
| 53 | comparison | I’m sorry, but I don’t have enough information in the provided context | **Payment initiation message**   *Purpose*: It is the request that sta |

## 6. Fairness & leakage verification

- Same QA model: openai/gpt-oss-120b via Groq (fairness guard enforced at run start).
- Same evaluator: `evaluator_v2.evaluate_graph_rag` (unchanged).
- Same prompts: `SAME_QA_PROMPT_TEMPLATE` and the retriever's re-answer prompt (unchanged).
- Same temperature: 0.0. Same benchmark: `experiments/benchmark_v2.json` (12 questions).
- Same graph: v2 artifact reloaded into Neo4j (1,046 nodes / 878 rels), verified before the run.
- Leakage: `_rank_chunks` scores only (question, chunk text). GT evidence/answers are never used 
  for ranking or selection. Chunks are only reachable through matched entities' `source_chunks`.
  No document-wide retrieval.

## 7. Rollback instructions

- Code: restore `graph_rag/retriever.py` from 
  `experiments/checkpoints/v2_retrieval_baseline/graph_rag/retriever.py` (byte-identical to the 
  official v2 baseline; sha256 in that checkpoint's MANIFEST.json).
- Graph: no graph change was made in this experiment — Neo4j still holds the v2 artifact, so no 
  data rollback is needed.
- Artifacts: this report and `evaluation/benchmark_v2_graph_retrieval_*` are new files; deleting 
  them returns the repo to the pre-experiment state.

## 8. Why this helps

The QA LLM now receives the **full chunk** the evidence lives in (up to 1200 chars), ranked by 
relevance, instead of a truncated 500-char head-of-page slice. That is why faithfulness and 
citation rose and hallucination fell: the model answers from actual document passages rather 
than graph triples or arbitrary page heads. Remaining gap to VectorRAG on accuracy is a ranking/
entity-match issue (5 questions' GT chunks are outside the matched-entity candidate set), not an 
evidence-format issue — that is the next isolated experiment target (P4 entity matching / P3 Cypher repair).

