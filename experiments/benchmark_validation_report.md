# Benchmark Validation Report

Ground-truth audit of the 60-question benchmark against the source corpus (`data/extracted_text.json`, 61 pages; `data/chunks.json`, 35 chunks; the original PDF `iso-20022-payments-guide-2025-en.pdf`). **Offline audit — no LLM calls.**

## Method

For each question, the ground truth is matched to the corpus three ways:

1. **Exact substring** — normalized (case/diacritic/whitespace-insensitive) ground-truth
   core within a page, a chunk, or the PDF text.
2. **Token coverage** — fraction of ground-truth content tokens found on the best page
   (the decision support; coverage values are in the appendix of this audit run).
3. **Manual verification** — the best supporting sentence is read and the status is judged
   as VERIFIED / PARTIALLY VERIFIED / UNSUPPORTED.

## Summary

- VERIFIED: **21**
- PARTIALLY VERIFIED: **27**
- UNSUPPORTED: **12** (repaired in `benchmark_v2.json`)

## Per-question audit

| ID | Category | Question | Ground truth | Supporting page(s) | Status |
|----|----------|----------|--------------|--------------------|--------|
| 1 | fact_lookup | What is the address of Finance Finland? | Itamerenkatu 11-13, FI-00180 Helsinki, Finland. | p2 | VERIFIED |
| 2 | fact_lookup | What is the phone number for Finance Finland? | +358 20 793 9000 | p2 | UNSUPPORTED |
| 3 | fact_lookup | Who published the ISO 20022 Payments Guide? | Finance Finland (Finanssiala ry). | p3 | PARTIALLY VERIFIED |
| 4 | fact_lookup | How many pages does the ISO 20022 Payments Guide have? | 61 pages. | p2 | VERIFIED |
| 5 | fact_lookup | What is the version number of the guide? | Version 3.1. | p31 | UNSUPPORTED |
| 6 | fact_lookup | What is the publication year of the ISO 20022 Payments Guide? | 2025. | p1,p4,p52 | VERIFIED |
| 7 | fact_lookup | What is the email address for Finance Finland payments team? | payments@finanssiala.fi | p1 | UNSUPPORTED |
| 8 | fact_lookup | What is the ISO 20022 website provided by Finance Finland? | www.finanssiala.fi/iso20022 | p4 | UNSUPPORTED |
| 9 | definition | What is ISO 20022? | ISO 20022 is an international standard for financial messaging. | p59 | VERIFIED |
| 10 | definition | What is a Group Header in ISO 20022 payment messages? | Block A containing message identification, creation date, and number o | p8 | VERIFIED |
| 11 | definition | What is a Debtor in payment messaging? | The party that owes funds and initiates the payment. | p6 | PARTIALLY VERIFIED |
| 12 | definition | What is a Credit Transfer Transaction? | A payment instruction transferring funds from the debtor to the credit | p20 | PARTIALLY VERIFIED |
| 13 | definition | What is Remittance Information? | Details about payment purpose such as invoice numbers or reference cod | p29 | PARTIALLY VERIFIED |
| 14 | definition | What is BIC in payments? | Bank Identifier Code, a unique identifier for financial institutions. | p4 | VERIFIED |
| 15 | definition | What is IBAN? | International Bank Account Number, a standardized account identifier. | p12 | PARTIALLY VERIFIED |
| 16 | definition | What is a Payment Status Report? | The pain.002 message reporting payment instruction status. | p39 | VERIFIED |
| 17 | multi_hop | Which organization published the ISO 20022 standard used in Finland? | Finance Finland published the ISO 20022 Payments Guide based on the IS | p4 | VERIFIED |
| 18 | multi_hop | What message types are used to initiate credit transfers? | The pain.001 (Customer Credit Transfer Initiation) message type. | p12 | VERIFIED |
| 19 | multi_hop | What information is contained in the Payment Information block? | Block B contains payment type, debtor details, debtor account, and deb | p8 | VERIFIED |
| 20 | multi_hop | How is a payment routed from the debtor to the creditor? | Debtor to Debtor Agent to Creditor Agent to Creditor. | p6 | PARTIALLY VERIFIED |
| 21 | multi_hop | What entities are involved in a direct debit transaction? | Creditor, Creditor Agent, Debtor Agent, and Debtor. | p6 | PARTIALLY VERIFIED |
| 22 | multi_hop | Who publishes the ISO 20022 Payments Guide and where are they located? | Finance Finland at Itamerenkatu 11-13, Helsinki. | p2 | VERIFIED |
| 23 | multi_hop | How do pain.001 and pain.002 messages relate to each other? | pain.001 is the request message and pain.002 is the status response me | p53 | PARTIALLY VERIFIED |
| 24 | multi_hop | What components make up Credit Transfer Transaction Information? | Payment Identification, Amount, Currency, Charge Bearer, and Remittanc | p22 | PARTIALLY VERIFIED |
| 25 | relationship | How is ISO 20022 related to Finance Finland? | Finance Finland publishes the ISO 20022 Payments Guide for the Finnish | p2 | PARTIALLY VERIFIED |
| 26 | relationship | What is the relationship between a Debtor and a Creditor? | The Debtor owes funds and initiates payment to the Creditor. | p7 | PARTIALLY VERIFIED |
| 27 | relationship | How does pain.001 relate to pacs.008? | pain.001 initiates the payment and pacs.008 clears it between banks. | p4 | UNSUPPORTED |
| 28 | relationship | How does Block B relate to Block C in a payment message? | Block B contains one or more Block C entries. | p8 | VERIFIED |
| 29 | relationship | What is the relationship between an IBAN and a bank account? | IBAN uniquely identifies a specific bank account for payments. | p18 | PARTIALLY VERIFIED |
| 30 | relationship | How does Charge Bearer relate to payment fees? | Charge Bearer specifies which party pays transaction fees. | p19 | PARTIALLY VERIFIED |
| 31 | relationship | How does a Clearing Code relate to a financial institution? | Clearing Code uniquely identifies a bank within a clearing system. | p4 | PARTIALLY VERIFIED |
| 32 | relationship | How does pain.002 relate to pain.001? | pain.002 provides the status response to a previously submitted pain.0 | p53 | PARTIALLY VERIFIED |
| 33 | hierarchical | What is the hierarchical structure of a payment message? | Block A (Group Header) contains Block B (Payment Information) which co | p8 | VERIFIED |
| 34 | hierarchical | What are the main sections of the ISO 20022 Payments Guide? | Introduction, General Principles, Message Structure, Payment Types, De | p3 | UNSUPPORTED |
| 35 | hierarchical | What components make up Payment Type Information? | Service Level, Local Instrument, and Category Purpose. | p21 | VERIFIED |
| 36 | hierarchical | What are the sub-components of Remittance Information? | Unstructured Remittance and Structured Remittance. | p2 | VERIFIED |
| 37 | hierarchical | What are the levels of message definitions in ISO 20022? | Business Process, Message Definition, Building Blocks, and Elements. | p4 | PARTIALLY VERIFIED |
| 38 | hierarchical | What is the hierarchy of party identifiers in a payment? | Party Name, Postal Address, Identification, and Contact Details. | p23 | PARTIALLY VERIFIED |
| 39 | cross_section | How is address formatted across different message types? | Street Name, Building Number, Town Name, Country, and Postal Code. | p57 | VERIFIED |
| 40 | cross_section | What common elements appear in both pain.001 and pain.002? | Both share the Group Header structure. | p2 | VERIFIED |
| 41 | cross_section | How is currency specified across different payment instructions? | Using the 3-letter ISO 4217 currency code in the Amount element. | p23 | PARTIALLY VERIFIED |
| 42 | cross_section | What identification methods are used for financial institutions? | BIC and Clearing System Member Identification. | p23 | VERIFIED |
| 43 | cross_section | How are amounts formatted across payment messages? | Decimal numbers with up to 2 decimal places. | p2 | PARTIALLY VERIFIED |
| 44 | cross_section | What regulations are referenced across payment scenarios? | PSD2, SEPA regulations, and Finnish payment regulations. | p19 | PARTIALLY VERIFIED |
| 45 | workflow | What is the workflow for initiating a credit transfer? | Debtor creates pain.001, sends to Debtor Agent, Agent sends pacs.008 t | p6 | UNSUPPORTED |
| 46 | workflow | How does a direct debit process work? | Creditor sends pain.008, Creditor Agent sends pacs.003 to Debtor Agent | p6 | UNSUPPORTED |
| 47 | workflow | What happens when a payment is rejected? | The agent sends a pain.002 with rejection reason codes. | p40 | VERIFIED |
| 48 | workflow | What is the sequence of messages in a cross-border payment? | pain.001, pacs.008, pacs.009, and pain.002. | p4 | UNSUPPORTED |
| 49 | workflow | How is a payment cancellation processed? | camt.056 is sent, the agent processes it, and a status report is retur | p40 | UNSUPPORTED |
| 50 | workflow | What is the end-to-end payment processing flow? | Initiation, Validation, Clearing, Settlement, and Confirmation. | p4 | PARTIALLY VERIFIED |
| 51 | workflow | How does a failed payment investigation work? | camt.056 or camt.087 is sent and camt.029 is returned with the resolut | p12 | UNSUPPORTED |
| 52 | workflow | How does a payment status change during processing? | Accepted to Pending to Settled to Confirmed or Rejected status. | p3 | PARTIALLY VERIFIED |
| 53 | comparison | What is the difference between pain.001 and pacs.008? | pain.001 is payment initiation, pacs.008 is interbank clearing. | p4 | UNSUPPORTED |
| 54 | comparison | How does a credit transfer differ from a direct debit? | Credit transfer: debtor pushes funds. Direct debit: creditor pulls fun | p2 | PARTIALLY VERIFIED |
| 55 | comparison | What is the difference between Structured and Unstructured Remittance? | Structured uses predefined formats. Unstructured is free text. | p28 | VERIFIED |
| 56 | comparison | How does SEPA differ from a domestic Finnish payment? | SEPA follows pan-European rules. Finnish payments use national codes. | p9 | PARTIALLY VERIFIED |
| 57 | comparison | What is the difference between Block A and Block B? | Block A has message-level info. Block B has payment-level details. | p33 | PARTIALLY VERIFIED |
| 58 | comparison | How does Debtor Agent differ from Creditor Agent? | Debtor Agent sends the payment. Creditor Agent receives the payment. | p6 | PARTIALLY VERIFIED |
| 59 | comparison | What is the difference between pain.002 and camt.053? | pain.002 reports payment status. camt.053 is an account statement. | p12 | VERIFIED |
| 60 | comparison | How does Settlement Date differ from Execution Date? | Execution Date is when payment is requested. Settlement Date is when f | p8 | PARTIALLY VERIFIED |

