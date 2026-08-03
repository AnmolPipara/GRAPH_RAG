"""
run_evaluation.py - Main Evaluation Runner.

Orchestrates the complete Vector RAG vs GraphRAG evaluation:
1. Optionally ingest the PDF into Vector RAG (records indexing time)
2. Run both systems on all 60 benchmark questions
3. Compute all metrics (QA + Graph quality)
4. Generate comparison report, tables, CSV, plots
5. Produce final analysis

Usage:
    python -m evaluation.run_evaluation
    python -m evaluation.run_evaluation --skip-eval   (report only from cached results)
    python -m evaluation.run_evaluation --quick        (run on first 10 questions only)
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.questions_benchmark import BENCHMARK_QUESTIONS, get_categories
from evaluation.metrics_v2 import compute_all_metrics
from evaluation.graph_metrics import compute_graph_statistics, print_graph_stats
from evaluation.report import generate_report, load_results
from config.settings import settings

logger = logging.getLogger(__name__)


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(Path(__file__).parent / "evaluation.log", mode="w"),
        ],
    )
    # Suppress verbose logs from libraries
    logging.getLogger("langchain").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("neo4j").setLevel(logging.WARNING)


def measure_indexing_time():
    """Measure Vector RAG indexing time and storage size."""
    from vector_rag.pipeline import VectorRAGPipeline

    logger.info("Measuring Vector RAG indexing time...")
    start = time.time()

    pipeline = VectorRAGPipeline()
    if pipeline.qa_chain is None:
        pipeline.ingest_document(settings.PDF_PATH)
        index_time = time.time() - start
    else:
        # Already indexed - estimate time as 0 (was done previously)
        index_time = 0.0
        logger.info("Vector RAG already initialized (using existing index).")

    # Measure storage size
    db_dir = Path(settings.vector_db_dir)
    storage_size = 0
    if db_dir.exists():
        for f in db_dir.rglob("*"):
            if f.is_file():
                storage_size += f.stat().st_size

    logger.info(f"Vector RAG indexing time: {index_time:.2f}s, storage: {storage_size / 1024:.1f} KB")
    return index_time, storage_size


def ingest_vector_rag():
    """Ingest the PDF into Vector RAG if not already indexed."""
    from vector_rag.pipeline import VectorRAGPipeline

    pipeline = VectorRAGPipeline()
    if pipeline.qa_chain is None:
        logger.info("Vector RAG not initialized. Ingesting document...")
        pipeline.ingest_document(settings.PDF_PATH)
        logger.info("Vector RAG ingestion complete.")
    else:
        logger.info("Vector RAG already initialized (FAISS index found).")


def run_full_evaluation(questions, quick=False):
    """Run the full evaluation on both systems."""
    if quick and len(questions) > 10:
        questions = questions[:10]
        logger.info(f"Quick mode: evaluating on {len(questions)} questions")

    logger.info(f"Starting evaluation on {len(questions)} questions across {len(get_categories())} categories")

    # Run Vector RAG evaluation
    from evaluation.evaluator_v2 import evaluate_vector_rag, EvaluationRecorder
    vec_recorder = EvaluationRecorder("VectorRAG")
    logger.info("=" * 60)
    logger.info("PHASE 1: Vector RAG Evaluation")
    logger.info("=" * 60)
    evaluate_vector_rag(questions, vec_recorder,
                        checkpoint_path=str(Path(__file__).parent / "vector_rag_results.json"))
    vec_recorder.save(str(Path(__file__).parent / "vector_rag_results.json"))
    logger.info(f"Vector RAG: {len(vec_recorder.records)}/{len(questions)} questions answered")

    # Run GraphRAG evaluation
    g_recorder = EvaluationRecorder("GraphRAG")
    logger.info("=" * 60)
    logger.info("PHASE 2: GraphRAG Evaluation")
    logger.info("=" * 60)
    from evaluation.evaluator_v2 import evaluate_graph_rag
    evaluate_graph_rag(questions, g_recorder,
                       checkpoint_path=str(Path(__file__).parent / "graph_rag_results.json"))
    g_recorder.save(str(Path(__file__).parent / "graph_rag_results.json"))
    logger.info(f"GraphRAG: {len(g_recorder.records)}/{len(questions)} questions answered")

    return vec_recorder, g_recorder


def compute_system_metrics(vec_records, graph_records, index_time=0.0, storage_size=0):
    """Compute system-level metrics including indexing time and storage size."""
    vec_latencies = [r.get("total_latency_s", 0) for r in vec_records]
    graph_latencies = [r.get("total_latency_s", 0) for r in graph_records]

    return {
        "vector_rag": {
            "indexing_time_s": round(index_time, 2),
            "storage_size_kb": round(storage_size / 1024, 1),
            "avg_retrieval_time": round(
                sum(r.get("retrieval_latency_s", 0) for r in vec_records) / len(vec_records), 4
            ) if vec_records else 0,
            "avg_generation_time": round(
                sum(r.get("generation_latency_s", 0) for r in vec_records) / len(vec_records), 4
            ) if vec_records else 0,
            "avg_total_time": round(sum(vec_latencies) / len(vec_latencies), 4) if vec_latencies else 0,
            "error_rate": round(
                sum(1 for r in vec_records if r.get("error")) / len(vec_records), 4
            ) if vec_records else 0,
            "total_questions": len(vec_records),
        },
        "graph_rag": {
            "indexing_time_s": "N/A (Neo4j pre-loaded)",
            "storage_size_kb": "N/A (Neo4j cloud)",
            "avg_retrieval_time": round(
                sum(r.get("retrieval_latency_s", 0) for r in graph_records) / len(graph_records), 4
            ) if graph_records else 0,
            "avg_generation_time": round(
                sum(r.get("generation_latency_s", 0) for r in graph_records) / len(graph_records), 4
            ) if graph_records else 0,
            "avg_total_time": round(sum(graph_latencies) / len(graph_latencies), 4) if graph_latencies else 0,
            "error_rate": round(
                sum(1 for r in graph_records if r.get("error")) / len(graph_records), 4
            ) if graph_records else 0,
            "total_questions": len(graph_records),
        },
    }


def print_comparison_analysis(vec_metrics, graph_metrics, system_metrics):
    """Print the final analysis summary."""
    print("\n" + "=" * 70)
    print("  ANALYSIS SUMMARY")
    print("=" * 70)

    v_agg = vec_metrics.get("aggregate", {})
    g_agg = graph_metrics.get("aggregate", {})

    # Where VectorRAG performs better
    print("\n  📍 Where Vector RAG Performs Better:")
    for metric in ["answer_accuracy", "context_precision", "context_recall",
                   "exact_match", "f1_score", "faithfulness"]:
        v = v_agg.get(metric, 0)
        g = g_agg.get(metric, 0)
        if v > g:
            print(f"    ✅ {metric}: VectorRAG={v:.3f} vs GraphRAG={g:.3f} (Δ={v-g:+.3f})")

    # Where GraphRAG performs better
    print("\n  📍 Where GraphRAG Performs Better:")
    for metric in ["answer_accuracy", "context_precision", "context_recall",
                   "exact_match", "f1_score", "faithfulness"]:
        v = v_agg.get(metric, 0)
        g = g_agg.get(metric, 0)
        if g > v:
            print(f"    ✅ {metric}: GraphRAG={g:.3f} vs VectorRAG={v:.3f} (Δ={g-v:+.3f})")

    # Latency comparison
    print("\n  ⏱️  Latency Comparison:")
    v_sys = system_metrics.get("vector_rag", {})
    g_sys = system_metrics.get("graph_rag", {})
    v_total = v_sys.get("avg_total_time", 0)
    g_total = g_sys.get("avg_total_time", 0)
    print(f"    VectorRAG avg: {v_total:.3f}s")
    print(f"    GraphRAG avg:  {g_total:.3f}s")
    if v_total < g_total:
        print(f"    VectorRAG is {g_total - v_total:.3f}s faster on average")
    else:
        print(f"    GraphRAG is {v_total - g_total:.3f}s faster on average")

    # Hallucination rate
    print("\n  🤔 Hallucination Rate:")
    print(f"    VectorRAG: {v_agg.get('hallucination_rate', 0):.3f}")
    print(f"    GraphRAG:  {g_agg.get('hallucination_rate', 0):.3f}")

    # Multi-hop success
    print("\n  🔗 Multi-hop Success Rate:")
    print(f"    VectorRAG: {v_agg.get('multi_hop_success', 0):.3f}")
    print(f"    GraphRAG:  {g_agg.get('multi_hop_success', 0):.3f}")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Vector RAG vs GraphRAG Evaluation Framework")
    parser.add_argument("--skip-eval", action="store_true",
                        help="Skip evaluation, only generate report from cached results")
    parser.add_argument("--quick", action="store_true",
                        help="Run on first 10 questions only")
    parser.add_argument("--ingest-only", action="store_true",
                        help="Only ingest PDF into Vector RAG, skip evaluation")
    args = parser.parse_args()

    setup_logging()
    logger.info("=" * 60)
    logger.info("Vector RAG vs GraphRAG Evaluation Framework")
    logger.info("=" * 60)

    if args.ingest_only:
        ingest_vector_rag()
        logger.info("Ingestion complete. Exiting.")
        return

    vec_records = []
    graph_records = []
    index_time = 0.0
    storage_size = 0

    if args.skip_eval:
        # Load cached results
        logger.info("Loading cached evaluation results...")
        results = load_results(
            str(Path(__file__).parent / "vector_rag_results.json"),
            str(Path(__file__).parent / "graph_rag_results.json"),
        )
        vec_records = results.get("VectorRAG", [])
        graph_records = results.get("GraphRAG", [])
        questions = BENCHMARK_QUESTIONS

        # Still measure storage if available
        db_dir = Path(settings.vector_db_dir)
        if db_dir.exists():
            for f in db_dir.rglob("*"):
                if f.is_file():
                    storage_size += f.stat().st_size
    else:
        # Measure Vector RAG indexing time
        logger.info("=" * 60)
        logger.info("PHASE 0: Indexing & System Metrics")
        logger.info("=" * 60)
        index_time, storage_size = measure_indexing_time()

        # Run evaluation
        questions = BENCHMARK_QUESTIONS
        vec_recorder, g_recorder = run_full_evaluation(questions, quick=args.quick)
        vec_records = vec_recorder.records
        graph_records = g_recorder.records

    if not vec_records and not graph_records:
        logger.error("No evaluation records found. Cannot generate report.")
        return

    logger.info("=" * 60)
    logger.info("PHASE 3: Computing Metrics")
    logger.info("=" * 60)

    # Compute QA metrics
    vec_answers = [r.get("answer", "") for r in vec_records]
    vec_ground_truths = [r.get("ground_truth", "") for r in vec_records]
    vec_contexts = [r.get("retrieved_chunks", []) or r.get("retrieved_entities", []) for r in vec_records]
    vec_categories = [r.get("category", "unknown") for r in vec_records]

    graph_answers = [r.get("answer", "") for r in graph_records]
    graph_ground_truths = [r.get("ground_truth", "") for r in graph_records]
    graph_contexts = [r.get("retrieved_chunks", []) or r.get("retrieved_entities", []) for r in graph_records]
    graph_categories = [r.get("category", "unknown") for r in graph_records]

    logger.info("Computing VectorRAG metrics...")
    vec_metrics = compute_all_metrics(vec_answers, vec_ground_truths, vec_contexts, vec_categories)
    logger.info("Computing GraphRAG metrics...")
    graph_metrics = compute_all_metrics(graph_answers, graph_ground_truths, graph_contexts, graph_categories)

    logger.info(f"VectorRAG: {json.dumps(vec_metrics['aggregate'], indent=2)}")
    logger.info(f"GraphRAG: {json.dumps(graph_metrics['aggregate'], indent=2)}")

    # Compute graph quality metrics
    logger.info("=" * 60)
    logger.info("PHASE 4: Graph Quality Analysis")
    logger.info("=" * 60)
    graph_stats = compute_graph_statistics()
    print_graph_stats(graph_stats)

    # Compute system metrics
    system_metrics = compute_system_metrics(vec_records, graph_records, index_time, storage_size)

    # Generate report
    logger.info("=" * 60)
    logger.info("PHASE 5: Report Generation")
    logger.info("=" * 60)
    generate_report(vec_records, graph_records, vec_metrics, graph_metrics,
                    graph_stats, system_metrics)

    # Print analysis
    print_comparison_analysis(vec_metrics, graph_metrics, system_metrics)

    logger.info("=" * 60)
    logger.info("Evaluation complete!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
