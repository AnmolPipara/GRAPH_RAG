"""
evaluator_v2.py - Enhanced Dual RAG Evaluator.

Runs both Vector RAG and GraphRAG on the same benchmark questions,
recording detailed per-question metrics for fair comparison.

FAIR COMPARISON RULES (enforced):
- Same LLM for answer generation: both systems use settings.ANSWER_MODEL
  with settings.ANSWER_PROVIDER and temperature=0.0
- Same embedding model for indexing (settings.embedding_model)
- Same prompt template for QA
- The ONLY difference: retrieval method (vector DB vs graph traversal)
"""

import json
import time
import logging
import os
import sys
from typing import Dict, Any, List
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from evaluation.questions_benchmark import BENCHMARK_QUESTIONS, get_categories

logger = logging.getLogger(__name__)

# ── Shared QA Prompt for fair comparison ───────────────────────────────

SAME_QA_PROMPT_TEMPLATE = (
    "You are an expert research assistant. Use the following pieces of retrieved context to answer the user's question.\n"
    "If you don't know the answer, just say that you don't know, don't try to make up an answer.\n"
    "Always cite the page numbers if provided in the context.\n\n"
    "Context:\n{context}\n\n"
    "Question: {question}\n\n"
    "Answer:"
)


def _create_qa_llm():
    """Create an LLM instance using the SAME settings as GraphRAG's answer model.

    Both systems will use this identical LLM so the comparison is fair.
    """
    # Lazy import to avoid module-level dependency
    from langchain_openai import ChatOpenAI

    provider = settings.ANSWER_PROVIDER
    model = settings.ANSWER_MODEL

    if provider.lower() == "huggingface":
        # Reasoning models (Qwen3.5-397B) need a parser that reads `content`
        # despite the `reasoning` field; ChatOpenAI cannot.
        from utils.hf_client import get_hf_model

        logger.info(f"Creating shared QA LLM (HF reasoning): {model}")
        return get_hf_model(model=model, api_key=settings.huggingface_api_key)

    api_key = settings.get_api_key_for_provider(provider)
    base_url = settings.get_base_url_for_provider(provider)

    kwargs = dict(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0.0,
        max_tokens=settings.max_tokens_answer,
    )
    # Groq blocks default python user-agents via Cloudflare (403 error 1010).
    if provider.lower() == "groq":
        kwargs["default_headers"] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        }
    logger.info(f"Creating shared QA LLM: {model} via {provider}")
    return ChatOpenAI(**kwargs)


def _invoke_with_retry(llm, prompt, max_retries=5):
    """Invoke the shared LLM with backoff retries on rate-limit errors.

    Both systems generate answers with the same model (Groq free tier is
    capped at 12K TPM / ~30 RPM), so long benchmark runs need to self-pace.

    Returns (answer, backoff_time_s): the backoff time is tracked so the
    evaluator can exclude rate-limit waiting from recorded latencies.
    """
    backoff_time = 0.0
    last_error = None
    for attempt in range(max_retries):
        try:
            result = llm.invoke(prompt)
            answer = result.content if hasattr(result, "content") else str(result)
            return answer, round(backoff_time, 3)
        except Exception as e:
            last_error = e
            msg = str(e).lower()
            # Daily caps / quota exhaustion won't clear with a short wait — fail fast.
            # NOTE: "billing" excluded on purpose — Groq appends the sales pitch
            # ".../settings/billing" to EVERY 429 (incl. per-minute TPM spikes
            # that clear in seconds), so matching it would falsely fail-fast on
            # recoverable limits. TPD matches via "per day"/"tpd"; HF 402 via
            # "credits"/"depleted".
            if any(k in msg for k in
                   ["per day", "tpd", "quota", "no credits",
                    "daily", "free tier", "credits", "depleted"]):
                raise RuntimeError(f"Quota exhausted: {str(e)}")
            if any(k in msg for k in
                   ["rate_limit", "429", "tpm", "too many requests", "throttl", "try again"]):
                wait = 15 * (attempt + 1)
                backoff_time += wait
                logger.warning(
                    f"[Eval] Rate limited (attempt {attempt + 1}/{max_retries}). "
                    f"Retrying in {wait}s: {str(e)[:120]}"
                )
                time.sleep(wait)
            elif any(k in msg for k in
                     ["timed out", "timeout", "connection", "getaddrinfo", "urlopen",
                      "winerror", "10054", "11001", "eof", "ssl", "unreachable",
                      "reset", "read operation", "network"]):
                # Transient transport failures (DNS resolution, connection reset,
                # read timeout) usually clear in seconds — retry with backoff
                # instead of failing the question.
                wait = 10 * (attempt + 1)
                backoff_time += wait
                logger.warning(
                    f"[Eval] Transport error (attempt {attempt + 1}/{max_retries}). "
                    f"Retrying in {wait}s: {str(e)[:120]}"
                )
                time.sleep(wait)
            else:
                raise
    # Preserve the last error so the poisoning guard can recognize a
    # transport failure (DNS/connection/timeout) instead of a generic
    # "rate limited" label that would mask the real cause.
    raise RuntimeError(f"LLM invoke failed after retries: {last_error}")