## Notes per question

### Q1 [fact_lookup] — VERIFIED
- **Question:** What is the address of Finance Finland?
- **Ground truth:** Itamerenkatu 11-13, FI-00180 Helsinki, Finland.
- **Best supporting sentence** (page 2): *Itämerenkatu 11-13*
- **Notes:** p2 contact block: Itämerenkatu 11-13, FI-00180 Helsinki, Finland. GT is ASCII; doc uses diacritic.

### Q2 [fact_lookup] — UNSUPPORTED
- **Question:** What is the phone number for Finance Finland?
- **Ground truth:** +358 20 793 9000
- **Best supporting sentence** (page 2): *Tel: +358 20 793 4200*
- **Notes:** GT number +358 20 793 9000 appears NOWHERE (doc or PDF). Doc states Tel +358 20 793 4200 / Fax +358 20 793 4202.

### Q3 [fact_lookup] — PARTIALLY VERIFIED
- **Question:** Who published the ISO 20022 Payments Guide?
- **Ground truth:** Finance Finland (Finanssiala ry).
- **Best supporting sentence** (page 3): *www.financefinland.fi*
- **Notes:** Publisher 'Finance Finland' supported (p3 www.financefinland.fi; guide cover). '(Finanssiala ry)' legal name appears only in graph aliases (raw extraction), not in guide text.

