"""
report.py - Comparison report generation with tables, CSV export, and plots.

Generates:
1. evaluation_results.json (combined)
2. evaluation_results.csv
3. Overall comparison table
4. Per-question evaluation logs
5. Graph statistics report
6. All 7 automatic plots (accuracy, latency, category accuracy, precision-recall,
   retrieval success rate, entity distribution, relationship distribution)
"""

import json
import csv
import logging
import os
from typing import Dict, List, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Try importing matplotlib, fall back gracefully
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    logger.warning("matplotlib not installed, plots will be skipped")


def load_results(vec_path: str = "vector_rag_results.json",
                  graph_path: str = "graph_rag_results.json") -> Dict:
    """Load evaluation results from JSON files."""
    results = {}
    base = Path(__file__).parent
    for system, path in [("VectorRAG", vec_path), ("GraphRAG", graph_path)]:
        fp = base / path
        if fp.exists():
            with open(fp, "r", encoding="utf-8") as f:
                results[system] = json.load(f)
            logger.info(f"Loaded {len(results[system])} records for {system}")
        else:
            logger.warning(f"Results not found: {fp}")
            results[system] = []
    return results


def save_combined_json(vec_records: List[Dict], graph_records: List[Dict],
                        vec_metrics: Dict, graph_metrics: Dict,
                        graph_stats: Dict, system_metrics: Dict):
    """Save combined evaluation_results.json."""
    import datetime
    combined = {
        "evaluation_date": datetime.datetime.now().isoformat(),
        "num_questions": max(len(vec_records), len(graph_records)),
        "vector_rag": {
            "results": vec_records,
            "metrics": vec_metrics,
        },
        "graph_rag": {
            "results": graph_records,
            "metrics": graph_metrics,
        },
        "graph_statistics": graph_stats,
        "system_metrics": system_metrics,
        "comparison_table": _build_comparison_table(vec_metrics, graph_metrics),
    }
    out_path = Path(__file__).parent / "evaluation_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved combined results to {out_path}")


def save_csv(vec_records: List[Dict], graph_records: List[Dict]):
    """Save evaluation_results.csv with per-question logs."""
    rows = []
    max_len = max(len(vec_records), len(graph_records))
    for i in range(max_len):
        v = vec_records[i] if i < len(vec_records) else {}
        g = graph_records[i] if i < len(graph_records) else {}
        row = {
            "question_id": v.get("question_id", g.get("question_id", i)),
            "category": v.get("category", g.get("category", "")),
            "question": v.get("question", g.get("question", "")),
            "ground_truth": v.get("ground_truth", g.get("ground_truth", "")),
            "vector_answer": v.get("answer", ""),
            "graph_answer": g.get("answer", ""),
            "vector_retrieval_latency": v.get("retrieval_latency_s", ""),
            "graph_retrieval_latency": g.get("retrieval_latency_s", ""),
            "vector_generation_latency": v.get("generation_latency_s", ""),
            "graph_generation_latency": g.get("generation_latency_s", ""),
            "vector_total_latency": v.get("total_latency_s", ""),
            "graph_total_latency": g.get("total_latency_s", ""),
            "vector_error": v.get("error", ""),
            "graph_error": g.get("error", ""),
            "vector_num_chunks": len(v.get("retrieved_chunks", [])),
            "graph_num_entities": len(g.get("retrieved_entities", [])),
            "graph_num_relationships": len(g.get("retrieved_relationships", [])),
        }
        rows.append(row)

    out_path = Path(__file__).parent / "evaluation_results.csv"
    if rows:
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    logger.info(f"Saved CSV to {out_path}")


def _build_comparison_table(vec_metrics: Dict, graph_metrics: Dict) -> List[Dict]:
    """Build overall comparison table with all 9 metrics + latency."""
    keys = [
        "answer_accuracy", "faithfulness", "context_precision", "context_recall",
        "exact_match", "f1_score", "hallucination_rate", "citation_correctness",
        "multi_hop_success",
    ]
    table = []
    for key in keys:
        v_val = vec_metrics.get("aggregate", {}).get(key, "N/A")
        g_val = graph_metrics.get("aggregate", {}).get(key, "N/A")
        try:
            diff = round(float(g_val) - float(v_val), 4) if v_val != "N/A" and g_val != "N/A" else "N/A"
        except (ValueError, TypeError):
            diff = "N/A"
        table.append({
            "metric": key,
            "vector_rag": v_val,
            "graph_rag": g_val,
            "difference": diff,
            "winner": "GraphRAG" if isinstance(diff, float) and diff > 0
                      else ("VectorRAG" if isinstance(diff, float) and diff < 0 else "Tie")
        })
    return table


