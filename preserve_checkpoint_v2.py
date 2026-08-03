"""
preserve_checkpoint_v2.py — Preserve the official v2 baseline as a checkpoint.

FREEZE: copies the exact code + artifacts that define "GraphRAG v2 (Graph +
Source Evidence + Construction Fix)" into experiments/checkpoints/v2_construction_baseline/
so every later improvement can be rolled back or compared against a byte-exact
baseline. Mirrors the v1_source_evidence checkpoint convention (MANIFEST.json
of sha256 hashes). ZERO LLM calls, read-only on the source tree.
"""

import hashlib
import json
import shutil
from pathlib import Path

def _find_root():
    """Locate the GraphRAG project root (the dir containing config/settings.py)."""
    cur = Path(__file__).resolve().parent
    while cur != cur.parent:
        if (cur / "config" / "settings.py").exists():
            return cur
        cur = cur.parent
    raise RuntimeError("Could not locate GraphRAG project root")


ROOT = _find_root()
DEST = ROOT / "experiments" / "checkpoints" / "v2_construction_baseline"

# (source path, destination path) — the exact files that define the baseline
FILES = [
    # ── evaluation harness (unchanged, must stay byte-identical) ──
    ("evaluation/evaluator_v2.py", "evaluator_v2.py"),
    ("evaluation/metrics_v2.py", "metrics_v2.py"),
    ("evaluation/run_construction_eval.py", "run_construction_eval.py"),
    ("evaluation/run_fair_eval.py", "run_fair_eval.py"),
    ("evaluation/run_v2_eval.py", "run_v2_eval.py"),
    ("evaluation/benchmark_v2_graph_construction_results.json", "benchmark_v2_graph_construction_results.json"),
    ("evaluation/benchmark_v2_graph_construction_summary.json", "benchmark_v2_graph_construction_summary.json"),
    ("evaluation/benchmark_v2_graph_results.json", "benchmark_v2_graph_results.json"),
    ("evaluation/benchmark_v2_summary.json", "benchmark_v2_summary.json"),
    ("evaluation/benchmark_v2_vector_results.json", "benchmark_v2_vector_results.json"),
    ("evaluation/construction_ablation_eval.log", "construction_ablation_eval.log"),
    # ── retrieval + construction pipeline (unchanged) ──
    ("graph_rag/retriever.py", "graph_rag/retriever.py"),
    ("graph_rag/chunker.py", "graph_rag/chunker.py"),
    ("graph_rag/knowledge_extractor.py", "graph_rag/knowledge_extractor.py"),
    ("graph_rag/graph_refiner.py", "graph_rag/graph_refiner.py"),
    ("graph_rag/graph_store.py", "graph_rag/graph_store.py"),
    ("utils/neo4j_loader.py", "utils/neo4j_loader.py"),
    ("config/settings.py", "config/settings.py"),
    ("rebuild_graph_v2.py", "rebuild_graph_v2.py"),
    ("gen_construction_report.py", "gen_construction_report.py"),
    # ── graph artifact + stats (the v2 graph itself) ──
    ("data/refined_graph_v2_construction.json", "data/refined_graph_v2_construction.json"),
    ("experiments/construction_stats_before.json", "construction_stats_before.json"),
    ("experiments/construction_stats_after.json", "construction_stats_after.json"),
    ("experiments/benchmark_v2.json", "benchmark_v2.json"),
    ("experiments/construction_ablation.md", "construction_ablation.md"),
]

def sha16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]

def main():
    DEST.mkdir(parents=True, exist_ok=True)
    manifest = {}
    missing = []
    for src_rel, dst_rel in FILES:
        src = ROOT / src_rel
        if not src.exists():
            missing.append(src_rel)
            continue
        dst = DEST / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        manifest[dst_rel] = sha16(dst)
    if missing:
        print(f"WARNING: missing source files (not copied): {missing}")
    (DEST / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Checkpoint written: {DEST}")
    print(f"  {len(manifest)} files, sha256-hashed in MANIFEST.json")
    for k in sorted(manifest):
        print(f"    {k}")

if __name__ == "__main__":
    main()
