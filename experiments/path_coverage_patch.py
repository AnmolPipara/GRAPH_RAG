"""Phase 4 gap-closure — path length + graph coverage (NO LLM calls).

Adds the two diagnostics the user's Phase-4 list required but the first pass
skipped: (1) PATH LENGTH — per-question 1-hop and 2-hop reachable-node counts
from the matched entities (pure Neo4j variable-length traversal); (2) GRAPH
COVERAGE — distinct graph nodes touched by retrieval as a fraction of the
1,046-node graph. Appends the results to experiments/retrieval_analysis.md.
"""
import logging
import sys
from pathlib import Path

logging.disable(logging.CRITICAL)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.questions_benchmark import BENCHMARK_QUESTIONS
from graph_rag.retriever import GraphRAGRetriever


def main():
    retriever = GraphRAGRetriever()
    total_nodes = retriever.graph.query("MATCH (n) RETURN count(n) AS c")[0]["c"]
    rows = []
    touched = set()

    for q in BENCHMARK_QUESTIONS:
        keywords = retriever._extract_entity_keywords(q["question"])
        if not keywords:
            rows.append({"id": q["id"], "hop1": 0, "hop2": 0})
            continue
        conds = []
        for kw in keywords[:2]:
            kwl = kw.lower().replace("'", "\\'")
            conds.append(
                f"(toLower(n.name) CONTAINS '{kwl}' "
                f"OR toLower(n.canonical_name) CONTAINS '{kwl}' "
                f"OR any(a IN coalesce(n.aliases, []) WHERE toLower(a) CONTAINS '{kwl}') "
                f"OR toLower(n.description) CONTAINS '{kwl}')"
            )
        where = " OR ".join(conds)
        try:
            # Matched entity names (bounded) for coverage + path-length roots.
            names = [r["name"] for r in retriever.graph.query(
                f"MATCH (n) WHERE {where} RETURN n.name AS name LIMIT 10")]
            touched.update(str(x) for x in names)
            if not names:
                rows.append({"id": q["id"], "hop1": 0, "hop2": 0})
                continue
            roots = "[" + ", ".join(f'"{n.replace(chr(34), chr(92) + chr(34))}"' for n in names) + "]"
            hop1 = retriever.graph.query(
                f"MATCH (m) WHERE m.name IN {roots} MATCH (m)-[*1]-(x) RETURN count(DISTINCT x) AS c"
            )[0]["c"]
            hop2 = retriever.graph.query(
                f"MATCH (m) WHERE m.name IN {roots} MATCH (m)-[*1..2]-(x) RETURN count(DISTINCT x) AS c"
            )[0]["c"]
            rows.append({"id": q["id"], "hop1": hop1, "hop2": hop2})
        except Exception as e:
            rows.append({"id": q["id"], "hop1": -1, "hop2": -1, "error": str(e)[:80]})

    # Exclude any error rows (hop1 < 0) so failed queries cannot pollute aggregates.
    good = [r for r in rows if r["hop1"] >= 0]
    n_good = len(good)
    avg1 = round(sum(r["hop1"] for r in good) / n_good, 2) if n_good else 0.0
    avg2 = round(sum(r["hop2"] for r in good) / n_good, 2) if n_good else 0.0
    # Path length proxy: questions where 2-hop reachability > 1-hop (multi-hop available)
    multihop = round(sum(1 for r in good if r["hop2"] > r["hop1"]) / n_good, 3) if n_good else 0.0
    coverage_pct = round(100 * len(touched) / max(total_nodes, 1), 1)

    block = (
        "\n## Path length & graph coverage (gap-closure, offline, no LLM)\n\n"
        f"- Total graph nodes: **{total_nodes}**\n"
        f"- **Avg 1-hop reachable nodes** per question (from matched entities): **{avg1}**\n"
        f"- **Avg 2-hop reachable nodes** per question: **{avg2}**\n"
        f"- **Multi-hop availability** (questions where 2-hop > 1-hop reachability): **{multihop}**\n"
        f"- **Graph coverage** (distinct nodes touched by retrieval across 60 questions): "
        f"**{len(touched)} / {total_nodes} ({coverage_pct}%)**\n\n"
        "> Path length is measured as reachable-node counts at 1 and 2 hops from the matched\n"
        "> entities (variable-length Cypher traversal, bounded to the first 10 matched entities\n"
        "> per question). Coverage is distinct touched nodes as a fraction of the whole graph.\n"
        "> Caveat: nodes are addressed by `name` IN-list, so duplicate node names (present in\n"
        "> this graph) are all matched — reachability counts are an upper-bound proxy.\n"
    )

    path = ROOT / "experiments" / "retrieval_analysis.md"
    text = path.read_text(encoding="utf-8")
    marker = "## Path length & graph coverage"
    if marker in text:
        # Replace the existing section (idempotent re-runs update the numbers).
        idx = text.index(marker)
        text = text[:idx].rstrip() + "\n" + block
    else:
        text = text.rstrip() + "\n" + block
    path.write_text(text, encoding="utf-8")
    print("APPENDED path-length & coverage section to retrieval_analysis.md")
    print(f"avg1={avg1} avg2={avg2} multihop={multihop} coverage={len(touched)}/{total_nodes} ({coverage_pct}%)")


if __name__ == "__main__":
    main()