def generate_plots(vec_metrics: Dict, graph_metrics: Dict, graph_stats: Dict,
                   vec_records: List[Dict], graph_records: List[Dict]):
    """Generate all 7 comparison plots."""
    if not HAS_MPL:
        logger.info("Skipping plots (matplotlib not available)")
        return

    out_dir = Path(__file__).parent / "plots"
    out_dir.mkdir(exist_ok=True)

    # 1. Accuracy comparison bar chart
    fig, ax = plt.subplots(figsize=(12, 6))
    keys = ["answer_accuracy", "faithfulness", "context_precision",
            "context_recall", "exact_match", "f1_score",
            "citation_correctness", "multi_hop_success"]
    v_vals = [vec_metrics.get("aggregate", {}).get(k, 0) for k in keys]
    g_vals = [graph_metrics.get("aggregate", {}).get(k, 0) for k in keys]
    x = range(len(keys))
    ax.bar([i - 0.2 for i in x], v_vals, 0.4, label="VectorRAG", alpha=0.8, color="#4C72B0")
    ax.bar([i + 0.2 for i in x], g_vals, 0.4, label="GraphRAG", alpha=0.8, color="#DD8452")
    ax.set_xticks(x)
    ax.set_xticklabels(keys, rotation=45, ha="right")
    ax.set_ylabel("Score")
    ax.set_title("RAG System Comparison - QA Metrics")
    ax.legend()
    ax.set_ylim(0, 1)
    fig.tight_layout()
    fig.savefig(out_dir / "accuracy_comparison.png", dpi=150)
    plt.close(fig)
    logger.info("Saved accuracy_comparison.png")

    # 2. Latency comparison (computed from per-question records)
    def _avg_latency(records, key):
        vals = [r.get(key, 0) for r in records]
        return sum(vals) / len(vals) if vals else 0

    fig, ax = plt.subplots(figsize=(8, 5))
    v_ret = _avg_latency(vec_records, "retrieval_latency_s")
    g_ret = _avg_latency(graph_records, "retrieval_latency_s")
    v_gen = _avg_latency(vec_records, "generation_latency_s")
    g_gen = _avg_latency(graph_records, "generation_latency_s")
    v_total = _avg_latency(vec_records, "total_latency_s")
    g_total = _avg_latency(graph_records, "total_latency_s")
    labels = ["Retrieval Time", "Generation Time", "Total Response Time"]
    v_vals = [v_ret, v_gen, v_total]
    g_vals = [g_ret, g_gen, g_total]
    x = range(len(labels))
    ax.bar([i - 0.2 for i in x], v_vals, 0.4, label="VectorRAG", alpha=0.8, color="#4C72B0")
    ax.bar([i + 0.2 for i in x], g_vals, 0.4, label="GraphRAG", alpha=0.8, color="#DD8452")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Seconds")
    ax.set_title("Latency Comparison (avg per question)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "latency_comparison.png", dpi=150)
    plt.close(fig)
    logger.info("Saved latency_comparison.png")

    # 3. Per-category accuracy comparison
    fig, ax = plt.subplots(figsize=(14, 6))
    v_cats = vec_metrics.get("per_category", {})
    g_cats = graph_metrics.get("per_category", {})
    all_cats = sorted(set(list(v_cats.keys()) + list(g_cats.keys())))
    v_acc = [v_cats.get(c, {}).get("answer_accuracy", 0) for c in all_cats]
    g_acc = [g_cats.get(c, {}).get("answer_accuracy", 0) for c in all_cats]
    x = range(len(all_cats))
    ax.bar([i - 0.2 for i in x], v_acc, 0.4, label="VectorRAG", alpha=0.8, color="#4C72B0")
    ax.bar([i + 0.2 for i in x], g_acc, 0.4, label="GraphRAG", alpha=0.8, color="#DD8452")
    ax.set_xticks(x)
    ax.set_xticklabels(all_cats, rotation=45, ha="right")
    ax.set_ylabel("Accuracy")
    ax.set_title("Per-Category Accuracy Comparison")
    ax.legend()
    ax.set_ylim(0, 1)
    fig.tight_layout()
    fig.savefig(out_dir / "category_accuracy.png", dpi=150)
    plt.close(fig)
    logger.info("Saved category_accuracy.png")

    # 4. Precision vs Recall scatter
    fig, ax = plt.subplots(figsize=(8, 6))
    v_p = vec_metrics.get("aggregate", {}).get("context_precision", 0)
    v_r = vec_metrics.get("aggregate", {}).get("context_recall", 0)
    g_p = graph_metrics.get("aggregate", {}).get("context_precision", 0)
    g_r = graph_metrics.get("aggregate", {}).get("context_recall", 0)
    ax.scatter([v_r], [v_p], s=200, label=f"VectorRAG (P={v_p:.3f}, R={v_r:.3f})",
               color="#4C72B0", alpha=0.8, zorder=5)
    ax.scatter([g_r], [g_p], s=200, label=f"GraphRAG (P={g_p:.3f}, R={g_r:.3f})",
               color="#DD8452", alpha=0.8, zorder=5)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title("Precision vs Recall")
    ax.legend()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "precision_recall.png", dpi=150)
    plt.close(fig)
    logger.info("Saved precision_recall.png")

    # 5. Retrieval Success Rate
    fig, ax = plt.subplots(figsize=(8, 5))
    v_success = sum(1 for r in vec_records if not r.get("error")) if vec_records else 0
    g_success = sum(1 for r in graph_records if not r.get("error")) if graph_records else 0
    v_total_q = len(vec_records) if vec_records else 1
    g_total_q = len(graph_records) if graph_records else 1
    v_rate = v_success / v_total_q
    g_rate = g_success / g_total_q
    bars = ax.bar(["VectorRAG", "GraphRAG"], [v_rate, g_rate],
                  color=["#4C72B0", "#DD8452"], alpha=0.8, width=0.5)
    ax.set_ylabel("Success Rate")
    ax.set_title("Retrieval Success Rate")
    ax.set_ylim(0, 1)
    for bar, rate in zip(bars, [v_rate, g_rate]):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f"{rate:.1%}", ha="center", va="bottom", fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_dir / "retrieval_success_rate.png", dpi=150)
    plt.close(fig)
    logger.info("Saved retrieval_success_rate.png")

    # 6. Entity type distribution (from graph stats)
    if graph_stats and "entity_type_distribution" in graph_stats:
        fig, ax = plt.subplots(figsize=(12, 6))
        etypes = graph_stats["entity_type_distribution"]
        labels = list(etypes.keys())[:15]
        values = list(etypes.values())[:15]
        bars = ax.barh(range(len(labels)), values, color="#4C72B0", alpha=0.8)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels)
        ax.set_xlabel("Count")
        ax.set_title("Top Entity Types in Knowledge Graph")
        for bar, val in zip(bars, values):
            ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                    str(val), va="center")
        fig.tight_layout()
        fig.savefig(out_dir / "entity_distribution.png", dpi=150)
        plt.close(fig)
        logger.info("Saved entity_distribution.png")

    # 7. Relationship type distribution (from graph stats)
    if graph_stats and "relationship_type_distribution" in graph_stats:
        fig, ax = plt.subplots(figsize=(12, 6))
        rtypes = graph_stats["relationship_type_distribution"]
        labels = list(rtypes.keys())[:15]
        values = list(rtypes.values())[:15]
        bars = ax.barh(range(len(labels)), values, color="#DD8452", alpha=0.8)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels)
        ax.set_xlabel("Count")
        ax.set_title("Top Relationship Types in Knowledge Graph")
        for bar, val in zip(bars, values):
            ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                    str(val), va="center")
        fig.tight_layout()
        fig.savefig(out_dir / "relationship_distribution.png", dpi=150)
        plt.close(fig)
        logger.info("Saved relationship_distribution.png")

    logger.info(f"All 7 plots saved to {out_dir}")