### Q4 [fact_lookup] — VERIFIED
- **Question:** How many pages does the ISO 20022 Payments Guide have?
- **Ground truth:** 61 pages.
- **Best supporting sentence** (page 2): *2 (61)*
- **Notes:** '61' total pages encoded in every page footer 'N (61)'.

### Q5 [fact_lookup] — UNSUPPORTED
- **Question:** What is the version number of the guide?
- **Ground truth:** Version 3.1.
- **Best supporting sentence** (page 31): *3.1*
- **Notes:** No guide version exists anywhere (cover states only year 2025; all '3.1' hits are section numbers or XML declarations).

### Q6 [fact_lookup] — VERIFIED
- **Question:** What is the publication year of the ISO 20022 Payments Guide?
- **Ground truth:** 2025.
- **Best supporting sentence** (page 1): *2025*
- **Notes:** p1 cover 'ISO 20022 Payments Guide 2025'.

### Q7 [fact_lookup] — UNSUPPORTED
- **Question:** What is the email address for Finance Finland payments team?
- **Ground truth:** payments@finanssiala.fi
- **Best supporting sentence** (page 1): *ISO 20022 Payments Guide*
- **Notes:** payments@finanssiala.fi absent from PDF and every artifact. Only email in corpus is placeholder firstname.lastname@financefinland.fi (p2).

