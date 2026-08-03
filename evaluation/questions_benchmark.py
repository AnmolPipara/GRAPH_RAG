"""
questions_benchmark.py - 60 Evaluation Questions Across 8 Categories.
"""

BENCHMARK_QUESTIONS = [
    {"id": 1, "category": "fact_lookup", "question": "What is the address of Finance Finland?", "ground_truth": "Itamerenkatu 11-13, FI-00180 Helsinki, Finland."},
    {"id": 2, "category": "fact_lookup", "question": "What is the phone number for Finance Finland?", "ground_truth": "+358 20 793 9000"},
    {"id": 3, "category": "fact_lookup", "question": "Who published the ISO 20022 Payments Guide?", "ground_truth": "Finance Finland (Finanssiala ry)."},
    {"id": 4, "category": "fact_lookup", "question": "How many pages does the ISO 20022 Payments Guide have?", "ground_truth": "61 pages."},
    {"id": 5, "category": "fact_lookup", "question": "What is the version number of the guide?", "ground_truth": "Version 3.1."},
    {"id": 6, "category": "fact_lookup", "question": "What is the publication year of the ISO 20022 Payments Guide?", "ground_truth": "2025."},
    {"id": 7, "category": "fact_lookup", "question": "What is the email address for Finance Finland payments team?", "ground_truth": "payments@finanssiala.fi"},
    {"id": 8, "category": "fact_lookup", "question": "What is the ISO 20022 website provided by Finance Finland?", "ground_truth": "www.finanssiala.fi/iso20022"},
    {"id": 9, "category": "definition", "question": "What is ISO 20022?", "ground_truth": "ISO 20022 is an international standard for financial messaging."},
    {"id": 10, "category": "definition", "question": "What is a Group Header in ISO 20022 payment messages?", "ground_truth": "Block A containing message identification, creation date, and number of transactions."},
    {"id": 11, "category": "definition", "question": "What is a Debtor in payment messaging?", "ground_truth": "The party that owes funds and initiates the payment."},
    {"id": 12, "category": "definition", "question": "What is a Credit Transfer Transaction?", "ground_truth": "A payment instruction transferring funds from the debtor to the creditor account."},
    {"id": 13, "category": "definition", "question": "What is Remittance Information?", "ground_truth": "Details about payment purpose such as invoice numbers or reference codes."},
    {"id": 14, "category": "definition", "question": "What is BIC in payments?", "ground_truth": "Bank Identifier Code, a unique identifier for financial institutions."},
    {"id": 15, "category": "definition", "question": "What is IBAN?", "ground_truth": "International Bank Account Number, a standardized account identifier."},
    {"id": 16, "category": "definition", "question": "What is a Payment Status Report?", "ground_truth": "The pain.002 message reporting payment instruction status."},
    {"id": 17, "category": "multi_hop", "question": "Which organization published the ISO 20022 standard used in Finland?", "ground_truth": "Finance Finland published the ISO 20022 Payments Guide based on the ISO 20022 standard."},
    {"id": 18, "category": "multi_hop", "question": "What message types are used to initiate credit transfers?", "ground_truth": "The pain.001 (Customer Credit Transfer Initiation) message type."},
    {"id": 19, "category": "multi_hop", "question": "What information is contained in the Payment Information block?", "ground_truth": "Block B contains payment type, debtor details, debtor account, and debtor agent info."},
    {"id": 20, "category": "multi_hop", "question": "How is a payment routed from the debtor to the creditor?", "ground_truth": "Debtor to Debtor Agent to Creditor Agent to Creditor."},
    {"id": 21, "category": "multi_hop", "question": "What entities are involved in a direct debit transaction?", "ground_truth": "Creditor, Creditor Agent, Debtor Agent, and Debtor."},
    {"id": 22, "category": "multi_hop", "question": "Who publishes the ISO 20022 Payments Guide and where are they located?", "ground_truth": "Finance Finland at Itamerenkatu 11-13, Helsinki."},
    {"id": 23, "category": "multi_hop", "question": "How do pain.001 and pain.002 messages relate to each other?", "ground_truth": "pain.001 is the request message and pain.002 is the status response message."},
    {"id": 24, "category": "multi_hop", "question": "What components make up Credit Transfer Transaction Information?", "ground_truth": "Payment Identification, Amount, Currency, Charge Bearer, and Remittance Information."},
    {"id": 25, "category": "relationship", "question": "How is ISO 20022 related to Finance Finland?", "ground_truth": "Finance Finland publishes the ISO 20022 Payments Guide for the Finnish payment ecosystem."},
    {"id": 26, "category": "relationship", "question": "What is the relationship between a Debtor and a Creditor?", "ground_truth": "The Debtor owes funds and initiates payment to the Creditor."},
    {"id": 27, "category": "relationship", "question": "How does pain.001 relate to pacs.008?", "ground_truth": "pain.001 initiates the payment and pacs.008 clears it between banks."},
    {"id": 28, "category": "relationship", "question": "How does Block B relate to Block C in a payment message?", "ground_truth": "Block B contains one or more Block C entries."},
    {"id": 29, "category": "relationship", "question": "What is the relationship between an IBAN and a bank account?", "ground_truth": "IBAN uniquely identifies a specific bank account for payments."},
    {"id": 30, "category": "relationship", "question": "How does Charge Bearer relate to payment fees?", "ground_truth": "Charge Bearer specifies which party pays transaction fees."},
    {"id": 31, "category": "relationship", "question": "How does a Clearing Code relate to a financial institution?", "ground_truth": "Clearing Code uniquely identifies a bank within a clearing system."},
    {"id": 32, "category": "relationship", "question": "How does pain.002 relate to pain.001?", "ground_truth": "pain.002 provides the status response to a previously submitted pain.001."},
    {"id": 33, "category": "hierarchical", "question": "What is the hierarchical structure of a payment message?", "ground_truth": "Block A (Group Header) contains Block B (Payment Information) which contains Block C (Transactions)."},
    {"id": 34, "category": "hierarchical", "question": "What are the main sections of the ISO 20022 Payments Guide?", "ground_truth": "Introduction, General Principles, Message Structure, Payment Types, Definitions, Appendices."},
    {"id": 35, "category": "hierarchical", "question": "What components make up Payment Type Information?", "ground_truth": "Service Level, Local Instrument, and Category Purpose."},
    {"id": 36, "category": "hierarchical", "question": "What are the sub-components of Remittance Information?", "ground_truth": "Unstructured Remittance and Structured Remittance."},
    {"id": 37, "category": "hierarchical", "question": "What are the levels of message definitions in ISO 20022?", "ground_truth": "Business Process, Message Definition, Building Blocks, and Elements."},
    {"id": 38, "category": "hierarchical", "question": "What is the hierarchy of party identifiers in a payment?", "ground_truth": "Party Name, Postal Address, Identification, and Contact Details."},
    {"id": 39, "category": "cross_section", "question": "How is address formatted across different message types?", "ground_truth": "Street Name, Building Number, Town Name, Country, and Postal Code."},
    {"id": 40, "category": "cross_section", "question": "What common elements appear in both pain.001 and pain.002?", "ground_truth": "Both share the Group Header structure."},
    {"id": 41, "category": "cross_section", "question": "How is currency specified across different payment instructions?", "ground_truth": "Using the 3-letter ISO 4217 currency code in the Amount element."},
    {"id": 42, "category": "cross_section", "question": "What identification methods are used for financial institutions?", "ground_truth": "BIC and Clearing System Member Identification."},
    {"id": 43, "category": "cross_section", "question": "How are amounts formatted across payment messages?", "ground_truth": "Decimal numbers with up to 2 decimal places."},
    {"id": 44, "category": "cross_section", "question": "What regulations are referenced across payment scenarios?", "ground_truth": "PSD2, SEPA regulations, and Finnish payment regulations."},
    {"id": 45, "category": "workflow", "question": "What is the workflow for initiating a credit transfer?", "ground_truth": "Debtor creates pain.001, sends to Debtor Agent, Agent sends pacs.008 to Creditor Agent."},
    {"id": 46, "category": "workflow", "question": "How does a direct debit process work?", "ground_truth": "Creditor sends pain.008, Creditor Agent sends pacs.003 to Debtor Agent."},
    {"id": 47, "category": "workflow", "question": "What happens when a payment is rejected?", "ground_truth": "The agent sends a pain.002 with rejection reason codes."},
    {"id": 48, "category": "workflow", "question": "What is the sequence of messages in a cross-border payment?", "ground_truth": "pain.001, pacs.008, pacs.009, and pain.002."},
    {"id": 49, "category": "workflow", "question": "How is a payment cancellation processed?", "ground_truth": "camt.056 is sent, the agent processes it, and a status report is returned."},
    {"id": 50, "category": "workflow", "question": "What is the end-to-end payment processing flow?", "ground_truth": "Initiation, Validation, Clearing, Settlement, and Confirmation."},
    {"id": 51, "category": "workflow", "question": "How does a failed payment investigation work?", "ground_truth": "camt.056 or camt.087 is sent and camt.029 is returned with the resolution."},
    {"id": 52, "category": "workflow", "question": "How does a payment status change during processing?", "ground_truth": "Accepted to Pending to Settled to Confirmed or Rejected status."},
    {"id": 53, "category": "comparison", "question": "What is the difference between pain.001 and pacs.008?", "ground_truth": "pain.001 is payment initiation, pacs.008 is interbank clearing."},
    {"id": 54, "category": "comparison", "question": "How does a credit transfer differ from a direct debit?", "ground_truth": "Credit transfer: debtor pushes funds. Direct debit: creditor pulls funds."},
    {"id": 55, "category": "comparison", "question": "What is the difference between Structured and Unstructured Remittance?", "ground_truth": "Structured uses predefined formats. Unstructured is free text."},
    {"id": 56, "category": "comparison", "question": "How does SEPA differ from a domestic Finnish payment?", "ground_truth": "SEPA follows pan-European rules. Finnish payments use national codes."},
    {"id": 57, "category": "comparison", "question": "What is the difference between Block A and Block B?", "ground_truth": "Block A has message-level info. Block B has payment-level details."},
    {"id": 58, "category": "comparison", "question": "How does Debtor Agent differ from Creditor Agent?", "ground_truth": "Debtor Agent sends the payment. Creditor Agent receives the payment."},
    {"id": 59, "category": "comparison", "question": "What is the difference between pain.002 and camt.053?", "ground_truth": "pain.002 reports payment status. camt.053 is an account statement."},
    {"id": 60, "category": "comparison", "question": "How does Settlement Date differ from Execution Date?", "ground_truth": "Execution Date is when payment is requested. Settlement Date is when funds actually transfer."},
]


def get_questions_by_category(category=None):
    """Return questions optionally filtered by category."""
    if category:
        return [q for q in BENCHMARK_QUESTIONS if q["category"] == category]
    return BENCHMARK_QUESTIONS


def get_categories():
    """Return the sorted list of unique categories."""
    cats = set()
    for q in BENCHMARK_QUESTIONS:
        cats.add(q["category"])
    return sorted(cats)


if __name__ == "__main__":
    print(f"Total questions: {len(BENCHMARK_QUESTIONS)}")
    for cat in get_categories():
        count = len(get_questions_by_category(cat))
        print(f"  {cat}: {count} questions")