def generate_report(
    vec_records: List[Dict],
    graph_records: List[Dict],
    vec_metrics: Dict,
    graph_metrics: Dict,
    graph_stats: Dict,
    system_metrics: Dict,
):
    """Generate the full evaluation report: JSON, CSV, plots, and console output."""
    out_dir = Path(__file__).parent
    out_dir.mkdir(exist_ok=True)

    logger.info("Generating evaluation report...")

    # 1. Save combined JSON
    save_combined_json(vec_records, graph_records, vec_metrics, graph_metrics,
                        graph_stats, system_metrics)

    # 2. Save CSV
    save_csv(vec_records, graph_records)

    # 3. Generate plots
    generate_plots(vec_metrics, graph_metrics, graph_stats, vec_records, graph_records)

    # 4. Console summary
    print("\n" + "=" * 70)
    print("  OVERALL COMPARISON TABLE")
    print("=" * 70)
    print(f"{'Metric':<30} {'VectorRAG':<12} {'GraphRAG':<12} {'Diff':<10} {'Winner':<10}")
    print("-" * 70)
    table = _build_comparison_table(vec_metrics, graph_metrics)
    for row in table:
        print(f"{row['metric']:<30} {str(row['vector_rag']):<12} {str(row['graph_rag']):<12} "
              f"{str(row['difference']):<10} {row['winner']:<10}")
    print("-" * 70)

    # Add system metrics to table
    for sys_name in ["vector_rag", "graph_rag"]:
        sm = system_metrics.get(sys_name, {})
        label = "VectorRAG" if sys_name == "vector_rag" else "GraphRAG"
        other = "GraphRAG" if sys_name == "vector_rag" else "VectorRAG"
        print(f"\n  {label} System Metrics:")
        for k, v in sm.items():
            print(f"    {k}: {v}")

    print(f"\n  Report files saved to: {out_dir}")
    print(f"    - evaluation_results.json")
    print(f"    - evaluation_results.csv")
    print(f"    - plots/ (7 charts)")
    print()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    print("Run `python -m evaluation.run_evaluation` to generate the full report.")