# ── Evaluation Recorder ────────────────────────────────────────────────


class EvaluationRecorder:
    """Records detailed per-question evaluation data for a single system."""

    def __init__(self, system_name: str):
        self.system_name = system_name
        self.records = []

    def record_question(
        self,
        question_id: int,
        category: str,
        question: str,
        ground_truth: str,
        answer: str,
        retrieved_chunks: List[str] = None,
        similarity_scores: List[float] = None,
        retrieved_entities: List[str] = None,
        retrieved_relationships: List[str] = None,
        graph_traversal_path: List[str] = None,
        retrieved_subgraph: Dict = None,
        retrieval_latency: float = 0.0,
        generation_latency: float = 0.0,
        total_latency: float = 0.0,
        error: str = None,
        extra: Dict = None,
    ):
        record = {
            "system": self.system_name,
            "question_id": question_id,
            "category": category,
            "question": question,
            "ground_truth": ground_truth,
            "answer": answer or "",
            "retrieved_chunks": retrieved_chunks or [],
            "similarity_scores": similarity_scores or [],
            "retrieved_entities": retrieved_entities or [],
            "retrieved_relationships": retrieved_relationships or [],
            "graph_traversal_path": graph_traversal_path or [],
            "retrieved_subgraph": retrieved_subgraph or {},
            "retrieval_latency_s": round(retrieval_latency, 3),
            "generation_latency_s": round(generation_latency, 3),
            "total_latency_s": round(total_latency, 3),
            "error": error,
            "extra": extra or {},
        }
        self.records.append(record)
        return record

    def save(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.records, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(self.records)} records to {filepath}")

    def get_answers(self) -> List[str]:
        return [r["answer"] for r in self.records]

    def get_ground_truths(self) -> List[str]:
        return [r["ground_truth"] for r in self.records]

    def get_contexts(self) -> List[List[str]]:
        c = []
        for r in self.records:
            ctx = r.get("retrieved_chunks", [])
            if not ctx:
                ctx = r.get("retrieved_entities", [])
            c.append(ctx)
        return c


# ── Vector RAG Evaluation ──────────────────────────────────────────────


def evaluate_vector_rag(questions: List[Dict], recorder: EvaluationRecorder,
                        checkpoint_path: str = None, checkpoint_every: int = 10):
    """Run Vector RAG evaluation on all questions.

    Uses the SAME LLM (ANSWER_MODEL) as GraphRAG for answer generation.
    When checkpoint_path is given, results are saved every `checkpoint_every`
    questions so a long run never loses all progress.
    """
    logger.info("=== Evaluating Vector RAG ===")

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from vector_rag.pipeline import VectorRAGPipeline
    from vector_rag.retriever import RetrievalOptions

    try:
        pipeline = VectorRAGPipeline()
        if pipeline.qa_chain is None:
            logger.warning("Vector RAG not initialized, ingesting document...")
            pipeline.ingest_document(settings.PDF_PATH)
    except Exception as e:
        logger.error(f"Vector RAG init failed: {e}")
        return

    # ── Override Vector RAG's LLM with the SAME one GraphRAG uses ──
    fair_llm = _create_qa_llm()

    for q_data in questions:
        qid = q_data["id"]
        question = q_data["question"]
        ground_truth = q_data["ground_truth"]
        category = q_data["category"]

        logger.info(f"  [Vector] Q{qid}/{len(questions)}: {question[:60]}...")

        # === RETRIEVAL PHASE (Vector RAG's native retriever) ===
        retrieval_start = time.time()
        source_docs = []
        retrieval_error = None
        try:
            retriever_opts = RetrievalOptions(k=5)
            source_docs = pipeline.retriever_manager.retrieve(question, retriever_opts)
        except AttributeError:
            try:
                retriever_opts = RetrievalOptions(k=5)
                retriever = pipeline.retriever_manager.get_retriever(retriever_opts)
                source_docs = retriever.invoke(question)
            except Exception as e2:
                retrieval_error = str(e2)
                logger.warning(f"  [Vector] Retrieve fallback error: {e2}")
        except Exception as e:
            retrieval_error = str(e)
            logger.warning(f"  [Vector] Retrieve error: {e}")
        retrieval_time = time.time() - retrieval_start

        retrieved_chunks = [d.page_content for d in source_docs]
        scores = []
        try:
            scores = [d.metadata.get("score", 0.0) for d in source_docs]
        except Exception:
            pass

        # === GENERATION PHASE (uses FAIR LLM = same as GraphRAG) ===
        gen_start = time.time()
        answer = ""
        gen_error = None
        backoff_time = 0.0
        try:
            # Lazy import
            from langchain_core.prompts import PromptTemplate

            # Use the SAME prompt template as a fair baseline
            context_text = pipeline._format_docs(source_docs) if hasattr(pipeline, '_format_docs') else \
                "\n\n".join(f"--- [Page {d.metadata.get('page', '?')}] ---\n{d.page_content}" for d in source_docs)
            prompt = PromptTemplate.from_template(SAME_QA_PROMPT_TEMPLATE)
            formatted = prompt.format(context=context_text, question=question)
            answer, backoff_time = _invoke_with_retry(fair_llm, formatted)
        except Exception as e:
            gen_error = str(e)
            logger.warning(f"  [Vector] Generation error: {e}")
        gen_time = time.time() - gen_start - backoff_time

        total_time = time.time() - retrieval_start - backoff_time

        recorder.record_question(
            question_id=qid,
            category=category,
            question=question,
            ground_truth=ground_truth,
            answer=answer,
            retrieved_chunks=retrieved_chunks,
            similarity_scores=scores,
            retrieval_latency=retrieval_time,
            generation_latency=gen_time,
            total_latency=total_time,
            error=retrieval_error or gen_error,
        )

        # Periodic checkpoint so a long run survives interruptions
        if checkpoint_path and (qid % checkpoint_every == 0):
            recorder.save(checkpoint_path)


