# Root-Cause Analysis — why is the ground-truth page attached only 16.7% of the time?


Pure offline diagnostic — **zero LLM calls**, no retrieval changes, no graph edits. Every benchmark question is traced through the v1 pipeline's own non-LLM components (keyword extraction → CONTAINS entity match → 1-hop neighbors → source_pages → attachment caps) and each GT-page miss is classified into exactly one of 9 categories.


## Methodology


- Pipeline replication (from `graph_rag/retriever.py`): keywords = `_extract_entity_keywords(question)`; match = CONTAINS on `name`/`canonical_name`/`aliases`/`description` for the **first two** keywords, LIMIT **6** entities; attached pages = first **2** pages per entity, dedup, max **3** paragraphs.

- Ground-truth page = `best_page` from `experiments/benchmark_audit_data.json` (same source as Phase 4).

- Two attach definitions: **(a) pipeline-attached** = GT page survives the caps (LIMIT 6 entities, first 2 pages/entity, max 3 paragraphs) — this is the number that actually reaches the QA LLM and it reproduces the Phase-4 headline **10/60 = 0.167** exactly; **(b) linked-union** = GT page in *any* page linked to a matched entity (a looser upper bound, 11/60). The classification uses definition (a).

- Per-question parity note: the Phase-4 table's Y/N flags were produced by a now-deleted diagnostic (`tmp_retrieval_diag.py`) whose exact page-collection caps cannot be recovered; its aggregate (10/60 = 0.167) is reproduced here exactly, and the per-question set differs on at most one question (Q39/Q54 swap, a page-collection ordering artifact). This appendix's definitions are fully documented and deterministic (matched entities name-ordered), so every row is reproducible.

- Category 7 (correct chunks retrieved but QA failed) **cannot be observed offline** — it requires a QA run. Zero questions are assigned to it by design.

## Failure-category summary


| # | Category | Questions | % of failures | % of all 60 |
|---|----------|-----------|---------------|-------------|
| 1 | Entity extraction failure | 0 | 0.0% | 0.0% |
| 2 | Entity exists but was not matched | 0 | 0.0% | 0.0% |
| 3 | Entity matched but missing source_pages | 0 | 0.0% | 0.0% |
| 4 | Wrong source_pages linked during graph construction | 38 | 73.1% | 63.3% |
| 5 | Correct pages linked but retrieval ranking discarded them | 1 | 1.9% | 1.7% |
| 6 | Correct pages retrieved but chunk selection discarded them | 0 | 0.0% | 0.0% |
| 7 | Correct chunks retrieved but QA still failed | 0 | 0% | 0% — not observable offline (needs QA run) |
| 8 | Benchmark issue (unsupported or incorrect ground truth) | 12 | 23.1% | 20.0% |
| 9 | Other | 1 | 1.9% | 1.7% |
| — | **OK — GT page attached (success)** | **8** | — | **13.3%** |
| — | **Total failures** | **52** | 100% | 86.7% |

> Note on definitions: the **pipeline-attached** count (the number that reaches the QA LLM) = **10/60 = 16.7%** — this reproduces `retrieval_analysis.md`'s 0.167 exactly. The looser linked-union (GT page in any page of a matched entity) = **11/60 = 18.3%**. The summary's OK row (8) is the subset of pipeline-attached questions whose GT is *valid* — Q2 and Q7 also attach (pipeline-attached = 10) but are classified as category 8 because their ground truths were audited unsupported, so the OK row is 8.

## Expected maximum improvement if each category were fixed independently


Fixing one category recovers its questions only; the attach rate cannot exceed (successes + that category) / 60. Estimates assume each fix is perfect and isolated (ablation contract: one component changed at a time).


| # | Category | Questions | Max attach rate if fixed | Fix cost |
|---|----------|-----------|--------------------------|----------|
| 1 | Entity extraction failure | 0 | 13.3% | Low — Better keyword extractor (noun-phrase heuristics) |
| 2 | Entity exists but was not matched | 0 | 13.3% | Low–Med — Alias/synonym/fuzzy matching; use ALL keywords, not just first 2 |
| 3 | Entity matched but missing source_pages | 0 | 13.3% | High — Backfill source_pages during ingestion (page-level provenance) |
| 4 | Wrong source_pages linked during graph construction | 38 | 76.7% | High — Re-link source_pages during graph construction |
| 5 | Correct pages linked but retrieval ranking discarded them | 1 | 15.0% | Very low — Relax caps: LIMIT 6→more, pages[:2]→all, 3→more paragraphs |
| 6 | Correct pages retrieved but chunk selection discarded them | 0 | 13.3% | Med — Chunk-level evidence selection with semantic ranking |
| 8 | Benchmark issue (unsupported or incorrect ground truth) | 12 | already repaired (v2 benchmark) | Already repaired → benchmark_v2.json (12 corrected questions) |
| 9 | Other | 1 | 15.0% | High — Re-run extraction with a frontier model for missing entities |

