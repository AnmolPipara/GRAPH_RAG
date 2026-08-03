"""candidate_gen_diagnostic.py — Offline gate for the candidate-generation ablation.

Replicates the NEW candidate-generation stage (ranked keywords + deterministic
entity cap, replacing keywords[:2] and LIMIT 6) WITHOUT any LLM calls or Neo4j
writes. To guarantee fidelity, the gate instantiates the REAL retriever class
(no __init__, so no Neo4j/LLM connection) and calls its actual methods:

  - _rank_keywords(question)          (the new keyword ranking)
  - _fetch_chunk_context(question)    (the new candidate generation + chunk rank)

The only simulated piece is a tiny stub ``graph`` whose query() serves the same
CONTAINS entity match over data/refined_graph.json (the v2 artifact loaded in
Neo4j — 1,046 entities), then passes the rows back in the exact shape the real
Neo4j driver returns. The chunk store is rebuilt deterministically from
data/extracted_text.json with the same chunker the retriever uses, so the
returned [Source (chunk N, pages X-Y)] strings are the real QA-facing context.

Per-question metrics computed for the NEW logic:
  - reachable GT chunk   (GT chunk present in the candidate set)
  - GT chunk attached    (GT chunk among the top-3 ranked chunks, QA-facing)
  - GT page attached     (GT page within the page range of an attached chunk)
  - candidate-set size   (distinct candidate chunks before ranking)
  - evidence recall      (fraction of GT evidence tokens in attached chunks)

Each is compared directly against the RECORDED v3 values in
experiments/retrieval_ablation_diagnostic.json (same definitions).

Exit code 0 => offline metrics improved vs v3 (gate PASSED, benchmark allowed).
Exit code 1 => no improvement (gate FAILED, stop and explain).
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from graph_rag.retriever import GraphRAGRetriever  # noqa: E402
from graph_rag.chunker import chunk_by_sections    # noqa: E402

BENCH_PATH = ROOT / "experiments" / "benchmark_v2.json"
DIAG_PATH = ROOT / "experiments" / "retrieval_ablation_diagnostic.json"
GRAPH_PATH = ROOT / "data" / "refined_graph.json"
TEXT_PATH = ROOT / "data" / "extracted_text.json"


class StubGraph:
    """Minimal stand-in for Neo4jGraph: executes the retriever's generated
    ``MATCH (n) WHERE <CONTAINS conds> RETURN ...`` query against the graph
    artifact, returning rows in the same dict shape the real driver yields.

    The generated Cypher is fixed-format (see _fetch_chunk_context): the only
    variable parts are the ``CONTAINS '<kw>'`` literals, which this stub
    extracts and applies with the same name/canonical/aliases/description
    semantics. Keyword values are escaped exactly as the retriever does.
    """

    def __init__(self, entities):
        self._entities = entities

    def query(self, cypher: str):
        kws = re.findall(r"CONTAINS '([^']*)'", cypher)
        if not kws:
            return []
        rows = []
        for e in self._entities:
            hay = [
                e.get("name", ""), e.get("canonical_name", ""),
                e.get("description", ""),
            ] + (e.get("aliases") or [])
            hay_l = " ".join(h or "" for h in hay).lower()
            if any(k in hay_l for k in kws):
                rows.append({
                    "name": e.get("name"),
                    "canonical_name": e.get("canonical_name"),
                    "aliases": e.get("aliases") or [],
                    "description": e.get("description"),
                    "frequency": e.get("frequency", 0),
                    # the retriever reads row.get("chunks") — the Cypher
                    # aliases n.source_chunks AS chunks, so the stub must
                    # return that alias name, not source_chunks.
                    "chunks": e.get("source_chunks") or [],
                })
        return rows


def rebuild_chunk_store():
    pages = json.load(open(TEXT_PATH, encoding="utf-8"))
    parts = []
    for r in pages:
        if r.get("page") is not None and r.get("text"):
            parts.append(f"[PAGE {r['page']}]\n{r['text']}")
    chunks = chunk_by_sections("\n\n".join(parts))
    return {
        c.chunk_id: {"text": c.text, "page_start": c.page_start, "page_end": c.page_end}
        for c in chunks
    }


def parse_attached(line):
    """Return (chunk_id, page_start, page_end) from a
    ``[Source (chunk N, pages X-Y)] ...`` line, or None."""
    m = re.match(r"\[Source \(chunk (\d+), pages (\d+)-(\d+)\)\]", line)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def fidelity_check(retr, bench, records):
    """Prove the stub + real methods reproduce the RECORDED v3 candidate sets
    for the questions where v3's old LIMIT 6 was NOT binding (i.e. the recorded
    set equals the full union of the old keywords[:2] CONTAINS match). Passing
    this is what makes the rest of the gate trustworthy."""
    exact = 0
    for q in bench:
        qid = q["id"]
        old_kws = retr._extract_entity_keywords(q["question"])[:2]
        conds = " OR ".join(f"CONTAINS '{k.lower()}'" for k in old_kws)
        rows = retr.graph.query("MATCH (n) WHERE %s RETURN ..." % conds)
        union = set()
        for r in rows:
            for c in r["chunks"]:
                try:
                    union.add(int(c))
                except (TypeError, ValueError):
                    pass
        recorded = set(records[qid].get("candidate_chunks") or [])
        if union == recorded:
            exact += 1
    return exact


def main():
    bench = json.load(open(BENCH_PATH, encoding="utf-8"))
    diag = json.load(open(DIAG_PATH, encoding="utf-8"))
    graph = json.load(open(GRAPH_PATH, encoding="utf-8"))
    records = {r["question_id"]: r for r in diag["records"]}

    # Instantiate the retriever WITHOUT __init__ (no Neo4j/LLM connection).
    retr = object.__new__(GraphRAGRetriever)
    retr._chunk_store = rebuild_chunk_store()
    retr.graph = StubGraph(graph["entities"])

    # Fidelity gate: the stub must reproduce v3's candidate sets on the
    # no-truncation questions (expected 6: Q2, Q7, Q27, Q34, Q46, Q48).
    n_exact = fidelity_check(retr, bench, records)
    print("FIDELITY SELF-CHECK: stub reproduces recorded v3 candidate sets on %d/12 "
          "questions (expected 6 where v3's LIMIT-6 was not binding)" % n_exact)
    if n_exact < 6:
        print("FIDELITY FAILED — stub is not faithful to the recorded v3 data; aborting.")
        return 1

    # Capture the REAL production candidate set: _fetch_chunk_context calls
    # self._rank_chunks(question, keywords, chunk_ids) — the chunk_ids set it
    # passes IS the candidate set. Wrapping the method records it exactly, so
    # reachable/candidate_size come from the production code path with zero
    # inline re-implementation (no drift risk).
    captured = {}
    _orig_rank_chunks = retr._rank_chunks

    def _recording_rank_chunks(question, keywords, chunk_ids):
        captured["chunk_ids"] = set(chunk_ids)
        captured["keywords"] = list(keywords)
        return _orig_rank_chunks(question, keywords, chunk_ids)

    retr._rank_chunks = _recording_rank_chunks

    rows = []
    for q in bench:
        qid = q["id"]
        qtext = q["question"]
        gt_chunks = records[qid]["gt_chunks"]
        gt_page = q.get("evidence_page")
        rec = records[qid]

        # Call the REAL candidate generation (exact production code path).
        captured["chunk_ids"] = set()
        captured["keywords"] = []
        attached_lines = retr._fetch_chunk_context(qtext)
        candidate_set = captured.get("chunk_ids") or set()
        attached = [parse_attached(l) for l in attached_lines]
        attached = [a for a in attached if a is not None]
        attached_ids = [a[0] for a in attached]

        # metrics (all derived from the production path)
        reachable = bool(set(gt_chunks) & candidate_set)
        chunk_attached = bool(set(gt_chunks) & set(attached_ids))
        page_attached = any(
            p0 <= (gt_page or 0) <= p1 for _cid, p0, p1 in attached
        )
        ev_tokens = []
        if q.get("evidence"):
            ev_tokens = [t for t in re.findall(r"[a-z0-9]+", q["evidence"].lower()) if len(t) > 2]
        recall = 0.0
        if ev_tokens:
            attached_text = " ".join(
                retr._chunk_store[cid]["text"].lower() for cid in attached_ids
                if cid in retr._chunk_store
            )
            recall = sum(1 for t in ev_tokens if t in attached_text) / len(ev_tokens)

        rows.append({
            "qid": qid,
            "keywords": captured.get("keywords") or [],
            "candidate_set": sorted(candidate_set),
            "candidate_size": len(candidate_set),
            "reachable_gt_chunk": reachable,
            "gt_chunk_attached": chunk_attached,
            "gt_page_attached": page_attached,
            "evidence_recall": round(recall, 4),
            # recorded v3 (same definitions)
            "v3_candidate_size": len(rec.get("candidate_chunks") or []),
            "v3_reachable": bool(set(gt_chunks) & set(rec.get("candidate_chunks") or [])),
            "v3_chunk_on": bool(rec.get("v3", {}).get("gt_chunk_on")),
            "v3_page_on": bool(rec.get("v3", {}).get("gt_page_on")),
            "v3_recall": round(float(rec.get("v3", {}).get("recall", 0.0)), 4),
        })

    n = len(rows)
    agg = {
        "reachable_gt_chunks": sum(r["reachable_gt_chunk"] for r in rows),
        "gt_chunks_attached": sum(r["gt_chunk_attached"] for r in rows),
        "gt_pages_attached": sum(r["gt_page_attached"] for r in rows),
        "mean_candidate_size": round(sum(r["candidate_size"] for r in rows) / n, 2),
        "mean_evidence_recall": round(sum(r["evidence_recall"] for r in rows) / n, 4),
        "v3_reachable_gt_chunks": sum(r["v3_reachable"] for r in rows),
        "v3_gt_chunks_attached": sum(r["v3_chunk_on"] for r in rows),
        "v3_gt_pages_attached": sum(r["v3_page_on"] for r in rows),
        "v3_mean_candidate_size": round(sum(r["v3_candidate_size"] for r in rows) / n, 2),
        "v3_mean_evidence_recall": round(sum(r["v3_recall"] for r in rows) / n, 4),
    }

    print("=" * 120)
    print(f"{'Q':>3} {'reach':>6} {'attch':>6} {'pgOn':>6} {'cand':>5} {'recall':>7} | "
          f"{'v3reach':>8} {'v3attch':>7} {'v3pgOn':>6} {'v3cand':>6} {'v3rec':>6}")
    print("-" * 120)
    for r in rows:
        print(f"{r['qid']:>3} {str(r['reachable_gt_chunk']):>6} {str(r['gt_chunk_attached']):>6} "
              f"{str(r['gt_page_attached']):>6} {r['candidate_size']:>5} {r['evidence_recall']:>7.3f} | "
              f"{str(r['v3_reachable']):>8} {str(r['v3_chunk_on']):>7} {str(r['v3_page_on']):>6} "
              f"{r['v3_candidate_size']:>6} {r['v3_recall']:>6.3f}")
    print("=" * 120)
    print("AGGREGATES")
    print(f"  NEW  reachable GT chunks : {agg['reachable_gt_chunks']}/{n}   (v3: {agg['v3_reachable_gt_chunks']}/{n})")
    print(f"  NEW  GT chunks attached  : {agg['gt_chunks_attached']}/{n}   (v3: {agg['v3_gt_chunks_attached']}/{n})")
    print(f"  NEW  GT pages attached   : {agg['gt_pages_attached']}/{n}   (v3: {agg['v3_gt_pages_attached']}/{n})")
    print(f"  NEW  mean candidate size : {agg['mean_candidate_size']}      (v3: {agg['v3_mean_candidate_size']})")
    print(f"  NEW  mean evidence recall: {agg['mean_evidence_recall']}     (v3: {agg['v3_mean_evidence_recall']})")

    improved = (
        agg["reachable_gt_chunks"] > agg["v3_reachable_gt_chunks"]
        or agg["gt_chunks_attached"] > agg["v3_gt_chunks_attached"]
        or agg["gt_pages_attached"] > agg["v3_gt_pages_attached"]
        or agg["mean_evidence_recall"] > agg["v3_mean_evidence_recall"]
    )
    # Candidate-size honesty: the QA-facing metrics can improve while the
    # candidate set degenerates toward the full corpus (a precision regression
    # that would confound any benchmark run: the gain would be trivially
    # explained by breadth, not by smarter selection). Gate on BOTH the mean
    # and a per-question bound (a few questions will legitimately span many
    # chunks for document-wide entities like ISO 20022, but most must stay
    # selective).
    full = len(retr._chunk_store)
    mean_ok = agg["mean_candidate_size"] <= 0.5 * full
    per_q_ok = sum(1 for r in rows if r["candidate_size"] > 0.8 * full) <= 2
    print()
    print("GATE verdict:")
    print("  QA-facing improved vs v3      :", improved)
    print("  mean candidate size %.1f <= 50%% corpus (%.1f): %s" % (
        agg["mean_candidate_size"], 0.5 * full, mean_ok))
    print("  per-question >80%% corpus count <= 2            :", per_q_ok)
    if improved and mean_ok and per_q_ok:
        print("  => PASSED — offline metrics improved with bounded candidate sets; "
              "benchmark allowed.")
        return 0
    print("  => NOT APPROVED — do NOT run the benchmark. If QA-facing metrics "
          "improved but candidate sets exploded to near-corpus width, the gain is "
          "confounded by breadth (any change removing LIMIT-6 would do the same). "
          "Tighten the entity/keyword caps or refine the deterministic ranking "
          "first, then re-gate.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
