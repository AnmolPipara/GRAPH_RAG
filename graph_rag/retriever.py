"""
retriever.py — Enhanced GraphRAG Retriever.

Builds a RAG pipeline over the Neo4j knowledge graph using:
1. Cypher query generation for relationship traversal
2. Full-text entity search
3. Configurable LLM providers for both generation and QA

This is the query-time companion to the ingestion pipeline.
"""

import json
import re
import sys
import time
import logging
from collections import Counter
from pathlib import Path
from typing import Dict, Any, List, Optional

from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate

from config.settings import settings

logger = logging.getLogger(__name__)


class GraphRAGRetriever:
    """Retrieves answers from the Knowledge Graph using LLM-generated Cypher."""

    # ── Candidate generation (retrieval ablation: candidate selection) ──
    # Configurable knobs for the candidate-generation stage ONLY. These
    # replace two hard-coded lossy heuristics that dropped correctly-matched
    # evidence before chunk ranking could see it:
    #   * OLD: only keywords[:2] used for entity matching.
    #   * OLD: MATCH ... LIMIT 6 let arbitrary DB row order decide which
    #          matched entities' source_chunks were collected.
    # Tuned via offline sweep (experiments/candidate_gen_diagnostic.py):
    # (8,30) achieved the same recall gains but let broad lowercase keywords
    # match ~250 entities, exploding candidate sets to near-full-corpus width
    # (mean 25/35 chunks), which would confound any benchmark run. (2,12)
    # keeps ALL the recall gains (10/12 reachable, 9/12 attached, 9/12 pages)
    # while bounding mean candidate size to 14.1/35 — the top-2 ranked
    # keywords are the most discriminative, and 12 entities with deterministic
    # ranking is more than enough to keep every evidence carrier.
    _KEYWORD_CAP = 2   # highest-informativeness keywords used to match entities
    _ENTITY_CAP = 12   # max matched entities kept (after deterministic ranking)

    def __init__(self):
        try:
            self.graph = Neo4jGraph(
                url=settings.neo4j_uri,
                username=settings.neo4j_username,
                password=settings.neo4j_password,
                database="410b7631",
            )
            self.graph.refresh_schema()
            logger.info("Connected to Neo4j and refreshed schema")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Neo4j graph: {e}")

        # Deterministically rebuilt source chunks ({chunk_id: {text, pages}}),
        # used to enrich retrieved entities with the FULL chunk they were
        # extracted from. Bare triples ("EntityA -[REL]-> EntityB") give the
        # QA LLM too little evidence; attaching the real chunk text (like
        # VectorRAG does) is what makes GraphRAG's context useful for
        # fact-lookup questions. The rebuild is pure-offline and
        # byte-deterministic (verified: 35/35 chunk char counts match
        # data/chunks.json), so provenance stays reproducible.
        self._chunk_store = self._load_chunk_text()
        logger.info("Rebuilt %d source chunks for retrieval enrichment", len(self._chunk_store))

        logger.info(
            f"Initializing Cypher LLM: {settings.CYPHER_MODEL} "
            f"via {settings.CYPHER_PROVIDER}"
        )
        self.cypher_llm = self._create_llm(
            provider=settings.CYPHER_PROVIDER,
            model=settings.CYPHER_MODEL,
            max_tokens=settings.max_tokens_cypher,
        )

        logger.info(
            f"Initializing QA LLM: {settings.ANSWER_MODEL} "
            f"via {settings.ANSWER_PROVIDER}"
        )
        self.qa_llm = self._create_llm(
            provider=settings.ANSWER_PROVIDER,
            model=settings.ANSWER_MODEL,
            max_tokens=settings.max_tokens_answer,
        )

        # Build the Cypher generation prompt
        self.cypher_prompt = self._build_cypher_prompt()

        # Create the QA chain
        self.chain = GraphCypherQAChain.from_llm(
            graph=self.graph,
            cypher_llm=self.cypher_llm,
            qa_llm=self.qa_llm,
            cypher_prompt=self.cypher_prompt,
            verbose=False,
            allow_dangerous_requests=True,
            return_intermediate_steps=True,
            validate_cypher=False,
            top_k=10,
        )
        # NOTE: validate_cypher=False — the built-in validation step sends the
        # FULL graph schema (graph.get_schema(), ~17K tokens) to a second LLM
        # call per question, which overflows Groq free-tier TPM (12K) and
        # roughly doubles token burn. The compact-schema prompt already
        # constrains the model; a 70B model writes valid Cypher without it.

    def _create_llm(self, provider: str, model: str, max_tokens: int = None) -> ChatOpenAI:
        """Create a LangChain LLM instance for the specified provider.

        The HuggingFace router serves reasoning models whose responses include
        a `reasoning` field; ChatOpenAI can't parse those, so we use the
        reasoning-aware HFReasoningChatModel instead.
        """
        if provider.lower() == "huggingface":
            from utils.hf_client import get_hf_model

            logger.info(f"Using HFReasoningChatModel: {model}")
            return get_hf_model(model=model, api_key=settings.huggingface_api_key)

        api_key = settings.get_api_key_for_provider(provider)
        base_url = settings.get_base_url_for_provider(provider)

        kwargs = dict(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.0,
        )
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        # Groq sits behind Cloudflare which blocks python urllib/httpx default
        # user-agents (HTTP 403 error 1010). A browser-like UA keeps calls flowing.
        if provider.lower() == "groq":
            kwargs["default_headers"] = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            }
        return ChatOpenAI(**kwargs)

    def _build_compact_schema(self) -> str:
        """Build a compact schema string (labels + relationship types only).

        The full Neo4j schema lists every property of ~70 node types and
        88 relationship types, which produces a ~17K-token Cypher prompt
        and blows past free-tier LLM token limits (e.g. Groq 12K TPM).
        The Cypher model only needs the entity types, relationship types,
        and the key filterable properties to write correct queries.
        """
        ss = self.graph.structured_schema
        node_props = ss.get("node_props", {})
        rel_props = ss.get("rel_props", {})
        rels = ss.get("relationships", [])

        lines = [
            "Node labels: " + ", ".join(sorted(node_props.keys())),
            "Relationship types: " + ", ".join(sorted(rel_props.keys())),
            "Key entity properties (for WHERE filters): name, canonical_name, description, aliases, type, confidence",
        ]

        # Most frequent (start)-[:REL]->(end) triples give the model valid traversal paths
        if rels:
            triple_counter = Counter(
                (r.get("start"), r.get("type"), r.get("end")) for r in rels
            )
            top_triples = triple_counter.most_common(40)
            lines.append("Valid relationship paths (top 40 by count):")
            for (start, rtype, end), cnt in top_triples:
                lines.append(f"  ({start})-[:{rtype}]->({end})  (x{cnt})")

        return "\n".join(lines)

    def _build_cypher_prompt(self) -> PromptTemplate:
        """Build the prompt template for Cypher query generation.

        NOTE: The full graph schema is NOT passed via a {schema} variable —
        a compact schema string is embedded directly into the template.
        GraphCypherQAChain fills {schema} from graph.get_schema(), which
        for this graph is ~17K tokens and exceeds free-tier LLM limits.
        """
        compact_schema = self._build_compact_schema()
        template = f"""Task: Generate Cypher statement to query a graph database.

STRICT RULES:
1. Use ONLY the relationship types listed in the Schema below. NEVER invent relationship types that are not listed.
2. Filter by entity name in the WHERE clause using a case-insensitive CONTAINS search:
   `WHERE toLower(n.canonical_name) CONTAINS toLower("keyword") OR toLower(n.name) CONTAINS toLower("keyword") OR toLower(n.description) CONTAINS toLower("keyword")`
3. Also check the 'aliases' list property when filtering entities:
   `OR any(alias IN n.aliases WHERE toLower(alias) CONTAINS toLower("keyword"))`
4. NEVER use `shortestPath` or unbounded variable length paths `-[*]-` without a limit (e.g. use `-[*1..3]-`).
5. If you reference the relationship in RETURN (e.g. `type(r)`), you MUST bind it: `MATCH (n1)-[r]->(n2)`.
6. Prefer CONTAINS matching over exact property equality (e.g. matching on the `name` property directly). Exact matches often miss aliased entities.
7. If a directed relationship pattern returns nothing, try the reverse direction `MATCH (n2)-[r]->(n1)`.
8. When unsure of the relationship type between two entities, match without a type filter: `MATCH (n1)-[r]->(n2)`.
9. ALWAYS return node properties directly (e.g., `n1.name, n1.description`).
10. For multi-hop questions, return the paths.
11. ALWAYS end with `LIMIT 20`.

Schema:
{compact_schema}

TEMPLATE (Follow this pattern for basic entity search):
MATCH (n1:Entity)-[r]->(n2:Entity)
WHERE toLower(n1.name) CONTAINS toLower("keyword") 
   OR any(a IN n1.aliases WHERE toLower(a) CONTAINS toLower("keyword"))
RETURN n1.name, n1.description, type(r), n2.name, n2.description
LIMIT 20

Question:
{{question}}

Return ONLY the Cypher statement. No explanations, no markdown formatting.
"""
        return PromptTemplate(
            input_variables=["question"],
            template=template
        )

    # ── Generic fallback retrieval ─────────────────────────────────────
    # When the LLM-generated Cypher returns no context (e.g. it constrains a
    # relationship type with no edges for the matched entity, like
    # ``-[:HAS_ADDRESS]->`` from an organization that has no address edge), the
    # QA LLM is asked to answer from an EMPTY context and replies "I don't know".
    # These label-agnostic keyword helpers recover real graph context so the QA
    # still has something to answer from.
    _FALLBACK_STOPWORDS = frozenset({
        "what", "who", "how", "when", "where", "which", "why", "is", "are",
        "was", "were", "does", "do", "did", "the", "a", "an", "of", "for",
        "in", "on", "at", "by", "to", "with", "and", "or", "from", "it",
        "its", "this", "that", "have", "has", "had", "be", "been", "can",
        "could", "would", "should", "please", "provide", "many", "much",
        "pages", "page", "version", "year", "number", "what is",
    })

    # Question-framing words dropped when ranking entity keywords (candidate
    # generation only). Kept separate from _FALLBACK_STOPWORDS so the fallback
    # neighbor-match path is untouched by this experiment.
    _KEYWORD_STOPWORDS = _FALLBACK_STOPWORDS | frozenset({
        "between", "difference", "using", "used", "use", "via", "within",
        "during", "before", "after", "upon", "under", "over", "into", "onto",
        "than", "then", "these", "those", "their", "there", "they", "them",
        "such", "each", "both", "other", "many", "much", "most", "more",
        "some", "any", "all", "one", "two", "three", "four", "five", "six",
        "seven", "eight", "nine", "ten", "first", "second", "third", "etc",
    })

    def _load_chunk_text(self) -> Dict[int, Dict[str, Any]]:
        """Deterministically rebuild {chunk_id: {text, page_start, page_end}}.

        data/chunks.json only persists a 203-char preview, so the full chunk
        text is rebuilt from data/extracted_text.json with the same
        section-aware chunker used at ingestion. Verified: 35/35 char counts
        match chunks.json, so the rebuilt text is byte-identical to what the
        extractor consumed.
        """
        try:
            from graph_rag.chunker import chunk_by_sections

            p = Path(__file__).resolve().parent.parent / "data" / "extracted_text.json"
            with open(p, encoding="utf-8") as f:
                pages = json.load(f)
            parts = []
            for r in pages:
                if r.get("page") is not None and r.get("text"):
                    parts.append(f"[PAGE {r['page']}]\n{r['text']}")
            chunks = chunk_by_sections("\n\n".join(parts))
            return {
                c.chunk_id: {
                    "text": c.text,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                }
                for c in chunks
            }
        except Exception as e:
            logger.warning("[GraphRAG] Could not rebuild chunk store: %s", e)
            return {}

    def _rank_keywords(self, question: str) -> List[str]:
        """Extract and rank candidate entity keywords by informativeness.

        Candidate generation only. Collects ALL meaningful keyword candidates
        (quoted phrases, capitalized multi-token runs, single capitalized
        tokens, and lowercase content words), removes stop words, then ranks
        by informativeness so the highest-scoring keywords drive entity
        matching — NOT the first two tokens in the question (the old
        ``keywords[:2]`` heuristic silently dropped informative lowercase
        terms like ``customer``/``bank``/``payee``, leaving evidence-bearing
        entities unreachable).

        Informativeness score = phrase-type specificity (quoted 4 >
        capitalized run 3 > single capitalized 2 > lowercase 1), plus phrase
        length, plus chunk-store rarity (a keyword appearing in fewer chunks
        is more discriminating). Deterministic: no LLM, no embeddings.
        """
        candidates = []
        # Quoted phrases first (most specific)
        for m in re.finditer(r'"([^"]+)"|\'([^\']+)\'', question):
            phrase = (m.group(1) or m.group(2) or "").strip()
            if phrase:
                candidates.append((phrase, 4))
        # Capitalized multi-token runs (e.g. "Finance Finland", "ISO 20022")
        for m in re.finditer(
            r"\b(?:[A-Z][A-Za-z0-9.\-]*|\d+)(?:\s+(?:[A-Z][A-Za-z0-9.\-]*|\d+)){1,}\b",
            question,
        ):
            phrase = m.group(0).strip()
            if phrase:
                candidates.append((phrase, 3))
        # Single capitalized tokens
        for m in re.finditer(r"\b[A-Z][A-Za-z0-9.\-]{2,}\b", question):
            word = m.group(0)
            if word.lower() not in self._KEYWORD_STOPWORDS:
                candidates.append((word, 2))
        # Lowercase content words (e.g. "customer", "bank", "payee")
        for m in re.finditer(r"\b[a-z][a-z0-9.\-]{2,}\b", question):
            word = m.group(0)
            if word.lower() not in self._KEYWORD_STOPWORDS:
                candidates.append((word, 1))

        # Dedupe keeping the highest-specificity spelling, strip punctuation
        seen = {}
        for c, prio in candidates:
            c = c.strip().strip("?. ,;:!").strip()
            cl = c.lower()
            if not c or cl in self._KEYWORD_STOPWORDS:
                continue
            if cl not in seen or prio > seen[cl][1]:
                seen[cl] = (c, prio)

        n_chunks = max(1, len(self._chunk_store))
        scored = []
        for cl, (c, prio) in seen.items():
            doc_freq = sum(
                1 for meta in self._chunk_store.values() if cl in meta["text"].lower()
            )
            rarity = (n_chunks - doc_freq) / n_chunks
            scored.append((c, prio * 100 + min(len(c), 12) + rarity * 10))
        scored.sort(key=lambda x: (-x[1], x[0].lower()))
        return [c for c, _ in scored[: self._KEYWORD_CAP]]

    def _fetch_chunk_context(self, question: str, max_chunks: int = 3,
                             max_chars: int = 1200) -> List[str]:
        """Resolve the question's matched entities to their linked source
        chunks as ``[Source (chunk N, pages X-Y)] ...`` lines.

        Chunk linkage: entity search -> matched nodes -> their source_chunks
        -> the full chunk text, ranked by lexical relevance to the question.
        This replaces the old page-level evidence (first 2 pages per entity,
        500 chars each) with the complete chunk(s) the evidence actually
        lives in, so the QA LLM sees the full supporting paragraph instead of
        a truncated page head.

        The graph stays the sole evidence source: chunks are only ever taken
        from ``source_chunks`` of entities already matched via Neo4j — never
        by searching the whole document.
        """
        keywords = self._rank_keywords(question)
        if not keywords or not self._chunk_store:
            return []
        conds = []
        for kw in keywords:
            kwl = kw.lower().replace("'", "\\'")
            conds.append(
                f"(toLower(n.name) CONTAINS '{kwl}' "
                f"OR toLower(n.canonical_name) CONTAINS '{kwl}' "
                f"OR any(a IN coalesce(n.aliases, []) WHERE toLower(a) CONTAINS '{kwl}') "
                f"OR toLower(n.description) CONTAINS '{kwl}')"
            )
        try:
            # NOTE: no LIMIT — every matched entity is returned and ranked
            # deterministically below, so arbitrary DB row order can no
            # longer decide which entities' source_chunks are collected
            # (the old ``LIMIT 6`` dropped correctly-matched evidence
            # carriers before their chunks could enter the candidate set).
            rows = self.graph.query(
                f"MATCH (n) WHERE {' OR '.join(conds)} "
                "RETURN n.name AS name, n.canonical_name AS canonical_name, "
                "       n.aliases AS aliases, n.description AS description, "
                "       n.frequency AS frequency, n.source_chunks AS chunks"
            )
        except Exception as e:
            logger.error("[GraphRAG] Chunk-context query failed: %s", e)
            return []

        # Deterministic entity ranking before truncation: prefer entities
        # whose NAME/canonical/aliases hit the most ranked keywords, then
        # description hits, then frequency. Replaces the arbitrary ``LIMIT 6``
        # so the SAME set of matched entities always survives to the cap.
        scored = []
        kwl = [k.lower() for k in keywords]
        for row in rows:
            name = row.get("name") or ""
            canonical = row.get("canonical_name") or ""
            aliases = row.get("aliases") or []
            desc = row.get("description") or ""
            try:
                freq = int(row.get("frequency") or 0)
            except (TypeError, ValueError):
                freq = 0
            identity = (name + " " + canonical + " " + " ".join(aliases)).lower()
            name_hits = sum(1 for k in kwl if k in identity)
            desc_hits = sum(1 for k in kwl if k in desc.lower())
            scored.append((name, row.get("chunks") or [], name_hits, desc_hits, freq, name.lower()))
        scored.sort(key=lambda t: (-t[2], -t[3], -t[4], t[5]))
        kept = scored[: self._ENTITY_CAP]

        # Collect every chunk linked to the surviving entities (graph-grounded).
        chunk_ids = set()
        for _name, chunks, _nh, _dh, _fr, _nl in kept:
            for c in chunks:
                try:
                    chunk_ids.add(int(c))
                except (TypeError, ValueError):
                    continue
        if not chunk_ids:
            return []

        ranked = self._rank_chunks(question, keywords, chunk_ids)
        out, seen = [], set()
        for cid, _score in ranked:
            if cid in seen:
                continue
            seen.add(cid)
            meta = self._chunk_store.get(cid)
            if not meta:
                continue
            text = meta["text"].strip()
            if not text:
                continue
            if len(text) > max_chars:
                text = text[:max_chars] + "..."
            out.append(
                f"[Source (chunk {cid}, pages {meta['page_start']}-{meta['page_end']})] {text}"
            )
            if len(out) >= max_chunks:
                break
        return out

    def _rank_chunks(self, question: str, keywords: List[str],
                     chunk_ids: set) -> List[tuple]:
        """Rank candidate chunks by lexical relevance to the question.

        Score = token overlap between the question and the chunk text, plus a
        keyword-containment bonus (2x per extracted entity keyword present).
        Deterministic and free (no embeddings, no LLM), so the ranked order
        is reproducible on every run.
        """
        q_tokens = set(re.sub(r"[^a-z0-9 ]", " ", question.lower()).split())
        q_tokens = {t for t in q_tokens if len(t) > 2}
        scored = []
        for cid in chunk_ids:
            meta = self._chunk_store.get(cid)
            if not meta:
                continue
            text = meta["text"].lower()
            c_tokens = set(re.sub(r"[^a-z0-9 ]", " ", text).split())
            overlap = len(q_tokens & c_tokens) if q_tokens else 0
            kw_hits = sum(1 for kw in keywords if kw.lower() in text)
            scored.append((cid, overlap + 2 * kw_hits))
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored

    def _extract_entity_keywords(self, question: str) -> List[str]:
        """Extract candidate entity keywords from a natural-language question.

        Prefers quoted phrases and runs of capitalized/uppercase tokens
        (e.g. "Finance Finland", "ISO 20022 Payments Guide"), which in this
        corpus are almost always entity names.
        """
        candidates = []
        # Quoted phrases first
        for m in re.finditer(r'"([^"]+)"|\'([^\']+)\'', question):
            phrase = (m.group(1) or m.group(2) or "").strip()
            if phrase:
                candidates.append(phrase)
        # Capitalized multi-token runs (e.g. "Finance Finland", "ISO 20022")
        for m in re.finditer(
            r"\b(?:[A-Z][A-Za-z0-9.\-]*|\d+)(?:\s+(?:[A-Z][A-Za-z0-9.\-]*|\d+)){1,}\b",
            question,
        ):
            phrase = m.group(0).strip()
            if phrase:
                candidates.append(phrase)
        # Fall back to single capitalized tokens
        if not candidates:
            for m in re.finditer(r"\b[A-Z][A-Za-z0-9.\-]{2,}\b", question):
                word = m.group(0)
                if word.lower() not in self._FALLBACK_STOPWORDS:
                    candidates.append(word)
        # Last resort: lowercase tokens (e.g. "the guide", "group header" in
        # lowercase) so questions without a capitalized entity still retrieve.
        if not candidates:
            for m in re.finditer(r"\b[a-z][a-z0-9.\-]{2,}\b", question):
                word = m.group(0)
                if word.lower() not in self._FALLBACK_STOPWORDS:
                    candidates.append(word)
        # Dedupe preserving order, drop stopwords and trailing punctuation
        seen, out = set(), []
        for c in candidates:
            c = c.strip().strip("?. ,;:!").strip()
            cl = c.lower()
            if not c or cl in seen or cl in self._FALLBACK_STOPWORDS:
                continue
            seen.add(cl)
            out.append(c)
        return out[:3]

    def _fallback_retrieve(self, question: str) -> List[str]:
        """Label-agnostic neighbor-match retrieval used when the LLM-generated
        Cypher returns no context.

        Runs a ``CONTAINS`` match on name/canonical_name/aliases/description and
        returns the matched entity plus its 1-hop neighborhood, so the QA LLM gets
        real graph context instead of an empty prompt. Returns a list of context
        strings (empty when nothing matched).
        """
        keywords = self._extract_entity_keywords(question)
        if not keywords:
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
        where = " OR ".join(conds)
        cypher = (
            f"MATCH (n) WHERE {where} "
            "OPTIONAL MATCH (n)-[r]->(m) "
            "RETURN n.name AS source, n.description AS source_desc, "
            "       type(r) AS rel, m.name AS target, m.description AS target_desc "
            "LIMIT 25"
        )
        try:
            rows = self.graph.query(cypher)
        except Exception as e:
            logger.error("[GraphRAG] Fallback query failed: %s", e)
            return []
        context = []
        for row in rows:
            src = row.get("source") or "?"
            rel = row.get("rel") or ""
            tgt = row.get("target") or "?"
            src_desc = row.get("source_desc") or ""
            tgt_desc = row.get("target_desc") or ""
            # Skip pure-noise rows (no relationship, no target, no descriptions).
            # Rows with a real node on either side are kept — e.g. an address
            # node with a description but no edges is exactly the context the
            # QA needs for "Where is Finance Finland located?".
            if not rel and tgt == "?" and not src_desc and not tgt_desc:
                continue
            line = f"{src} -[{rel}]-> {tgt}"
            if src_desc:
                line += f" | {src}: {src_desc}"
            if tgt_desc:
                line += f" | {tgt}: {tgt_desc}"
            context.append(line)
        return context

    def _try_fallback(self, question: str, stale_answer: str, reason: str,
                      backoff_time: float) -> Optional[Dict[str, Any]]:
        """Try generic neighbor-match retrieval + re-answer with the shared QA model.

        Shared by FALLBACK 1 (LLM Cypher returned empty context) and FALLBACK 2
        (LLM Cypher raised a Neo4j error). Returns a result dict with
        fallback_used=True, or None if the fallback also found no context.
        """
        fb_context = self._fallback_retrieve(question)
        if not fb_context:
            return None
        fb_context = self._append_sources(question, fb_context)
        answer = self._reanswer_from_context(question, fb_context, stale_answer)
        logger.info(
            "[GraphRAG] Fallback retrieval used after %s (%d context rows) for: %s",
            reason, len(fb_context), question[:60],
        )
        return {
            "answer": answer,
            "context": fb_context,
            "backoff_time_s": round(backoff_time, 3),
            "fallback_used": True,
        }

    def _append_sources(self, question: str, context: list) -> list:
        """Attach the matched entities' linked source chunks to a context list.

        Returns the context unchanged when no chunks resolve, so callers can
        detect enrichment by comparing lengths.
        """
        src = self._fetch_chunk_context(question)
        if src:
            return list(context) + src
        return context

    def _reanswer_from_context(self, question: str, context: list, stale_answer: str) -> str:
        """Re-answer a question from retrieved context using the shared QA model.

        Used by the fallback path: the QA LLM (same model the vector phase uses,
        keeping the comparison fair) is asked to answer from the fallback
        context with the same rate-limit/transport backoff the chain gets.
        Returns the new answer, or the stale answer if re-answering fails.
        """
        try:
            from langchain_core.messages import HumanMessage

            context_text = "\n".join(context)
            prompt = (
                "You are an expert research assistant. Use the following pieces of "
                "retrieved context to answer the user's question.\n"
                "If you don't know the answer, just say that you don't know, don't "
                "try to make up an answer.\n\n"
                f"Context:\n{context_text}\n\n"
                f"Question: {question}\n\nAnswer:"
            )
            resp = None
            fb_last_error = None
            for fb_attempt in range(3):
                try:
                    resp = self.qa_llm.invoke([HumanMessage(content=prompt)])
                    break
                except Exception as fb_e:
                    fb_last_error = fb_e
                    fb_msg = str(fb_e).lower()
                    if any(k in fb_msg for k in
                           ["rate_limit", "429", "tpm", "too many requests", "throttl", "try again"]):
                        time.sleep(5 * (fb_attempt + 1))
                    elif any(k in fb_msg for k in
                             ["timed out", "timeout", "connection", "getaddrinfo", "urlopen",
                              "winerror", "10054", "11001", "eof", "ssl", "unreachable",
                              "reset", "read operation", "network"]):
                        time.sleep(5 * (fb_attempt + 1))
                    else:
                        break
            if resp is not None:
                new_answer = getattr(resp, "content", str(resp))
                if new_answer and new_answer.strip():
                    return new_answer
            elif fb_last_error is not None:
                logger.warning(
                    "[GraphRAG] Fallback re-answer failed (%s); keeping chain answer",
                    fb_last_error,
                )
        except Exception as e:
            logger.warning(
                "[GraphRAG] Fallback re-answer failed (%s); keeping chain answer", e
            )
        return stale_answer

    def query(self, question: str) -> Dict[str, Any]:
        """Execute a natural language query against the knowledge graph.

        Includes retry-with-backoff for LLM rate-limit errors (e.g. Groq
        free-tier TPM/RPM limits) so long benchmark runs self-pace.

        On failure returns {"answer": "", "context": [], "error": str} so
        callers can record errors distinctly from answers.
        """
        last_error = None
        backoff_time = 0.0
        for attempt in range(5):
            try:
                result = self.chain.invoke({"query": question})

                # Extract context from intermediate steps
                steps = result.get("intermediate_steps", [])
                context = []
                if len(steps) > 1 and isinstance(steps[1], dict) and "context" in steps[1]:
                    context_data = steps[1]["context"]
                    if isinstance(context_data, list):
                        context = [str(item) for item in context_data]
                    else:
                        context = [str(context_data)]

                chain_answer = result.get(
                    "result", "I couldn't find the answer in the knowledge graph."
                )
                # Enrich the LLM-Cypher triples with the original source
                # paragraphs so the QA answers from real document text
                # (chunk linkage), not just entity triples. The chain already
                # generated its answer from bare triples, so when source text
                # was attached we re-answer with the SAME QA model to make the
                # answer reflect the real text.
                if context:
                    enriched = self._append_sources(question, context)
                    if len(enriched) > len(context):
                        context = enriched
                        chain_answer = self._reanswer_from_context(
                            question, context, chain_answer
                        )
                    else:
                        context = enriched

                # FALLBACK 1: if the LLM-generated Cypher succeeded but returned
                # no context (e.g. it used a relationship type with no edges for
                # the matched entity), run a generic neighbor-match query so the
                # QA LLM gets real graph context, then re-answer with the SAME
                # QA model for a fair comparison.
                if not context:
                    stale = result.get(
                        "result", "I couldn't find the answer in the knowledge graph."
                    )
                    fb_res = self._try_fallback(question, stale, "empty context", backoff_time)
                    if fb_res is not None:
                        return fb_res

                return {
                    "answer": chain_answer,
                    "context": context,
                    "backoff_time_s": round(backoff_time, 3),
                    "fallback_used": False,
                }
            except Exception as e:
                last_error = e
                msg = str(e).lower()
                # Daily token caps (TPD) / quota exhaustion won't clear with a
                # short wait — fail fast instead of burning minutes per question.
                # NOTE: "billing" is deliberately NOT here: Groq appends the
                # sales pitch "Upgrade to Dev Tier today at
                # .../settings/billing" to EVERY 429 (including per-minute TPM
                # spikes that clear in seconds), so matching it would falsely
                # fail-fast on recoverable rate limits. TPD messages still match
                # via "per day"/"tpd"; HF 402 still matches via "credits"/"depleted".
                if any(k in msg for k in
                       ["per day", "tpd", "quota", "no credits",
                        "daily", "free tier", "credits", "depleted"]):
                    logger.error(f"[GraphRAG] Daily quota exhausted, failing fast: {str(e)[:150]}")
                    return {
                        "answer": "",
                        "context": [],
                        "backoff_time_s": round(backoff_time, 3),
                        "error": f"Quota exhausted: {str(e)}",
                        "fallback_used": False,
                    }
                if any(k in msg for k in
                       ["rate_limit", "429", "tpm", "too many requests", "throttl", "try again"]):
                    wait = 15 * (attempt + 1)
                    backoff_time += wait
                    logger.warning(
                        f"[GraphRAG] Rate limited (attempt {attempt + 1}/5). "
                        f"Retrying in {wait}s: {str(e)[:120]}"
                    )
                    time.sleep(wait)
                    continue
                if any(k in msg for k in
                       ["timed out", "timeout", "connection", "getaddrinfo", "urlopen",
                        "winerror", "10054", "11001", "eof", "ssl", "unreachable",
                        "reset", "read operation", "network"]):
                    # Transient transport failures (DNS resolution, connection
                    # reset, read timeout) usually clear in seconds — retry
                    # with backoff instead of failing the question.
                    wait = 10 * (attempt + 1)
                    backoff_time += wait
                    logger.warning(
                        f"[GraphRAG] Transport error (attempt {attempt + 1}/5). "
                        f"Retrying in {wait}s: {str(e)[:120]}"
                    )
                    time.sleep(wait)
                    continue
                # FALLBACK 2: the LLM-generated Cypher failed to EXECUTE (e.g.
                # syntax error like `Variable r not defined`, or an invented
                # label). The generic neighbor-match query still recovers real
                # context, so re-answer instead of failing the question.
                if any(k in msg for k in
                       ["neo.clienterror", "syntaxerror", "invalid input", "not defined"]):
                    stale = "I couldn't find the answer in the knowledge graph."
                    fb_res = self._try_fallback(question, stale, "Cypher error", backoff_time)
                    if fb_res is not None:
                        return fb_res
                logger.error(f"Error executing GraphRAG query: {e}")
                return {
                    "answer": "",
                    "context": [],
                    "backoff_time_s": round(backoff_time, 3),
                    "error": f"Error executing query: {str(e)}",
                    "fallback_used": False,
                }

        logger.error(f"GraphRAG query failed after retries: {last_error}")
        return {
            "answer": "",
            "context": [],
            "backoff_time_s": round(backoff_time, 3),
            "error": f"Error executing query (rate limited): {last_error}",
            "fallback_used": False,
        }


# ══════════════════════════════════════════════════════════════════════════════
# INTERACTIVE CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "=" * 60)
    print("GraphRAG Interactive Retriever")
    print("=" * 60)
    
    try:
        retriever = GraphRAGRetriever()
        print("\nInitialization complete. Type 'quit' to exit.")
        print("-" * 60)
    except Exception as e:
        print(f"\nFailed to initialize retriever: {e}")
        sys.exit(1)

    while True:
        try:
            question = input("\nQ: ").strip()
            if not question:
                continue

            if question.lower() in ["quit", "exit", "q"]:
                break

            print("\nGenerating Cypher and querying graph...\n")
            result = retriever.query(question)
            
            print(f"\nAnswer:\n{result['answer']}")
            
            if result['context']:
                print("\n[Context Used]")
                for i, ctx in enumerate(result['context'][:3]):  # Show up to 3 context items
                    preview = ctx[:200] + "..." if len(ctx) > 200 else ctx
                    print(f"  {i+1}. {preview}")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\nError: {e}")

    print("\nGoodbye!")


if __name__ == "__main__":
    main()
