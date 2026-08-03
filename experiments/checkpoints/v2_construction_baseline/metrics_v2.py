"""
metrics_v2.py - Enhanced QA Evaluation Metrics.

Computes all 9 requested metrics:
  - Answer Accuracy, Faithfulness, Context Precision, Context Recall,
    Exact Match (EM), F1 Score, Hallucination Rate, Citation Correctness,
    Multi-hop Success Rate.
"""

import re
import math
from typing import List, Dict, Tuple
from collections import Counter


def normalize_answer(text: str) -> str:
    """Normalize answer text for comparison."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def exact_match(answer: str, ground_truth: str) -> float:
    """Exact Match score after normalization."""
    return 1.0 if normalize_answer(answer) == normalize_answer(ground_truth) else 0.0


def f1_score(answer: str, ground_truth: str) -> float:
    """Token-level F1 score."""
    a_tokens = normalize_answer(answer).split()
    g_tokens = normalize_answer(ground_truth).split()

    if not a_tokens or not g_tokens:
        return 0.0

    common = Counter(a_tokens) & Counter(g_tokens)
    num_same = sum(common.values())

    if num_same == 0:
        return 0.0

    precision = num_same / len(a_tokens)
    recall = num_same / len(g_tokens)
    return 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0


def answer_accuracy(answer: str, ground_truth: str) -> float:
    """Accuracy score based on key phrase overlap."""
    a_norm = normalize_answer(answer)
    g_norm = normalize_answer(ground_truth)

    g_keywords = set(g_norm.split())
    a_words = set(a_norm.split())

    if not g_keywords:
        return 0.0

    overlap = g_keywords & a_words
    return len(overlap) / len(g_keywords)


def faithfulness(answer: str, contexts: List[str]) -> float:
    """Estimate faithfulness: fraction of answer claims supported by context.

    Simplified: checks if named entities in answer appear in the context.
    """
    if not contexts or not answer:
        return 1.0 if not answer else 0.0

    a_lower = answer.lower()
    context_text = " ".join(c.lower() for c in contexts if c)

    if not context_text:
        return 0.0

    words = normalize_answer(answer).split()
    if not words:
        return 1.0

    supported = sum(1 for w in words if w in context_text)
    return supported / len(words)


def context_precision(contexts: List[str], ground_truth: str) -> float:
    """Estimate context precision: how much of the context is relevant to the question."""
    if not contexts:
        return 0.0

    g_norm = normalize_answer(ground_truth)
    g_words = set(g_norm.split())

    if not g_words:
        return 1.0

    total_scores = []
    for ctx in contexts:
        ctx_norm = normalize_answer(ctx)
        ctx_words = set(ctx_norm.split())
        if not ctx_words:
            total_scores.append(0.0)
        else:
            overlap = len(g_words & ctx_words)
            total_scores.append(overlap / len(ctx_words))

    return sum(total_scores) / len(total_scores) if total_scores else 0.0


def context_recall(contexts: List[str], ground_truth: str) -> float:
    """Estimate context recall: how much of the ground truth is covered by context."""
    if not contexts:
        return 0.0

    g_norm = normalize_answer(ground_truth)
    g_words = set(g_norm.split())

    if not g_words:
        return 1.0

    context_text = " ".join(normalize_answer(c) for c in contexts if c)
    c_words = set(context_text.split())

    overlap = len(g_words & c_words)
    return overlap / len(g_words)


def hallucination_rate(answer: str, contexts: List[str]) -> float:
    """Estimate hallucination rate: fraction of answer not supported by context.

    Higher = more hallucination. 0.0 = fully grounded, 1.0 = fully hallucinated.
    """
    if not answer:
        return 0.0
    if not contexts:
        return 1.0

    f = faithfulness(answer, contexts)
    return 1.0 - f


def citation_correctness(answer: str, ground_truth: str, contexts: List[str]) -> float:
    """Estimate whether the answer is correctly grounded in the provided contexts.

    Combines faithfulness (claims in answer are supported by context) with
    accuracy (answer matches ground truth). This is a proxy metric: we check
    that the answer both contains the correct information AND is grounded in
    the retrieved context.

    Returns a score from 0.0 (no correct citations) to 1.0 (perfect).
    """
    if not answer:
        return 0.0

    # Factor 1: answer is faithful to context (claims are supported)
    faith = faithfulness(answer, contexts)

    # Factor 2: answer is accurate (covers ground truth)
    acc = answer_accuracy(answer, ground_truth)

    # Combined: both must be present for a correct citation
    return (faith * 0.5) + (acc * 0.5)


def multi_hop_success(answer: str, ground_truth: str) -> float:
    """For multi-hop questions, check if answer captures multiple hops.

    Simplified: check if answer contains multiple distinct entities/concepts
    that overlap with the ground truth.
    """
    a_entities = set(normalize_answer(answer).split())
    g_entities = set(normalize_answer(ground_truth).split())

    overlap = a_entities & g_entities

    if not g_entities:
        return 0.0
    return len(overlap) / len(g_entities)


def compute_all_metrics(
    answers: List[str],
    ground_truths: List[str],
    contexts_list: List[List[str]],
    categories: List[str] = None,
) -> Dict:
    """Compute all 9 metrics for a set of Q&A pairs."""
    results = []

    for i, (ans, gt, ctxs) in enumerate(zip(answers, ground_truths, contexts_list)):
        cat = categories[i] if categories else "unknown"

        entry = {
            "index": i,
            "category": cat,
            "exact_match": exact_match(ans, gt),
            "f1_score": f1_score(ans, gt),
            "answer_accuracy": answer_accuracy(ans, gt),
            "faithfulness": faithfulness(ans, ctxs),
            "context_precision": context_precision(ctxs, gt),
            "context_recall": context_recall(ctxs, gt),
            "hallucination_rate": hallucination_rate(ans, ctxs),
            "citation_correctness": citation_correctness(ans, gt, ctxs),
            "multi_hop_success": multi_hop_success(ans, gt),
        }
        results.append(entry)

    # Aggregate averages
    agg = {}
    for key in ["exact_match", "f1_score", "answer_accuracy", "faithfulness",
                 "context_precision", "context_recall", "hallucination_rate",
                 "citation_correctness", "multi_hop_success"]:
        values = [r[key] for r in results]
        agg[key] = round(sum(values) / len(values), 4) if values else 0.0

    # Per-category breakdown
    cat_breakdown = {}
    if categories:
        for cat in set(categories):
            cat_results = [r for r in results if r["category"] == cat]
            if cat_results:
                cat_agg = {}
                for key in agg:
                    vals = [r[key] for r in cat_results]
                    cat_agg[key] = round(sum(vals) / len(vals), 4) if vals else 0.0
                cat_breakdown[cat] = cat_agg

    return {
        "per_question": results,
        "aggregate": agg,
        "per_category": cat_breakdown,
    }


if __name__ == "__main__":
    # Quick test
    test_answers = ["Finance Finland is at Itamerenkatu 11-13 in Helsinki."]
    test_gts = ["Itamerenkatu 11-13, FI-00180 Helsinki, Finland."]
    test_ctxs = [["Finance Finland, Itamerenkatu 11-13, FI-00180 Helsinki, Finland"]]

    m = compute_all_metrics(test_answers, test_gts, test_ctxs)
    print("Aggregate:", m["aggregate"])
