# -*- coding: utf-8 -*-
"""benchmark_compare.py - Vector RAG vs Graph RAG comparison on the ISO 20022 guide.

Fair comparison design (same as evaluation/evaluator_v2.py):
- BOTH systems generate answers with the SAME LLM (OpenRouter gpt-4o-mini)
- BOTH use the SAME QA prompt template
- The ONLY difference is the retrieval method:
    Vector RAG : top-k chunk similarity search over embedded PDF text
    Graph RAG  : entity matching + multi-hop traversal over the knowledge graph
                 (built from merged_knowledge.json), enriched with the source
                 pages that graph evidence is linked to (chunk-linkage).
"""
import io
import json
import logging
import math
import re
import sys
import time
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("benchmark")
for name in ("httpx", "openai", "urllib3", "faiss", "sentence_transformers", "langchain"):
    logging.getLogger(name).setLevel(logging.WARNING)

sys.path.insert(0, str(ROOT.parent / "evaluation"))
from metrics_v2 import compute_all_metrics  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
import os as _os
ANSWER_PROVIDER = _os.getenv("ANSWER_PROVIDER", "groq").strip().lower()
ANSWER_MODEL = _os.getenv("ANSWER_MODEL", "llama-3.3-70b-versatile").strip()
EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
TOP_K = 5
GRAPH_MAX_DEPTH = 3
GRAPH_MAX_ENTITIES = 25
GRAPH_KEYWORD_CAP = 6
GRAPH_MAX_CHUNKS = 12
GRAPH_CHUNK_CHARS = 1000
GRAPH_MAX_PATHS = 6
GRAPH_MAX_TRIPLES = 10
GRAPH_MAX_CHARS = 15000
GRAPH_MAX_ENTITY_LINES = 15
QA_MAX_TOKENS = 512

QA_PROMPT_TEMPLATE = (
    "You are an expert research assistant. Use the following pieces of retrieved "
    "context to answer the user's question.\n"
    "If you don't know the answer, just say that you don't know, don't try to "
    "make up an answer.\n"
    "Always cite the page numbers if provided in the context.\n\n"
    "Context:\n{context}\n\n"
    "Question: {question}\n\n"
    "Answer:"
)

STOPWORDS = frozenset({
    "what", "who", "how", "when", "where", "which", "why", "is", "are", "was",
    "were", "does", "do", "did", "the", "a", "an", "of", "for", "in", "on", "at",
    "by", "to", "with", "and", "or", "from", "it", "its", "this", "that", "have",
    "has", "had", "be", "been", "can", "could", "would", "should", "please",
    "provide", "many", "much", "pages", "page", "version", "year", "number",
    "between", "difference", "using", "used", "use", "via", "within", "during",
    "before", "after", "upon", "under", "over", "into", "onto", "than", "then",
    "these", "those", "their", "there", "they", "them", "such", "each", "both",
    "other", "most", "more", "some", "any", "all", "one", "two", "three", "four",
    "five", "six", "seven", "eight", "nine", "ten", "first", "second", "third",
    "etc", "said", "according", "guide", "accordingly", "if", "pay", "own", "may",
})

# ---------------------------------------------------------------------------
# LLM client (same model for both systems -> fair)
# ---------------------------------------------------------------------------
def create_llm():
    from dotenv import load_dotenv
    import os
    from langchain_openai import ChatOpenAI

    load_dotenv(ROOT.parent / ".env")
    provider = os.getenv("ANSWER_PROVIDER", ANSWER_PROVIDER).strip().lower()
    model = os.getenv("ANSWER_MODEL", ANSWER_MODEL).strip()
    if provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        base_url = "https://openrouter.ai/api/v1"
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = "https://api.openai.com/v1"
    else:  # groq
        api_key = os.getenv("GROQ_API_KEY", "")
        base_url = "https://api.groq.com/openai/v1"
    if not api_key:
        raise RuntimeError(f"{provider.upper()}_API_KEY not found")
    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0.0,
        max_tokens=QA_MAX_TOKENS,
        default_headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        },
    )


def invoke_with_retry(llm, prompt, max_retries=5):
    last_error = None
    for attempt in range(max_retries):
        try:
            result = llm.invoke(prompt)
            answer = result.content if hasattr(result, "content") else str(result)
            return answer.strip()
        except Exception as e:
            last_error = e
            msg = str(e).lower()
            if any(k in msg for k in ("per day", "tpd", "quota", "no credits", "credits", "depleted")):
                # daily token caps / quota exhaustion won't clear with a short
                # wait — fail fast instead of burning minutes per question
                raise RuntimeError(f"LLM invoke failed (quota): {str(e)[:200]}")
            if any(k in msg for k in ("rate_limit", "429", "tpm", "too many requests", "throttl", "try again", "timed out", "timeout", "connection", "unreachable", "reset")):
                # per-minute limits: wait longer so the call succeeds on retry
                wait = 30 * (attempt + 1)
                logger.warning("LLM retry %d/%d after %ss: %s", attempt + 1, max_retries, wait, str(e)[:90])
                time.sleep(wait)
            else:
                break
    raise RuntimeError(f"LLM invoke failed: {last_error}")


