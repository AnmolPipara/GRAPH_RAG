"""retrieval_ablation_diagnostic.py — P2 offline gate: page-level vs chunk-level evidence.

Zero-cost offline diagnostic (NO LLM calls, NO writes to Neo4j). Replays the
deterministic retrieval evidence-selection for the 12 benchmark questions
under BOTH designs:

  BEFORE (v2 page-level): verbatim copy of the checkpointed
      ``_fetch_source_context`` (6 entities, first 2 pages each, 3 paragraphs
      x 500 chars).
  AFTER  (v3 chunk-level): the live retriever's ``_fetch_chunk_context``
      (same entity match, ALL source_chunks of matched entities, lexically
      ranked, top-3 chunks x up to 1200 chars).

Measures per question (SAME definition on both sides):
  - GT-page attach  : is the evidence_page's text in the attached context?
                      (v2 lines are "[Source (page N)]"; v3 lines are
                      "[Source (chunk C, pages X-Y)]" — a v3 chunk attaches
                      every page in its range, so page X is attached iff some
                      attached chunk covers X.)
  - GT-chunk attach : is a chunk containing all GT evidence tokens selected?
                      (v2 has no chunk concept — shown for reference only.)
  - evidence recall : fraction of GT evidence tokens present in attached text
  - precision       : fraction of attached context tokens that are GT-relevant
  - GT rank         : rank of the GT chunk within the ACTUAL graph-linked
                      candidate set that _fetch_chunk_context considers.

Outputs experiments/retrieval_ablation_diagnostic.json + .md. The GATE
decision (PROCEED to benchmark vs STOP) is printed and written to the JSON.

NOTE on the v2 baseline: the earlier retrieval_diagnostic.md reported
"GT page attached 6/12" using a LOOSER reachability definition (page in the
entity page-lists, no 3-paragraph cap). This diagnostic measures what the QA
LLM actually receives under the retriever's real caps, for BOTH designs, so
the before/after comparison is apples-to-apples.
"""

import json
import logging
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

logging.disable(logging.CRITICAL)

from config.settings import settings  # noqa: E402
from langchain_neo4j import Neo4jGraph  # noqa: E402

from graph_rag.chunker import chunk_by_sections  # noqa: E402
from graph_rag.retriever import GraphRAGRetriever  # noqa: E402

BENCH = ROOT / "experiments" / "benchmark_v2.json"
OUT_JSON = ROOT / "experiments" / "retrieval_ablation_diagnostic.json"
OUT_MD = ROOT / "experiments" / "retrieval_ablation_diagnostic.md"

MAX_ENTITIES = 6
V2_PAGES_PER_ENTITY = 2
V2_MAX_PARAS = 3
V2_MAX_CHARS = 500
V3_MAX_CHUNKS = 3
V3_MAX_CHARS = 1200

# The v2/v3 entity queries use the SAME LIMIT 6 / first-2-pages caps; the
# constants below keep those caps named so they cannot drift from the replay.
MAX_ENTITIES = 6
V2_PAGES_PER_ENTITY = 2


# ── shared: rebuild chunk store (deterministic, verified) ──────────────
def build_chunk_store():
    pages = json.load(open(ROOT / "data" / "extracted_text.json", encoding="utf-8"))
    parts = []
    for p in pages:
        if p.get("page") is not None and p.get("text"):
            parts.append(f"[PAGE {p['page']}]\n{p['text']}")
    chunks = chunk_by_sections("\n\n".join(parts))
    return {c.chunk_id: {"text": c.text, "page_start": c.page_start, "page_end": c.page_end}
            for c in chunks}, chunks


def _norm(t):
    return re.sub(r"[^a-z0-9 ]", " ", t.lower()).split()


# ── v2 page-level evidence selection (verbatim from checkpoint) ────────
STOP = frozenset({"what", "who", "how", "when", "where", "which", "why",
                  "is", "are", "was", "were", "does", "do", "did", "the",
                  "a", "an", "of", "for", "in", "on", "at", "by", "to",
                  "with", "and", "or", "from", "it", "its", "this", "that",
                  "have", "has", "had", "be", "been", "can", "could",
                  "would", "should", "please", "provide", "many", "much",
                  "pages", "page", "version", "year", "number", "what is"})