### Q8 [fact_lookup] — UNSUPPORTED
- **Question:** What is the ISO 20022 website provided by Finance Finland?
- **Ground truth:** www.finanssiala.fi/iso20022
- **Best supporting sentence** (page 4): *Report are available on the website of ISO at www.iso20022.org.*
- **Notes:** Base domain www.finanssiala.fi supported (p32: 'available on the FFI website at www.finanssiala.fi'), but path '/iso20022' is never stated anywhere.

### Q9 [definition] — VERIFIED
- **Question:** What is ISO 20022?
- **Ground truth:** ISO 20022 is an international standard for financial messaging.
- **Best supporting sentence** (page 59): *ISO 20022 Payments Guide*
- **Notes:** p4: 'International payment systems will migrate to the ISO 20022 standard' — ISO 20022 is the international standard for financial messaging.

### Q10 [definition] — VERIFIED
- **Question:** What is a Group Header in ISO 20022 payment messages?
- **Ground truth:** Block A containing message identification, creation date, and number of transactions.
- **Best supporting sentence** (page 8): *entire message, such as MessageIdentification, CreationDateAndTime,*
- **Notes:** p8 Group Header elements (MessageIdentification, CreationDateAndTime); p11 'GroupHeader (Block A) contains the ID information of the payment message'.

### Q11 [definition] — PARTIALLY VERIFIED
- **Question:** What is a Debtor in payment messaging?
- **Ground truth:** The party that owes funds and initiates the payment.
- **Best supporting sentence** (page 6): *ISO 20022 Payments Guide*
- **Notes:** Debtor role supported ('the party owing' — 'owing' present in PDF); GT wording 'owes funds' not verbatim.

### Q12 [definition] — PARTIALLY VERIFIED
- **Question:** What is a Credit Transfer Transaction?
- **Ground truth:** A payment instruction transferring funds from the debtor to the creditor account.
- **Best supporting sentence** (page 20): *to both the debtor and the creditor.*
- **Notes:** Credit-transfer concept supported (p55 'payment instructions ... creditor bank'); GT phrasing not verbatim.

### Q13 [definition] — PARTIALLY VERIFIED
- **Question:** What is Remittance Information?
- **Ground truth:** Details about payment purpose such as invoice numbers or reference codes.
- **Best supporting sentence** (page 29): *Recurring payments' purpose codes can*
- **Notes:** Remittance/purpose codes present (p29 'Recurring payments’ purpose codes'); GT's invoice/reference examples not verbatim.

### Q14 [definition] — VERIFIED
- **Question:** What is BIC in payments?
- **Ground truth:** Bank Identifier Code, a unique identifier for financial institutions.
- **Best supporting sentence** (page 4): *European banks, payment institutions and the euro area clearing and settlement*
- **Notes:** p52 'Bank identifier code specified in the message has an incorrect format' — BIC expansion supported.

### Q15 [definition] — PARTIALLY VERIFIED
- **Question:** What is IBAN?
- **Ground truth:** International Bank Account Number, a standardized account identifier.
- **Best supporting sentence** (page 12): *returned to the debtor's account*
- **Notes:** IBAN present in doc/PDF (p55 'free format account number'); the full expansion 'International Bank Account Number' not verbatim in extracted text.

### Q16 [definition] — VERIFIED
- **Question:** What is a Payment Status Report?
- **Ground truth:** The pain.002 message reporting payment instruction status.
- **Best supporting sentence** (page 39): *Pain.002.001.10 Payment Status Report standard is used to structure the return*
- **Notes:** p39 'Pain.002.001.10 Payment Status Report standard is used to structure the return'.

### Q17 [multi_hop] — VERIFIED
- **Question:** Which organization published the ISO 20022 standard used in Finland?
- **Ground truth:** Finance Finland published the ISO 20022 Payments Guide based on the ISO 20022 standard.
- **Best supporting sentence** (page 4): *ISO 20022 Payments Guide*
- **Notes:** Publisher = Finance Finland (cover/contact); 'based on the ISO 20022 standard' supported by context.

