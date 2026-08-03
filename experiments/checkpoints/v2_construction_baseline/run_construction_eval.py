"""run_construction_eval.py — CONSTRUCTION ABLATION: graph-side re-evaluation.

Runs the SAME corrected 12-question benchmark (benchmark_v2.json) through the
EXACT same evaluator (evaluator_v2.evaluate_graph_rag), QA model
(settings.ANSWER_MODEL/ANSWER_PROVIDER), prompt template, temperature (0.0),
and retrieval pipeline (graph_rag.retriever.GraphRAGRetriever) as the official
v2 run — against the REBUILT graph (corrected full-range source_pages).

The vector phase is NOT re-run: the construction fix does not touch the vector
system (FAISS index, embeddings, QA model all unchanged), so the recorded
vector results remain the valid unchanged control.

Outputs:
  evaluation/benchmark_v2_graph_construction_results.json  (new graph records)
  evaluation/benchmark_v2_graph_construction_summary.json  (metrics + report data)
  experiments/construction_ablation.md is generated separately by
  gen_construction_report.py from the summary JSON (kept as a distinct,
  pure-offline step so the report can be regenerated without LLM calls).

Usage (must reproduce the recorded v2 model config):
  ANSWER_MODEL=openai/gpt-oss-120b ANSWER_PROVIDER=groq \
  CYPHER_MODEL=openai/gpt-oss-120b CYPHER_PROVIDER=groq \
  python evaluation/run_construction_eval.py [--skip-preflight]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.metrics_v2 import compute_all_metrics  # noqa: E402
from config.settings import settings  # noqa: E402

EVAL_DIR = Path(__file__).parent
V2_PATH = ROOT / "experiments" / "benchmark_v2.json"
V1_GRAPH_RESULTS = EVAL_DIR / "benchmark_v2_graph_results.json"
V1_SUMMARY = EVAL_DIR / "benchmark_v2_summary.json"
NEW_GRAPH_RESULTS = EVAL_DIR / "benchmark_v2_graph_construction_results.json"
NEW_SUMMARY = EVAL_DIR / "benchmark_v2_graph_construction_summary.json"
BEFORE_STATS = ROOT / "experiments" / "construction_stats_before.json"
AFTER_STATS = ROOT / "experiments" / "construction_stats_after.json"


def _assert_fair_config():
    """Fail loudly unless the recorded v2 model config is reproduced.

    The ENTIRE ablation's fairness rests on running the exact QA + Cypher
    models the official v2 run used (openai/gpt-oss-120b via groq, per
    benchmark_v2_summary.json and benchmark_v2_eval.log). Current settings
    defaults point at Qwen/HF, so omitting the env overrides would silently
    produce a mislabeled "same QA model" report.
    """
    expected = ("openai/gpt-oss-120b", "groq")
    got = (settings.ANSWER_MODEL, settings.ANSWER_PROVIDER)
    got_cypher = (settings.CYPHER_MODEL, settings.CYPHER_PROVIDER)
    if got != expected:
        raise SystemExit(
            f"FAIRNESS GUARD FAILED: ANSWER model {got} != recorded {expected}.\n"
            "Re-run with: ANSWER_MODEL=openai/gpt-oss-120b ANSWER_PROVIDER=groq "
            "CYPHER_MODEL=openai/gpt-oss-120b CYPHER_PROVIDER=groq "
            "python evaluation/run_construction_eval.py"
        )
    if got_cypher != expected:
        raise SystemExit(
            f"FAIRNESS GUARD FAILED: CYPHER model {got_cypher} != recorded {expected} "
            "(Cypher generation is part of retrieval and must match v2)."
        )


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(EVAL_DIR / "construction_ablation_eval.log", mode="a", encoding="utf-8"),
        ],
    )
    logging.getLogger("langchain").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("neo4j").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


def _poisoned(record: dict) -> bool:
    err = (record.get("error") or "").lower()
    return ("quota exhausted" in err) or any(
        h in err for h in ("timed out", "timeout", "connection", "getaddrinfo",
                           "urlopen", "winerror", "10054", "11001", "eof", "ssl",
                           "unreachable", "reset", "read operation", "network")
    )


def phase_complete(path, expected: int) -> bool:
    p = Path(path)
    if not p.exists():
        return False
    try:
        with open(p, encoding="utf-8") as f:
            recs = json.load(f)
        return len(recs) == expected and not any(_poisoned(r) for r in recs)
    except Exception:
        return False


def run_graph_phase(questions, out_path):
    from evaluation.evaluator_v2 import EvaluationRecorder, evaluate_graph_rag

    if phase_complete(out_path, len(questions)):
        logging.getLogger(__name__).info("Graph phase already complete, skipping.")
        with open(out_path, encoding="utf-8") as f:
            return json.load(f)
    recorder = EvaluationRecorder("GraphRAG-ConstructionV2")
    evaluate_graph_rag(questions, recorder, checkpoint_path=str(out_path))
    recorder.save(str(out_path))
    return recorder.records


def main():
    parser = argparse.ArgumentParser(description="Construction ablation: graph-side re-eval")
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args()

    setup_logging()
    _assert_fair_config()
    logger = logging.getLogger(__name__)
    logger.info("CONSTRUCTION ABLATION graph phase: %s via %s (cypher %s via %s)",
                settings.ANSWER_MODEL, settings.ANSWER_PROVIDER,
                settings.CYPHER_MODEL, settings.CYPHER_PROVIDER)

    questions = json.load(open(V2_PATH, encoding="utf-8"))
    logger.info("Loaded %d corrected questions", len(questions))

    if not args.skip_preflight and not phase_complete(NEW_GRAPH_RESULTS, len(questions)):
        from evaluation.run_fair_eval import preflight_credits
        if not preflight_credits():
            logger.error("Preflight failed — not starting the run.")
            return

    records = run_graph_phase(questions, NEW_GRAPH_RESULTS)

    # ── Metrics (same computation as run_v2_eval) ─────────────────────
    new_metrics = compute_all_metrics(
        [r.get("answer", "") for r in records],
        [r.get("ground_truth", "") for r in records],
        [r.get("retrieved_chunks", []) or r.get("retrieved_entities", []) for r in records],
        [r.get("category", "unknown") for r in records],
    )

    v1_graph_metrics = {}
    if V1_GRAPH_RESULTS.exists():
        v1_records = json.load(open(V1_GRAPH_RESULTS, encoding="utf-8"))
        v1_graph_metrics = compute_all_metrics(
            [r.get("answer", "") for r in v1_records],
            [r.get("ground_truth", "") for r in v1_records],
            [r.get("retrieved_chunks", []) or r.get("retrieved_entities", []) for r in v1_records],
            [r.get("category", "unknown") for r in v1_records],
        )["aggregate"]

    v1_vector_metrics = {}
    v1_metrics_from_summary = {}
    if V1_SUMMARY.exists():
        s = json.load(open(V1_SUMMARY, encoding="utf-8"))
        v1_metrics_from_summary = s.get("graph_rag_metrics", {})
        v1_vector_metrics = s.get("vector_rag_metrics", {})

    before_stats = json.load(open(BEFORE_STATS, encoding="utf-8")) if BEFORE_STATS.exists() else {}
    after_stats = json.load(open(AFTER_STATS, encoding="utf-8")) if AFTER_STATS.exists() else {}

    # per-question before/after answer comparison
    v1_by_id = {r["question_id"]: r for r in json.load(open(V1_GRAPH_RESULTS, encoding="utf-8"))} \
        if V1_GRAPH_RESULTS.exists() else {}
    per_question = []
    for r in records:
        qid = r["question_id"]
        old = v1_by_id.get(qid, {})
        per_question.append({
            "question_id": qid,
            "category": r["category"],
            "question": r["question"],
            "ground_truth": r["ground_truth"],
            "v1_answer": old.get("answer"),
            "v2_answer": r.get("answer"),
            "v1_error": old.get("error"),
            "v2_error": r.get("error"),
        })

    summary = {
        "config": {
            "model": settings.ANSWER_MODEL,
            "provider": settings.ANSWER_PROVIDER,
            "cypher_model": settings.CYPHER_MODEL,
            "cypher_provider": settings.CYPHER_PROVIDER,
            "temperature": 0.0,
            "n_questions": len(questions),
            "same_evaluator": True,
            "same_prompt_template": "SAME_QA_PROMPT_TEMPLATE (unchanged)",
            "same_retrieval_code": True,
            "same_graph_schema": True,
            "only_change": "graph construction (source_pages full-range attribution)",
        },
        "v1_graph_metrics": v1_graph_metrics or v1_metrics_from_summary,
        "v2_graph_metrics": new_metrics["aggregate"],
        "v1_vector_metrics": v1_vector_metrics,
        "construction_stats_before": before_stats,
        "construction_stats_after": after_stats,
        "per_question": per_question,
    }
    with open(NEW_SUMMARY, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    logger.info("V1 graph aggregate: %s", json.dumps(summary["v1_graph_metrics"]))
    logger.info("V2 graph aggregate: %s", json.dumps(summary["v2_graph_metrics"]))
    logger.info("Summary written to %s", NEW_SUMMARY)


if __name__ == "__main__":
    main()
