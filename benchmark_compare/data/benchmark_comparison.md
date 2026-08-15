# Vector RAG vs Graph RAG — ISO 20022 Payments Guide

- LLM (both systems): **llama-3.1-8b-instant** via groq (temperature 0)
- Embeddings: **sentence-transformers/all-mpnet-base-v2**, chunks 1000/200, top-5
- Graph: 602 nodes / 401 edges from merged_knowledge.json (max depth 3)
- Total wall time: 0.0s

## Judge verdicts (LLM-as-judge, per question)

| Q | Difficulty | Vector RAG | Graph RAG |
|---|------------|------------|-----------|
| 1 | easy | correct | correct |
| 2 | easy | correct | correct |
| 3 | easy | correct | wrong |
| 4 | medium | wrong | correct |
| 5 | medium | correct | correct |
| 6 | medium | partial | correct |
| 7 | medium | correct | correct |
| 8 | hard | wrong | partial |
| 9 | hard | partial | correct |
| 10 | hard | correct | wrong |

## Aggregate judge scores (correct=1, partial=0.5, wrong=0)

- Vector RAG: **0.70**
- Graph RAG: **0.75**

## Lexical metrics (metrics_v2, per system)

| Metric | Vector RAG | Graph RAG |
|--------|-----------|-----------|
| f1_score | 0.262 | 0.243 |
| answer_accuracy | 0.713 | 0.800 |
| context_recall | 0.456 | 0.732 |
| faithfulness | 0.647 | 0.689 |
| hallucination_rate | 0.353 | 0.311 |

## Per-question answers

### Q1 [easy] — correct vs correct

**Question:** The ISO 20022 standard is used for payment messages. Which legislative body enacted the regulation that made the ISO 20022 standard mandatory in euro transactions between banks and their customers?

**Reference:** The European Parliament and the Council (Regulation (EU) No 260/2012).

**Vector RAG** (accurately quotes the reference answer):

> The legislative body that enacted the regulation making the ISO 20022 standard mandatory in euro transactions between banks and their customers is the European Parliament and the Council. This is stated on page 4 of the provided context, specifically in the sentence: "Regulation (EU) No 260/2012 of the European Parliament and the Council establishing technical and business requirements for credit transfers and direct debits in euro makes the ISO 20022 standard mandatory also in transactions between banks and their customers."

**Graph RAG** (accurately quotes the reference answer):

> The legislative body that enacted the regulation making the ISO 20022 standard mandatory in euro transactions between banks and their customers is the European Parliament and the Council. This is mentioned in the context on page 4 of the ISO 20022 Payments Guide, which states that Regulation (EU) No 260/2012 of the European Parliament and the Council establishes technical and business requirements for credit transfers and direct debits in euro, making the ISO 20022 standard mandatory in these transactions.

*Vector retrieved pages:* [4, 4, 31, 4, 46]  |  *Graph matched entities:* ['ISO 20022', 'ISO', 'ISO 20022-compliant reporting messages', 'ISO 20022 Message Definition Report', '1.1 Usage of ISO 20022 in Finland', 'ISO 20022 Address Elements', 'ISO 20022 Payments Guide', 'Instant Payments Regulation', 'Regulation (EU) No 260/2012', 'Customer', 'ISO 11649', 'International Organization for Standardization', 'CustomerCreditTransferInitiationV09', 'Customer Payment Status Report V10', 'Payment Status Report', 'European Parliament', 'Section 2.54', 'Section 2.55', 'Section 2.60', 'Section 2.61', 'Section 2.67', 'Section 2.68', 'Section 2.70', 'Section 2.71', 'Section 2.72']

### Q2 [easy] — correct vs correct

**Question:** According to the guide, the latest versions of the SEPA Rulebooks and Implementation Guidelines should always be checked from www.europeanpaymentscouncil.eu. Which organisation publishes and maintains these SEPA documents and operates that website?

**Reference:** The European Payments Council (EPC).

**Vector RAG** (All key facts present):

> According to the context, the European Payments Council (EPC) publishes and maintains the SEPA documents and operates the website www.europeanpaymentscouncil.eu.

**Graph RAG** (All key facts present):

