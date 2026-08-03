"""make_retrieval_checkpoint.py — preserve the v2 retrieval baseline.

Freezes the EXACT pre-P2-change state (retriever, chunker, evaluator,
metrics, runner, benchmark, v2 results, graph artifact, diagnostic) into
experiments/checkpoints/v2_retrieval_baseline/ with a sha256 manifest so
the P2 chunk-level-evidence ablation can be rolled back byte-for-byte.

Pure offline file copy — no LLM calls, no Neo4j writes.
"""

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments" / "checkpoints" / "v2_retrieval_baseline"

# (source relative path, dest relative path)
FILES = [
    ("graph_rag/retriever.py", "graph_rag/retriever.py"),
    ("graph_rag/chunker.py", "graph_rag/chunker.py"),
    ("evaluation/evaluator_v2.py", "evaluation/evaluator_v2.py"),
    ("evaluation/metrics_v2.py", "evaluation/metrics_v2.py"),
    ("evaluation/run_quality_eval.py", "evaluation/run_quality_eval.py"),
    ("evaluation/run_fair_eval.py", "evaluation/run_fair_eval.py"),
    ("evaluation/run_v2_eval.py", "evaluation/run_v2_eval.py"),
    ("evaluation/benchmark_v2_graph_construction_results.json",
     "evaluation/benchmark_v2_graph_construction_results.json"),
    ("evaluation/benchmark_v2_graph_construction_summary.json",
     "evaluation/benchmark_v2_graph_construction_summary.json"),
    ("evaluation/benchmark_v2_graph_results.json", "evaluation/benchmark_v2_graph_results.json"),
    ("evaluation/benchmark_v2_vector_results.json", "evaluation/benchmark_v2_vector_results.json"),
    ("experiments/benchmark_v2.json", "experiments/benchmark_v2.json"),
    ("experiments/retrieval_diagnostic.json", "experiments/retrieval_diagnostic.json"),
    ("experiments/retrieval_diagnostic.md", "experiments/retrieval_diagnostic.md"),
    ("config/settings.py", "config/settings.py"),
    ("data/refined_graph_v2_construction.json", "data/refined_graph_v2_construction.json"),
]

def sha16(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()[:16]

def main():
    manifest = {}
    for src_rel, dst_rel in FILES:
        src = ROOT / src_rel
        if not src.exists():
            print(f"MISSING (skipped): {src_rel}")
            continue
        dst = OUT / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        manifest[dst_rel] = sha16(src)
        print(f"copied {src_rel}")
    with open(OUT / "MANIFEST.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    print(f"\nManifest written with {len(manifest)} files -> {OUT}")

if __name__ == "__main__":
    main()
