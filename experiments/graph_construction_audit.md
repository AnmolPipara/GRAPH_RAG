# Graph Construction Audit — Forensic Trace of `source_pages`

> **Scope:** trace all 61 PDF pages through the 6-stage ingestion pipeline (extraction → chunking → knowledge extraction → refinement → Neo4j → statistics) and identify exactly where the 49 unlinked pages disappear. **Pure offline diagnostic: zero LLM calls, no graph writes, no re-extraction, no retrieval changes.** All numbers below are reproduced deterministically from `data/` artifacts + read-only Neo4j queries.

## Headline finding

**The 49 unlinked pages were NOT skipped by the pipeline — their text was fully extracted and fed to the LLM inside multi-page chunks. The pages disappeared at the *page-attribution* step: entities and relationships are stamped with `source_pages = [chunk.page_start]` only (the chunk's FIRST page), and the chunker assigned `page_start = 1` to 24 of 35 chunks — so 1004 of 1549 raw entities (64.8%) were stamped with page 1, a cover page containing 29 characters.**

- Pages with text: **61/61** (only page 1 is near-empty: 29 chars — the cover).
- Chunk coverage: **all 61 pages** are covered by ≥1 chunk (pages 1–61, none missing).
- Chunking reproduces `data/chunks.json` **exactly** (0 page-range mismatches across 35 chunks).
- Distinct chunk `page_start` values: `[1, 2, 7, 14, 29, 35, 37, 52, 57, 59, 60, 61]` — **identical to the 12 pages linked in Neo4j `source_pages`.**
- Neo4j: page 1 holds **725 of 1046 nodes (69.3%)** and 580 of 878 relationships — the single largest page bucket, for a page with 29 characters of text.

## Root cause — two compounding bugs (no LLM, no graph issue)

### Bug A (Stage 2 — chunker): `page_start` collapses to 1

`_extract_page_range()` returns `(1, 1)` whenever a section's text contains no `[PAGE N]` marker, and `chunk_by_sections()` locks a batch's `page_start` to the **first** section added to it:

```python
def _extract_page_range(text):
    pages = re.findall(r"\[PAGE (\d+)\]", text)
    if pages:
        page_nums = [int(p) for p in pages]
        return min(page_nums), max(page_nums)
    return 1, 1   # <-- no markers in section text -> page 1
```

Of **334 detected sections**, **274 (82.0%)** contain no `[PAGE N]` marker (section text that does not cross a page boundary and is not headed by a marker). A batch whose first such section is markerless gets `page_start = 1` forever, even as later sections push `page_end` up to 10–13.

Chunk `page_start` histogram: `{1: 24, 2: 1, 7: 1, 14: 1, 29: 1, 35: 1, 37: 1, 52: 1, 57: 1, 59: 1, 60: 1, 61: 1}` — **24 of 35 chunks (68.6%)** start at page 1.

### Bug B (Stage 3 — extractor): only `page_start` is written, never the range

`_validate_entity()` / `_validate_relationship()` stamp a single page:

```python
source_pages=[page_start] if page_start else []   # first page ONLY
```

- **0 of 1549** raw entities/relationships carry more than one page in `source_pages`.
- Raw entity `source_pages` distribution by chunk `page_start`: `{'1': 1004, '2': 87, '7': 36, '14': 31, '29': 36, '35': 59, '37': 81, '52': 38, '57': 44, '59': 32, '60': 39, '61': 62}` — **1004 entities stamped page 1 (64.8%)**.

**Net effect:** the set of pages that can EVER appear in `source_pages` is exactly the set of chunk `page_start` values — `{1, 2, 7, 14, 29, 35, 37, 52, 57, 59, 60, 61}`. Pages 3–6, 8–13, 15–28, 30–34, 36, 38–51, 53–56, 58 are structurally unreachable, even though their text was extracted, chunked, and processed by the LLM.

## Stage-by-stage page loss

| Stage | Pages present | Pages with page-level attribution | Loss |
|---|---|---|---|
| S1 PDF extraction | 61 (text extracted per page) | 61 | 0 |
| S2 Chunking | 61 (covered by ≥1 chunk) | 12 (distinct page_start) | 49 |
| S3 Knowledge extraction | 61 (text fed to LLM) | 12 (source_pages=[page_start]) | 49 |
| S4 Refinement (merge) | 12 | 12 (union of page_starts) | 0 |
| S5 Neo4j ingestion | 12 | 12 (source_pages written as-is) | 0 |
| S6 Statistics | 12 | 12 | 0 |

**Pages disappear at Stage 2/3 (page attribution), not at extraction or ingestion.** Stages 4–6 are faithful: refinement unions `source_pages`, Neo4j writes them as-is, and 0 nodes have empty `source_pages`.

## Classification of the 49 unlinked pages

| Hypothesis | Pages | % of 49 |
|---|---|---|
| H1 — never processed | 0 | 0.0% |
| H2 — processed but produced no entities | 0 | 0.0% |
| H3 — produced entities but lost source_pages | 49 | 100.0% |
| H4 — dropped during graph construction | 0 | 0% |

**All 49 pages fall into H3.** Every missing page has substantive text (800–4,700 chars), is covered by ≥1 chunk, and the covering chunk(s) produced entities — but none of those entities cite the page in `source_pages`.

**Legitimacy check (expected vs bug):** no missing page is legitimately empty. The only near-empty page is **page 1 (29 chars, cover) — and it is the most-linked page in the graph (725 nodes)**, which is itself the clearest symptom of the attribution bug, not an expected outcome.

## Per-page statistics (61 pages)

> Columns: text length (chars, S1) · entities extracted = entities from chunks whose text spans the page (S3) · relationships extracted (S3) · nodes created = Neo4j nodes with the page in `source_pages` (S5) · source_pages written (S5).

| Page | Text len | Entities extracted | Rels extracted | Nodes created | source_pages | Status |
|---|---|---|---|---|---|---|
| 1 | 29 | 1004 | 686 | 725 | YES | LINKED |
| 2 | 4710 | 1091 | 712 | 84 | YES | LINKED |
| 3 | 2571 | 1004 | 686 | 0 | no | H3-LOST-SOURCE_PAGES |
| 4 | 3224 | 971 | 660 | 0 | no | H3-LOST-SOURCE_PAGES |
| 5 | 2641 | 908 | 643 | 0 | no | H3-LOST-SOURCE_PAGES |
| 6 | 1548 | 883 | 622 | 0 | no | H3-LOST-SOURCE_PAGES |
| 7 | 1139 | 892 | 627 | 36 | YES | LINKED |
| 8 | 1996 | 892 | 627 | 0 | no | H3-LOST-SOURCE_PAGES |
| 9 | 1223 | 856 | 599 | 0 | no | H3-LOST-SOURCE_PAGES |
| 10 | 975 | 856 | 599 | 0 | no | H3-LOST-SOURCE_PAGES |
| 11 | 1628 | 827 | 581 | 0 | no | H3-LOST-SOURCE_PAGES |
| 12 | 1790 | 827 | 581 | 0 | no | H3-LOST-SOURCE_PAGES |
| 13 | 1458 | 773 | 530 | 0 | no | H3-LOST-SOURCE_PAGES |
| 14 | 1547 | 770 | 525 | 31 | YES | LINKED |
| 15 | 985 | 770 | 525 | 0 | no | H3-LOST-SOURCE_PAGES |
| 16 | 1056 | 770 | 525 | 0 | no | H3-LOST-SOURCE_PAGES |
| 17 | 1485 | 739 | 501 | 0 | no | H3-LOST-SOURCE_PAGES |
| 18 | 1119 | 739 | 501 | 0 | no | H3-LOST-SOURCE_PAGES |
| 19 | 1535 | 708 | 474 | 0 | no | H3-LOST-SOURCE_PAGES |
| 20 | 1669 | 708 | 474 | 0 | no | H3-LOST-SOURCE_PAGES |
| 21 | 1186 | 678 | 447 | 0 | no | H3-LOST-SOURCE_PAGES |
| 22 | 1518 | 678 | 447 | 0 | no | H3-LOST-SOURCE_PAGES |
| 23 | 1582 | 574 | 423 | 0 | no | H3-LOST-SOURCE_PAGES |
| 24 | 1014 | 541 | 398 | 0 | no | H3-LOST-SOURCE_PAGES |
| 25 | 1007 | 541 | 398 | 0 | no | H3-LOST-SOURCE_PAGES |
| 26 | 1314 | 541 | 398 | 0 | no | H3-LOST-SOURCE_PAGES |
| 27 | 1480 | 541 | 398 | 0 | no | H3-LOST-SOURCE_PAGES |
| 28 | 1789 | 512 | 371 | 0 | no | H3-LOST-SOURCE_PAGES |
| 29 | 1294 | 512 | 375 | 36 | YES | LINKED |
| 30 | 1130 | 512 | 375 | 0 | no | H3-LOST-SOURCE_PAGES |
| 31 | 1835 | 512 | 375 | 0 | no | H3-LOST-SOURCE_PAGES |
| 32 | 2253 | 476 | 338 | 0 | no | H3-LOST-SOURCE_PAGES |
| 33 | 1105 | 426 | 307 | 0 | no | H3-LOST-SOURCE_PAGES |
| 34 | 1298 | 426 | 307 | 0 | no | H3-LOST-SOURCE_PAGES |
| 35 | 1148 | 451 | 348 | 59 | YES | LINKED |
| 36 | 1047 | 451 | 348 | 0 | no | H3-LOST-SOURCE_PAGES |
| 37 | 996 | 473 | 317 | 78 | YES | LINKED |
| 38 | 838 | 473 | 317 | 0 | no | H3-LOST-SOURCE_PAGES |
| 39 | 1904 | 473 | 317 | 0 | no | H3-LOST-SOURCE_PAGES |
| 40 | 1724 | 392 | 283 | 0 | no | H3-LOST-SOURCE_PAGES |
| 41 | 1584 | 358 | 250 | 0 | no | H3-LOST-SOURCE_PAGES |
| 42 | 1126 | 358 | 250 | 0 | no | H3-LOST-SOURCE_PAGES |
| 43 | 1524 | 315 | 228 | 0 | no | H3-LOST-SOURCE_PAGES |
| 44 | 1351 | 315 | 228 | 0 | no | H3-LOST-SOURCE_PAGES |
| 45 | 1220 | 256 | 198 | 0 | no | H3-LOST-SOURCE_PAGES |
| 46 | 862 | 256 | 198 | 0 | no | H3-LOST-SOURCE_PAGES |
| 47 | 868 | 256 | 198 | 0 | no | H3-LOST-SOURCE_PAGES |
| 48 | 861 | 215 | 164 | 0 | no | H3-LOST-SOURCE_PAGES |
| 49 | 1449 | 215 | 164 | 0 | no | H3-LOST-SOURCE_PAGES |
| 50 | 1328 | 215 | 164 | 0 | no | H3-LOST-SOURCE_PAGES |
| 51 | 1814 | 170 | 125 | 0 | no | H3-LOST-SOURCE_PAGES |
| 52 | 2586 | 157 | 115 | 38 | YES | LINKED |
| 53 | 2425 | 119 | 78 | 0 | no | H3-LOST-SOURCE_PAGES |
| 54 | 1987 | 78 | 52 | 0 | no | H3-LOST-SOURCE_PAGES |
| 55 | 947 | 41 | 22 | 0 | no | H3-LOST-SOURCE_PAGES |
| 56 | 1247 | 41 | 22 | 0 | no | H3-LOST-SOURCE_PAGES |
| 57 | 1275 | 44 | 42 | 44 | YES | LINKED |
| 58 | 1480 | 44 | 42 | 0 | no | H3-LOST-SOURCE_PAGES |
| 59 | 2063 | 32 | 15 | 32 | YES | LINKED |
| 60 | 1286 | 39 | 11 | 39 | YES | LINKED |
| 61 | 878 | 62 | 33 | 45 | YES | LINKED |

## Expected improvement if page attribution were fixed

**Fix (not implemented here):** stamp each entity/relationship with the FULL chunk page range `[page_start..page_end]` (or per-paragraph page attribution), and stop collapsing markerless sections to page 1. This is a construction change — no retrieval, no evaluator, no QA model changes.

| Quantity | Now | After fix (bound) |
|---|---|---|
| Pages linked in `source_pages` | 12/61 | 61/61 (all) |
| Nodes attributable to page 1 | 725 | ~0 (redistributed to real pages) |
| GT-page attach rate (pipeline-attached) | 10/60 = 16.7% | ≤ 46/60 = 76.7% (8 OK + 38 category-4 questions from root_cause_analysis.md) |

The 38 category-4 questions in `root_cause_analysis.md` are exactly the questions whose ground-truth page is linked to **no** node in the graph. Re-linking pages to the entities extracted from their text would make those pages attachable, raising the attach rate from 16.7% toward the 76.7% bound. The remaining gap to 100% is the retrieval ranking caps (first 2 pages per entity, max 3 paragraphs) — the next bottleneck after construction.

## Is the GraphRAG vs VectorRAG comparison retrieval-limited or construction-limited?

**Evidence says construction-limited, decisively:**

1. Retrieval diagnostics are healthy: entity-matching accuracy 0.983 (`retrieval_analysis.md`), and root-cause categories 1–3 (extraction failure, unmatched entity, missing source_pages) each account for **0** of 60 questions.
2. The 16.7% GT-page attach rate is a *hard structural ceiling*, not a ranking defect: only 12 of 61 pages exist in `source_pages` at all, and 69% of the graph is pinned to a 29-character cover page. **No retriever can attach a page that the graph never links.**
3. The one page-attach failure that IS retrieval-related (category 5, ranking caps) accounts for exactly 1 of 60 questions.

**Conclusion:** the v1 comparison understates GraphRAG because the graph construction stage discards page-level provenance for 49/61 pages before retrieval ever runs. The correct next experiment is to repair construction (full-range `source_pages`), keep retrieval fixed, and re-run the same 12-question validated benchmark — an isolated, measurable ablation.

## Reproducibility

- Chunking reproduction check: `0` page-range mismatches vs `data/chunks.json` (deterministic, no LLM).
- Full text reconstructed: 92672 chars, 61 `[PAGE N]` markers (matches S1).
- Neo4j totals: 1046 nodes / 878 relationships; 0 nodes with empty `source_pages`.
- Raw extractions: 1549 raw entities → 1046 deduped; 1038 raw rels → 931 deduped (pipeline_statistics.json; diagnostic sum: 1549).

Regenerate with: `python experiments/graph_construction_audit.py`
