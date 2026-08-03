# Retrieval Failure Diagnostic — GraphRAG v2 (zero-cost, offline)

> No LLM calls, no code modification, no graph changes. Replays the retriever's deterministic keyword extraction + source-attachment logic against the live v2 graph (read-only) and classifies each question's retrieval outcome. The actual LLM-generated Cypher is only observable where Neo4j logged a DBMS warning (4 leaked queries); other questions are classified from the v2 run log.

## 1. Headline numbers

- Questions: **12**
- LLM-Cypher path returned context: **3/12**
- LLM-Cypher empty context (fallback fired): **6/12**
- LLM-Cypher syntax/reference error (fallback fired): **3/12**
- GT page attached by the fallback path: **6/12**
- GT evidence tokens reachable (within 500-char paragraph caps): **12/12**
- GT evidence tokens present on the GT page itself (token-level check): **11/12**

## 2. Failure summary table

| Failure class | Questions | Meaning |
|---|---|---|
| `S_LLM_CYPHER_SUCCEEDED` | 3 | LLM Cypher returned context (no fallback) |
| `E5_GT_PAGE_OUT_OF_CAPS` | 3 | GT page exists but falls outside the retriever's page caps |
| `E3_CYPHER_SYNTAX_ERROR` | 3 | LLM Cypher raised a Neo4j syntax/reference error |
| `E1_INVENTED_PROPERTY_RECOVERED` | 2 | LLM Cypher referenced a non-existent property (leaked query); fallback recovered the GT page |
| `E2_INFERRED_OVERCONSTRAINED_RECOVERED` | 1 | LLM Cypher empty (query not observable); label-agnostic fallback recovered the GT page → likely over-constrained/invented pattern (inferred) |

## 3. Root-cause analysis (evidence-based)

1. **The LLM-Cypher path is the weak link, not the graph.** The Cypher model repeatedly invents schema that does not exist: `(org:Organization)-[r]->(c:Contact)` with `c.phoneNumber`/`c.faxNumber`/`pn.value` — but **0 nodes carry those properties**, the `Contact` label has only 2 nodes, and Finance Finland's only edges are `PUBLISHES` (the phone/fax nodes are disconnected: reverse-neighbor query returns 0 rows). A syntactically valid query therefore returns 0 rows → empty context → fallback.
2. **The fallback carries the system.** 9 of 12 questions fall back to the generic CONTAINS + 1-hop neighbor match, which is what actually attaches the GT page on the questions that pass.
3. **Page caps still bite.** Even under the fallback, the caps (6 entities, first 2 pages per entity, 3 paragraphs of ≤500 chars) keep the GT page out of context on 6 questions — the residual context-recall gap to VectorRAG.

## 4. Per-question trace

