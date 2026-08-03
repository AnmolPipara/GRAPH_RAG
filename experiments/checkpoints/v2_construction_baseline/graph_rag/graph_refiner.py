"""
graph_refiner.py — Global Graph Deduplication and Refinement.

Merges entities by their stable ID and relationships by (source, target, relation).
Collects all provenance (chunks, pages) and sums frequency.
"""

import logging
from collections import defaultdict
from typing import List, Dict, Tuple

from graph_rag.knowledge_extractor import Entity, Relationship, ExtractionResult

logger = logging.getLogger(__name__)


def refine_graph(
    chunk_results: List[ExtractionResult],
    use_llm: bool = False,
) -> ExtractionResult:
    """Perform global deduplication across all extracted chunks.
    
    Args:
        chunk_results: List of extraction results from individual chunks.
        use_llm: Currently ignored, using deterministic ID-based merging.
        
    Returns:
        ExtractionResult containing the globally deduplicated graph.
    """
    logger.info(f"Starting global deduplication across {len(chunk_results)} chunks")
    
    entities_map: Dict[str, Entity] = {}
    relationships_map: Dict[str, Relationship] = {}
    
    for result in chunk_results:
        # Merge Entities
        for e in result.entities:
            if e.id in entities_map:
                existing = entities_map[e.id]
                # Combine aliases
                existing_aliases = set(existing.aliases)
                existing_aliases.update(e.aliases)
                existing.aliases = list(existing_aliases)
                
                # Combine provenance
                existing.source_pages.extend(e.source_pages)
                existing.source_chunks.extend(e.source_chunks)
                existing.frequency += e.frequency
                
                # Update attributes
                existing.attributes.update(e.attributes)
                
                # Append evidence if different
                if e.evidence and e.evidence not in (existing.evidence or ""):
                    if existing.evidence:
                        existing.evidence += "\n" + e.evidence
                    else:
                        existing.evidence = e.evidence
                        
                # Keep highest confidence
                existing.confidence = max(existing.confidence, e.confidence)
                
                # Prefer longer description
                if len(e.description) > len(existing.description):
                    existing.description = e.description
            else:
                # Copy lists to avoid sharing references
                e.source_pages = list(e.source_pages)
                e.source_chunks = list(e.source_chunks)
                entities_map[e.id] = e
                
        # Merge Relationships
        for r in result.relationships:
            # The key must exactly match source, target, and relation
            rel_key = f"{r.source}-[{r.relation}]->{r.target}"
            
            if rel_key in relationships_map:
                existing_rel = relationships_map[rel_key]
                # Combine provenance
                existing_rel.source_pages.extend(r.source_pages)
                existing_rel.source_chunks.extend(r.source_chunks)
                existing_rel.frequency += r.frequency
                
                # Append evidence
                if r.evidence and r.evidence not in (existing_rel.evidence or ""):
                    if existing_rel.evidence:
                        existing_rel.evidence += "\n" + r.evidence
                    else:
                        existing_rel.evidence = r.evidence
                        
                # Keep highest confidence
                existing_rel.confidence = max(existing_rel.confidence, r.confidence)
                
                # Prefer longer description
                if len(r.description) > len(existing_rel.description):
                    existing_rel.description = r.description
            else:
                r.source_pages = list(r.source_pages)
                r.source_chunks = list(r.source_chunks)
                relationships_map[rel_key] = r

    # Clean up provenance lists (remove exact duplicates)
    for e in entities_map.values():
        e.source_pages = sorted(list(set(e.source_pages)))
        e.source_chunks = sorted(list(set(e.source_chunks)))
        
    for r in relationships_map.values():
        r.source_pages = sorted(list(set(r.source_pages)))
        r.source_chunks = sorted(list(set(r.source_chunks)))

    # ── Resolve cross-chunk relationship references ──────────────────
    # Relationships extracted in one chunk may reference entities by
    # slugified names (e.g., "iso-20022-cross-chunk") that don't match
    # the canonical entity IDs (e.g., "iso-20022-standard"). Try to
    # match these by comparing the slugified canonical name.
    import re
    def _slugify(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r'[^\w\s-]', '', text)
        return re.sub(r'[\s_-]+', '-', text)
    
    # Build a map from slugified canonical_name to entity ID
    slug_to_entity_id = {}
    for eid, e in entities_map.items():
        slugified = _slugify(e.canonical_name)
        slug_to_entity_id[slugified] = eid
        # Also map the bare slug (without type suffix)
        bare_slug = slugified.rsplit("-", 1)[0] if "-" in slugified else slugified
        slug_to_entity_id[bare_slug] = eid
    
    resolved_count = 0
    for r in relationships_map.values():
        # Try to resolve source -"/.*-cross-chunk/" to a real entity
        if r.source.endswith("-cross-chunk"):
            bare_source = r.source.replace("-cross-chunk", "")
            if bare_source in slug_to_entity_id:
                r.source = slug_to_entity_id[bare_source]
                resolved_count += 1
        if r.target.endswith("-cross-chunk"):
            bare_target = r.target.replace("-cross-chunk", "")
            if bare_target in slug_to_entity_id:
                r.target = slug_to_entity_id[bare_target]
                resolved_count += 1
    
    logger.info(f"Cross-chunk relationship resolution: resolved {resolved_count} references")

    merged = ExtractionResult(
        entities=list(entities_map.values()),
        relationships=list(relationships_map.values())
    )
    
    logger.info(
        f"Global deduplication complete: "
        f"{len(merged.entities)} entities, {len(merged.relationships)} relationships"
    )
    
    return merged
