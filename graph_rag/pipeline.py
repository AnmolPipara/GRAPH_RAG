"""
pipeline.py — Production-Quality Knowledge Graph Extraction Pipeline.

Orchestrates the full GraphRAG indexing pipeline:

    Step 1: PDF Extraction       → pdf_extractor.py
    Step 2: Text Cleaning        → pdf_extractor.py (integrated)
    Step 3: Semantic Chunking    → chunker.py
    Step 4: Knowledge Extraction → knowledge_extractor.py (per-chunk, frontier LLM)
    Step 5: Graph Refinement     → graph_refiner.py (global, frontier LLM)
    Step 6: Neo4j Ingestion      → neo4j_loader.py
    Step 7: Statistics & Validation

Each step saves intermediate results to data/ for debugging and reproducibility.

Usage:
    python -m graph_rag.pipeline
    python -m graph_rag.pipeline --pdf path/to/document.pdf
    python -m graph_rag.pipeline --no-llm-refine    # Skip LLM refinement (fast)
    python -m graph_rag.pipeline --no-images         # Skip image extraction
"""

import os
import sys
import json
import time
import argparse
import logging
from collections import Counter
from typing import Optional, Tuple, List

# Ensure project root is on sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from config.settings import settings
from graph_rag.pdf_extractor import extract_document, DocumentContent
from graph_rag.chunker import chunk_document, Chunk
from graph_rag.knowledge_extractor import (
    extract_from_chunk,
    extract_from_image,
    ExtractionResult,
)
from graph_rag.llm_client import get_extraction_client, get_vlm_client
from graph_rag.graph_refiner import refine_graph
from utils.neo4j_loader import Neo4jLoader

# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════


def save_json(data, filename: str):
    """Save data to a JSON file in the data/ directory."""
    os.makedirs("data", exist_ok=True)
    path = os.path.join("data", filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"Saved {filename}")
    except Exception as e:
        logger.error(f"Failed to save {filename}: {e}")


def generate_statistics(merged: ExtractionResult, all_extractions: List[ExtractionResult]) -> dict:
    """Generate and log extraction statistics including before/after deduplication."""
    entity_types = Counter(e.type for e in merged.entities)
    rel_types = Counter(r.relation for r in merged.relationships)

    raw_entities_count = sum(len(r.entities) for r in all_extractions)
    raw_relationships_count = sum(len(r.relationships) for r in all_extractions)

    entities_with_aliases = sum(1 for e in merged.entities if e.aliases)
    entities_with_desc = sum(1 for e in merged.entities if e.description)
    entities_with_attrs = sum(1 for e in merged.entities if e.attributes)
    implicit_rels = sum(1 for r in merged.relationships if r.implicit)

    # Calculate top connected entities
    degree_counter = Counter()
    for r in merged.relationships:
        degree_counter[r.source] += 1
        degree_counter[r.target] += 1
        
    top_entities = [
        {"id": entity_id, "degree": count} 
        for entity_id, count in degree_counter.most_common(5)
    ]

    stats = {
        "raw_entities": raw_entities_count,
        "deduped_entities": len(merged.entities),
        "raw_relationships": raw_relationships_count,
        "deduped_relationships": len(merged.relationships),
        "entities_by_type": dict(entity_types.most_common()),
        "relationships_by_type": dict(rel_types.most_common()),
        "entities_with_aliases": entities_with_aliases,
        "entities_with_descriptions": entities_with_desc,
        "entities_with_attributes": entities_with_attrs,
        "implicit_relationships": implicit_rels,
        "top_connected_entities": top_entities,
        "avg_entity_confidence": round(
            sum(e.confidence for e in merged.entities) / max(1, len(merged.entities)), 3
        ),
        "avg_relationship_confidence": round(
            sum(r.confidence for r in merged.relationships) / max(1, len(merged.relationships)), 3
        ),
    }

    logger.info("=" * 60)
    logger.info("EXTRACTION STATISTICS")
    logger.info("=" * 60)
    logger.info(f"  Raw Entities       : {stats['raw_entities']} -> {stats['deduped_entities']} deduped")
    logger.info(f"  Raw Relationships  : {stats['raw_relationships']} -> {stats['deduped_relationships']} deduped")
    logger.info(f"  With Aliases       : {stats['entities_with_aliases']}")
    logger.info(f"  With Descriptions  : {stats['entities_with_descriptions']}")
    logger.info(f"  With Attributes    : {stats['entities_with_attributes']}")
    logger.info(f"  Implicit Relations : {stats['implicit_relationships']}")
    logger.info(f"  Avg Entity Conf    : {stats['avg_entity_confidence']}")
    logger.info(f"  Avg Rel Confidence : {stats['avg_relationship_confidence']}")
    logger.info("  Entity Types:")
    for t, c in entity_types.most_common():
        logger.info(f"    {t:20s} : {c}")
    logger.info("  Relationship Types (top 15):")
    for t, c in rel_types.most_common(15):
        logger.info(f"    {t:25s} : {c}")
    logger.info("  Top Connected Entities:")
    for te in top_entities:
        logger.info(f"    {te['id']:25s} : {te['degree']} connections")
    logger.info("=" * 60)

    return stats