| Q | Category | LLM-Cypher | Keywords | Matched (top-3) | Pages attached | GT page in? | Evidence tokens? | Class |
|---|---|---|---|---|---|---|---|---|
| 2 | fact_lookup | empty | Finance Finland | Tel: +358 20 793 4200(Contact), Fax: +358 20 793 4202(Contact), Itämerenkatu 11-13(Location) | 2,3,2,3,1,2 | Y | Y | E1_INVENTED_PROPERTY_RECOVERED |
| 5 | fact_lookup | success | characters;unstructured;remittance | Unstructured Address(BusinessConcept), Character set(TechnicalConcept), Scandinavian Characters(TechnicalConcept) | 5,6,2,3,31,32 | Y | Y | S_LLM_CYPHER_SUCCEEDED |
| 7 | fact_lookup | empty | Finance Finland | Tel: +358 20 793 4200(Contact), Fax: +358 20 793 4202(Contact), Itämerenkatu 11-13(Location) | 2,3,2,3,1,2 | Y | Y | E1_INVENTED_PROPERTY_RECOVERED |
| 8 | fact_lookup | empty | ISO 20022;Finance Finland | Tel: +358 20 793 4200(Contact), Fax: +358 20 793 4202(Contact), ISO 20022 Payments Guide Purpose(Concept) | 2,3,2,3,3,4 | N | Y | E5_GT_PAGE_OUT_OF_CAPS |
| 27 | relationship | empty | C2B | Customer-to-Bank Payment(PaymentType), C2B Payment Files(FileType), C2B Payment File(FileType) | 3,4,52,53,53,54 | Y | Y | E2_INFERRED_OVERCONSTRAINED_RECOVERED |
| 34 | hierarchical | success | ISO 20022 Payments Guide | ISO 20022 Payments Guide Purpose(Concept), ISO 20022 Payments Guide(Document) | 3,4,1,2 | Y | Y | S_LLM_CYPHER_SUCCEEDED |
| 45 | workflow | success | customer;initiate;credit | Know-Your-Customer(BusinessProcess), Customer Credit Transfer Initiation(BusinessProcess), Customer Credit Transfer(PaymentScheme) | 5,6,20,21,16,17 | N | Y | S_LLM_CYPHER_SUCCEEDED |
| 46 | workflow | error | C2B | Customer-to-Bank Payment(PaymentType), C2B Payment Files(FileType), C2B Payment File(FileType) | 3,4,52,53,53,54 | Y | Y | E3_CYPHER_SYNTAX_ERROR |
| 48 | workflow | error | C2B | Customer-to-Bank Payment(PaymentType), C2B Payment Files(FileType), C2B Payment File(FileType) | 3,4,52,53,53,54 | N | Y | E3_CYPHER_SYNTAX_ERROR |
| 49 | workflow | empty | returned;payment;reported | Payment initiation(BusinessProcess), Payment processing(BusinessProcess), Payment Type(BusinessProcess) | 1,2,1,2,20,21 | N | Y | E5_GT_PAGE_OUT_OF_CAPS |
| 51 | workflow | empty | bank;verify;payee | Account(BusinessConcept), Bank-Specific Rules(BusinessConcept), Service Descriptions(BusinessConcept) | 6,7,8,9,8,9 | N | Y | E5_GT_PAGE_OUT_OF_CAPS |
| 53 | comparison | error | difference;between;payment | Customer-to-PSP Conditions(BusinessConcept), Character set(TechnicalConcept), Transactions Between Banks and Customers(Concept) | 12,13,2,3,3,4 | N | Y | E3_CYPHER_SYNTAX_ERROR |

Note: `fallback_context_rows` (in the JSON) is the **fallback's** context-row count from the run log — the LLM-Cypher's own row count is not observable without re-running the model (the queries returned empty or errored).

## 5. Leaked generated Cypher (from Neo4j warnings)

These are the only queries whose text was captured (Neo4j logs a DBMS warning when a query references a non-existent property). All fail on non-existent schema:

**Q2:**
- `MATCH (org:Organization)-[r]->(c:Contact) WHERE toLower(org.canonical_name) CONTAINS toLower("Finance Finland") ... RETURN org.name, org.description, type(r), c.name, c.description, c.phoneNumber LIMIT 20`
- `MATCH (org:Organization)-[r:HAS|HAS_NUMBER]->(pn:PhoneNumber) ... RETURN org.name, org.description, pn.name, pn.description, pn.value LIMIT 20`

**Q7:**
- `MATCH (org:Organization)-[r]->(c:Contact) ... RETURN org.name, org.description, type(r), c.name, c.faxNumber LIMIT 20`
- `MATCH (org:Organization)-[r]->(fax:FaxNumber) ... RETURN org.name, org.description, type(r), fax.value LIMIT 20`

## 6. What this rules out

- **Missing indexes:** the graph is small (1,046 nodes); CONTAINS scans are fast and the fulltext index exists. Indexes are not the bottleneck.
- **Graph construction:** the GT evidence tokens are present on the GT page for **11/12** questions (token-level check against `extracted_text.json`; exact-substring fails because evidence strings contain literal `...`), and the graph holds the facts. The failure is retrieval-side.

## 7. Implication for the next experiment

The highest-impact isolated retrieval improvement is **not** better Cypher generation (the model cannot be trusted to emit valid schema references), and **not** graph changes (frozen). It is to **make the deterministic fallback path the primary retriever and fix its evidence selection**: rank matched entities/pages by relevance, raise/replace the hard caps (2 pages/entity, 3 paragraphs) with an adaptive budget, and prefer the GT-carrying paragraphs the graph already links. See the proposal section in the experiment plan.
