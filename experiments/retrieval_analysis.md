# Retrieval Analysis — offline diagnostics (no LLM calls)

Retrieval behavior of the GraphRAG pipeline over all 60 benchmark questions, measured
with the pipeline's own non-LLM components: keyword extraction, the 1-hop neighbor
fallback Cypher, and source-page attachment. All evidence stays graph-grounded
(only `source_pages` of matched entities are read).

## Graph structure (live Neo4j)

- Total nodes: **1046** | relationships: **878**
- Degree — min **1**, max **34**, mean **2.32**, median **1.0**
- Isolated nodes (degree 0): **290** (27.7% of all nodes)

## Aggregate retrieval metrics (60 questions)

| Metric | Value |
|---|---|
| Avg keywords extracted / question | 1.98 |
| Avg matched entities / question | 19.68 |
| Entity-matching accuracy (>=1 entity matched) | 0.983 |
| Avg degree of matched entities | 3.62 |
| Avg fallback triples (1-hop) / question | 18.62 |
| Avg source paragraphs attached / question | 2.15 |
| Avg retrieved pages / question | 4.87 |
| Avg linked chunks / question | 4.67 |
| Chunk-level recall (GT tokens in linked chunks) | 0.396 |
| Ground-truth page attached rate | 0.167 |
| Avg context recall (retrieval-only) | 0.549 |
| Avg context precision (retrieval-only) | 0.119 |
| Distinct entities touched by retrieval | 144 |

> Context recall/precision here are computed on the *retrieved context only* (no answer
> generation, no LLM) — they measure the retrieval component in isolation.

## Per-question diagnostics