# ══════════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ══════════════════════════════════════════════════════════════════════════════


def run_pipeline(
    pdf_path: str = None,
    use_llm_refine: bool = True,
    extract_images_flag: bool = True,
    chunk_strategy: str = "section",
    sample_size: int = None,
) -> Tuple[Optional[ExtractionResult], Optional[List[Chunk]]]:
    """Run the full knowledge graph extraction pipeline.
    
    Args:
        pdf_path: Path to PDF file. Defaults to settings.PDF_PATH.
        use_llm_refine: Whether to use LLM for graph refinement (Step 5).
        extract_images_flag: Whether to extract and process images.
        chunk_strategy: Chunking strategy ('section' or 'recursive').
        
    Returns:
        Tuple of (final ExtractionResult, list of Chunks).
    """
    start_time = time.time()

    if pdf_path is None:
        pdf_path = settings.PDF_PATH

    logger.info("=" * 70)
    logger.info("STARTING KNOWLEDGE GRAPH PIPELINE")
    logger.info("=" * 70)
    logger.info(f"  PDF Path           : {pdf_path}")
    logger.info(f"  Extraction Model   : {settings.EXTRACTION_MODEL}")
    logger.info(f"  Extraction Provider: {settings.EXTRACTION_PROVIDER}")
    logger.info(f"  Refinement Model   : {settings.REFINEMENT_MODEL}")
    logger.info(f"  LLM Refinement     : {'Enabled' if use_llm_refine else 'Disabled'}")
    logger.info(f"  Image Extraction   : {'Enabled' if extract_images_flag else 'Disabled'}")
    logger.info(f"  Chunk Strategy     : {chunk_strategy}")
    logger.info(f"  Chunk Size         : {settings.CHUNK_SIZE_GRAPH}")
    logger.info("=" * 70)

    # ── STEP 1 + 2: PDF Extraction & Text Cleaning ─────────────────────
    logger.info("STEP 1-2: Loading and cleaning PDF...")
    doc_content = extract_document(pdf_path, extract_images=extract_images_flag)
    if doc_content is None:
        logger.error("Could not load PDF. Aborting.")
        return None, None

    logger.info(f"  Pages: {doc_content.total_pages}")
    logger.info(f"  Full text: {len(doc_content.full_text)} chars")

    total_images = sum(len(p.images) for p in doc_content.pages)
    logger.info(f"  Images: {total_images}")

    # Save extracted text
    save_json(
        [{"page": p.page_num, "text": p.text} for p in doc_content.pages],
        "extracted_text.json",
    )

    # ── STEP 3: Semantic Chunking ──────────────────────────────────────
    logger.info("STEP 3: Semantic chunking...")
    chunks = chunk_document(
        doc_content.full_text,
        strategy=chunk_strategy,
    )
    
    if sample_size and sample_size > 0:
        logger.info(f"  Sampling first {sample_size} chunks out of {len(chunks)} for testing")
        chunks = chunks[:sample_size]
        
    logger.info(f"  Produced {len(chunks)} chunks")

    # Save chunks for debugging
    save_json(
        [
            {
                "chunk_id": c.chunk_id,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "section_title": c.section_title,
                "char_count": c.char_count,
                "text_preview": c.text[:200] + "..." if len(c.text) > 200 else c.text,
            }
            for c in chunks
        ],
        "chunks.json",
    )

    # ── STEP 4: Per-Chunk Knowledge Extraction ─────────────────────────
    logger.info(f"STEP 4: Knowledge extraction ({settings.EXTRACTION_MODEL})...")
    extraction_client = get_extraction_client()
    all_extractions: List[ExtractionResult] = []
    
    os.makedirs(settings.CACHE_DIR, exist_ok=True)

    for i, chunk in enumerate(chunks):
        cache_file = os.path.join(settings.CACHE_DIR, f"chunk_{chunk.chunk_id}.json")
        
        # Check Cache First
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                result = ExtractionResult(**cached_data)
                logger.info(f"  [CACHE HIT] Loaded chunk {chunk.chunk_id} from cache ({len(result.entities)} entities)")
                all_extractions.append(result)
                continue
            except Exception as e:
                logger.warning(f"  [CACHE ERROR] Could not load {cache_file}: {e}. Re-extracting...")

        logger.info(
            f"  Processing chunk {i + 1}/{len(chunks)} "
            f"(pages {chunk.page_start}-{chunk.page_end}, "
            f"{chunk.char_count} chars)"
        )
        result = extract_from_chunk(
            chunk_text=chunk.text,
            chunk_id=chunk.chunk_id,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            section_title=chunk.section_title,
            client=extraction_client,
        )
        if result.entities or result.relationships:
            all_extractions.append(result)
            
            # Save to Cache
            try:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(result.model_dump(), f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"  [CACHE ERROR] Failed to save {cache_file}: {e}")

    # ── STEP 4b: Image Extraction (if enabled) ─────────────────────────
    if extract_images_flag and total_images > 0:
        logger.info(f"STEP 4b: Image extraction ({settings.VLM_MODEL})...")
        vlm_client = get_vlm_client()
        for page in doc_content.pages:
            for img in page.images:
                result = extract_from_image(
                    image_bytes=img.image_bytes,
                    page_num=img.page_num,
                    client=vlm_client,
                )
                if result.entities or result.relationships:
                    all_extractions.append(result)

    logger.info(f"  Total extraction results: {len(all_extractions)}")

    # Count raw extractions
    raw_entities = sum(len(r.entities) for r in all_extractions)
    raw_rels = sum(len(r.relationships) for r in all_extractions)
    logger.info(f"  Raw entities: {raw_entities}, Raw relationships: {raw_rels}")

    # Save raw extractions
    save_json(
        {
            "total_chunks": len(all_extractions),
            "extractions": [r.model_dump() for r in all_extractions],
        },
        "raw_extractions.json",
    )

    # ── STEP 5: Graph Refinement ───────────────────────────────────────
    logger.info("STEP 5: Graph refinement...")
    merged = refine_graph(
        all_extractions,
        use_llm=use_llm_refine,
    )

    logger.info(
        f"  Refined graph: {len(merged.entities)} entities, "
        f"{len(merged.relationships)} relationships"
    )

    # Save refined graph
    save_json(merged.model_dump(), "refined_graph.json")

    # ── STEP 6: Neo4j Ingestion ────────────────────────────────────────
    logger.info("STEP 6: Loading into Neo4j...")
    loader = None
    try:
        loader = Neo4jLoader(
            settings.neo4j_uri,
            settings.neo4j_username,
            settings.neo4j_password,
        )
        loader.load_all(merged, settings.ENTITY_TYPES)
        loader.validate()
    except Exception as e:
        logger.error(f"Neo4j loading failed: {e}")
        logger.warning("Graph was saved to data/refined_graph.json for manual loading")
    finally:
        if loader:
            try:
                loader.close()
            except Exception:
                pass

    # ── STEP 7: Statistics ─────────────────────────────────────────────
    logger.info("STEP 7: Generating statistics...")
    stats = generate_statistics(merged, all_extractions)
    save_json(stats, "pipeline_statistics.json")

    elapsed = time.time() - start_time
    logger.info(f"Pipeline finished in {elapsed:.1f} seconds ({elapsed / 60:.1f} minutes)")

    return merged, chunks


# ══════════════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="Run the GraphRAG knowledge extraction pipeline."
    )
    parser.add_argument(
        "--pdf",
        type=str,
        default=None,
        help="Path to the PDF file (default: from settings)",
    )
    parser.add_argument(
        "--no-llm-refine",
        action="store_true",
        help="Skip LLM-based graph refinement (use heuristic only)",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip image extraction",
    )
    parser.add_argument(
        "--chunk-strategy",
        type=str,
        default="section",
        choices=["section", "recursive"],
        help="Chunking strategy (default: section)",
    )

    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Number of chunks to sample (for testing/rate-limit avoidance)",
    )

    args = parser.parse_args()

    merged, chunks = run_pipeline(
        pdf_path=args.pdf,
        use_llm_refine=not args.no_llm_refine,
        extract_images_flag=not args.no_images,
        chunk_strategy=args.chunk_strategy,
        sample_size=args.sample,
    )

    if merged:
        print(f"\n{'=' * 50}")
        print(f"Pipeline complete!")
        print(f"  Entities      : {len(merged.entities)}")
        print(f"  Relationships : {len(merged.relationships)}")
        print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