> According to the context, the European Payments Council (EPC) is the organisation responsible for publishing and maintaining the SEPA documents, including the SEPA Rulebooks and Implementation Guidelines. They also operate the website www.europeanpaymentscouncil.eu, where the latest versions of these documents can be checked.

*Vector retrieved pages:* [4, 4, 4, 52, 31]  |  *Graph matched entities:* ['SEPA', 'Organisation', 'SEPA Instant Credit Transfer Customer-to-PSP Implementation Guidelines', 'SEPA Credit Transfer Customer-to-PSP Implementation Guidelines', 'SEPA Credit Transfer Implementation Guidelines', 'SEPA Implementation Guidelines', 'SEPA Rulebook', 'Bank-Specific Implementation Guidelines', 'Other Organisation Identification', 'Other Organisation Identifier', 'Organisation Identification', 'SEPA Credit Transfer Rulebook', 'T11/11 SEPA Supplementary Data', 'SEPA Instant Credit Transfer', 'European Payments Council', 'Implementation Guide', 'SEPA Credit Transfer', 'Organisation ID', 'SEPA Countries', 'SEPA Payments', 'Payment', 'SEPA CT', 'Euro', 'Id', 'AT-xx']

### Q3 [easy] — correct vs wrong

**Question:** In SEPA credit transfers, which value of the ChargeBearer element in the Payment Information block indicates that the debtor and the creditor each pay their own charges?

**Reference:** SLEV.

**Vector RAG** (Fully answers the question with the correct value.):

> According to the provided context, in SEPA credit transfers, the value of the ChargeBearer element in the Payment Information block that indicates that the debtor and the creditor each pay their own charges is "SLEV" (Service Level).

**Graph RAG** (Does not explicitly mention the correct value for the ChargeBearer element.):

> According to the provided context, on page 75, it is mentioned that "With SEPA payments ”SLEV” = Service level". However, the specific value for the ChargeBearer element that indicates the debtor and the creditor each pay their own charges is not explicitly mentioned in the provided context.

However, on page 75, it is mentioned that "With SEPA payments ”SLEV” = Service level". But the ChargeBearer element is mentioned on page 75 as "Specifies which party/parties will bear the charges associated with the processing of the payment transaction." 

But on page 75, it is also mentioned that "Recommended use is on the PaymentInformation level. With SEPA payments ”SLEV” = Service level". 

However, the specific value for the ChargeBearer element that indicates the debtor and the creditor each pay their own charges is not explicitly mentioned in the provided context.

However, on page 75, it is mentioned that "With SEPA payments ”SLEV” = Service level". But the ChargeBearer element is mentioned on page 75 as "Specifies which party/parties will bear the charges associated with the processing of the payment transaction." 

However, the specific value for the ChargeBearer element that indicates the debtor and the creditor each pay their own charges is not explicitly mentioned in the provided context.

However, on page 75, it is mentioned that "With SEPA payments ”SLEV” = Service level". But the ChargeBearer element is mentioned on page 75 as "Specifies which party/parties will bear the charges associated with the processing of the payment transaction." 

However, the specific value for the ChargeBearer element that indicates the debtor and the creditor each pay their own charges is not explicitly mentioned in the provided context.

However, on page 75, it is mentioned that "With SEPA payments ”SLEV” = Service level". But the ChargeBearer element is mentioned on page 75 as "Specifies which party/parties will bear the charges associated with the processing of the payment transaction." 

However, the specific value for the ChargeBearer element that indicates the debtor and the creditor each pay their own charges is not explicitly mentioned in the provided context.

However, on page 75, it is mentioned that "With SEPA payments ”SLEV” = Service level". But the ChargeBearer element is mentioned on page 75 as "Specifies which party/parties will bear the charges associated with the processing of the payment transaction." 

However, the specific value for the ChargeBearer element that indicates the debtor and