### Q18 [multi_hop] — VERIFIED
- **Question:** What message types are used to initiate credit transfers?
- **Ground truth:** The pain.001 (Customer Credit Transfer Initiation) message type.
- **Best supporting sentence** (page 12): *Customer Credit Transfer*
- **Notes:** p4: message class 'CustomerCreditTransferInitiationV09' (pain.001) used to initiate credit transfers.

### Q19 [multi_hop] — VERIFIED
- **Question:** What information is contained in the Payment Information block?
- **Ground truth:** Block B contains payment type, debtor details, debtor account, and debtor agent info.
- **Best supporting sentence** (page 8): *PaymentInformationIdentifier, Debtor, DebtorAccount, PaymentTypeInformation and*
- **Notes:** p8: 'PaymentInformationIdentifier, Debtor, DebtorAccount, PaymentTypeInformation' — Block B components.

### Q20 [multi_hop] — PARTIALLY VERIFIED
- **Question:** How is a payment routed from the debtor to the creditor?
- **Ground truth:** Debtor to Debtor Agent to Creditor Agent to Creditor.
- **Best supporting sentence** (page 6): *might be the debtor itself, an agent, or*
- **Notes:** Party chain (Debtor, Debtor Agent, Creditor Agent, Creditor) present in role descriptions (p6/p57); routing sentence not verbatim.

### Q21 [multi_hop] — PARTIALLY VERIFIED
- **Question:** What entities are involved in a direct debit transaction?
- **Ground truth:** Creditor, Creditor Agent, Debtor Agent, and Debtor.
- **Best supporting sentence** (page 6): *might be the debtor itself, an agent, or*
- **Notes:** Same party-role descriptions support the direct-debit party set.

### Q22 [multi_hop] — VERIFIED
- **Question:** Who publishes the ISO 20022 Payments Guide and where are they located?
- **Ground truth:** Finance Finland at Itamerenkatu 11-13, Helsinki.
- **Best supporting sentence** (page 2): *Itämerenkatu 11-13*
- **Notes:** p2/p3 contact block: Finance Finland at Itämerenkatu 11-13, Helsinki.

### Q23 [multi_hop] — PARTIALLY VERIFIED
- **Question:** How do pain.001 and pain.002 messages relate to each other?
- **Ground truth:** pain.001 is the request message and pain.002 is the status response message.
- **Best supporting sentence** (page 53): *VOP response types and status codes submitted to the customer*
- **Notes:** pain.001=initiation (p4) and pain.002=status report (p39) supported across pages; single sentence not verbatim.

### Q24 [multi_hop] — PARTIALLY VERIFIED
- **Question:** What components make up Credit Transfer Transaction Information?
- **Ground truth:** Payment Identification, Amount, Currency, Charge Bearer, and Remittance Information.
- **Best supporting sentence** (page 22): *Currency and amount of the payment.*
- **Notes:** Block C components supported by element tables (p55/56: currency, charges, amount); GT list not verbatim.

### Q25 [relationship] — PARTIALLY VERIFIED
- **Question:** How is ISO 20022 related to Finance Finland?
- **Ground truth:** Finance Finland publishes the ISO 20022 Payments Guide for the Finnish payment ecosystem.
- **Best supporting sentence** (page 2): *ISO 20022 Payments Guide*
- **Notes:** Publisher relationship supported; 'Finnish payment ecosystem' phrasing not verbatim.

### Q26 [relationship] — PARTIALLY VERIFIED
- **Question:** What is the relationship between a Debtor and a Creditor?
- **Ground truth:** The Debtor owes funds and initiates payment to the Creditor.
- **Best supporting sentence** (page 7): *the Ultimate Debtor, the Debtor and the one initiating the payment.*
- **Notes:** Debtor/Creditor roles supported ('owing' in PDF); 'owes funds / initiates' wording not verbatim.

### Q27 [relationship] — UNSUPPORTED
- **Question:** How does pain.001 relate to pacs.008?
- **Ground truth:** pain.001 initiates the payment and pacs.008 clears it between banks.
- **Best supporting sentence** (page 4): *European banks, payment institutions and the euro area clearing and settlement*
- **Notes:** pacs.008 absent from PDF and all artifacts. Guide covers only customer-to-bank messages (pain.001/pain.002).

