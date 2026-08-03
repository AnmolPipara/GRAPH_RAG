"""run_retrieval_eval.py — PRIORITY 2 RETRIEVAL ABLATION: graph-side re-evaluation.

Runs the SAME corrected 12-question benchmark (benchmark_v2.json) through the
EXACT same evaluator (evaluator_v2.evaluate_graph_rag), QA model
(settings.ANSWER_MODEL/ANSWER_PROVIDER), prompt template, temperature (0.0),
and Cypher model as the official v2 run — against the SAME v2 graph (1,046
nodes / 878 rels, unchanged).

The ONLY change: the retriever's evidence selection. v2 attached page-level
evidence (first 2 source_pages per matched entity, 3 paragraphs x 500 chars).
This run's retriever attaches chunk-level evidence (ALL source_chunks of
matched entities, lexically ranked, top-3 chunks x up to 1200 chars). See
experiments/retrieval_ablation_diagnostic.md for the offline gate that
approved this run.

The vector phase is NOT re-run: the retrieval change does not touch the vector
system, so the recorded vector results remain the valid unchanged control.

Outputs:
  evaluation/benchmark_v2_graph_candidategen_results.json  (new graph records)
  evaluation/benchmark_v2_graph_candidategen_summary.json  (metrics + comparison)
  NOTE: distinct filenames from the retained v3 baseline
  (benchmark_v2_graph_retrieval_{results,summary}.json) so the recorded v3
  chunk-level run stays untouched as the comparison baseline. The markdown
  report (experiments/candidate_gen_ablation.md) is generated from the
  summary JSON (pure-offline step).

Usage (must reproduce the recorded model config):
  ANSWER_MODEL=openai/gpt-oss-120b ANSWER_PROVIDER=groq \
  CYPHER_MODEL=openai/gpt-oss-120b CYPHER_PROVIDER=groq \
  python evaluation/run_retrieval_eval.py [--skip-preflight]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.metrics_v2 import compute_all_metrics  # noqa: E402
from config.settings import settings  # noqa: E402

EVAL_DIR = ROOT / "evaluation"
V2_PATH = ROOT / "experiments" / "benchmark_v2.json"
V2_SUMMARY = EVAL_DIR / "benchmark_v2_graph_construction_summary.json"
NEW_GRAPH_RESULTS = EVAL_DIR / "benchmark_v2_graph_candidategen_results.json"
NEW_SUMMARY = EVAL_DIR / "benchmark_v2_graph_candidategen_summary.json"
V2_GRAPH_RESULTS = EVAL_DIR / "benchmark_v2_graph_construction_results.json"


def _assert_fair_config():
    """Fail loudly unless the recorded v2 model config is reproduced.

    The ENTIRE ablation's fairness rests on running the exact QA + Cypher
    models the official v2 run used (openai/gpt-oss-120b via groq). Current
    settings defaults point at Qwen/HF, so omitting the env overrides would
    silently produce a mislabeled "same QA model" report.
    """
    expected = ("openai/gpt-oss-120b", "groq")
    got = (settings.ANSWER_MODEL, settings.ANSWER_PROVIDER)
    got_cypher = (settings.CYPHER_MODEL, settings.CYPHER_PROVIDER)
    if got != expected:
        raise SystemExit(
            f"FAIRNESS GUARD FAILED: ANSWER model {got} != recorded {expected}.\n"
            "Re-run with: ANSWER_MODEL=openai/gpt-oss-120b ANSWER_PROVIDER=groq "
            "CYPHER_MODEL=openai/gpt-oss-120b CYPHER_PROVIDER=groq "
            "python evaluation/run_retrieval_eval.py"
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
            logging.FileHandler(EVAL_DIR / "retrieval_ablation_eval.log", mode="a", encoding="utf-8"),
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
    recorder = EvaluationRecorder("GraphRAG-CandidateGen")
    evaluate_graph_rag(questions, recorder, checkpoint_path=str(out_path))
    recorder.save(str(out_path))
    return recorder.records


def main():
    parser = argparse.ArgumentParser(description="Retrieval ablation: graph-side re-eval")
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args()

    setup_logging()
    _assert_fair_config()
    logger = logging.getLogger(__name__)
    logger.info("RETRIEVAL ABLATION graph phase: %s via %s (cypher %s via %s)",
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

    # ── Metrics (same computation as run_construction_eval) ────────────
    new_metrics = compute_all_metrics(
        [r.get("answer", "") for r in records],
        [r.get("ground_truth", "") for r in records],
        [r.get("retrieved_chunks", []) or r.get("retrieved_entities", []) for r in records],
        [r.get("category", "unknown") for r in records],
    )

    v2_graph_metrics = {}
    v1_vector_metrics = {}
    if V2_SUMMARY.exists():
        s = json.load(open(V2_SUMMARY, encoding="utf-8"))
        v2_graph_metrics = s.get("v2_graph_metrics", {})
        v1_vector_metrics = s.get("v1_vector_metrics", {})

    # per-question before/after answer comparison (v2 vs retrieval-v3)
    v2_by_id = {}
    if V2_GRAPH_RESULTS.exists():
        v2_by_id = {r["question_id"]: r for r in json.load(open(V2_GRAPH_RESULTS, encoding="utf-8"))}
    per_question = []
    for r in records:
        qid = r["question_id"]
        old = v2_by_id.get(qid, {})
        per_question.append({
            "question_id": qid,
            "category": r["category"],
            "question": r["question"],
            "ground_truth": r["ground_truth"],
            "v2_answer": old.get("answer"),
            "v3_answer": r.get("answer"),
            "v2_error": old.get("error"),
            "v3_error": r.get("error"),
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
            "same_graph_schema": True,
            "same_graph_data": True,
            "same_benchmark": str(V2_PATH),
            "only_change": "candidate generation: ranked-keyword entity matching + deterministic entity cap (2 ranked keywords, 12 entities) replacing keywords[:2] + LIMIT 6 (see experiments/candidate_gen_ablation.md)",
        },
        "v2_graph_metrics": v2_graph_metrics,
        "v3_graph_metrics": new_metrics["aggregate"],
        "v1_vector_metrics": v1_vector_metrics,
        "per_question": per_question,
    }
    with open(NEW_SUMMARY, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    logger.info("V2 graph aggregate: %s", json.dumps(summary["v2_graph_metrics"]))
    logger.info("V3 (chunk-level) graph aggregate: %s", json.dumps(summary["v3_graph_metrics"]))
    logger.info("Summary written to %s", NEW_SUMMARY)


if __name__ == "__main__":
    main()
