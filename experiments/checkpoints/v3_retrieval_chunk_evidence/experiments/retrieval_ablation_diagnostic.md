# Retrieval Ablation Diagnostic — page-level (v2) vs chunk-level (v3)

Zero-cost offline replay (no LLM calls, read-only Neo4j). 12 benchmark questions.

## Gate verdict

**PROCEED**

- GT-page attach (same def, QA-facing) v2=3 v3=5 (Δ+2)
- GT-chunk attach v2=0 v3=5 (Δ+5)
- evidence recall mean v2=0.4258 v3=0.6286 (Δ+0.2028)
- precision mean v2=0.0402 v3=0.0308
- v3 attaches chunk page RANGES (pages X-Y), v2 attaches single pages — same GT-page test applied to both.

## Aggregate

| Metric | v2 (page-level) | v3 (chunk-level) |
|---|---|---|
| GT-page attach (QA-facing, same def) | 3/12 | 5/12 |
| GT-chunk attach | 0/12 | 5/12 |
| Evidence recall (mean) | 0.4258 | 0.6286 |
| Precision (mean) | 0.0402 | 0.0308 |

## Per-question

| Q | GT pg | GT chunk(s) | candidates | v2 pg-on | v3 pg-on | v3 chunk-on | v2 rec | v3 rec | GT rank |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 2 | [0, 1] | 7 | True | False | False | 1.0 | 0.0 | 5 |
| 5 | 32 | [18] | 5 | False | True | True | 0.4286 | 1.0 | 1 |
| 7 | 2 | [0, 1] | 7 | True | True | True | 1.0 | 1.0 | 2 |
| 8 | 32 | [18] | 30 | False | True | True | 0.3333 | 1.0 | 2 |
| 27 | 53 | [29] | 5 | False | True | True | 0.4545 | 1.0 | 3 |
| 34 | 3 | [] | 24 | True | False | False | 0.2778 | 0.4444 | None |
| 45 | 53 | [29] | 5 | False | False | False | 0.375 | 0.5 | None |
| 46 | 53 | [29] | 5 | False | True | True | 0.2143 | 1.0 | 1 |
| 48 | 39 | [21] | 5 | False | False | False | 0.3636 | 0.6364 | None |
| 49 | 40 | [21] | 3 | False | False | False | 0.1818 | 0.1818 | None |
| 51 | 53 | [29] | 5 | False | False | False | 0.2083 | 0.4167 | None |
| 53 | 39 | [21] | 6 | False | False | False | 0.2727 | 0.3636 | None |

## Notes

- v2 = checkpointed `_fetch_source_context` (6 entities, first 2 pages each, 3 paras x 500 chars).
- v3 = `_fetch_chunk_context` (same entity match, ALL `source_chunks`, lexical rank, top-3 x 1200 chars).
- GT chunk = chunk covering the evidence page whose text contains all GT evidence tokens.
- GT rank = rank of the GT chunk in the live retriever's candidate ranking (1 = first).
- The earlier retrieval_diagnostic.md '6/12 GT-page attached' used a looser reachability
  definition (page in entity page-lists, no paragraph cap). This diagnostic measures the
  QA-facing context for both designs under their real caps, so v2 shows 3/12 here.
- No prompts, evaluator, QA model, temperature, or benchmark were changed.