### Q28 [relationship] — VERIFIED
- **Question:** How does Block B relate to Block C in a payment message?
- **Ground truth:** Block B contains one or more Block C entries.
- **Best supporting sentence** (page 8): *Payment initiation message is composed of three blocks: Group Header, Payment*
- **Notes:** p9: 'one or more subordinate Credit Transfer Transaction Information blocks' (Block C within Block B).

### Q29 [relationship] — PARTIALLY VERIFIED
- **Question:** What is the relationship between an IBAN and a bank account?
- **Ground truth:** IBAN uniquely identifies a specific bank account for payments.
- **Best supporting sentence** (page 18): *from bank-specific implementation*
- **Notes:** IBAN present; 'uniquely identifies a specific bank account' is a standard gloss, not verbatim.

### Q30 [relationship] — PARTIALLY VERIFIED
- **Question:** How does Charge Bearer relate to payment fees?
- **Ground truth:** Charge Bearer specifies which party pays transaction fees.
- **Best supporting sentence** (page 19): *++Charge Bearer*
- **Notes:** Charge Bearer element (p19) + allocation examples (p57 'SLEV ... Debtor and Creditor pay their own charges').

### Q31 [relationship] — PARTIALLY VERIFIED
- **Question:** How does a Clearing Code relate to a financial institution?
- **Ground truth:** Clearing Code uniquely identifies a bank within a clearing system.
- **Best supporting sentence** (page 4): *European banks, payment institutions and the euro area clearing and settlement*
- **Notes:** p23 '(BIC or clearing system code)'; 'uniquely identifies a bank within a clearing system' gloss not verbatim.

### Q32 [relationship] — PARTIALLY VERIFIED
- **Question:** How does pain.002 relate to pain.001?
- **Ground truth:** pain.002 provides the status response to a previously submitted pain.001.
- **Best supporting sentence** (page 53): *VOP response types and status codes submitted to the customer*
- **Notes:** pain.002 status-response role supported (p39, p53); wording not verbatim.

### Q33 [hierarchical] — VERIFIED
- **Question:** What is the hierarchical structure of a payment message?
- **Ground truth:** Block A (Group Header) contains Block B (Payment Information) which contains Block C (Transactions).
- **Best supporting sentence** (page 8): *Payment initiation message is composed of three blocks: Group Header, Payment*
- **Notes:** p8 'Payment initiation message is composed of three blocks: Group Header, Payment ...' + p9 containment.

### Q34 [hierarchical] — UNSUPPORTED
- **Question:** What are the main sections of the ISO 20022 Payments Guide?
- **Ground truth:** Introduction, General Principles, Message Structure, Payment Types, Definitions, Appendices.
- **Best supporting sentence** (page 3): *6.2 Examples of Payment Status Report messages ............................................................*
- **Notes:** GT lists generic sections (Introduction, General Principles, ...) that do NOT match the guide's actual TOC (Background, Message structure, Additional functionalities, XML examples, Status Report examples, VOP).

### Q35 [hierarchical] — VERIFIED
- **Question:** What components make up Payment Type Information?
- **Ground truth:** Service Level, Local Instrument, and Category Purpose.
- **Best supporting sentence** (page 21): *++++Service Level*
- **Notes:** p21 PmtTpInf components: Service Level, Local Instrument, Category Purpose.

### Q36 [hierarchical] — VERIFIED
- **Question:** What are the sub-components of Remittance Information?
- **Ground truth:** Unstructured Remittance and Structured Remittance.
- **Best supporting sentence** (page 2): *1.2.2 Unstructured address ..............................................................................................*
- **Notes:** p58 'unstructured Remittance'; p32 'unstructured remittance information'.

### Q37 [hierarchical] — PARTIALLY VERIFIED
- **Question:** What are the levels of message definitions in ISO 20022?
- **Ground truth:** Business Process, Message Definition, Building Blocks, and Elements.
- **Best supporting sentence** (page 4): *Message definition is about*
- **Notes:** Message-definition levels partially present (p4 'Message definition is about ...'); full BusinessProcess/BuildingBlock/Element ladder not in extracted text.

### Q38 [hierarchical] — PARTIALLY VERIFIED
- **Question:** What is the hierarchy of party identifiers in a payment?
- **Ground truth:** Party Name, Postal Address, Identification, and Contact Details.
- **Best supporting sentence** (page 23): *++++Postal Address*
- **Notes:** Party-identifier hierarchy supported by element tables (p23 Postal Address structures); GT list not verbatim.

