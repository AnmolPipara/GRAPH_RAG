"""Resumable driver for the CORRECTED benchmark (benchmark_v2.json).

Phase 3 of the benchmark-validation study. Runs ONLY the corrected questions
(12) through the EXACT same evaluator functions, QA model, prompt template,
temperature, retrieval pipeline, and graph as the official v1 run
(run_fair_eval.py). The ONLY difference is the question set.

No evaluator, model, prompt, temperature, retrieval, or graph changes here —
this file only wires the existing components to the repaired question list.
Results go to benchmark_v2_{vector,graph}_results.json (separate from the
official checkpoints so the v1 records stay untouched).
"""

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.metrics_v2 import compute_all_metrics
from config.settings import settings

logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).parent
V2_PATH = ROOT / "experiments" / "benchmark_v2.json"
VEC_PATH = EVAL_DIR / "benchmark_v2_vector_results.json"
GRAPH_PATH = EVAL_DIR / "benchmark_v2_graph_results.json"
SUMMARY_PATH = EVAL_DIR / "benchmark_v2_summary.json"

# Original v1 smoke records (for the original-vs-validated comparison).
V1_CHECKPOINT = ROOT / "experiments" / "checkpoints" / "v1_source_evidence"


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(EVAL_DIR / "benchmark_v2_eval.log", mode="a", encoding="utf-8"),
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


def run_phase(kind: str, questions, out_path):
    from evaluation.evaluator_v2 import EvaluationRecorder

    if phase_complete(out_path, len(questions)):
        logger.info("Phase %s already complete (%d records), skipping.", kind, len(questions))
        with open(out_path, encoding="utf-8") as f:
            return json.load(f)
    if kind == "vector":
        from evaluation.evaluator_v2 import evaluate_vector_rag
        recorder = EvaluationRecorder("VectorRAG")
        evaluate_vector_rag(questions, recorder, checkpoint_path=str(out_path))
    else:
        from evaluation.evaluator_v2 import evaluate_graph_rag
        recorder = EvaluationRecorder("GraphRAG")
        evaluate_graph_rag(questions, recorder, checkpoint_path=str(out_path))
    recorder.save(str(out_path))
    logger.info("Phase %s done: %d/%d records", kind, len(recorder.records), len(questions))
    return recorder.records


def main():
    parser = argparse.ArgumentParser(description="Run corrected benchmark (benchmark_v2.json)")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip the quota preflight probe")
    args = parser.parse_args()

    setup_logging()
    logger.info("CORRECTED BENCHMARK (benchmark_v2.json): %s via %s",
                settings.ANSWER_MODEL, settings.ANSWER_PROVIDER)

    questions = json.load(open(V2_PATH, encoding="utf-8"))
    logger.info("Loaded %d corrected questions", len(questions))

    if not args.skip_preflight and (not phase_complete(VEC_PATH, len(questions))
                                    or not phase_complete(GRAPH_PATH, len(questions))):
        from evaluation.run_fair_eval import preflight_credits
        if not preflight_credits():
            logger.error("Preflight failed — not starting the run.")
            return

    vec_records = run_phase("vector", questions, VEC_PATH)
    graph_records = run_phase("graph", questions, GRAPH_PATH)

    if not vec_records or not graph_records:
        logger.error("Incomplete records. Vector=%d Graph=%d", len(vec_records), len(graph_records))
        return

    # Same metric computation as run_fair_eval (unchanged evaluator logic).
    vec_metrics = compute_all_metrics(
        [r.get("answer", "") for r in vec_records],
        [r.get("ground_truth", "") for r in vec_records],
        [r.get("retrieved_chunks", []) or r.get("retrieved_entities", []) for r in vec_records],
        [r.get("category", "unknown") for r in vec_records],
    )
    graph_metrics = compute_all_metrics(
        [r.get("answer", "") for r in graph_records],
        [r.get("ground_truth", "") for r in graph_records],
        [r.get("retrieved_chunks", []) or r.get("retrieved_entities", []) for r in graph_records],
        [r.get("category", "unknown") for r in graph_records],
    )

    # Load v1 original smoke records for the overlap questions (2, 5, 7, 8)
    # so the original-vs-validated comparison covers BOTH systems.
    def load_v1(name):
        p = V1_CHECKPOINT / name
        if not p.exists():
            return {}
        return {r["question_id"]: r for r in json.load(open(p, encoding="utf-8"))}

    v1_vec = load_v1("vector_rag_results.json")
    v1_graph = load_v1("graph_rag_results.json")
    v2_vec = {r["question_id"]: r for r in vec_records}

    summary = {
        "config": {
            "model": settings.ANSWER_MODEL,
            "provider": settings.ANSWER_PROVIDER,
            "temperature": 0.0,
            "n_questions": len(questions),
            "same_evaluator": True,
            "same_prompt_template": "SAME_QA_PROMPT_TEMPLATE (unchanged)",
            "same_retrieval": True,
            "same_graph": True,
        },
        "vector_rag_metrics": vec_metrics["aggregate"],
        "graph_rag_metrics": graph_metrics["aggregate"],
        "vector_rag_per_category": vec_metrics["per_category"],
        "graph_rag_per_category": graph_metrics["per_category"],
        "overlap_original_vs_corrected": [],
    }
    for rec in graph_records:
        qid = rec["question_id"]
        orig = v1_graph.get(qid)
        orig_vec = v1_vec.get(qid)
        new_vec = v2_vec.get(qid)
        summary["overlap_original_vs_corrected"].append({
            "question_id": qid,
            "category": rec["category"],
            "original_question": orig["question"] if orig else None,
            "original_ground_truth": orig["ground_truth"] if orig else None,
            "original_answer": orig["answer"] if orig else None,
            "original_vector_answer": orig_vec["answer"] if orig_vec else None,
            "corrected_question": rec["question"],
            "corrected_ground_truth": rec["ground_truth"],
            "corrected_answer": rec["answer"],
            "corrected_vector_answer": new_vec["answer"] if new_vec else None,
        })
    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    logger.info("VectorRAG corrected aggregate: %s", json.dumps(vec_metrics["aggregate"]))
    logger.info("GraphRAG corrected aggregate: %s", json.dumps(graph_metrics["aggregate"]))
    logger.info("SUMMARY written to %s", SUMMARY_PATH)


if __name__ == "__main__":
    main()
