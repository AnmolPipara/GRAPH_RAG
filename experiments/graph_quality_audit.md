# Graph Quality Audit — GraphRAG v2 (construction-fixed graph)

> Offline audit of `data/refined_graph_v2_construction.json`. Zero LLM calls, read-only, deterministic.

## 1. Totals

- Entities: **1046**
- Relationships: **931**
- Entities with ≥1 relationship endpoint: **824**

## 2. Degree distribution

- Mean total degree: **1.728**; max: **34**
- Isolated nodes (degree 0): **264** (25.2%)
- Near-isolated (degree 1): **429**

| Total degree | Nodes |
|---|---|
| 0 | 264 |
| 1 | 429 |
| 2 | 178 |
| 3 | 78 |
| 4 | 29 |
| 5 | 19 |
| 6 | 8 |
| 7 | 7 |
| 8 | 7 |
| 9 | 6 |
| 10 | 4 |
| 11 | 1 |
| 12 | 2 |
| 34 | 1 |

## 3. Weakly-connected components

- Components: **349**; largest: **590**; singletons: **292**
- Component sizes (top 10): [590, 16, 9, 6, 5, 5, 4, 4, 4, 4]

## 4. Duplicate-entity candidates

- Exact-name groups (same canonical name, different IDs): **122** groups / **271** entities
- Name-vs-alias collisions: **225**

Sample exact-name groups:

- `Tel: +358 20 793 4200` / `Tel: +358 20 793 4200` (PhoneNumber, Contact)
- `Fax: +358 20 793 4202` / `Fax: +358 20 793 4202` (FaxNumber, Contact)
- `Group Header` / `Group Header` (BusinessComponent, XMLElement)
- `Payment Information` / `Payment Information` (BusinessComponent, BusinessConcept)
- `Credit Transfer Transaction Information` / `Credit Transfer Transaction Information` (BusinessComponent, BusinessConcept)
- `Remittance Information` / `Remittance Information` (BusinessComponent, PaymentInformation)
- `Message structure` / `Message Structure` (BusinessComponent, BusinessConcept)
- `Debit booking alternatives` / `Debit Booking Alternatives` (BusinessComponent, BusinessConcept)

Sample name-vs-alias collisions:

- `Finland` ↔ alias of `FI`
- `Message root` ↔ alias of `Message root`
- `Message root` ↔ alias of `Message root`
- `Debtor` ↔ alias of `Debtor Agent`
- `Debtor` ↔ alias of `Dbtr`
- `Credit transfer` ↔ alias of `Credit Transfers`
- `Credit transfer` ↔ alias of `Customer Credit Transfer`
- `Credit transfer` ↔ alias of `Credit Transfer Transaction`
- `Credit transfer` ↔ alias of `Credit Transfer Transaction`
- `Credit transfer` ↔ alias of `Credit Transfer Instruction`

## 5. Alias & description coverage

- Entities with ≥1 alias: **480** (45.9%)
- Entities with non-empty description: **1046** (100.0%)
- Entities with empty description: **0**

## 6. Sparsity & direction quality

- Relationship types: **91**

| Relationship type | Count |
|---|---|
| CONTAINS | 353 |
| RELATED_TO | 154 |
| PART_OF | 67 |
| IDENTIFIED_BY | 56 |
| DEFINES | 47 |
| IS_A | 25 |
| PUBLISHES | 16 |
| USED_BY | 16 |
| TRANSLATES_TO | 15 |
| USES | 14 |
| INCLUDES | 10 |
| REFERENCES | 10 |
| EQUALS | 9 |
| PUBLISHED_BY | 6 |
| IDENTIFIES | 6 |

