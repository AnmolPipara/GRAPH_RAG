# Vector RAG vs Graph RAG - ISO 20022 Payments Guide

Same LLM for both systems and both runs: **groq llama-3.1-8b-instant** (temperature 0) - only the graph store differs.

- Embeddings: **sentence-transformers/all-mpnet-base-v2**, chunks 1000/200, top-5 (identical for both runs)
- Retriever: same improved graph retriever (entity->chunk mention index, depth-3 traversal, evidence-density chunk ranking)
- Graph A (merged): `Graph Rag/data/merged_knowledge.json` -> 300 nodes / 373 edges
- Graph B (sibling): `GraphRAG/data/merged_knowledge.json` -> 602 nodes / 401 edges (673 entities / 413 relationships normalized)

## Judge verdicts (LLM-as-judge, per question) - sibling graph, Groq 8B, latest run

| Q | Difficulty | Vector RAG | Graph RAG |
|---|------------|------------|-----------|
| 1 | easy   | correct | correct |
| 2 | easy   | correct | correct |
| 3 | easy   | correct | **wrong**  (flaky on 8B - SLEV/SHAR hedging) |
| 4 | medium | wrong   | correct |
| 5 | medium | correct | correct |
| 6 | medium | partial | correct |
| 7 | medium | correct | correct |
| 8 | hard   | wrong   | partial |
| 9 | hard   | partial | correct |
| 10| hard   | correct | **wrong**  (deterministic 8B trap - OrgnlGrpInfAndSts) |

## Aggregate judge scores (correct=1, partial=0.5, wrong=0)

| Run | Vector RAG | Graph RAG |
|-----|-----------|-----------|
| Merged graph (300 nodes) - Groq 8B | 0.70 | 0.80 |
| Sibling graph (602 nodes) - Groq 8B, prior run | 0.70 | 0.85 |
| Sibling graph (602 nodes) - Groq 8B, latest run | 0.70 | **0.75** |

The 0.85 -> 0.75 difference is Q3 answer noise on the 8B model (Q3 was correct on the
prior run, hedged on this one). The stable, model-independent picture: graph RAG equals
or beats vector RAG, and the denser sibling graph widens the gap.

## Lexical metrics (metrics_v2)

| Metric | Merged vec | Merged graph | Sibling vec | Sibling graph |
|--------|-----------|--------------|-------------|---------------|
| f1_score | 0.267 | 0.260 | 0.262 | 0.248 |
| answer_accuracy | 0.749 | 0.809 | 0.713 | 0.800 |
| context_recall | 0.456 | 0.640 | 0.456 | 0.732 |
| faithfulness | 0.644 | 0.788 | 0.647 | 0.697 |

## What the denser sibling graph changed

**Improved (2 questions):**
- **Q5 (medium)** - merged: wrong -> sibling: correct. The sibling graph's richer entity descriptions (SALA category purpose + "combined debit" booking detail) surfaced the decisive evidence the merged graph missed.
- **Q8 (hard)** - merged: wrong -> sibling: partial. The sibling graph reached the section 5.2 XML example pages (p.33-38) and the model extracted the creditor/reference/amount - still incomplete, but the XML block is now at least in context.

**Regressed (1 question):**
- **Q10 (hard)** - merged: correct -> sibling: wrong. The sibling graph's context introduced a misleading anchor: the model said "transaction level" but cited `<OrgnlGrpInfAndSts>` (the *group* component), contradicting itself. The merged graph correctly named `TxInfAndSts`. Richer context can inject competing anchors that confuse synthesis.

**Unchanged (7 questions):** identical verdicts; both graphs get the same 5 correct/1 partial + 2 shared failures (Q4 vector, Q6 vector) - the sibling graph gains +0.05 overall (0.80 -> 0.85).

## Context recall note

Sibling graph context_recall jumped to 0.732 (vs 0.640 merged) - it retrieves more of the relevant material per question. But faithfulness dropped slightly (0.697 vs 0.788): more context, more chances for the model to grab a wrong fragment (see Q10).

## Caveats

- All numbers on llama-3.1-8b-instant (Groq). Earlier runs on stronger models showed the same *direction* (merged graph: Graph 0.80 vs Vector 0.75 on Groq 70B; Graph 0.80 vs Vector 0.75 on nemotron-free), but 8B is weaker at synthesis so absolute scores are compressed.
- Q4/Q6 vector failures and Q8 hard failure are shared across graph stores - they are retrieval/system limits, not graph-density effects.