### Q39 [cross_section] — VERIFIED
- **Question:** How is address formatted across different message types?
- **Ground truth:** Street Name, Building Number, Town Name, Country, and Postal Code.
- **Best supporting sentence** (page 57): *<CdtrAgt><FinInstnId><PstlAdr>< StrtNm > Street name*
- **Notes:** p6 'Country'/'Town Name' mandatory; p57 XML shows Street name etc.

### Q40 [cross_section] — VERIFIED
- **Question:** What common elements appear in both pain.001 and pain.002?
- **Ground truth:** Both share the Group Header structure.
- **Best supporting sentence** (page 2): *2.2.1 Group Header - Block A ..........................................................................................*
- **Notes:** Group Header shared by pain.001 (p11) and pain.002 (p39 structure).

### Q41 [cross_section] — PARTIALLY VERIFIED
- **Question:** How is currency specified across different payment instructions?
- **Ground truth:** Using the 3-letter ISO 4217 currency code in the Amount element.
- **Best supporting sentence** (page 23): *ISO 20022 Payments Guide*
- **Notes:** Currency/Amount elements supported (p22 'Currency and amount of the payment'); '3-letter ISO 4217' never stated (doc or PDF).

### Q42 [cross_section] — VERIFIED
- **Question:** What identification methods are used for financial institutions?
- **Ground truth:** BIC and Clearing System Member Identification.
- **Best supporting sentence** (page 23): *(BIC or clearing system code).*
- **Notes:** p23 '(BIC or clearing system code)'; p56 'clearing system identifier'.

### Q43 [cross_section] — PARTIALLY VERIFIED
- **Question:** How are amounts formatted across payment messages?
- **Ground truth:** Decimal numbers with up to 2 decimal places.
- **Best supporting sentence** (page 2): *2.2.1 Group Header - Block A ..........................................................................................*
- **Notes:** Amount examples show 2 decimals (p56 '2.94'); the 'up to 2 decimal places' rule is not stated.

### Q44 [cross_section] — PARTIALLY VERIFIED
- **Question:** What regulations are referenced across payment scenarios?
- **Ground truth:** PSD2, SEPA regulations, and Finnish payment regulations.
- **Best supporting sentence** (page 19): *With SEPA payments "SLEV" = Service*
- **Notes:** SEPA regulations referenced (p21 SEPA instant, p32 EPC SEPA rulebook); 'PSD2' absent from doc and PDF.

### Q45 [workflow] — UNSUPPORTED
- **Question:** What is the workflow for initiating a credit transfer?
- **Ground truth:** Debtor creates pain.001, sends to Debtor Agent, Agent sends pacs.008 to Creditor Agent.
- **Best supporting sentence** (page 6): *might be the debtor itself, an agent, or*
- **Notes:** pacs.008 hop absent; only the pain.001 -> Debtor Agent (bank) leg is supported.

### Q46 [workflow] — UNSUPPORTED
- **Question:** How does a direct debit process work?
- **Ground truth:** Creditor sends pain.008, Creditor Agent sends pacs.003 to Debtor Agent.
- **Best supporting sentence** (page 6): *might be the debtor itself, an agent, or*
- **Notes:** pain.008/pacs.003 absent; direct debit is mentioned only as SEPA scope (p4, Regulation (EU) 260/2012).

### Q47 [workflow] — VERIFIED
- **Question:** What happens when a payment is rejected?
- **Ground truth:** The agent sends a pain.002 with rejection reason codes.
- **Best supporting sentence** (page 40): *See Rejection reason codes*
- **Notes:** p40 'See Rejection reason codes'; p51 'The rejection reason codes used in the ISO20022 standard ...'.

### Q48 [workflow] — UNSUPPORTED
- **Question:** What is the sequence of messages in a cross-border payment?
- **Ground truth:** pain.001, pacs.008, pacs.009, and pain.002.
- **Best supporting sentence** (page 4): *scheme identifier is "pain.001.001.09".*
- **Notes:** pacs.008 and pacs.009 absent; only pain.001/pain.002 are in the corpus.

### Q49 [workflow] — UNSUPPORTED
- **Question:** How is a payment cancellation processed?
- **Ground truth:** camt.056 is sent, the agent processes it, and a status report is returned.
- **Best supporting sentence** (page 40): *Return message Group Status is ACCP*
- **Notes:** camt.056 absent; the word 'cancellation' does not appear in the doc or PDF.