def safe_text(s, limit=160):
    """ASCII-safe preview for terminal printing (Windows cp1252 console)."""
    s = (s or "").replace("\n", " ")
    return s[:limit]

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_pages():
    with io.open(DATA / "extracted_text.json", encoding="utf-8") as f:
        pages = json.load(f)
    return {p["page"]: p["text"] for p in pages if p.get("text")}


def _first_valid_page(pages):
    """First usable page number from a source_pages list (int in 2..61).
    Page 1 is the extraction default (cover/TOC) in the sibling graph and
    carries no content, so it's skipped as a linkage signal."""
    for p in (pages or []):
        try:
            p = int(p)
        except (TypeError, ValueError):
            continue
        if 2 <= p <= 61:
            return p
    return None


def load_graph_data(source=None):
    """Load entities/relationships. `source` (or GRAPH_DATA env):
      - "merged" (default): this project's 300-entity extraction
      - "sibling": the sibling GraphRAG project's richer 673-entity / 413-rel graph,
        normalized to this benchmark's schema — relationships resolve their
        slug ids to readable entity names, descriptions become source_text,
        aliases are kept for matching/mention linkage, and the page-1
        extraction default is dropped.
    """
    if source is None:
        source = _os.getenv("GRAPH_DATA", "merged").strip().lower()
    if source == "sibling":
        path = ROOT.parent / "data" / "merged_knowledge.json"
        with io.open(path, encoding="utf-8") as f:
            g = json.load(f)
        name_by_id = {e.get("id"): e["name"] for e in g["entities"] if e.get("id")}
        entities = [{
            "name": e["name"],
            "type": e.get("type"),
            "source_text": e.get("description") or "",
            "page": _first_valid_page(e.get("source_pages")),
            "aliases": e.get("aliases") or [],
        } for e in g["entities"]]
        names = {e["name"] for e in entities}
        relationships = []
        for r in g["relationships"]:
            src = name_by_id.get(r.get("source"))
            tgt = name_by_id.get(r.get("target"))
            if not src or not tgt or src not in names or tgt not in names:
                continue
            relationships.append({
                "source": src,
                "target": tgt,
                "relation": r.get("relation", "RELATED_TO"),
                "source_text": r.get("description") or "",
                "page": _first_valid_page(r.get("source_pages")),
            })
        return entities, relationships
    with io.open(DATA / "merged_knowledge.json", encoding="utf-8") as f:
        g = json.load(f)
    return g["entities"], g["relationships"]


def load_questions():
    with io.open(DATA / "graph_rag_questions.json", encoding="utf-8") as f:
        data = json.load(f)
    qs = []
    for q in data["questions"]:
        qs.append({
            "id": q["id"],
            "category": q["difficulty"],
            "question": q["question"],
            "ground_truth": q["answer"],
        })
    return qs


# ---------------------------------------------------------------------------
# Vector RAG: chunk + embed + FAISS index
# ---------------------------------------------------------------------------
def build_vector_store(pages):
    from langchain_core.documents import Document
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import FAISS

    logger.info("Loading embedding model %s ...", EMBEDDING_MODEL)
    t0 = time.time()
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    logger.info("Embedding model loaded in %.1fs", time.time() - t0)

    docs = [Document(page_content=text, metadata={"page": page})
            for page, text in sorted(pages.items())]
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    chunks = splitter.split_documents(docs)
    logger.info("Split %d pages into %d chunks", len(docs), len(chunks))

    global PAGE_CHUNKS
    PAGE_CHUNKS = {}
    for c in chunks:
        pg = c.metadata.get("page")
        PAGE_CHUNKS.setdefault(pg, []).append(c.page_content)

    cache = DATA / "faiss_index"
    if (cache / "index.faiss").exists():
        t0 = time.time()
        store = FAISS.load_local(str(cache), embeddings, allow_dangerous_deserialization=True)
        logger.info("Loaded cached FAISS index in %.1fs", time.time() - t0)
        return store
    t0 = time.time()
    store = FAISS.from_documents(chunks, embeddings)
    store.save_local(str(cache))
    logger.info("FAISS index built and cached in %.1fs", time.time() - t0)
    return store


def vector_retrieve(store, question, k=TOP_K):
    docs = store.similarity_search_with_score(question, k=k)
    return [(d.metadata.get("page"), d.page_content, round(float(s), 4)) for d, s in docs]