*Vector retrieved pages:* [19, 13, 14, 12, 22]  |  *Graph matched entities:* ['Payment Information', 'PaymentInformation', 'Charge Bearer', 'SEPA', 'SEPA Instant Credit Transfer Customer-to-PSP Implementation Guidelines', 'SEPA Credit Transfer Customer-to-PSP Implementation Guidelines', 'SEPA Credit Transfer Implementation Guidelines', 'Original Payment Information Identification', '6.1.6 Original Payment Information And Status', 'National Corporate File Transfer Solution', 'Original Payment Information And Status', 'Payment Information Identification', 'PaymentInformationIdentifier', 'SEPA Implementation Guidelines', '2.2.2 Payment Information - Block B', 'Original Payment Information', 'SEPA Credit Transfer Rulebook', 'T11/11 SEPA Supplementary Data', 'SEPA Instant Credit Transfer', 'Payment Information Status', 'Payment Information Block', 'International Transfers', '2.3.3 Payment Information', 'PaymentInformationId', 'SEPA Credit Transfer']

### Q4 [medium] — wrong vs correct

**Question:** A payment is credited to the account of a financing company, but the ultimate creditor of the payment is a customer of that financing company. Which element in the Credit Transfer Transaction Information block (Block C) is used to identify this customer as the ultimate beneficiary?

**Reference:** The UltimateCreditor element (index 2.148).

**Vector RAG** (Incorrect index and sub-elements):

> Based on the provided context, the element used to identify the ultimate creditor (customer of the financing company) in the Credit Transfer Transaction Information block (Block C) is the "Ultimate Creditor" element (2.149, 0..1).

More specifically, within the "Ultimate Creditor" element, the "Name" (2.149, 0..1) and "Identification" (2.151, 0..1) sub-elements are used to forward the name and ID of the ultimate creditor, respectively.

Therefore, the correct answer is the "Ultimate Creditor" element (2.149, 0..1) in the Credit Transfer Transaction Information block (Block C).

**Graph RAG** (Correctly identified Ultimate Creditor element):

> Based on the provided context, the element used to identify the ultimate creditor (beneficiary) in the Credit Transfer Transaction Information block (Block C) is the "Ultimate Creditor" element.

According to the context, the "Ultimate Creditor" element is defined as:

"The party who is the ultimate creditor of the payment. For example, a payment is credited to the account of a financing company, but the ultimate creditor is a customer of the financing company."

This element is part of the Credit Transfer Transaction Information block (Block C) and is used to identify the ultimate creditor of the payment, which in this case is the customer of the financing company.

The relevant context is:

[Source chunk | page 7] Debtor or Originator Reference Party 
is used when the receiver of the 
invoice is different from the debtor.  
Initiating 
Party 
 
The party on whose initiative the 
payment data is established. This 
might be the debtor itself, an agent, or 
the company service centre.  
Creditor 
Beneficiary 
Seller 
The party whose account is credited 
with the payment.  
Ultimate 
Creditor 
Ultimate Beneficiary 
Beneficiary Reference Party 
The party who is the ultimate creditor 
of the payment. For example, a 
payment is credited to the account of 
a financing company, but the ultimate 
creditor is a customer of the financing 
company.  
Debtor 
agent  
Bank (Originating Bank  
Originator’s Bank  
Debtor’s Bank) 
Party is the bank of the debtor. 
 
Creditor 
agent 
Bank (Creditor’s Bank 
Seller’s Bank) 
Party is the bank of the creditor.

[Source chunk | page 8] 2.2.3 
Credit Transfer Transaction Information – Block C 
Credit Transfer Transaction Information is an element in the Payment Information 
block. It is mandatory and can occur multiple times. It contains information related to 
the credit side of the transaction, such as Creditor, CreditorAgent and 
RemittanceInformation.

*Vector retrieved pages:* [27, 31, 12, 11, 20]  |  *Graph matched entities:* ['Credit Transfer Transaction Information', 'CreditTransferTransactionInformation', '2.2.3 Credit Transfer Transaction Information - Block C', 'Financing Company', 'FI', '2.3.4 Credit Transfer Transaction Information', '2.2.2 Payment Information - Block B', 'Payment Information Block', 'Transaction Information', '2.2.1 Group Header - Block A', 'Debtor Company Plc', 'Credit Transfer', 'Transaction', 'Block A', 'Block C', 'BENE', 'Ultimate Creditor', 'Business ID', 'Subsidiary', 'Creditor', 'Original Payment Information And Status', 'Transaction Information And Status', 'Payment Identification', 'Original Transaction', 'Shared Service Centre']

### Q5 [medium] — correct vs correct