def extract_keywords_v2(question: str):
    """Verbatim copy of the v2 retriever's _extract_entity_keywords."""
    candidates = []
    for m in re.finditer(r'"([^"]+)"|\'([^\']+)\'', question):
        phrase = (m.group(1) or m.group(2) or "").strip()
        if phrase:
            candidates.append(phrase)
    for m in re.finditer(
        r"\b(?:[A-Z][A-Za-z0-9.\-]*|\d+)(?:\s+(?:[A-Z][A-Za-z0-9.\-]*|\d+)){1,}\b",
        question,
    ):
        phrase = m.group(0).strip()
        if phrase:
            candidates.append(phrase)
    if not candidates:
        for m in re.finditer(r"\b[A-Z][A-Za-z0-9.\-]{2,}\b", question):
            word = m.group(0)
            if word.lower() not in STOP:
                candidates.append(word)
    if not candidates:
        for m in re.finditer(r"\b[a-z][a-z0-9.\-]{2,}\b", question):
            word = m.group(0)
            if word.lower() not in STOP:
                candidates.append(word)
    seen, out = set(), []
    for c in candidates:
        c = c.strip().strip("?. ,;:!").strip()
        cl = c.lower()
        if not c or cl in seen or cl in STOP:
            continue
        seen.add(cl)
        out.append(c)
    return out[:3]


def v2_fetch_source_context(graph, page_text, question):
    """Byte-equivalent replay of the v2 retriever's _fetch_source_context."""
    keywords = extract_keywords_v2(question)
    if not keywords or not page_text:
        return []
    conds = []
    for kw in keywords[:2]:
        kwl = kw.lower().replace("'", "\\'")
        conds.append(
            f"(toLower(n.name) CONTAINS '{kwl}' "
            f"OR toLower(n.canonical_name) CONTAINS '{kwl}' "
            f"OR any(a IN coalesce(n.aliases, []) WHERE toLower(a) CONTAINS '{kwl}') "
            f"OR toLower(n.description) CONTAINS '{kwl}')"
        )
    rows = graph.query(
        f"MATCH (n) WHERE {' OR '.join(conds)} "
        f"RETURN n.name AS name, n.source_pages AS pages LIMIT {MAX_ENTITIES}"
    )
    out_lines, seen_pages = [], set()
    for row in rows:
        for p in (row.get("pages") or [])[:V2_PAGES_PER_ENTITY]:
            try:
                key = int(p)
            except (TypeError, ValueError):
                continue
            if key in seen_pages or key not in page_text:
                continue
            seen_pages.add(key)
            text = page_text[key].strip()
            if not text:
                continue
            if len(text) > V2_MAX_CHARS:
                text = text[:V2_MAX_CHARS] + "..."
            out_lines.append(f"[Source (page {key})] {text}")
            if len(out_lines) >= V2_MAX_PARAS:
                return out_lines
    return out_lines


# ── v3 candidate set (same entity query the live retriever runs) ───────
def v3_candidate_chunks(graph, question):
    """Return the {chunk_id} union of source_chunks of the entities the live
    retriever's _fetch_chunk_context would match (same keywords[:2], LIMIT 6)."""
    keywords = extract_keywords_v2(question)
    if not keywords:
        return set()
    conds = []
    for kw in keywords[:2]:
        kwl = kw.lower().replace("'", "\\'")
        conds.append(
            f"(toLower(n.name) CONTAINS '{kwl}' "
            f"OR toLower(n.canonical_name) CONTAINS '{kwl}' "
            f"OR any(a IN coalesce(n.aliases, []) WHERE toLower(a) CONTAINS '{kwl}') "
            f"OR toLower(n.description) CONTAINS '{kwl}')"
        )
    rows = graph.query(
        f"MATCH (n) WHERE {' OR '.join(conds)} "
        f"RETURN n.name AS name, n.source_chunks AS chunks LIMIT {MAX_ENTITIES}"
    )
    out = set()
    for row in rows:
        for c in (row.get("chunks") or []):
            try:
                out.add(int(c))
            except (TypeError, ValueError):
                continue
    return out