- Bidirectional pairs with non-inverse types (possible direction errors / redundant duplicates): **32**
  - `ISO 20022 Payments Guide` -[RELATED_TO]-> `ISO 20022` and reverse `-[PUBLISHES]->`
  - `Payment Message` -[CONTAINS]-> `Payment Information` and reverse `-[RELATED_TO]->`
  - `Payment Message` -[CONTAINS]-> `Credit Transfer Transaction Information` and reverse `-[RELATED_TO]->`
  - `Payment Message` -[CONTAINS]-> `Remittance Information` and reverse `-[RELATED_TO]->`
  - `Payment Information` -[RELATED_TO]-> `Payment Message` and reverse `-[CONTAINS]->`
  - `Credit Transfer Transaction Information` -[RELATED_TO]-> `Payment Message` and reverse `-[CONTAINS]->`
  - `Remittance Information` -[RELATED_TO]-> `Payment Message` and reverse `-[CONTAINS]->`
  - `ISO 20022 Payments Guide` -[PART_OF]-> `ISO 20022` and reverse `-[PUBLISHES]->`
  - `Swift4 Payment Market Practice Group` -[ISSUES]-> `Recommendation` and reverse `-[ISSUED_BY]->`
  - `Recommendation` -[ISSUED_BY]-> `Swift4 Payment Market Practice Group` and reverse `-[ISSUES]->`
  - `Debtor Agent` -[REPRESENTS]-> `Debtor` and reverse `-[CONTAINS]->`
  - `ISO 20022 Payments Guide` -[PUBLISHES]-> `ISO 20022` and reverse `-[PUBLISHES]->`

## 7. Benchmark entity hit-rate

For each benchmark question, how many graph entities share a non-stopword token with the question, and their degrees (retrieval reach).

| Q | Category | Matched | Matched entities (degree) |
|---|---|---|---|
| 2 | fact_lookup | 38 | `Itämerenkatu 11-13`(0), `Finance Finland`(2), `FI-00180 Helsinki`(0), `Finland`(4), `Twitter.com/finfinance`(0), `1.1 Usage of ISO 20022 in Finland`(0) |
| 5 | fact_lookup | 98 | `1.2.2 Unstructured address`(0), `2.2.2 Payment Information - Block B`(0), `2.2.3 Credit Transfer Transaction Information - Block C`(0), `2.2.4 Remittance Information`(0), `2.3.3 Payment Information`(0), `2.3.4 Credit Transfer Transaction Information`(0) |
| 7 | fact_lookup | 39 | `Itämerenkatu 11-13`(0), `Finance Finland`(2), `FI-00180 Helsinki`(0), `Fax: +358 20 793 4202`(0), `Finland`(4), `Twitter.com/finfinance`(0) |
| 8 | fact_lookup | 34 | `ISO 20022`(27), `ISO 20022 Payments Guide`(27), `Itämerenkatu 11-13`(0), `Finance Finland`(2), `FI-00180 Helsinki`(0), `Finland`(4) |
| 27 | relationship | 185 | `2.1 Parties of the Transaction`(0), `2.2 Payment Message structure`(0), `2.2.2 Payment Information - Block B`(0), `2.3.3 Payment Information`(0), `Payment Message`(31), `Payment Information`(21) |
| 34 | hierarchical | 55 | `ISO 20022`(27), `ISO 20022 Payments Guide`(27), `1.1 Usage of ISO 20022 in Finland`(0), `2.1 Parties of the Transaction`(0), `Structure of the Payment Status Report`(2), `Content of the Payment Status Report`(2) |
| 45 | workflow | 67 | `2.2.3 Credit Transfer Transaction Information - Block C`(0), `2.3.4 Credit Transfer Transaction Information`(0), `Credit Transfer Transaction Information`(9), `Credit transfer`(3), `Credit Transfer Transaction Information information`(0), `Credit Transfer Transaction Information information information`(0) |
| 46 | workflow | 165 | `2.1 Parties of the Transaction`(0), `2.2 Payment Message structure`(0), `2.2.2 Payment Information - Block B`(0), `2.3.3 Payment Information`(0), `Payment Message`(31), `Payment Information`(21) |
| 48 | workflow | 169 | `2.1 Parties of the Transaction`(0), `2.2 Payment Message structure`(0), `2.2.3 Credit Transfer Transaction Information - Block C`(0), `2.2.5 Message structure`(0), `2.3 Message content`(0), `2.3.1 Message root`(0) |
| 49 | workflow | 112 | `2.2 Payment Message structure`(0), `2.2.2 Payment Information - Block B`(0), `2.3.3 Payment Information`(0), `Payment Message`(31), `Payment Information`(21), `Payment initiation`(3) |
| 51 | workflow | 152 | `2.1 Parties of the Transaction`(0), `2.2 Payment Message structure`(0), `2.2.2 Payment Information - Block B`(0), `2.3.3 Payment Information`(0), `Payment Message`(31), `Payment Information`(21) |
| 53 | comparison | 220 | `2.1 Parties of the Transaction`(0), `2.2 Payment Message structure`(0), `2.2.2 Payment Information - Block B`(0), `2.2.5 Message structure`(0), `2.3 Message content`(0), `2.3.1 Message root`(0) |