### Highest-impact bottleneck


The single biggest recoverable cause is **category 4: Wrong source_pages linked during graph construction** (38 questions). Fixing it alone would raise the pipeline-attached GT-page rate from **13.3%** to **76.7%** — the recommended next experiment.


## Per-question retrieval trace


Legend — `Kw`: extracted keywords · `Matched`: matched entities (all / LIMIT-6 subset) · `Rel`: 1-hop relationship rows · `Linked`: pages linked to matched entities · `Attach`: pages the pipeline would attach · `GT pg`: ground-truth page · `GT?`: GT page ∈ linked-union (looser bound) · `Att?`: GT page pipeline-attached (reproduces Phase-4 0.167) · `ChunkR`: chunk-level recall of GT tokens · `Fail cat`: failure category.


| ID | Cat | Keywords | Matched | Rel | Linked | Attach | GT pg | GT? | Att? | ChunkR | Fail cat | Reason |
|----|-----|----------|---------|-----|--------|--------|-------|-----|------|--------|----------|--------|
| 1 | fact_lookup | Finance Finland | 7→6 | 9 | 1,2,61 | 1,2 | 2 | Y | Y | 0.857 | OK — GT page attached (success) | GT page attached by the pipeline (success). |
| 2 | fact_lookup | Finance Finland | 7→6 | 9 | 1,2,61 | 1,2 | 2 | Y | Y | 0.75 | Benchmark issue (unsupported or incorrect ground truth) | Ground truth audited UNSUPPORTED (Phase 1); page cannot validate a wrong GT. |
| 3 | fact_lookup | ISO 20022 Payments Guide | 2→2 | 23 | 1,2,7,14,29,57,60, | 1,2 | 3 | N | N | 0.25 | Wrong source_pages linked during graph construction | GT page 3 is linked to NO node in the graph (page never linked during construction). |
| 4 | fact_lookup | ISO 20022 Payments Guide | 2→2 | 23 | 1,2,7,14,29,57,60, | 1,2 | 2 | Y | Y | 0.5 | OK — GT page attached (success) | GT page attached by the pipeline (success). |
| 5 | fact_lookup | guide | 12→6 | 25 | 1,2,7,14,29,57,60, | 1,2 | 31 | N | N | 1.0 | Benchmark issue (unsupported or incorrect ground truth) | Ground truth audited UNSUPPORTED (Phase 1); page cannot validate a wrong GT. |
| 6 | fact_lookup | ISO 20022 Payments Guide | 2→2 | 23 | 1,2,7,14,29,57,60, | 1,2 | 1 | Y | Y | 1.0 | OK — GT page attached (success) | GT page attached by the pipeline (success). |
| 7 | fact_lookup | Finance Finland | 7→6 | 9 | 1,2,61 | 1,2 | 1 | Y | Y | 0.667 | Benchmark issue (unsupported or incorrect ground truth) | Ground truth audited UNSUPPORTED (Phase 1); page cannot validate a wrong GT. |
| 8 | fact_lookup | ISO 20022, Finance Finland | 21→6 | 25 | 1,2,29 | 2,1,29 | 4 | N | N | 0.5 | Benchmark issue (unsupported or incorrect ground truth) | Ground truth audited UNSUPPORTED (Phase 1); page cannot validate a wrong GT. |
| 9 | definition | ISO 20022 | 14→6 | 25 | 1,2,7,14,29,35,37, | 2,1,29 | 59 | Y | N | 0.444 | Correct pages linked but retrieval ranking discarded them | GT page 59 linked to matched entities but dropped by caps (LIMIT 6 entities / 2 pages per  |
| 10 | definition | Group Header, ISO 20022 | 25→6 | 25 | 1,2,29 | 2,1,29 | 8 | N | N | 0.182 | Wrong source_pages linked during graph construction | GT page 8 is linked to NO node in the graph (page never linked during construction). |
| 11 | definition | Debtor | 24→6 | 25 | 1,2,7,14,35,37,57 | 1,57,35 | 6 | N | N | 0.375 | Wrong source_pages linked during graph construction | GT page 6 is linked to NO node in the graph (page never linked during construction). |
| 12 | definition | Credit Transfer Transaction | 18→6 | 25 | 1,2,29,35,37,61 | 2,35,37 | 20 | N | N | 0.455 | Wrong source_pages linked during graph construction | GT page 20 is linked to NO node in the graph (page never linked during construction). |
| 13 | definition | Remittance Information | 27→6 | 25 | 1,2,29,52,59 | 2,59,29 | 29 | Y | Y | 0.273 | OK — GT page attached (success) | GT page attached by the pipeline (success). |
| 14 | definition | BIC | 15→6 | 15 | 1,35,37 | 1,37,35 | 4 | N | N | 0.25 | Wrong source_pages linked during graph construction | GT page 4 is linked to NO node in the graph (page never linked during construction). |
| 15 | definition | IBAN | 10→6 | 12 | 1,35,37,52,57,59,6 | 52,37,57 | 12 | N | N | 0.286 | Wrong source_pages linked during graph construction | GT page 12 is linked to NO node in the graph (page never linked during construction). |
| 16 | definition | Payment Status Report | 19→6 | 25 | 1 | 1 | 39 | N | N | 0.875 | Wrong source_pages linked during graph construction | GT page 39 is linked to NO node in the graph (page never linked during construction). |
| 17 | multi_hop | ISO 20022 | 14→6 | 25 | 1,2,7,14,29,35,37, | 2,1,29 | 4 | N | N | 0.727 | Wrong source_pages linked during graph construction | GT page 4 is linked to NO node in the graph (page never linked during construction). |
| 18 | multi_hop | message, types, used | 112→6 | 25 | 1,2,52 | 1,2,52 | 12 | N | N | 0.333 | Wrong source_pages linked during graph construction | GT page 12 is linked to NO node in the graph (page never linked during construction). |
| 19 | multi_hop | Payment Information | 40→6 | 25 | 1,2 | 2,1 | 8 | N | N | 0.364 | Wrong source_pages linked during graph construction | GT page 8 is linked to NO node in the graph (page never linked during construction). |
| 20 | multi_hop | payment, routed, debtor | 245→6 | 25 | 1,2 | 2,1 | 6 | N | N | 0.75 | Wrong source_pages linked during graph construction | GT page 6 is linked to NO node in the graph (page never linked during construction). |
| 21 | multi_hop | entities, involved, direct | 5→5 | 5 | 1,7 | 1,7 | 6 | N | N | 0.5 | Wrong source_pages linked during graph construction | GT page 6 is linked to NO node in the graph (page never linked during construction). |
| 22 | multi_hop | ISO 20022 Payments Guide | 2→2 | 23 | 1,2,7,14,29,57,60, | 1,2 | 2 | Y | Y | 0.571 | OK — GT page attached (success) | GT page attached by the pipeline (success). |
| 23 | multi_hop | pain.001, pain.002, messages | 14→6 | 14 | 1 | 1 | 53 | N | N | 0.4 | Wrong source_pages linked during graph construction | GT page 53 is linked to NO node in the graph (page never linked during construction). |
| 24 | multi_hop | Credit Transfer Transaction  | 13→6 | 19 | 1,2,7,29,35,37 | 2,35,37 | 22 | N | N | 0.333 | Wrong source_pages linked during graph construction | GT page 22 is linked to NO node in the graph (page never linked during construction). |
| 25 | relationship | ISO 20022, Finance Finland | 21→6 | 25 | 1,2,29 | 2,1,29 | 2 | Y | Y | 0.583 | OK — GT page attached (success) | GT page attached by the pipeline (success). |
| 26 | relationship | Debtor, Creditor | 98→6 | 25 | 1,14,37,52,57 | 1,52,14 | 7 | N | N | 0.667 | Wrong source_pages linked during graph construction | GT page 7 linked only to unmatched nodes ['Account', 'Account Owner', 'Bank'] (wrong/extra |
| 27 | relationship | pain.001, relate, pacs.008 | 25→6 | 25 | 1 | 1 | 4 | N | N | 0.25 | Benchmark issue (unsupported or incorrect ground truth) | Ground truth audited UNSUPPORTED (Phase 1); page cannot validate a wrong GT. |
| 28 | relationship | Block B, Block C | 6→6 | 25 | 1,2,7,14,29 | 2,1 | 8 | N | N | 0.625 | Wrong source_pages linked during graph construction | GT page 8 is linked to NO node in the graph (page never linked during construction). |
| 29 | relationship | IBAN | 10→6 | 12 | 1,35,37,52,57,59,6 | 52,37,57 | 18 | N | N | 0.333 | Wrong source_pages linked during graph construction | GT page 18 is linked to NO node in the graph (page never linked during construction). |
| 30 | relationship | Charge Bearer | 2→2 | 5 | 1,57 | 1,57 | 19 | N | N | 0.375 | Wrong source_pages linked during graph construction | GT page 19 is linked to NO node in the graph (page never linked during construction). |
| 31 | relationship | Clearing Code | 1→1 | 1 | 1 | 1 | 4 | N | N | 0.125 | Wrong source_pages linked during graph construction | GT page 4 is linked to NO node in the graph (page never linked during construction). |
| 32 | relationship | pain.002, relate, pain.001 | 13→6 | 25 | 1,2,7,14,29 | 1,2 | 53 | N | N | 0.182 | Wrong source_pages linked during graph construction | GT page 53 is linked to NO node in the graph (page never linked during construction). |
| 33 | hierarchical | hierarchical, structure, pay | 37→6 | 25 | 1,2 | 2,1 | 8 | N | N | 0.091 | Wrong source_pages linked during graph construction | GT page 8 is linked to NO node in the graph (page never linked during construction). |
| 34 | hierarchical | ISO 20022 Payments Guide | 2→2 | 23 | 1,2,7,14,29,57,60, | 1,2 | 3 | N | N | 0.222 | Benchmark issue (unsupported or incorrect ground truth) | Ground truth audited UNSUPPORTED (Phase 1); page cannot validate a wrong GT. |
| 35 | hierarchical | Payment Type Information | 6→6 | 8 | 1,14,35,37 | 1,14,35 | 21 | N | N | 0.286 | Wrong source_pages linked during graph construction | GT page 21 is linked to NO node in the graph (page never linked during construction). |
| 36 | hierarchical | Remittance Information | 27→6 | 25 | 1,2,29,52,59 | 2,59,29 | 2 | Y | Y | 0.25 | OK — GT page attached (success) | GT page attached by the pipeline (success). |
| 37 | hierarchical | ISO 20022 | 14→6 | 25 | 1,2,7,14,29,35,37, | 2,1,29 | 4 | N | N | 0.25 | Wrong source_pages linked during graph construction | GT page 4 is linked to NO node in the graph (page never linked during construction). |
| 38 | hierarchical | hierarchy, party, identifier | 38→6 | 25 | 1,2,7,57,59,60,61 | 59,61,1 | 23 | N | N | 0.25 | Wrong source_pages linked during graph construction | GT page 23 is linked to NO node in the graph (page never linked during construction). |
| 39 | cross_section | address, formatted, across | 34→6 | 25 | 1,2,52 | 2,1,52 | 57 | N | N | 0.556 | Wrong source_pages linked during graph construction | GT page 57 linked only to unmatched nodes ['1010', '123', '15'] (wrong/extra entity pages  |
| 40 | cross_section | common, elements, appear | 9→6 | 17 | 1 | 1 | 2 | N | N | 0.333 | Wrong source_pages linked during graph construction | GT page 2 linked only to unmatched nodes ['1.1 Usage of ISO 20022 in Finland', '1.2 Addres |
| 41 | cross_section | currency, specified, across | 13→6 | 13 | 1 | 1 | 23 | N | N | 0.364 | Wrong source_pages linked during graph construction | GT page 23 is linked to NO node in the graph (page never linked during construction). |
| 42 | cross_section | identification, methods, use | 75→6 | 25 | 1,57,60,61 | 60,57,61 | 23 | N | N | 0.333 | Wrong source_pages linked during graph construction | GT page 23 is linked to NO node in the graph (page never linked during construction). |
| 43 | cross_section | amounts, formatted, across | 2→2 | 2 | 1 | 1 | 2 | N | N | 0.143 | Wrong source_pages linked during graph construction | GT page 2 linked only to unmatched nodes ['1.1 Usage of ISO 20022 in Finland', '1.2 Addres |
| 44 | cross_section | regulations, referenced, acr | 0→0 | 0 | — | — | 19 | N | N | 0.0 | Other | Entity absent from knowledge graph (graph-construction gap). |
| 45 | workflow | workflow, initiating, credit | 6→6 | 9 | 1,7,35 | 35,1,7 | 6 | N | N | 0.2 | Benchmark issue (unsupported or incorrect ground truth) | Ground truth audited UNSUPPORTED (Phase 1); page cannot validate a wrong GT. |
| 46 | workflow | direct, debit, process | 26→6 | 25 | 1,2,7,59 | 2,7,1 | 6 | N | N | 0.222 | Benchmark issue (unsupported or incorrect ground truth) | Ground truth audited UNSUPPORTED (Phase 1); page cannot validate a wrong GT. |
| 47 | workflow | happens, payment, rejected | 245→6 | 25 | 1,2 | 2,1 | 40 | N | N | 0.2 | Wrong source_pages linked during graph construction | GT page 40 is linked to NO node in the graph (page never linked during construction). |
| 48 | workflow | sequence, messages, cross-bo | 3→3 | 3 | 1 | 1 | 4 | N | N | 0.0 | Benchmark issue (unsupported or incorrect ground truth) | Ground truth audited UNSUPPORTED (Phase 1); page cannot validate a wrong GT. |
| 49 | workflow | payment, cancellation, proce | 245→6 | 25 | 1,2 | 2,1 | 40 | N | N | 0.231 | Benchmark issue (unsupported or incorrect ground truth) | Ground truth audited UNSUPPORTED (Phase 1); page cannot validate a wrong GT. |
| 50 | workflow | end-to-end, payment, process | 252→6 | 25 | 1,2 | 2,1 | 4 | N | N | 0.0 | Wrong source_pages linked during graph construction | GT page 4 is linked to NO node in the graph (page never linked during construction). |
| 51 | workflow | failed, payment, investigati | 246→6 | 25 | 1,2 | 2,1 | 12 | N | N | 0.167 | Benchmark issue (unsupported or incorrect ground truth) | Ground truth audited UNSUPPORTED (Phase 1); page cannot validate a wrong GT. |
| 52 | workflow | payment, status, change | 293→6 | 25 | 1,2,52 | 2,1,52 | 3 | N | N | 0.25 | Wrong source_pages linked during graph construction | GT page 3 is linked to NO node in the graph (page never linked during construction). |
| 53 | comparison | difference, between, pain.00 | 7→6 | 9 | 1 | 1 | 4 | N | N | 0.333 | Benchmark issue (unsupported or incorrect ground truth) | Ground truth audited UNSUPPORTED (Phase 1); page cannot validate a wrong GT. |
| 54 | comparison | credit, transfer, differ | 142→6 | 25 | 1,2,7,52 | 2,1,7 | 2 | Y | Y | 0.333 | OK — GT page attached (success) | GT page attached by the pipeline (success). |
| 55 | comparison | Unstructured Remittance | 2→2 | 2 | 1,59 | 1,59 | 28 | N | N | 0.125 | Wrong source_pages linked during graph construction | GT page 28 is linked to NO node in the graph (page never linked during construction). |
| 56 | comparison | SEPA, Finnish | 60→6 | 25 | 1,52,60,61 | 1,61,60 | 9 | N | N | 0.2 | Wrong source_pages linked during graph construction | GT page 9 is linked to NO node in the graph (page never linked during construction). |
| 57 | comparison | Block A, Block B | 5→5 | 25 | 1,2,7,14,29,35,37 | 2,35,1 | 33 | N | N | 0.444 | Wrong source_pages linked during graph construction | GT page 33 is linked to NO node in the graph (page never linked during construction). |
| 58 | comparison | Debtor Agent, Creditor Agent | 5→5 | 10 | 1,7,35,37,57 | 35,37,1 | 6 | N | N | 0.571 | Wrong source_pages linked during graph construction | GT page 6 is linked to NO node in the graph (page never linked during construction). |
| 59 | comparison | difference, between, pain.00 | 7→6 | 9 | 1 | 1 | 12 | N | N | 0.182 | Wrong source_pages linked during graph construction | GT page 12 is linked to NO node in the graph (page never linked during construction). |
| 60 | comparison | Settlement Date, Execution D | 10→6 | 10 | 1,35,37,60 | 60,1,35 | 8 | N | N | 0.5 | Wrong source_pages linked during graph construction | GT page 8 is linked to NO node in the graph (page never linked during construction). |

## Interpretation


- Categories **1–5 & 9** are upstream retrieval failures — fixing them is what raises the attach rate.

- Category **4** (wrong/missing page linkage at construction) and category **2** (match strategy) are graph-side, not ranking-side — they cost more to fix than category 5.

- Category **5** (ranking caps) is the cheapest win whenever it is non-empty: relaxing `LIMIT 6` / `pages[:2]` / `max 3` needs no re-extraction.

- Category **6** is a *future* risk: the current pipeline attaches page text, not chunks, so page-attach successes are not yet gated on chunks; if a later experiment moves to chunk-level evidence, low `ChunkR` rows are the ones to watch.

- Category **8** = the 12 already-repaired benchmark questions (`benchmark_v2.json`); their GT pages could never validate the old GTs.

- Cross-reference: `retrieval_analysis.md` (Phase 4) reports the same 0.167 attach rate, 0.983 entity-match accuracy, and 0.396 chunk recall; this appendix adds the *reason* for every miss, which Phase 4 deliberately did not include.