**Question:** Salaries and pensions are paid as recurring credit transfers. Which Category Purpose code is used to recognise them, and how are these credit transfers booked on the debtor's account statement?

**Reference:** Category Purpose code SALA; they are made as a combined debit on the debtor's account statement.

**Vector RAG** (fully answers with correct details):

> According to the provided context, salaries and pensions are paid as recurring credit transfers and are recognised by the Category Purpose code "SALA" (Page 32). 

These credit transfers are made as a combined debit on the debtor's account statement (Page 32).

**Graph RAG** (fully answers with correct details):

> According to the provided context, salaries and pensions are paid as recurring credit transfers. The Category Purpose code used to recognise them is "SALA" (page 14). 

These credit transfers are made as a combined debit on the debtor's account statement (page 32).

*Vector retrieved pages:* [28, 32, 29, 14, 17]  |  *Graph matched entities:* ['3.5 Salaries and pensions', 'Salaries and Pensions', 'Category Purpose', 'Purpose', 'PENS', 'SALA', 'Purpose Code']

### Q6 [medium] — partial vs correct

**Question:** The additional optional service of combining invoices (AOS2) was replaced in November 2019 by another AOS. Which service replaced it, and of which rulebook is that service an optional part?

**Reference:** The AOS Extended Remittance Information (ERI); it is an optional part of the European Payments Council (EPC) SEPA Credit Transfer Rulebook.

**Vector RAG** (missing reference to rulebook):

> According to the context, the additional optional service of combining invoices (AOS2) was replaced in November 2019 with the AOS Extended Remittance Information (ERI). 

This information can be found on page 32 of the context.

**Graph RAG** (fully answers with all key facts present):

> According to the provided context, the additional optional service of combining invoices (AOS2) was replaced in November 2019 by the Extended Remittance Information (ERI). 

ERI is an optional part of the European Payments Council SEPA Credit Transfer Rulebook.

So, the service that replaced AOS2 is ERI, and it is an optional part of the SEPA Credit Transfer Rulebook.

*Vector retrieved pages:* [32, 29, 10, 32, 31]  |  *Graph matched entities:* ['AOS', 'Combining Invoices', '0..1', '4.2 Combining invoices and credit notes / Extended Remittance Information (ERI)', 'Additional Optional Service (AOS)', '4.1 Payment Date (AOS1)', 'Payment Date']

### Q7 [medium] — correct vs correct

**Question:** When the payee is a legal person and the verification of payee is performed against an identification code such as a business ID, VAT number or Legal Entity Identifier (LEI), which VOP response types are possible?

**Reference:** Only Match, No match and Not possible. (Close match is not possible when a legal person is verified with an identification code.)

**Vector RAG** (Fully answers with correct key facts):

> According to the context, when the payee is a legal person and the verification of payee is performed against an identification code such as a business ID, VAT number or Legal Entity Identifier (LEI), the following VOP response types are possible:

- MATCH
- NO MATCH
- NOT POSSIBLE

This information is found on page 54 of the context.

**Graph RAG** (Fully answers with correct key facts):

> According to the provided context, when the payee is a legal person and the verification of payee is performed against an identification code such as a business ID, VAT number or Legal Entity Identifier (LEI), the following VOP response types are possible:

- MATCH
- NO MATCH
- NOT POSSIBLE

These response types are mentioned in the context on page 54, which states: "If the verification is performed for a legal person using an identification code, only MATCH, NO MATCH and NOT POSSIBLE responses are possible."

*Vector retrieved pages:* [53, 52, 52, 53, 54]  |  *Graph matched entities:* ['LEI', 'VOP', 'FI', 'Verification of Payee', 'EPC Recommendations for the Matching Processes under the VOP Scheme Rulebook', "European Payments Council's Verification of Payee Scheme Rulebook", 'Private Identification', 'Inter-PSP Verification', 'Single VOP Requests', 'VOP Scheme Rulebook', 'VOP Response Types', 'VOP Data File', 'VOP Response', 'VOP Request', 'VOP Service', 'Private ID', 'VAT Number', 'VOP Scheme', 'Entity', 'ERI', 'Id', 'Corporate Customer', '9 October 2025', 'NOT POSSIBLE', 'CLOSE MATCH']

### Q8 [hard] — wrong vs partial

