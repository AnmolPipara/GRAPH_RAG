"""make_retrieval_v3_checkpoint.py — preserve the v3 (chunk-level evidence) baseline.

v3 was retained as the official GraphRAG baseline after the P2 retrieval
ablation (MIXED-POSITIVE: context recall +0.16, faithfulness +0.09,
hallucination -0.09, citation +0.04). Freeze the exact v3 state so future
experiments can roll back to it.

Pure offline file copy — no LLM calls, no Neo4j writes.
"""

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments" / "checkpoints" / "v3_retrieval_chunk_evidence"

FILES = [
    ("graph_rag/retriever.py", "graph_rag/retriever.py"),
    ("graph_rag/chunker.py", "graph_rag/chunker.py"),
    ("evaluation/evaluator_v2.py", "evaluation/evaluator_v2.py"),
    ("evaluation/metrics_v2.py", "evaluation/metrics_v2.py"),
    ("evaluation/run_retrieval_eval.py", "evaluation/run_retrieval_eval.py"),
    ("evaluation/benchmark_v2_graph_retrieval_results.json",
     "evaluation/benchmark_v2_graph_retrieval_results.json"),
    ("evaluation/benchmark_v2_graph_retrieval_summary.json",
     "evaluation/benchmark_v2_graph_retrieval_summary.json"),
    ("experiments/benchmark_v2.json", "experiments/benchmark_v2.json"),
    ("experiments/retrieval_ablation_diagnostic.json",
     "experiments/retrieval_ablation_diagnostic.json"),
    ("experiments/retrieval_ablation_diagnostic.md",
     "experiments/retrieval_ablation_diagnostic.md"),
    ("experiments/retrieval_ablation.md", "experiments/retrieval_ablation.md"),
    ("gen_retrieval_report.py", "gen_retrieval_report.py"),
    ("config/settings.py", "config/settings.py"),
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
