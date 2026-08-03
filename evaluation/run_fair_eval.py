"""Resumable fair evaluation driver for Vector RAG vs GraphRAG.

Both systems generate answers with the SAME model/provider
(settings.ANSWER_MODEL via settings.ANSWER_PROVIDER) so the comparison
isolates the retrieval method. Skips phases already complete in the
checkpoint files.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.questions_benchmark import BENCHMARK_QUESTIONS
from evaluation.metrics_v2 import compute_all_metrics
from evaluation.graph_metrics import compute_graph_statistics, print_graph_stats
from evaluation.report import generate_report
from config.settings import settings

logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).parent
VEC_PATH = EVAL_DIR / "vector_rag_results.json"
GRAPH_PATH = EVAL_DIR / "graph_rag_results.json"


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(EVAL_DIR / "evaluation.log", mode="a", encoding="utf-8"),
        ],
    )
    logging.getLogger("langchain").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("neo4j").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


def _is_quota_poisoned(record: dict) -> bool:
    """True if a record's error marks quota exhaustion rather than a genuine
    query failure. Every fail-fast path writes the literal prefix
    "Quota exhausted: ..." (retriever.query returns it; evaluator's
    _invoke_with_retry raises RuntimeError("Quota exhausted: ...") which is
    recorded verbatim). Checking the exact prefix avoids false positives on
    domain words like "credits" in payments-corpus error text.
    """
    return "quota exhausted" in (record.get("error") or "").lower()


_TRANSPORT_HINTS = (
    "timed out", "timeout", "connection", "getaddrinfo", "urlopen",
    "winerror", "10054", "11001", "eof", "ssl", "unreachable",
    "reset", "read operation", "network",
)


def _is_network_poisoned(record: dict) -> bool:
    """True if a record's error marks a transient transport failure (DNS
    resolution, connection reset, read timeout) rather than a genuine
    retrieval/quality outcome. The evaluator now retries these, so any that
    survive retries mean the provider was unreachable for that question;
    treating the phase as complete would bake network garbage into the report.
    """
    err = (record.get("error") or "").lower()
    return any(h in err for h in _TRANSPORT_HINTS)


def _is_poisoned(record: dict) -> bool:
    """Infrastructure failure (quota exhausted OR transport/network error)
    rather than a genuine query failure.
    """
    return _is_quota_poisoned(record) or _is_network_poisoned(record)


def phase_complete(path, expected: int) -> bool:
    """True only if the checkpoint holds EXACTLY the expected record count
    and none of those records are infrastructure failures (quota exhaustion
    or network/transport errors).

    Using == (not >=) avoids mixing question sets: a full 60-record file must
    not satisfy a 10-question --quick run, and an interrupted partial file
    (e.g. 25 records) still fails the check so the phase re-runs.

    The quota-poisoning check is essential: when the daily token cap is hit,
    fail-fast records errors for every remaining question (so the file still
    reaches `expected` records) — treating that as complete would generate a
    report from fabricated failures.
    """
    path = Path(path)
    if not path.exists():
        return False
    try:
        with open(path, encoding="utf-8") as f:
            records = json.load(f)
        if len(records) != expected:
            return False
        return not any(_is_poisoned(r) for r in records)
    except Exception:
        return False


def _count_poisoned(records) -> int:
    return sum(1 for r in records if _is_poisoned(r))


def _quarantine_poisoned(paths):
    """Move ONLY the quota-poisoned checkpoint files aside so the next run
    starts fresh, while preserving any clean phase's valid results.
    """
    qdir = EVAL_DIR / "poisoned_quota"
    qdir.mkdir(exist_ok=True)
    for p in paths:
        p = Path(p)
        if p.exists():
            dest = qdir / p.name
            if dest.exists():
                dest.unlink()
            p.rename(dest)
            logger.info("Quarantined poisoned checkpoint %s -> %s/%s", p.name, qdir.name, dest.name)


def run_vector_phase(questions):
    from evaluation.evaluator_v2 import evaluate_vector_rag, EvaluationRecorder

    logger.info("PHASE 1: Vector RAG Evaluation (fair LLM = %s via %s)",
                settings.ANSWER_MODEL, settings.ANSWER_PROVIDER)
    recorder = EvaluationRecorder("VectorRAG")
    evaluate_vector_rag(questions, recorder, checkpoint_path=str(VEC_PATH))
    recorder.save(str(VEC_PATH))
    logger.info("Vector RAG: %d/%d questions", len(recorder.records), len(questions))
    return recorder.records


def run_graph_phase(questions):
    from evaluation.evaluator_v2 import evaluate_graph_rag, EvaluationRecorder

    logger.info("PHASE 2: GraphRAG Evaluation (fair LLM = %s via %s)",
                settings.ANSWER_MODEL, settings.ANSWER_PROVIDER)
    recorder = EvaluationRecorder("GraphRAG")
    evaluate_graph_rag(questions, recorder, checkpoint_path=str(GRAPH_PATH))
    recorder.save(str(GRAPH_PATH))
    logger.info("GraphRAG: %d/%d questions", len(recorder.records), len(questions))
    return recorder.records


def compute_system_metrics(vec_records, graph_records):
    def avg(records, key):
        vals = [r.get(key, 0) for r in records]
        return round(sum(vals) / len(vals), 4) if vals else 0

    def err_rate(records):
        return round(sum(1 for r in records if r.get("error")) / len(records), 4) if records else 0

    return {
        "vector_rag": {
            "provider": settings.ANSWER_PROVIDER,
            "model": settings.ANSWER_MODEL,
            "avg_retrieval_time": avg(vec_records, "retrieval_latency_s"),
            "avg_generation_time": avg(vec_records, "generation_latency_s"),
            "avg_total_time": avg(vec_records, "total_latency_s"),
            "error_rate": err_rate(vec_records),
            "total_questions": len(vec_records),
        },
        "graph_rag": {
            "provider": settings.ANSWER_PROVIDER,
            "model": settings.ANSWER_MODEL,
            "avg_retrieval_time": avg(graph_records, "retrieval_latency_s"),
            "avg_generation_time": avg(graph_records, "generation_latency_s"),
            "avg_total_time": avg(graph_records, "total_latency_s"),
            "error_rate": err_rate(graph_records),
            "total_questions": len(graph_records),
        },
    }


def _preserve_oversized_checkpoint(path, n: int):
    """Back up a clean checkpoint that holds MORE records than the current run.

    phase_complete() requires an exact record count, so a finished full-60 run
    is treated as "incomplete" by a 10-question smoke and would otherwise be
    silently overwritten. Moving it to previous/ preserves the valid results.
    """
    p = Path(path)
    if not p.exists():
        return
    try:
        with open(p, encoding="utf-8") as f:
            recs = json.load(f)
    except Exception:
        return
    # Backup decision stays on QUOTA poisoning only: quota means the whole
    # run is garbage (every remaining question fail-fasts), while a single
    # transient transport error (now retried) doesn't invalidate an otherwise
    # clean larger checkpoint that a smaller smoke run would overwrite.
    if len(recs) > n and not any(_is_quota_poisoned(r) for r in recs):
        backup_dir = EVAL_DIR / "previous"
        backup_dir.mkdir(exist_ok=True)
        dest = backup_dir / p.name
        try:
            if dest.exists():
                dest.unlink()
            p.rename(dest)
        except OSError as e:
            logger.error("Could not back up %s to previous/ (%s); the phase "
                         "re-run will overwrite the existing checkpoint.", p.name, e)
            return
        logger.warning(
            "Backed up existing %d-record clean checkpoint %s -> previous/%s "
            "(current run: %d questions)", len(recs), p.name, p.name, n
        )


def preflight_credits() -> bool:
    """Make one micro-call to verify the answer provider still has credits/quota.

    An exhausted account makes the whole benchmark fail-fast through every
    question on HTTP 402s (fast but pointless), then the post-run guard
    quarantines everything. A single tiny probe (~$0.0001 on the HF router)
    catches it up front and aborts with a clear message instead.
    """
    provider = settings.ANSWER_PROVIDER.lower()
    if provider == "huggingface":
        import urllib.error
        import urllib.request

        try:
            from utils.hf_client import HFReasoningChatModel
            routing = HFReasoningChatModel.routing_suffix
        except Exception:
            routing = ":cheapest"
        body = json.dumps({
            "model": settings.huggingface_model + routing,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 8,
            "enable_thinking": False,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://router.huggingface.co/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {settings.huggingface_api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30):
                logger.info("PREFLIGHT: answer provider responds (credits OK).")
                return True
        except urllib.error.HTTPError as e:
            if e.code == 402:
                logger.error(
                    "PREFLIGHT FAILED: HuggingFace included credits are depleted (HTTP 402). "
                    "Add credits at huggingface.co/settings/billing, or wait for the next "
                    "monthly reset. Not starting the run."
                )
                return False
            if e.code == 401:
                logger.error(
                    "PREFLIGHT FAILED: HuggingFace API key rejected (HTTP 401). "
                    "Check HUGGINGFACE_API_KEY in .env. Not starting the run."
                )
                return False
            logger.warning("PREFLIGHT: provider returned HTTP %s (non-quota); continuing.", e.code)
            return True
        except Exception as e:
            logger.warning("PREFLIGHT: probe error %s (non-quota); continuing.", e)
            return True
    # Non-HF providers: probe through the shared QA LLM.
    try:
        from evaluation.evaluator_v2 import _create_qa_llm

        _create_qa_llm().invoke("ping")
        logger.info("PREFLIGHT: answer provider responds (quota OK).")
        return True
    except Exception as e:
        msg = str(e).lower()
        if any(k in msg for k in
               ("quota", "credits", "depleted", "402", "per day", "tpd",
                "daily", "free tier", "no credits", "401",
                "unauthorized", "invalid api key")):
            # NOTE: "billing" excluded on purpose — Groq appends the sales pitch
            # ".../settings/billing" to EVERY 429 (incl. per-minute TPM spikes
            # that clear in seconds), so matching it would falsely abort the run
            # before launch. TPD matches via "per day"/"tpd"; HF 402 via
            # "credits"/"depleted".
            logger.error("PREFLIGHT FAILED: answer provider has no quota left (%s). "
                         "Not starting the run.", str(e)[:160])
            return False
        logger.warning("PREFLIGHT: probe failed for a non-quota reason (%s); continuing.", str(e)[:120])
        return True


def main():
    parser = argparse.ArgumentParser(description="Resumable fair Vector RAG vs GraphRAG evaluation")
    parser.add_argument("--quick", action="store_true",
                        help="Evaluate on first 10 questions (same as --questions 10)")
    parser.add_argument("--questions", type=int, default=0,
                        help="Evaluate on the first N questions only (0 = all 60). "
                             "Cheap smoke: --questions 10 costs ~$0.05 on the HF router; "
                             "the full 60x2 run costs ~$1.20-1.80.")
    args = parser.parse_args()

    setup_logging()
    logger.info("FAIR EVALUATION: Vector RAG vs GraphRAG")
    logger.info("  Shared model  : %s via %s", settings.ANSWER_MODEL, settings.ANSWER_PROVIDER)

    questions = BENCHMARK_QUESTIONS
    if args.questions:
        questions = questions[:args.questions]
        logger.info("Smoke mode: %d questions", len(questions))
    elif args.quick:
        questions = questions[:10]
        logger.info("Quick mode: %d questions", len(questions))

    n = len(questions)

    # PREFLIGHT: never launch a benchmark doomed to fail-fast through every
    # question on quota/credit 402s — one micro-call detects it up front.
    if (not phase_complete(VEC_PATH, n)) or (not phase_complete(GRAPH_PATH, n)):
        if not preflight_credits():
            return

    # A larger clean checkpoint (e.g. a finished full-60 run) must not be
    # silently overwritten by a smaller smoke run — back it up first.
    _preserve_oversized_checkpoint(VEC_PATH, n)

    if phase_complete(VEC_PATH, n):
        with open(VEC_PATH, encoding="utf-8") as f:
            vec_records = json.load(f)
        logger.info("Vector RAG phase already complete (%d records), skipping.", len(vec_records))
    else:
        vec_records = run_vector_phase(questions)

    _preserve_oversized_checkpoint(GRAPH_PATH, n)

    if phase_complete(GRAPH_PATH, n):
        with open(GRAPH_PATH, encoding="utf-8") as f:
            graph_records = json.load(f)
        logger.info("GraphRAG phase already complete (%d records), skipping.", len(graph_records))
    else:
        graph_records = run_graph_phase(questions)

    if not vec_records or not graph_records:
        logger.error("Incomplete records. Vector=%d Graph=%d", len(vec_records), len(graph_records))
        return

    # GUARD: a run that hit the daily token cap mid-way records quota errors for
    # every remaining question (fail-fast). Generating metrics/report from that
    # would silently present fabricated failures as results — abort instead and
    # quarantine the poisoned files so the next run starts clean.
    vec_poisoned = _count_poisoned(vec_records)
    graph_poisoned = _count_poisoned(graph_records)
    if vec_poisoned or graph_poisoned:
        # Quarantine ONLY the poisoned phase's file so a clean, already-complete
        # phase keeps its valid results and is not re-run wastefully.
        to_quarantine = []
        if vec_poisoned:
            to_quarantine.append(VEC_PATH)
        if graph_poisoned:
            to_quarantine.append(GRAPH_PATH)
        logger.error(
            "ABORTED: quota/network errors mid-run (Vector %d/%d records poisoned, "
            "Graph %d/%d). Results would be invalid - report NOT generated. "
            "Add provider credits/quota or retry once the network recovers.",
            vec_poisoned, len(vec_records), graph_poisoned, len(graph_records),
        )
        _quarantine_poisoned(to_quarantine)
        return

    logger.info("PHASE 3: Computing Metrics")
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
    logger.info("VectorRAG aggregate: %s", json.dumps(vec_metrics["aggregate"]))
    logger.info("GraphRAG aggregate: %s", json.dumps(graph_metrics["aggregate"]))

    logger.info("PHASE 4: Graph Quality Analysis")
    graph_stats = compute_graph_statistics()
    print_graph_stats(graph_stats)

    logger.info("PHASE 5: Report Generation")
    system_metrics = compute_system_metrics(vec_records, graph_records)
    generate_report(vec_records, graph_records, vec_metrics, graph_metrics,
                    graph_stats, system_metrics)

    logger.info("EVALUATION COMPLETE — results in evaluation/")


if __name__ == "__main__":
    main()