**Question:** In the XML message example of section 5.2, the second Payment Information block identifies its payment as a SEPA instant credit transfer using the Local Instrument code INST. Which creditor receives this payment, which creditor reference is attached to it, and what instructed amount in euro is given?

**Reference:** SAAJA TOIMITTAJA OY; creditor reference RF47892182916 (with Issuer ISO); instructed amount 2000.02 EUR.

**Vector RAG** (Lacks key information about the creditor and instructed amount):

> Unfortunately, the provided context does not contain information about the XML message example of section 5.2. The context only contains information about the structure and elements of the Customer Credit Transfer Initiation V09 message, but it does not provide a specific example.

However, based on the provided context, I can tell you that the Local Instrument code "INST" is used to specify the payment as a SEPA instant credit transfer (section 2.89, page 21).

To answer the question, I would need more information about the XML message example of section 5.2, which is not provided in the given context.

**Graph RAG** (Identifies creditor reference but not instructed amount, and incorrectly states that creditor reference is in Payment Information block):

> Based on the provided context, we can analyze the XML message example in section 5.2. 

The XML message example is as follows:

```xml
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.09" 
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
xsi:schemaLocation="urn:iso:std:iso:20022:tech:xsd:pain.001.001.09 
pain.001.001.09.xsd"> 
 
<CstmrCdtTrfInitn> 
 
 
<GrpHdr> 
 
 
 
<MsgId>MSGID000001</MsgId> 
 
 
 
<CreDtTm>2023-04-03T10:30:00</CreDtTm> 
 
 
 
<NbOfTxs>2</NbOfTxs> 
 
 
 
<CtrlSum>3000.03</CtrlSum> 
 
 
 
<InitgPty> 
 
 
 
 
<Nm>Group Finance</Nm> 
 
 
 
 
<PstlAdr> 
 
 
 
 
 
<StrtNm>Aleksanterinkatu</StrtNm> 
 
 
 
 
 
<BldgNb>123</BldgNb> 
 
 
 
 
 
<PstCd>00100</PstCd> 
 
 
 
 
 
<TwnNm>HELSINKI</TwnNm> 
 
 
 
 
 
<Ctry>FI</Ctry>
```

However, the second Payment Information block is not provided in the given XML message example. We need to look at the structure of the Payment Information block to understand how it is related to the creditor, creditor reference, and instructed amount.

According to the context, the Payment Information block contains elements related to the debit side of the transaction. This information is common to all the credit transfers (Block C) attached to this PaymentInformation.

The Payment Information block is composed of the following elements:

- Payment Information Identification (Identifier): Unique identification of the PaymentInformation element assigned by the Initiating Party.
- Debtor Account (BusinessComponent): Information related to the debtor's account.
- Payment Type Information (BusinessComponent): Information related to the payment type.
- Requested Execution Date (Date): The debit date requested by the customer.

However, the creditor reference and instructed amount are not directly related to the Payment Information block. The creditor reference is related to the Ultimate Creditor Identification (BusinessComponent) in the Credit Transfer Transaction Information block,

*Vector retrieved pages:* [19, 21, 12, 13, 10]  |  *Graph matched entities:* ['Local Instrument', 'INST', 'Payment Information', 'PaymentInformation', 'SEPA', 'SEPA Instant Credit Transfer Customer-to-PSP Implementation Guidelines', '5.2 Credit transfer with message - XML message example', 'Local Instrument Proprietary', 'SEPA Instant Credit Transfer', 'Local Instrument Code', 'SEPA Credit Transfer Customer-to-PSP Implementation Guidelines', 'SEPA Credit Transfer Implementation Guidelines', 'Original Payment Information Identification', '6.1.6 Original Payment Information And Status', 'Original Payment Information And Status', 'Financial Institution Identification', 'Original Instruction Identification', 'Payment Information Identification', 'PaymentInformationIdentifier', 'SEPA Implementation Guidelines', '2.2.2 Payment Information - Block B', 'Camt.053 XML Account Statement', 'Original Payment Information', 'SEPA Credit Transfer Rulebook', 'T11/11 SEPA Supplementary Data']

### Q9 [hard] — partial vs correct