# ── GraphRAG Evaluation ────────────────────────────────────────────────


def evaluate_graph_rag(questions: List[Dict], recorder: EvaluationRecorder,
                       checkpoint_path: str = None, checkpoint_every: int = 10):
    """Run GraphRAG evaluation on all questions.

    GraphRAG natively uses settings.ANSWER_MODEL and settings.ANSWER_PROVIDER
    via GraphRAGRetriever (which creates its own QA LLM from those same settings).
    No override needed — it already uses the same model as the fair LLM above.
    When checkpoint_path is given, results are saved every `checkpoint_every`
    questions so a long run never loses all progress.
    """
    logger.info("=== Evaluating GraphRAG ===")

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from graph_rag.retriever import GraphRAGRetriever

    try:
        retriever = GraphRAGRetriever()
    except Exception as e:
        logger.error(f"GraphRAG init failed: {e}")
        return

    for q_data in questions:
        qid = q_data["id"]
        question = q_data["question"]
        ground_truth = q_data["ground_truth"]
        category = q_data["category"]

        logger.info(f"  [GraphRAG] Q{qid}/{len(questions)}: {question[:60]}...")

        # === GRAPH RETRIEVAL & GENERATION ===
        retrieval_start = time.time()
        result = {}
        error = None
        try:
            result = retriever.query(question)
        except Exception as e:
            error = str(e)
            logger.warning(f"  [GraphRAG] Query error: {e}")
            result = {"answer": "", "context": []}

        retrieval_time = time.time() - retrieval_start - result.get("backoff_time_s", 0.0)

        answer = result.get("answer", "")
        context = result.get("context", [])
        # Record query-level errors (retriever returns answer="" + error key on failure)
        if not error and result.get("error"):
            error = result["error"]

        # Parse context into entities vs relationships
        retrieved_entities = []
        retrieved_relationships = []
        graph_traversal_path = []
        for ctx_item in context:
            ctx_str = str(ctx_item)
            # Heuristic: relationship-like strings contain arrow patterns
            if "->" in ctx_str or "--" in ctx_str or "RELATED" in ctx_str.upper() or "CONTAINS" in ctx_str.upper():
                retrieved_relationships.append(ctx_str)
                graph_traversal_path.append(ctx_str)
            else:
                retrieved_entities.append(ctx_str)

        # Build a simple subgraph representation
        retrieved_subgraph = {
            "entities": retrieved_entities,
            "relationships": retrieved_relationships,
            "paths": graph_traversal_path,
        }

        gen_time = retrieval_time  # GraphRAG generates inline with retrieval
        total_time = retrieval_time

        recorder.record_question(
            question_id=qid,
            category=category,
            question=question,
            ground_truth=ground_truth,
            answer=answer,
            retrieved_entities=retrieved_entities,
            retrieved_relationships=retrieved_relationships,
            graph_traversal_path=graph_traversal_path,
            retrieved_subgraph=retrieved_subgraph,
            retrieval_latency=retrieval_time,
            generation_latency=gen_time,
            total_latency=total_time,
            error=error if not answer else None,
        )

        # Periodic checkpoint so a long run survives interruptions
        if checkpoint_path and (qid % checkpoint_every == 0):
            recorder.save(checkpoint_path)


# ── Entry Point ─────────────────────────────────────────────────────────


def run_evaluation():
    """Run full evaluation on both systems."""
    questions = BENCHMARK_QUESTIONS
    logger.info(f"Loaded {len(questions)} questions across {len(get_categories())} categories")
    eval_dir = Path(__file__).parent

    vec_recorder = EvaluationRecorder("VectorRAG")
    evaluate_vector_rag(questions, vec_recorder, checkpoint_path=str(eval_dir / "vector_rag_results.json"))
    vec_recorder.save(str(eval_dir / "vector_rag_results.json"))

    g_recorder = EvaluationRecorder("GraphRAG")
    evaluate_graph_rag(questions, g_recorder, checkpoint_path=str(eval_dir / "graph_rag_results.json"))
    g_recorder.save(str(eval_dir / "graph_rag_results.json"))

    logger.info("Evaluation complete!")
    return vec_recorder, g_recorder


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    run_evaluation()