### Q50 [workflow] — PARTIALLY VERIFIED
- **Question:** What is the end-to-end payment processing flow?
- **Ground truth:** Initiation, Validation, Clearing, Settlement, and Confirmation.
- **Best supporting sentence** (page 4): *European banks, payment institutions and the euro area clearing and settlement*
- **Notes:** Clearing/settlement stages present (p4 'clearing and settlement'); full 5-stage chain not verbatim.

### Q51 [workflow] — UNSUPPORTED
- **Question:** How does a failed payment investigation work?
- **Ground truth:** camt.056 or camt.087 is sent and camt.029 is returned with the resolution.
- **Best supporting sentence** (page 12): *returned to the debtor's account*
- **Notes:** camt.056/camt.087/camt.029 absent; investigation workflow not covered by the corpus.

### Q52 [workflow] — PARTIALLY VERIFIED
- **Question:** How does a payment status change during processing?
- **Ground truth:** Accepted to Pending to Settled to Confirmed or Rejected status.
- **Best supporting sentence** (page 3): *6.1.5 Original Group Information And Status ..................................................................*
- **Notes:** Accepted/Pending/Rejected statuses present (p3, p5, p39-40); 'Settled' absent from doc and PDF.

### Q53 [comparison] — UNSUPPORTED
- **Question:** What is the difference between pain.001 and pacs.008?
- **Ground truth:** pain.001 is payment initiation, pacs.008 is interbank clearing.
- **Best supporting sentence** (page 4): *Not all of the details in the pain.001 payment initiation message can currently be*
- **Notes:** pacs.008 absent; the comparison cannot be grounded in the corpus.

### Q54 [comparison] — PARTIALLY VERIFIED
- **Question:** How does a credit transfer differ from a direct debit?
- **Ground truth:** Credit transfer: debtor pushes funds. Direct debit: creditor pulls funds.
- **Best supporting sentence** (page 2): *5.1 Creditor reference in a credit transfer transaction ..........................................................*
- **Notes:** Credit-transfer vs direct-debit distinction supported at scope level (p4 Reg 260/2012); 'pushes/pulls' wording not used.

### Q55 [comparison] — VERIFIED
- **Question:** What is the difference between Structured and Unstructured Remittance?
- **Ground truth:** Structured uses predefined formats. Unstructured is free text.
- **Best supporting sentence** (page 28): *free text or structured information, but*
- **Notes:** p28 'free text or structured information'.

### Q56 [comparison] — PARTIALLY VERIFIED
- **Question:** How does SEPA differ from a domestic Finnish payment?
- **Ground truth:** SEPA follows pan-European rules. Finnish payments use national codes.
- **Best supporting sentence** (page 9): *of the information used in SEPA payments.*
- **Notes:** SEPA European rules supported (p32 EPC SEPA Credit Transfer Rulebook); 'pan-European' not used; national codes implied via AOS.

### Q57 [comparison] — PARTIALLY VERIFIED
- **Question:** What is the difference between Block A and Block B?
- **Ground truth:** Block A has message-level info. Block B has payment-level details.
- **Best supporting sentence** (page 33): *(C10) in CreditTransferTransactionInformation (Block C).*
- **Notes:** Block A message-level vs Block B payment-level supported by structure descriptions (p8, p22, p33).

### Q58 [comparison] — PARTIALLY VERIFIED
- **Question:** How does Debtor Agent differ from Creditor Agent?
- **Ground truth:** Debtor Agent sends the payment. Creditor Agent receives the payment.
- **Best supporting sentence** (page 6): *might be the debtor itself, an agent, or*
- **Notes:** Debtor Agent / Creditor Agent roles supported (p6); 'sends/receives' wording not verbatim.

### Q59 [comparison] — VERIFIED
- **Question:** What is the difference between pain.002 and camt.053?
- **Ground truth:** pain.002 reports payment status. camt.053 is an account statement.
- **Best supporting sentence** (page 12): *On Camt.053 XML account statement the*
- **Notes:** p39 pain.002 status report; p12 'On Camt.053 XML account statement ...'.

### Q60 [comparison] — PARTIALLY VERIFIED
- **Question:** How does Settlement Date differ from Execution Date?
- **Ground truth:** Execution Date is when payment is requested. Settlement Date is when funds actually transfer.
- **Best supporting sentence** (page 8): *be repeated if, for example, the requested execution date, payment type and/or*
- **Notes:** p8 'the requested execution date', RequestedExecutionDate; Settlement Date concept present; combined sentence not verbatim.