| ID | Category | Kw | Entities | Deg | Triples | Pages | Chunks | GT page? | Recall | Precision |
|----|----------|----|----------|-----|---------|-------|--------|----------|--------|-----------|
| 1 | fact_lookup | 1 | 7 | 0.86 | 9 | 3 | 5 | Y | 0.86 | 0.16 |
| 2 | fact_lookup | 1 | 7 | 0.86 | 9 | 3 | 5 | Y | 0.75 | 0.06 |
| 3 | fact_lookup | 1 | 2 | 15.0 | 23 | 4 | 5 | N | 0.5 | 0.01 |
| 4 | fact_lookup | 1 | 2 | 15.0 | 23 | 4 | 5 | Y | 0.5 | 0.0 |
| 5 | fact_lookup | 1 | 12 | 3.25 | 25 | 4 | 5 | N | 0.67 | 0.02 |
| 6 | fact_lookup | 1 | 2 | 15.0 | 23 | 4 | 5 | Y | 1.0 | 0.01 |
| 7 | fact_lookup | 1 | 7 | 0.86 | 9 | 3 | 5 | Y | 0.67 | 0.04 |
| 8 | fact_lookup | 2 | 21 | 5.48 | 25 | 8 | 5 | N | 0.75 | 0.01 |
| 9 | definition | 1 | 14 | 7.79 | 25 | 7 | 5 | N | 0.89 | 0.36 |
| 10 | definition | 2 | 25 | 5.56 | 25 | 8 | 5 | N | 1.0 | 0.07 |
| 11 | definition | 1 | 24 | 3.42 | 25 | 7 | 5 | N | 0.5 | 0.08 |
| 12 | definition | 1 | 18 | 1.72 | 25 | 7 | 5 | N | 0.73 | 0.07 |
| 13 | definition | 1 | 27 | 1.59 | 25 | 6 | 5 | Y | 0.36 | 0.08 |
| 14 | definition | 1 | 15 | 1.53 | 15 | 5 | 5 | N | 1.0 | 0.34 |
| 15 | definition | 1 | 10 | 1.2 | 12 | 7 | 5 | N | 0.86 | 0.18 |
| 16 | definition | 1 | 19 | 3.42 | 25 | 2 | 5 | N | 1.0 | 0.27 |
| 17 | multi_hop | 1 | 14 | 7.79 | 25 | 7 | 5 | N | 0.64 | 0.28 |
| 18 | multi_hop | 3 | 50 | 2.5 | 25 | 8 | 5 | N | 1.0 | 0.24 |
| 19 | multi_hop | 1 | 40 | 2.23 | 25 | 7 | 5 | N | 0.73 | 0.23 |
| 20 | multi_hop | 3 | 50 | 1.54 | 25 | 5 | 5 | N | 0.25 | 0.02 |
| 21 | multi_hop | 3 | 5 | 1.0 | 5 | 2 | 4 | N | 0.75 | 0.01 |
| 22 | multi_hop | 1 | 2 | 15.0 | 23 | 4 | 5 | Y | 0.71 | 0.01 |
| 23 | multi_hop | 3 | 14 | 1.14 | 14 | 2 | 5 | N | 0.6 | 0.3 |
| 24 | multi_hop | 1 | 13 | 1.38 | 19 | 6 | 5 | N | 0.56 | 0.15 |
| 25 | relationship | 2 | 21 | 5.48 | 25 | 8 | 5 | Y | 0.75 | 0.35 |
| 26 | relationship | 2 | 50 | 2.48 | 25 | 8 | 5 | N | 0.56 | 0.15 |
| 27 | relationship | 3 | 25 | 2.2 | 25 | 4 | 5 | N | 0.58 | 0.18 |
| 28 | relationship | 2 | 6 | 7.83 | 25 | 5 | 5 | N | 0.62 | 0.09 |
| 29 | relationship | 1 | 10 | 1.2 | 12 | 7 | 5 | N | 0.67 | 0.28 |
| 30 | relationship | 1 | 2 | 4.0 | 5 | 2 | 3 | N | 0.62 | 0.21 |
| 31 | relationship | 1 | 1 | 1.0 | 1 | 1 | 1 | N | 0.5 | 0.2 |
| 32 | relationship | 3 | 13 | 3.31 | 25 | 5 | 5 | N | 0.55 | 0.13 |
| 33 | hierarchical | 3 | 37 | 1.22 | 25 | 5 | 5 | N | 0.45 | 0.12 |
| 34 | hierarchical | 1 | 2 | 15.0 | 23 | 4 | 5 | N | 0.22 | 0.08 |
| 35 | hierarchical | 1 | 6 | 2.33 | 8 | 4 | 5 | N | 0.86 | 0.09 |
| 36 | hierarchical | 1 | 27 | 1.59 | 25 | 6 | 5 | Y | 1.0 | 0.18 |
| 37 | hierarchical | 1 | 14 | 7.79 | 25 | 7 | 5 | N | 0.12 | 0.02 |
| 38 | hierarchical | 3 | 38 | 3.66 | 25 | 10 | 5 | N | 0.75 | 0.13 |
| 39 | cross_section | 3 | 34 | 1.76 | 25 | 9 | 5 | Y | 0.89 | 0.2 |
| 40 | cross_section | 3 | 9 | 2.56 | 17 | 1 | 5 | N | 0.17 | 0.03 |
| 41 | cross_section | 3 | 13 | 0.77 | 13 | 4 | 5 | N | 0.64 | 0.31 |
| 42 | cross_section | 3 | 50 | 2.0 | 25 | 7 | 5 | N | 0.33 | 0.08 |
| 43 | cross_section | 3 | 2 | 0.5 | 2 | 1 | 2 | N | 0.0 | 0.0 |
| 44 | cross_section | 3 | 0 | 0.0 | 0 | 0 | 0 | N | 0.0 | 0.0 |
| 45 | workflow | 3 | 6 | 2.0 | 9 | 3 | 5 | N | 0.3 | 0.04 |
| 46 | workflow | 3 | 26 | 2.58 | 25 | 7 | 5 | N | 0.44 | 0.04 |
| 47 | workflow | 3 | 50 | 1.54 | 25 | 5 | 5 | N | 0.2 | 0.04 |
| 48 | workflow | 3 | 3 | 1.33 | 3 | 1 | 3 | N | 0.0 | 0.0 |
| 49 | workflow | 3 | 50 | 1.54 | 25 | 5 | 5 | N | 0.31 | 0.07 |
| 50 | workflow | 3 | 50 | 1.12 | 25 | 4 | 5 | N | 0.0 | 0.0 |
| 51 | workflow | 3 | 50 | 1.44 | 25 | 6 | 5 | N | 0.17 | 0.03 |
| 52 | workflow | 3 | 50 | 0.98 | 25 | 3 | 5 | N | 0.25 | 0.08 |
| 53 | comparison | 3 | 7 | 1.71 | 9 | 1 | 5 | N | 0.11 | 0.02 |
| 54 | comparison | 3 | 50 | 2.42 | 25 | 9 | 5 | N | 0.67 | 0.14 |
| 55 | comparison | 1 | 2 | 0.5 | 2 | 2 | 2 | N | 0.25 | 0.09 |
| 56 | comparison | 2 | 50 | 1.44 | 25 | 9 | 5 | N | 0.4 | 0.15 |
| 57 | comparison | 2 | 5 | 7.6 | 25 | 5 | 5 | N | 0.67 | 0.11 |
| 58 | comparison | 2 | 5 | 6.6 | 10 | 5 | 5 | N | 0.71 | 0.17 |
| 59 | comparison | 3 | 7 | 1.71 | 9 | 1 | 5 | N | 0.27 | 0.04 |
| 60 | comparison | 2 | 10 | 1.1 | 10 | 5 | 5 | N | 0.6 | 0.29 |

## Interpretation

- **Entity matching** works for most questions (keywords resolve to >=1 node), which is
  why source-text enrichment lifted context recall to ~0.59 on the smoke set.
- **GT-page attach rate** measures the graph's ability to *link* the answer's page to a
  matched entity — the key lever behind fact-lookup success. Low values on specific
  questions pinpoint where page linkage (`source_pages`) is missing, not retrieval ranking.
- **Context precision** is low on triples (each triple carries neighbor noise); source
  paragraphs dominate the evidence that matters.
- **Degree stats** quantify the hub/sparsity structure (28% isolated nodes) that caps
  1-hop neighbor recall on sparse subgraphs.

## Path length & graph coverage (gap-closure, offline, no LLM)

- Total graph nodes: **1046**
- **Avg 1-hop reachable nodes** per question (from matched entities): **21.95**
- **Avg 2-hop reachable nodes** per question: **93.25**
- **Multi-hop availability** (questions where 2-hop > 1-hop reachability): **0.967**
- **Graph coverage** (distinct nodes touched by retrieval across 60 questions): **245 / 1046 (23.4%)**

> Path length is measured as reachable-node counts at 1 and 2 hops from the matched
> entities (variable-length Cypher traversal, bounded to the first 10 matched entities
> per question). Coverage is distinct touched nodes as a fraction of the whole graph.
> Caveat: nodes are addressed by `name` IN-list, so duplicate node names (present in
> this graph) are all matched — reachability counts are an upper-bound proxy.