**Question:** The payment message with MessageIdentification MSGID000001 passes structural validation at the bank. Which schema does the bank use for the return message, which Group Status does that return message carry, and which original identifier does it include?

**Reference:** The Payment Status Report schema pain.002.001.10 with Group Status ACTC; it returns the original MessageIdentification MSGID000001 (in the OrgnlMsgId element).

**Vector RAG** (Incorrectly states schema validation for the return message):

> Based on the provided context, since the payment message with MessageIdentification MSGID000001 passes structural validation at the bank, the bank uses schema A: Structure, schema validation for the return message.

According to the context on page 39, when the payment message is approved technically, the return message Group Status is ACTC, and the return message returns the value of the original MessageIdentification.

Therefore, the bank uses the schema pain.002.001.10 return for the return message, the Group Status of the return message is ACTC, and the return message includes the original MessageIdentification, which is MSGID000001.

**Graph RAG** (Accurately identifies schema, Group Status, and original MessageIdentification):

> Based on the provided context, the payment message with MessageIdentification MSGID000001 passes structural validation at the bank. 

The bank uses the schema pain.002.001.10 for the return message (Source chunk | page 39). 

The return message carries the Group Status ACTC, indicating that the whole payment message is received and approved technically (Source chunk | page 39).

The return message includes the original MessageIdentification, which is MSGID000001 (Source chunk | page 39).

*Vector retrieved pages:* [39, 39, 41, 40, 39]  |  *Graph matched entities:* ['MSGID000001', 'Id', 'Group Status', 'GroupStatus', 'Validation', 'MsgId', '0..1', '6.1.1 Validation of message structure', 'Message Identification', 'MessageIdentification', '6.1.2 Content validation', 'Structure Validation', 'Content Validation', 'Identification', 'FI', 'Nm', 'ACCP', 'ACTC', 'PART', 'RJCT']

### Q10 [hard] — correct vs wrong

**Question:** During content validation, a single transaction is rejected because the format of the account number specified is not correct. Which status reason code is returned, at which component level of the pain.002.001.10 message is the rejection reported, and which transaction status does it carry?

**Reference:** Status reason code AC01; the rejection is reported at transaction level in the TransactionInformationAndStatus component of the OriginalPaymentInformationAndStatus block; the transaction status is RJCT.

**Vector RAG** (All key facts present and accurate.):

> Based on the provided context, during content validation, a single transaction is rejected because the format of the account number specified is not correct. 

The status reason code returned is AC01 (Format of the account number specified is not correct), as specified in the External Code List / ExternalStatusReason1Code (Page 51).

The rejection is reported at the Transaction level, as mentioned in 6.1.2 Content validation (Page 39), where it is stated that a return message is created on Credit Transfer Transaction level.

The transaction status it carries is RJCT (all rejected), as specified in the GroupStatus field (Page 39).

**Graph RAG** (Incorrect component level specified.):

> Based on the provided context, the answer to the question is as follows:

The status reason code returned is AC01, which indicates that the format of the account number specified is not correct.

The rejection is reported at the transaction level of the pain.002.001.10 message, specifically within the <OrgnlGrpInfAndSts> component.

The transaction status it carries is RJCT, which indicates that the transaction has been rejected.

This information is based on the following excerpts from the provided context:

- Rejection reason codes (page None): AC01 is the code for "Format of the account number specified is not correct".
- 6.1.2 Content validation (page None): A single transaction has been rejected, and the rejection reason is returned as a code or/and a description.
- 6.1.3 Message root (page 40): The rejection reason is returned within the <OrgnlGrpInfAndSts> component.
- 6.1.4 Group Header (page 40): The transaction status RJCT is used to indicate that the transaction has been rejected.

*Vector retrieved pages:* [39, 51, 40, 39, 39]  |  *Graph matched entities:* ['Validation', '0..1', '1..1', '6.1.1 Validation of message structure', 'Rejection Reason Description', '6.1.2 Content validation', 'Rejection Reason Codes', 'Rejection Reason Code', 'Structure Validation', 'Content Validation', 'FI', 'Id', 'Requested Execution Date', 'Private Identification', 'Category Purpose', 'Local Instrument', 'Debtor Account', 'Postal Address', 'Organisation', 'Proprietary', 'Purpose', 'Proxy']