def main():
    questions = json.load(open(BENCH, encoding="utf-8"))
    graph = Neo4jGraph(url=settings.neo4j_uri, username=settings.neo4j_username,
                       password=settings.neo4j_password, database="410b7631")
    _chunk_store, chunks = build_chunk_store()
    pages = json.load(open(ROOT / "data" / "extracted_text.json", encoding="utf-8"))
    page_text = {int(r["page"]): r["text"] for r in pages if r.get("page") is not None and r.get("text")}

    # ONE live retriever for the v3 path (shared across questions).
    retriever = GraphRAGRetriever()

    records = []
    for q in questions:
        qid = q["id"]
        ep = q["evidence_page"]
        ev_toks = {t for t in _norm(q["evidence"]) if len(t) > 2}

        # GT chunks: chunks covering the evidence page whose text contains all
        # evidence tokens; fall back to any chunk containing all tokens.
        gt_chunks = []
        for c in chunks:
            if c.page_start <= ep <= c.page_end:
                c_toks = set(_norm(c.text))
                if ev_toks and ev_toks <= c_toks:
                    gt_chunks.append(c.chunk_id)
        if not gt_chunks:
            for c in chunks:
                c_toks = set(_norm(c.text))
                if ev_toks and ev_toks <= c_toks:
                    gt_chunks.append(c.chunk_id)

        v2_lines = v2_fetch_source_context(graph, page_text, q["question"])
        v3_lines = retriever._fetch_chunk_context(
            q["question"], max_chunks=V3_MAX_CHUNKS, max_chars=V3_MAX_CHARS
        )

        def parse_attached(lines):
            """Return (pages_attached, chunks_attached) with prefix-anchored parsing.

            Anchoring to the ``[Source ...]`` prefix avoids false positives from
            document prose that mentions "page N" or "pages X-Y" (the guide is
            full of cross-references like "see section 7.2.2").
            """
            pages_attached, chunks_attached = set(), set()
            for ln in lines:
                m = re.match(r"\[Source \(page (\d+)\)\]", ln)
                if m:
                    pages_attached.add(int(m.group(1)))
                    continue
                m = re.match(r"\[Source \(chunk (\d+), pages (\d+)-(\d+)\)\]", ln)
                if m:
                    chunks_attached.add(int(m.group(1)))
                    for pg in range(int(m.group(2)), int(m.group(3)) + 1):
                        pages_attached.add(pg)
            return pages_attached, chunks_attached

        def attach_metrics(lines):
            toks = {t for ln in lines for t in _norm(ln)}
            rec = len(ev_toks & toks) / len(ev_toks) if ev_toks else 0.0
            prec = len(ev_toks & toks) / len(toks) if toks else 0.0
            pages_attached, chunks_attached = parse_attached(lines)
            return {
                "recall": round(rec, 4),
                "precision": round(prec, 4),
                "gt_page_on": ep in pages_attached,
                "gt_chunk_on": bool(gt_chunks and (set(gt_chunks) & chunks_attached)),
                "n_pages": len(pages_attached),
                "n_chunks": len(chunks_attached),
                "n_lines": len(lines),
            }

        v2m = attach_metrics(v2_lines)
        v3m = attach_metrics(v3_lines)

        # GT rank within the ACTUAL candidate set the live retriever considers.
        # A GT chunk OUTSIDE the candidate set is entity-match-limited: the live
        # system can never select it, so its rank is honestly reported as None.
        candidates = v3_candidate_chunks(graph, q["question"])
        gt_rank = None
        if gt_chunks and (set(gt_chunks) & candidates):
            ranked = retriever._rank_chunks(
                q["question"], retriever._extract_entity_keywords(q["question"]),
                candidates,
            )
            for i, (cid, _s) in enumerate(ranked):
                if cid in gt_chunks:
                    gt_rank = i + 1
                    break

        records.append({
            "question_id": qid, "category": q["category"], "question": q["question"],
            "evidence_page": ep, "gt_chunks": gt_chunks, "candidate_chunks": sorted(candidates),
            "v2": {"attached_lines": v2_lines, **v2m},
            "v3": {"attached_lines": v3_lines, **v3m},
            "gt_rank_in_candidates": gt_rank,
        })

    n = len(records)
    agg = {
        "n_questions": n,
        "gt_page_on": {"v2": sum(1 for r in records if r["v2"]["gt_page_on"]),
                       "v3": sum(1 for r in records if r["v3"]["gt_page_on"])},
        "gt_chunk_on": {"v2": sum(1 for r in records if r["v2"]["gt_chunk_on"]),
                        "v3": sum(1 for r in records if r["v3"]["gt_chunk_on"])},
        "evidence_recall_mean": {"v2": round(sum(r["v2"]["recall"] for r in records) / n, 4),
                                 "v3": round(sum(r["v3"]["recall"] for r in records) / n, 4)},
        "precision_mean": {"v2": round(sum(r["v2"]["precision"] for r in records) / n, 4),
                           "v3": round(sum(r["v3"]["precision"] for r in records) / n, 4)},
        "gt_rank_in_candidates": {r["question_id"]: r["gt_rank_in_candidates"] for r in records},
    }

    # GATE: PROCEED iff the SAME-definition GT-page attach improves AND mean
    # evidence recall improves meaningfully (>= +0.05). Chunk attach is a
    # supporting signal (v2 has no chunk concept, so its 0 is structural).
    d_page = agg["gt_page_on"]["v3"] - agg["gt_page_on"]["v2"]
    d_recall = agg["evidence_recall_mean"]["v3"] - agg["evidence_recall_mean"]["v2"]
    gate = {
        "decision": "PROCEED" if (d_page > 0 and d_recall >= 0.05) else "STOP",
        "reasons": [
            f"GT-page attach (same def, QA-facing) v2={agg['gt_page_on']['v2']} v3={agg['gt_page_on']['v3']} (Δ{d_page:+d})",
            f"GT-chunk attach v2={agg['gt_chunk_on']['v2']} v3={agg['gt_chunk_on']['v3']} (Δ{agg['gt_chunk_on']['v3'] - agg['gt_chunk_on']['v2']:+d})",
            f"evidence recall mean v2={agg['evidence_recall_mean']['v2']} v3={agg['evidence_recall_mean']['v3']} (Δ{d_recall:+.4f})",
            f"precision mean v2={agg['precision_mean']['v2']} v3={agg['precision_mean']['v3']}",
            "v3 attaches chunk page RANGES (pages X-Y), v2 attaches single pages — same GT-page test applied to both.",
        ],
    }

    out = {"stats": agg, "gate": gate, "records": records}
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    # ── markdown report ──────────────────────────────────────────────
    lines = [
        "# Retrieval Ablation Diagnostic — page-level (v2) vs chunk-level (v3)",
        "",
        f"Zero-cost offline replay (no LLM calls, read-only Neo4j). {n} benchmark questions.",
        "",
        "## Gate verdict",
        "",
        f"**{gate['decision']}**",
        "",
        *[f"- {r}" for r in gate["reasons"]],
        "",
        "## Aggregate",
        "",
        "| Metric | v2 (page-level) | v3 (chunk-level) |",
        "|---|---|---|",
        f"| GT-page attach (QA-facing, same def) | {agg['gt_page_on']['v2']}/{n} | {agg['gt_page_on']['v3']}/{n} |",
        f"| GT-chunk attach | {agg['gt_chunk_on']['v2']}/{n} | {agg['gt_chunk_on']['v3']}/{n} |",
        f"| Evidence recall (mean) | {agg['evidence_recall_mean']['v2']} | {agg['evidence_recall_mean']['v3']} |",
        f"| Precision (mean) | {agg['precision_mean']['v2']} | {agg['precision_mean']['v3']} |",
        "",
        "## Per-question",
        "",
        "| Q | GT pg | GT chunk(s) | candidates | v2 pg-on | v3 pg-on | v3 chunk-on | v2 rec | v3 rec | GT rank |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        lines.append(
            f"| {r['question_id']} | {r['evidence_page']} | {r['gt_chunks']} | "
            f"{len(r['candidate_chunks'])} | {r['v2']['gt_page_on']} | {r['v3']['gt_page_on']} | "
            f"{r['v3']['gt_chunk_on']} | {r['v2']['recall']} | {r['v3']['recall']} | "
            f"{r['gt_rank_in_candidates']} |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "- v2 = checkpointed `_fetch_source_context` (6 entities, first 2 pages each, 3 paras x 500 chars).",
        "- v3 = `_fetch_chunk_context` (same entity match, ALL `source_chunks`, lexical rank, top-3 x 1200 chars).",
        "- GT chunk = chunk covering the evidence page whose text contains all GT evidence tokens.",
        "- GT rank = rank of the GT chunk in the live retriever's candidate ranking (1 = first).",
        "- The earlier retrieval_diagnostic.md '6/12 GT-page attached' used a looser reachability",
        "  definition (page in entity page-lists, no paragraph cap). This diagnostic measures the",
        "  QA-facing context for both designs under their real caps, so v2 shows 3/12 here.",
        "- No prompts, evaluator, QA model, temperature, or benchmark were changed.",
    ]
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(json.dumps({"stats": agg, "gate": gate}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