# ---------------------------------------------------------------------------
# Graph RAG: in-memory knowledge graph + traversal
# ---------------------------------------------------------------------------
def build_graph(entities, relationships):
    import networkx as nx

    G = nx.MultiDiGraph()
    for e in entities:
        G.add_node(e["name"], type=e.get("type"), source_text=e.get("source_text"),
                   page=e.get("page"), aliases=e.get("aliases") or [])
    rel_keys = set()
    for r in relationships:
        src, tgt = r.get("source"), r.get("target")
        if src not in G or tgt not in G:
            continue
        rel = r.get("relation", "RELATED_TO")
        key = (src, tgt, rel)
        if key in rel_keys:
            continue
        rel_keys.add(key)
        G.add_edge(src, tgt, relation=rel, source_text=r.get("source_text"),
                   page=r.get("page"))
    logger.info("Graph: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())
    return G


def extract_keywords(question):
    """Candidate entity keywords: quoted phrases > capitalized runs > ALL-CAPS
    codes > single capitals > lowercase content words.

    Runs are punctuation-free (a trailing dot used to swallow the next
    sentence-initial word, e.g. 'INST. Which'), leading determiners are
    stripped ('The ISO 20022' -> 'ISO 20022'), and keywords that are mere
    substrings of a more specific one ('20022', 'ISO', 'Local') are dropped
    so short noisy variants don't dominate chunk scoring."""
    cands = []
    for m in re.finditer(r'"([^"]+)"|\'([^\']+)\'', question):
        phrase = (m.group(1) or m.group(2) or "").strip()
        if phrase:
            cands.append((phrase, 4))
    for m in re.finditer(
        r"\b(?:[A-Z][A-Za-z0-9\-]*[A-Za-z0-9]|\d+)"
        r"(?:\s+(?:[A-Z][A-Za-z0-9\-]*[A-Za-z0-9]|\d+))+\b",
        question,
    ):
        phrase = m.group(0).strip()
        if phrase:
            cands.append((phrase, 3))
    for m in re.finditer(r"\b[A-Z0-9][A-Za-z0-9.\-]{2,}\b", question):
        word = m.group(0)
        if word.lower() not in STOPWORDS:
            cands.append((word, 2))
    for m in re.finditer(r"\b[a-z][a-z0-9.\-]{2,}\b", question):
        word = m.group(0)
        if word.lower() not in STOPWORDS:
            cands.append((word, 1))
    seen = OrderedDict()
    for c, prio in cands:
        c = c.strip().strip("?. ,;:!").strip()
        # sentence-initial particles glom onto runs ('In SEPA credit transfers')
        c = re.sub(r"^(the|a|an|in|on|at|by|for|of|to|with|from|as|if)\s+", "", c,
                   flags=re.IGNORECASE).strip()
        cl = c.lower()
        if not c or cl in STOPWORDS:
            continue
        if cl not in seen or prio > seen[cl][1]:
            seen[cl] = (c, prio)
    # keep more specific keywords first; drop shorter ones whose words appear
    # as a contiguous run inside a longer kept keyword (e.g. 'ISO' inside
    # 'ISO 20022'). Codes ('INST', 'MSGID000001', 'AOS2', 'SALA') are kept
    # even when they're a word inside a phrase — 'inst' is only a normalized
    # substring of 'Local Instrument' by concatenation, and dropping the code
    # would lose a strong entity anchor.
    code_re = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{2,}$")
    items = sorted(seen.values(), key=lambda t: (-t[1], -len(t[0]), t[0].lower()))
    kept, kept_words = [], []
    for c, prio in items:
        words = [w for w in re.split(r"[^a-z0-9]+", c.lower()) if w]
        if not words:
            continue
        if any(_subwords(words, kw) for kw in kept_words) and not code_re.match(c.strip()):
            continue
        kept.append((c, prio))
        kept_words.append(words)
    return kept



PAGE_CHUNKS = {}     # page -> [chunk texts], filled by build_vector_store
CHUNK_INDEX = {}     # built by build_chunk_index(): chunk <-> entity mention maps


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _subwords(sub, full):
    """True if the word list `sub` appears as a contiguous slice of `full`."""
    n = len(sub)
    return any(full[i:i + n] == sub for i in range(len(full) - n + 1))


def build_chunk_index(entity_records):
    """Inverted index linking graph entities to every document chunk that
    mentions them (by name or alias), plus per-page chunk maps.

    This is the 'dense entity-to-chunk linkage': the graph decides which
    entities matter (keyword matching + traversal in graph_retrieve), and the
    index locates ALL chunks where those entities appear — not just the single
    page recorded on the entity record. Evidence that straddles pages (XML
    listings, tables, worked examples) becomes reachable, which page-level
    linkage alone misses.
    """
    global CHUNK_INDEX
    chunks = []       # {page, text, norm}
    page_chunks = {}  # page -> [chunk ids]
    for pg in sorted(PAGE_CHUNKS):
        ids = []
        for text in PAGE_CHUNKS[pg]:
            cid = len(chunks)
            chunks.append({"page": pg, "text": text, "norm": _norm(text)})
            ids.append(cid)
        page_chunks[pg] = ids

    ent_mentions = {}
    chunk_entities = {}
    for rec in entity_records:
        name = rec["name"] if isinstance(rec, dict) else rec
        aliases = (rec.get("aliases") or []) if isinstance(rec, dict) else []
        nnorm = _norm(name)
        if len(nnorm) < 3:
            continue
        hits = set()
        for cand in [name] + list(aliases):
            cn = _norm(cand)
            if len(cn) < 3:
                continue
            if len(cn) < 5:
                # short names (SLEV, EUR, VOP...): standalone-token match so
                # we don't hit 'slev' inside unrelated words
                pat = re.compile(r"(?<![a-z0-9])" + re.escape(cn) + r"(?![a-z0-9])")
                hits.update(i for i, c in enumerate(chunks) if pat.search(c["norm"]))
            else:
                hits.update(i for i, c in enumerate(chunks) if cn in c["norm"])
        if not hits:
            continue
        ent_mentions[nnorm] = hits
        for i in hits:
            chunk_entities.setdefault(i, set()).add(nnorm)
    CHUNK_INDEX = {
        "chunks": chunks,
        "ent_mentions": ent_mentions,
        "chunk_entities": chunk_entities,
        "page_chunks": page_chunks,
    }
    logger.info("Chunk index: %d chunks, %d entities with mention links",
                len(chunks), len(ent_mentions))
    return CHUNK_INDEX


def select_keywords(question, pages, cap=None):
    """Rank extracted keywords by (specificity, corpus rarity) and keep the
    most discriminative ones for entity matching (like the sibling's
    _KEYWORD_CAP). Rarity = fraction of pages NOT containing the keyword."""
    if cap is None:
        cap = GRAPH_KEYWORD_CAP
    kws = extract_keywords(question)
    texts = [t.lower() for t in pages.values()]
    n = max(1, len(texts))
    scored = []
    for kw, prio in kws:
        kl = kw.lower()
        df = sum(1 for t in texts if kl in t)
        rarity = (n - df) / n
        scored.append((kw, prio * 100 + rarity * 30 + min(len(kw), 15)))
    scored.sort(key=lambda t: (-t[1], t[0].lower()))
    return [kw for kw, _ in scored[:cap]]


def match_entities(G, keywords, max_entities=GRAPH_MAX_ENTITIES):
    """Score entities by normalized-name match strength against keywords.

    Exact normalized equality dominates, then substring containment in either
    direction (e.g. keyword 'ChargeBearer' -> entity 'Charge Bearer'), then
    keyword presence in the entity's source_text as a weak signal. Deterministic
    ordering (score, name length, name) so the same set always survives to the
    cap.
    """
    kw_norm = [k for k in (_norm(x) for x in keywords) if k]
    kwl = [k.lower() for k in keywords]
    scored = []
    for name in G.nodes:
        nnorm = _norm(name)
        if not nnorm:
            continue
        attrs = G.nodes[name]
        al = " " + " ".join(attrs.get("aliases") or []).lower() + " "
        s = 0
        for kn in kw_norm:
            if kn == nnorm:
                s += 8
            elif kn in nnorm or nnorm in kn:
                s += 3
            elif kn in al:
                s += 2
        if s == 0:
            st = (attrs.get("source_text") or "").lower()
            if any(k in st for k in kwl):
                s += 1
        if s:
            scored.append((name, s, len(nnorm)))
    scored.sort(key=lambda t: (-t[1], -t[2], t[0].lower()))
    return [x[0] for x in scored[:max_entities]]


def graph_retrieve(G, pages, question, max_depth=GRAPH_MAX_DEPTH):
    """Graph-anchored retrieval with dense entity->chunk linkage.

    Pipeline: ranked keywords -> matched entities (seeds) -> BFS traversal up
    to max_depth collecting edges, multi-hop path chains and an expanded
    reachable set -> candidate chunks (entity mentions + keyword mentions +
    linked/adjacent pages) ranked by evidence density -> context assembled as
    entity evidence, top chunks, path chains, then triples.
    """
    keywords = select_keywords(question, pages)
    matched = match_entities(G, keywords)
    context, seen = [], set()

    def add_line(line):
        if line not in seen:
            seen.add(line)
            context.append(line)

    # 1) Entity evidence (the graph's own records for the seeds)
    for name in matched[:GRAPH_MAX_ENTITY_LINES]:
        attrs = G.nodes[name]
        st = (attrs.get("source_text") or "").strip()
        if st:
            add_line(f"[Entity | page {attrs.get('page')}] {name} "
                     f"({attrs.get('type')}): {st}")

    # 2) BFS up to max_depth: edges, path chains, reachable set
    edges = []          # (src, rel, tgt, source_text, page)
    reached = set(matched)
    frontier = list(matched)
    for depth in range(max_depth):
        nxt = []
        for node in frontier:
            for _, tgt, _k, ed in G.out_edges(node, keys=True, data=True):
                edges.append((node, ed.get("relation", "RELATED_TO"), tgt,
                              (ed.get("source_text") or "").strip(), ed.get("page")))
                if tgt not in reached:
                    reached.add(tgt)
                    nxt.append(tgt)
            for src, _, _k, ed in G.in_edges(node, keys=True, data=True):
                if src in reached:
                    continue
                edges.append((src, ed.get("relation", "RELATED_TO"), node,
                              (ed.get("source_text") or "").strip(), ed.get("page")))
                reached.add(src)
                nxt.append(src)
        frontier = nxt
        if not frontier:
            break

    paths = []          # node chains from each seed, up to max_depth edges

    def dfs(node, chain, depth):
        if len(paths) >= 60:
            return
        if depth >= max_depth:
            return
        for _, tgt, _k, _ed in G.out_edges(node, keys=True, data=True):
            nchain = chain + [tgt]
            paths.append(nchain)
            dfs(tgt, nchain, depth + 1)

    for m in matched:
        dfs(m, [m], 0)

    # 3) Candidate chunks: entity mentions + keyword mentions + linked pages
    cidx = CHUNK_INDEX or build_chunk_index(
        [{"name": n, "aliases": G.nodes[n].get("aliases") or []} for n in G.nodes])
    chunks = cidx["chunks"]
    page_chunks = cidx["page_chunks"]
    ent_mentions = cidx["ent_mentions"]
    q_tokens = {t for t in re.sub(r"[^a-z0-9 ]", " ", question.lower()).split()
                if len(t) > 2}

    cand = {}
    matched_norm = {_norm(n) for n in matched if _norm(n)}

    def bump(cid, amt):
        cand[cid] = cand.get(cid, 0.0) + amt

    # matched entities: strong mention signal (the graph decided these matter).
    # Capped per chunk so pages that merely repeat many entity names (structure
    # tables) can't outrank a single decisive mention (e.g. an XML evidence page)
    for nnorm in matched_norm:
        for cid in ent_mentions.get(nnorm, ()):
            bump(cid, 5.0)
    for cid in list(cand):
        if cand[cid] > 10.0:
            cand[cid] = 10.0

    # pages directly linked from graph evidence (entities + edges + path nodes)
    anchored = set()
    for name in matched:
        pg = G.nodes[name].get("page")
        if pg:
            anchored.add(int(pg))
    for _s, _r, _t, _st, pg in edges:
        if pg:
            anchored.add(int(pg))
    for chain in paths:
        for nd in chain:
            pg = G.nodes[nd].get("page")
            if pg:
                anchored.add(int(pg))
    for pg in anchored:
        for cid in page_chunks.get(pg, ()):
            bump(cid, 3.0)
        for nbr in (pg - 1, pg + 1):
            for cid in page_chunks.get(nbr, ()):
                bump(cid, 1.5)

    # keyword presence + question-token overlap (lexical recall; bounded so
    # common terms can't let an index page outrank entity-anchored evidence)
    kw_norm = {k for k in (_norm(x) for x in keywords) if k}
    for cid in cand:
        ctext = chunks[cid]["norm"]
        kw_hits = sum(1 for k in kw_norm if k in ctext)
        overlap = sum(1 for t in q_tokens if t in ctext)
        cand[cid] += 1.5 * min(kw_hits, 4) + 0.25 * min(overlap, 8)

    ranked = sorted(cand.items(), key=lambda kv: (-kv[1], kv[0]))
    # diversity: at most 2 chunks per page, so a single section can't monopolize
    # the budget at the expense of other evidence-bearing pages
    selected = []
    page_counts = {}
    for cid, _sc in ranked:
        if len(selected) >= GRAPH_MAX_CHUNKS:
            break
        pg = chunks[cid]["page"]
        if page_counts.get(pg, 0) >= 2:
            continue
        page_counts[pg] = page_counts.get(pg, 0) + 1
        selected.append(cid)

    # continuity fill: passages often straddle a page boundary, so pull the
    # adjacent chunks of already-selected evidence pages — neighbors of the
    # highest-scoring selected chunks first (not lowest page number)
    rank_of = {cid: i for i, (cid, _sc) in enumerate(ranked)}
    fill_pages = []
    seen_fill = set()
    for cid in sorted(selected, key=lambda c: rank_of[c]):
        pg = chunks[cid]["page"]
        for nbr in (pg - 1, pg + 1):
            if nbr not in seen_fill:
                seen_fill.add(nbr)
                fill_pages.append(nbr)
    for pg in fill_pages:
        for cid in page_chunks.get(pg, ()):
            if cid in selected:
                continue
            selected.append(cid)
            if len(selected) >= GRAPH_MAX_CHUNKS + 2:
                break
        if len(selected) >= GRAPH_MAX_CHUNKS + 2:
            break
    for cid in selected:
        text = chunks[cid]["text"].strip()
        if len(text) > GRAPH_CHUNK_CHARS:
            text = text[:GRAPH_CHUNK_CHARS] + " ..."
        add_line(f"[Source chunk | page {chunks[cid]['page']}] {text}")

    # 4) Multi-hop path chains, scored by matched-endpoint count
    matched_set = set(matched)
    path_lines = []
    for chain in paths:
        parts, st_parts = [], []
        ok = True
        for a, b in zip(chain, chain[1:]):
            if not G.has_edge(a, b):
                ok = False
                break
            rels = list(G.get_edge_data(a, b).values())
            rel = rels[0].get("relation", "RELATED_TO")
            parts.append(f"{a} -[{rel}]-> {b}")
            st = (rels[0].get("source_text") or "").strip()
            if st:
                st_parts.append(f"(page {rels[0].get('page')}): {st}")
        if not ok:
            continue
        line = " ".join(parts)
        matched_ends = sum(1 for nd in chain if nd in matched_set)
        text = line.lower()
        overlap = sum(1 for t in q_tokens if t in text)
        path_lines.append((line, st_parts,
                           matched_ends * 3 + (2 if st_parts else 0) + overlap))
    path_lines.sort(key=lambda t: (-t[2], t[0].lower()))
    for line, st_parts, _sc in path_lines[:GRAPH_MAX_PATHS]:
        add_line("[Path] " + line)
        for sp in st_parts:
            add_line("   " + sp)

    # 5) Single triples (deduped, prefer those carrying source text)
    seen_t = set()
    triple_lines = []
    for src, rel, tgt, st, pg in edges:
        key = (src, rel, tgt)
        if key in seen_t:
            continue
        seen_t.add(key)
        line = f"{src} -[{rel}]-> {tgt}"
        if st:
            line += f" (page {pg}): {st}"
        text = line.lower()
        overlap = sum(1 for t in q_tokens if t in text)
        triple_lines.append((line, (2 if st else 0) + overlap))
    triple_lines.sort(key=lambda t: (-t[1], t[0].lower()))
    for line, _sc in triple_lines[:GRAPH_MAX_TRIPLES]:
        add_line(line)

    total = 0
    final = []
    for line in context:
        total += len(line)
        if total > GRAPH_MAX_CHARS:
            break
        final.append(line)
    return final, list(matched), [t[0] for t in triple_lines]
# ---------------------------------------------------------------------------
# Run both systems on all questions
# ---------------------------------------------------------------------------
def run_question(llm, store, G, pages, q):
    qid, question, gt = q["id"], q["question"], q["ground_truth"]
    out = {"id": qid, "category": q["category"], "question": question,
           "ground_truth": gt}

    # ---- Vector RAG ----
    t0 = time.time()
    try:
        hits = vector_retrieve(store, question)
        vec_context = "\n\n".join(
            f"--- [Page {pg}] ---\n{text}" for pg, text, _score in hits
        )
        prompt = QA_PROMPT_TEMPLATE.format(context=vec_context, question=question)
        vec_answer = invoke_with_retry(llm, prompt)
        time.sleep(6)
        out["vector"] = {
            "answer": vec_answer,
            "retrieved_pages": [pg for pg, _t, _s in hits],
            "retrieved_chunks": [text[:300] for _pg, text, _s in hits],
            "scores": [s for _pg, _t, s in hits],
            "latency_s": round(time.time() - t0, 2),
        }
    except Exception as e:
        out["vector"] = {"answer": "", "error": str(e)[:300],
                         "retrieved_pages": [], "latency_s": round(time.time() - t0, 2)}

    # ---- Graph RAG ----
    t0 = time.time()
    try:
        g_context, ents, rels = graph_retrieve(G, pages, question)
        graph_context = "\n".join(g_context)
        prompt = QA_PROMPT_TEMPLATE.format(context=graph_context, question=question)
        g_answer = invoke_with_retry(llm, prompt)
        time.sleep(6)
        out["graph"] = {
            "answer": g_answer,
            "retrieved_entities": ents,
            "retrieved_relationships": rels,
            "context_characters": sum(len(c) for c in g_context),
            "latency_s": round(time.time() - t0, 2),
        }
    except Exception as e:
        out["graph"] = {"answer": "", "error": str(e)[:300],
                        "retrieved_entities": [], "latency_s": round(time.time() - t0, 2)}
    return out


JUDGE_PROMPT = """You are grading two RAG systems' answers to a question about the ISO 20022 Payments Guide.

Question: {question}

Reference answer (ground truth): {reference}

Answer A (Vector RAG): {vec_answer}

Answer B (Graph RAG): {graph_answer}

For EACH answer, decide: "correct" (fully answers, all key facts present), "partial" (some correct facts but missing/extra-wrong details), or "wrong" (does not answer or is incorrect). Answers like "I don't know" or "cannot be determined" are "wrong".

Return ONLY a raw JSON object with this exact shape — no markdown, no prose, no reasoning before or after:
{{"vector": "correct|partial|wrong", "vector_reason": "one short line", "graph": "correct|partial|wrong", "graph_reason": "one short line"}}"""


def judge_answers(llm, q):
    vec = q.get("vector", {}).get("answer", "")
    gra = q.get("graph", {}).get("answer", "")
    prompt = JUDGE_PROMPT.format(
        question=q["question"],
        reference=q["ground_truth"],
        vec_answer=vec or "(no answer)",
        graph_answer=gra or "(no answer)",
    )
    raw = invoke_with_retry(llm, prompt)
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        verdict = json.loads(raw[start:end + 1])
        verdict["raw"] = raw
    except Exception:
        verdict = {"vector": "unknown", "graph": "unknown",
                   "vector_reason": "judge parse failed", "graph_reason": "judge parse failed",
                   "raw": raw}
    return verdict

# ---------------------------------------------------------------------------
# Metrics + report
# ---------------------------------------------------------------------------
def compute_system_metrics(results, key):
    answers = [r[key].get("answer", "") for r in results]
    truths = [r["ground_truth"] for r in results]
    contexts = [r[key].get("retrieved_chunks") or r[key].get("retrieved_relationships") or [] for r in results]
    cats = [r["category"] for r in results]
    return compute_all_metrics(answers, truths, contexts, cats)


def judge_score(verdict):
    return {"correct": 1.0, "partial": 0.5, "wrong": 0.0, "unknown": 0.0}[verdict]


def build_report(results, verdicts, vec_metrics, graph_metrics, run_seconds):
    lines = []
    lines.append("# Vector RAG vs Graph RAG — ISO 20022 Payments Guide")
    lines.append("")
    lines.append(f"- LLM (both systems): **{ANSWER_MODEL}** via {ANSWER_PROVIDER} (temperature 0)")
    lines.append(f"- Embeddings: **{EMBEDDING_MODEL}**, chunks {CHUNK_SIZE}/{CHUNK_OVERLAP}, top-{TOP_K}")
    lines.append(f"- Graph: {results[0].get('_graph_nodes', 0)} nodes "
                 f"/ {results[0].get('_graph_edges', 0)} edges from merged_knowledge.json "
                 f"(max depth {GRAPH_MAX_DEPTH})")
    lines.append(f"- Total wall time: {run_seconds:.1f}s")
    lines.append("")
    lines.append("## Judge verdicts (LLM-as-judge, per question)")
    lines.append("")
    vid = {v.get("question_id"): v for v in verdicts}
    lines.append("| Q | Difficulty | Vector RAG | Graph RAG |")
    lines.append("|---|------------|------------|-----------|")
    for r in results:
        v = vid.get(r["id"], {})
        lines.append(f"| {r['id']} | {r['category']} | {v.get('vector', '?')} | {v.get('graph', '?')} |")
    lines.append("")
    lines.append("## Aggregate judge scores (correct=1, partial=0.5, wrong=0)")
    lines.append("")
    vec_total = sum(judge_score(v["vector"]) for v in verdicts) / len(verdicts)
    graph_total = sum(judge_score(v["graph"]) for v in verdicts) / len(verdicts)
    lines.append(f"- Vector RAG: **{vec_total:.2f}**")
    lines.append(f"- Graph RAG: **{graph_total:.2f}**")
    lines.append("")
    lines.append("## Lexical metrics (metrics_v2, per system)")
    lines.append("")
    lines.append("| Metric | Vector RAG | Graph RAG |")
    lines.append("|--------|-----------|-----------|")
    for m in ("f1_score", "answer_accuracy", "context_recall", "faithfulness", "hallucination_rate"):
        lines.append(f"| {m} | {vec_metrics['aggregate'].get(m, 0):.3f} | {graph_metrics['aggregate'].get(m, 0):.3f} |")
    lines.append("")
    lines.append("## Per-question answers")
    lines.append("")
    for r in results:
        v = vid.get(r["id"], {})
        lines.append(f"### Q{r['id']} [{r['category']}] — {v.get('vector', '?')} vs {v.get('graph', '?')}")
        lines.append("")
        lines.append(f"**Question:** {r['question']}")
        lines.append("")
        lines.append(f"**Reference:** {r['ground_truth']}")
        lines.append("")
        lines.append(f"**Vector RAG** ({v.get('vector_reason', '')}):")
        lines.append("")
        lines.append(f"> {r['vector'].get('answer') or '(no answer)'}")
        lines.append("")
        lines.append(f"**Graph RAG** ({v.get('graph_reason', '')}):")
        lines.append("")
        lines.append(f"> {r['graph'].get('answer') or '(no answer)'}")
        lines.append("")
        vpages = r['vector'].get('retrieved_pages', [])
        gents = r['graph'].get('retrieved_entities', [])
        lines.append(f"*Vector retrieved pages:* {vpages}  |  *Graph matched entities:* {gents}")
        lines.append("")
    return "\n".join(lines)


def main():
    logger.info("=== Vector RAG vs Graph RAG benchmark (10 questions) ===")
    pages = load_pages()
    entities, relationships = load_graph_data()
    questions = load_questions()
    logger.info("Loaded %d pages, %d entities, %d relationships, %d questions",
                len(pages), len(entities), len(relationships), len(questions))

    llm = create_llm()
    store = build_vector_store(pages)
    G = build_graph(entities, relationships)
    build_chunk_index(entities)

    results = []
    verdicts = []
    done_ids = set()
    progress_path = DATA / "benchmark_progress.json"
    if progress_path.exists():
        try:
            with io.open(progress_path, encoding="utf-8") as f:
                prog = json.load(f)
            for r in prog.get("results", []):
                results.append(r)
                done_ids.add(r["id"])
            verdicts = list(prog.get("verdicts", []))
            logger.info("Resuming: %d questions completed, %d verdicts", len(done_ids), len(verdicts))
        except Exception:
            results = []
    for q in questions:
        if q["id"] in done_ids:
            continue
        logger.info("Q%d [%s]: %s", q["id"], q["category"], safe_text(q["question"], 80))
        r = run_question(llm, store, G, pages, q)
        r["_graph_nodes"] = G.number_of_nodes()
        r["_graph_edges"] = G.number_of_edges()
        results.append(r)
        logger.info("  vector: %s", safe_text(r["vector"].get("answer", ""), 110))
        logger.info("  graph : %s", safe_text(r["graph"].get("answer", ""), 110))
        with io.open(DATA / "benchmark_progress.json", "w", encoding="utf-8") as f:
            json.dump({"results": results, "verdicts": verdicts}, f, ensure_ascii=False, indent=2)

    verdicts = []
    judged_ids = set()
    if progress_path.exists():
        try:
            with io.open(progress_path, encoding="utf-8") as f:
                prog = json.load(f)
            for v in prog.get("verdicts", []):
                verdicts.append(v)
            judged_ids = {v.get("question_id") for v in verdicts}
        except Exception:
            verdicts = []
    for r in results:
        if r["id"] in judged_ids:
            continue
        v = judge_answers(llm, r)
        v["question_id"] = r["id"]
        time.sleep(6)
        verdicts.append(v)
        logger.info("  Q%d judge: vector=%s graph=%s", r["id"], v["vector"], v["graph"])
        with io.open(progress_path, "w", encoding="utf-8") as f:
            json.dump({"results": results, "verdicts": verdicts}, f, ensure_ascii=False, indent=2)

    vec_metrics = compute_system_metrics(results, "vector")
    graph_metrics = compute_system_metrics(results, "graph")

    payload = {
        "config": {"provider": ANSWER_PROVIDER, "model": ANSWER_MODEL,
                   "embedding": EMBEDDING_MODEL, "top_k": TOP_K,
                   "graph_depth": GRAPH_MAX_DEPTH},
        "results": results,
        "verdicts": verdicts,
        "metrics": {"vector_rag": vec_metrics, "graph_rag": graph_metrics},
    }
    with io.open(DATA / "benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info("Saved data/benchmark_results.json")

    report = build_report(results, verdicts, vec_metrics, graph_metrics, 0.0)
    with io.open(DATA / "benchmark_comparison.md", "w", encoding="utf-8") as f:
        f.write(report)
    logger.info("Saved data/benchmark_comparison.md")

    # Terminal summary
    vid = {v.get("question_id"): v for v in verdicts}
    print("\n=== JUDGE SUMMARY ===")
    print(f"{'Q':>2} {'diff':<6} {'vector':<8} {'graph':<8}")
    for r in results:
        v = vid.get(r["id"], {})
        print(f"{r['id']:>2} {r['category']:<6} {v.get('vector', '?'):<8} {v.get('graph', '?'):<8}")
        vec_total = sum(judge_score(v["vector"]) for v in verdicts) / len(verdicts)
    graph_total = sum(judge_score(v["graph"]) for v in verdicts) / len(verdicts)
    print(f"average: vector={vec_total:.2f} graph={graph_total:.2f}")
    for m in ("f1_score", "answer_accuracy", "context_recall", "faithfulness"):
        print(f"  {m}: vector={vec_metrics['aggregate'].get(m, 0):.3f} graph={graph_metrics['aggregate'].get(m, 0):.3f}")


if __name__ == "__main__":
    main()
