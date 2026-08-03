"""
knowledge_extractor.py — Per-Chunk Knowledge Extraction via Frontier LLM.

This is the core module of the GraphRAG pipeline. For each text chunk, it
calls a frontier-class LLM (≥100B parameters) to extract:

1. Entities — with canonical names, types, attributes, aliases, descriptions
2. Relationships — with direction, confidence, and source text evidence
3. Implicit relationships — inferred from context but not explicitly stated
4. Hierarchical structures — parent-child, contains, part-of relationships

The extraction prompt is carefully engineered for maximum recall and precision
on technical documents (research papers, ISO standards, financial specs, manuals).

Output is structured JSON validated against Pydantic models.
"""

import io
import base64
import logging
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field

from config.settings import settings
from graph_rag.llm_client import get_extraction_client, get_vlm_client, LLMClient

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# PYDANTIC DATA MODELS
# ══════════════════════════════════════════════════════════════════════════════


class Entity(BaseModel):
    """An entity extracted from a document chunk."""
    id: str = Field(..., description="Unique deterministic ID (slug)")
    canonical_name: str = Field(..., description="Canonical name of the entity")
    name: str = Field(..., description="Display name of the entity")
    type: str = Field(..., description="Entity type from the predefined ontology")
    description: str = Field("", description="Brief description of the entity")
    aliases: List[str] = Field(
        default_factory=list,
        description="Alternative names, abbreviations, or acronyms"
    )
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured attributes (e.g., version, domain, publisher)"
    )
    confidence: float = Field(0.0, description="Extraction confidence 0.0-1.0")
    evidence: Optional[str] = Field(
        None, description="Evidence text from the document"
    )
    # Metadata (tracked over batches)
    source_pages: List[int] = Field(default_factory=list)
    source_chunks: List[int] = Field(default_factory=list)
    frequency: int = Field(1, description="Number of times extracted")


class Relationship(BaseModel):
    """A directed relationship between two entities."""
    source: str = Field(..., description="Source entity ID or canonical name")
    relation: str = Field(..., description="Relationship type from ontology")
    target: str = Field(..., description="Target entity ID or canonical name")
    description: str = Field("", description="Brief description of the relationship")
    confidence: float = Field(0.0, description="Extraction confidence 0.0-1.0")
    evidence: Optional[str] = Field(
        None, description="Evidence text from the document"
    )
    implicit: bool = Field(
        False,
        description="True if this relationship was inferred rather than explicit"
    )
    # Metadata
    source_pages: List[int] = Field(default_factory=list)
    source_chunks: List[int] = Field(default_factory=list)
    frequency: int = Field(1, description="Number of times extracted")


class ExtractionResult(BaseModel):
    """Complete extraction output from a single chunk."""
    entities: List[Entity] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════════
# EXTRACTION PROMPTS — Optimized for High Density
# ══════════════════════════════════════════════════════════════════════════════


def _build_system_prompt() -> str:
    """Build a concise, high-recall system prompt for knowledge extraction.
    Focused on completeness with concrete density targets.
    """
    entity_types = ", ".join(settings.ENTITY_TYPES)
    relationship_types = ", ".join(settings.RELATIONSHIP_TYPES)

    return f"""You are an expert Knowledge Graph Indexing engine for OFFLINE indexing.
This is NOT QA or summarization — extract EVERY entity and relationship.

─── DENSITY TARGET (critical) ───
For ~3000 chars of text, extract:
- 80-150+ entities (every named concept: standards, orgs, roles, XML elements, codes, fields, identifiers, components)
- 120-300+ relationships (every connection: contains, uses, publishes, creates, related_to, etc.)
If below 50 entities you are under-extracting.

─── PER-PARAGRAPH PROTOCOL ───
Process each paragraph, heading, table row, and bullet. Do NOT move to the next paragraph until you have extracted ALL entities from the current one. For each:
1. List every named concept/term/role/code/identifier as an entity
2. Connect each entity to all related entities via relationships
3. Include acronyms as aliases, field names, XML tags, code values

Include specifically: XML element names, codes, field names, identifiers, table cell values, acronyms, and abbreviations as distinct entities.

─── ALLOWED ENTITY TYPES ───
{entity_types}

─── ALLOWED RELATIONSHIP TYPES ───
{relationship_types}

─── WHAT TO EXTRACT (EVERYTHING) ───
Organizations, standards, message types, payment roles, codes, identifiers, account types, currencies, business components, data elements, XML messages, technical concepts, business concepts, documents, sections, tables, figures, dates, versions, events, people, tools, APIs, products, services, protocols, frameworks, rules, workflows.

─── RELATIONSHIP MINING ───
For every co-occurring entity pair, create a relationship. Every entity needs 1-3+ relationships.
Use CONTAINS, PART_OF, HAS_COMPONENT for structure.
Use CREATED_BY, PUBLISHES, OWNS for ownership.
Use USES, IMPLEMENTS, SUPPORTS, ENABLES for dependencies.
Use REFERENCES, IDENTIFIED_BY for cross-refs.
Default to RELATED_TO if unsure.

─── EXAMPLE (abbreviated — your actual output must have 80-150+ entities) ───
{{"entities": [
  {{"canonical_name": "ISO 20022", "name": "ISO 20022", "type": "Standard", "description": "Universal financial industry message scheme", "aliases": ["ISO20022"], "attributes": {{"domain": "Financial messaging"}}, "confidence": 0.99, "evidence": "ISO 20022 is the universal financial industry message scheme..."}},
  {{"canonical_name": "Finance Finland", "name": "Finance Finland", "type": "Organization", "description": "Financial industry organization in Finland", "aliases": ["Finanssiala ry"], "attributes": {{"country": "Finland"}}, "confidence": 0.98, "evidence": "Published by Finance Finland"}},
  {{"canonical_name": "Payment Message", "name": "Payment Message", "type": "XMLMessage", "description": "ISO 20022 XML payment initiation message", "aliases": [], "attributes": {{"block_count": "3"}}, "confidence": 0.98, "evidence": "2.2 Payment Message structure"}},
  {{"canonical_name": "Group Header", "name": "Group Header", "type": "BusinessComponent", "description": "Block A of payment message", "aliases": ["Block A", "GroupHeader"], "attributes": {{"block": "A", "multiplicity": "1..1"}}, "confidence": 0.98, "evidence": "2.2.1 Group Header"}},
  {{"canonical_name": "Debtor", "name": "Debtor", "type": "PaymentRole", "description": "Party whose account is debited", "aliases": ["Originator", "Payer"], "attributes": {{"side": "debit"}}, "confidence": 0.99, "evidence": "Debtor: party whose account is debited"}}
],
"relationships": [
  {{"source": "Finance Finland", "target": "ISO 20022 Payments Guide", "relation": "PUBLISHES", "description": "Finance Finland publishes the guide", "confidence": 0.99, "evidence": "Published by Finance Finland", "implicit": false}},
  {{"source": "Payment Message", "target": "Group Header", "relation": "HAS_COMPONENT", "description": "Message contains Group Header", "confidence": 0.99, "evidence": "2.2 Payment Message", "implicit": false}},
  {{"source": "Group Header", "target": "Debtor", "relation": "CONTAINS", "description": "Group Header can reference Debtor", "confidence": 0.95, "evidence": "Group header elements", "implicit": true}}
]}}

─── FINAL CHECKLIST ───
☐ Every paragraph, heading, table row analyzed
☐ Each paragraph → 5-15+ entities
☐ Each entity has type, description, evidence
☐ Each entity has 1-3+ relationships
☐ Acronyms as aliases, codes as entities
☐ Total: 80-150+ entities per chunk
☐ Relationships exceed entities
☐ Valid JSON only, no markdown/explanations

COMPLETENESS > BREVITY. Extract more than you think is needed.
Return ONLY valid JSON with entities and relationships arrays.
"""


def _build_user_prompt(text: str, section_title: str = None) -> str:
    """Build the user prompt with explicit per-paragraph extraction instructions."""
    header = ""
    if section_title:
        header = f"SECTION: {section_title}\n\n"

    return f"""{header}DOCUMENT TEXT TO EXTRACT (extract 80-150+ entities from this chunk):

{text}

─── EXTRACTION INSTRUCTIONS ───
1. Process the text PARAGRAPH BY PARAGRAPH, starting from the first line.
2. For EACH paragraph, extract ALL entities mentioned AND relationships between them.
3. Pay special attention to: headings, table cells, XML elements, codes, acronyms.
4. Every field name, code value, and role mentioned should be its own entity.
5. Group related entities under parent entities using CONTAINS relationships.
6. Cross-reference entities between paragraphs — don't treat them in isolation.
7. Target: at least 80 entities for this chunk. If you have fewer than 50, re-scan.

Return ONLY valid JSON with "entities" and "relationships" arrays.
"""


def _build_image_prompt() -> str:
    """Build the prompt for image-based knowledge extraction."""
    entity_types = ", ".join(settings.ENTITY_TYPES)
    relationship_types = ", ".join(settings.RELATIONSHIP_TYPES)

    return f"""Analyze this image from a technical document and extract ALL structured knowledge visible.

ENTITY TYPES AVAILABLE: {entity_types}
RELATIONSHIP TYPES AVAILABLE: {relationship_types}

For each element visible in the image, create an entity. For connections, create relationships.

For flowcharts/process diagrams: each step is an entity, arrows are RELATED_TO or FLOWS_TO
For hierarchy/org charts: each box is an entity, lines are CONTAINS, PART_OF, or MANAGES
For architecture diagrams: each component is an entity, lines are HAS_COMPONENT, CONNECTED_TO
For tables: each row header is an entity, each cell value is an entity or attribute
For code/XML snippets: each tag is an entity, nesting creates CONTAINS relationships

Extract aggressively. Every text label, icon label, and component should be an entity.

Return ONLY valid JSON:
{{"entities": [{{"name": "...", "type": "...", "description": "...", "aliases": [], "attributes": {{}}, "confidence": 0.9, "source_text": "..."}}],
 "relationships": [{{"source": "...", "relation": "...", "target": "...", "description": "...", "confidence": 0.9, "evidence": "...", "implicit": false}}]}}

Ignore: logos, decorative graphics, icons, borders, watermarks, page numbers, backgrounds.
If the image contains no meaningful knowledge, return: {{"entities": [], "relationships": []}}
"""


# ══════════════════════════════════════════════════════════════════════════════
# NOISE FILTERING — Loosened to preserve more entities
# ══════════════════════════════════════════════════════════════════════════════


import re

_NOISE_PATTERNS = [
    re.compile(r"^\+?\d[\d\s\-()]{6,}$"),       # Phone numbers
    re.compile(r"^[\w.\-]+@[\w.\-]+\.\w+$"),     # Email addresses
    re.compile(r"^https?://"),                     # URLs
    re.compile(r"^www\."),                         # Websites
    re.compile(r"^[A-F0-9\-]{24,}$"),            # UUIDs/hashes
    re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,}$"), # IBANs
]


def _is_noise_entity(name: str) -> bool:
    """Check if an entity name is noise (should be filtered).

    Loosened from original: bare numbers up to 3 digits are now ALLOWED
    since codes like '001', 'AOS1' are valid business identifiers.
    """
    if not name or len(name.strip()) < 2:
        return True
    name = name.strip()
    return any(p.match(name) for p in _NOISE_PATTERNS)


# ══════════════════════════════════════════════════════════════════════════════
# ENTITY TYPE NORMALIZATION
# ══════════════════════════════════════════════════════════════════════════════

# Maps variant type names to canonical types
ENTITY_TYPE_MAPPING = {
    "Country": "Location",
    "City": "Location",
    "State": "Location",
    "Province": "Location",
    "Region": "Location",
    "Continent": "Location",
    "Address": "Location",
    "Company": "Organization",
    "Institution": "Organization",
    "Agency": "Organization",
    "Software": "Product",
    "Guide": "Document",
    "Specification": "Document",
    "Manual": "Document",
    "Report": "Document",
    "Workflow": "Process",
    "Procedure": "Process",
    "Algorithm": "Process",
    "Framework": "Technology",
    "Library": "Technology",
    "Platform": "Technology",
    "Tool": "Technology",
    "API": "Technology",
    "Interface": "System",
    "Module": "System",
    "Component": "System",
    "Scheme": "Standard",
    "Norm": "Standard",
    "Guideline": "Standard",
    "Code": "Identifier",
    "CodeValue": "Code",
}


def _normalize_entity_type(entity_type: str) -> str:
    """Normalize entity type to a canonical type in ENTITY_TYPES."""
    mapped = ENTITY_TYPE_MAPPING.get(entity_type, entity_type)
    if mapped in settings.ENTITY_TYPES:
        return mapped
    # If still not in the allowed list, default to "Concept"
    return mapped  # Return the mapped type even if not in the canonical list


# ══════════════════════════════════════════════════════════════════════════════
# RELATIONSHIP NORMALIZATION
# ══════════════════════════════════════════════════════════════════════════════

RELATION_MAPPING = {
    "CREATE": "CREATED",
    "DEVELOPS": "DEVELOPED_BY",
    "PUBLISHED": "PUBLISHES",
    "ISSUED": "ISSUED_BY",
    "ADOPTED": "USES",
    "MIGRATES_TO": "USES",
    "IMPLEMENTED": "IMPLEMENTS",
    "BELONGS": "BELONGS_TO",
    "PARTOF": "PART_OF",
    "ESTABLISHED": "CREATED",
    "ESTABLISHES": "CREATED",
    "PERMITS": "SUPPORTS",
    "ALLOWS": "ENABLES",
    "CONNECTED_TO": "RELATED_TO",
    "LINKS_TO": "REFERENCES",
}


def _normalize_relation(relation: str) -> str:
    """Normalize relationship type to a canonical type.
    
    Changed from defaulting to RELATED_TO to instead keeping the original
    relation type when it's not in the mapping, to preserve LLM output.
    """
    mapped = RELATION_MAPPING.get(relation, relation)
    if mapped in settings.RELATIONSHIP_TYPES:
        return mapped
    # If we got here, keep the original relation type (don't collapse to RELATED_TO)
    return mapped.upper().replace(" ", "_")


# ══════════════════════════════════════════════════════════════════════════════
# EXTRACTION FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════


def extract_from_chunk(
    chunk_text: str,
    chunk_id: int,
    page_start: int,
    page_end: int,
    section_title: str = None,
    client: LLMClient = None,
) -> ExtractionResult:
    """Extract knowledge from a single text chunk using the frontier LLM.
    
    Args:
        chunk_text: The text content of the chunk.
        chunk_id: Unique identifier for this chunk.
        page_start: Starting page number.
        page_end: Ending page number.
        section_title: Optional section heading for context.
        client: LLM client to use. Creates extraction client if None.
        
    Returns:
        ExtractionResult with validated entities and relationships.
    """
    if not chunk_text or len(chunk_text.strip()) < 30:
        logger.debug(f"Chunk {chunk_id}: text too short, skipping")
        return ExtractionResult()

    if client is None:
        client = get_extraction_client()

    logger.info(
        f"Extracting chunk {chunk_id} "
        f"(pages {page_start}-{page_end}, {len(chunk_text)} chars)"
    )

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(chunk_text, section_title)

    try:
        data = client.extract_json(system_prompt, user_prompt)
    except Exception as e:
        logger.error(f"Chunk {chunk_id}: extraction failed: {e}")
        return ExtractionResult()

    # Validate and normalize entities
    valid_entities = []
    valid_entities_map = {}
    for e_data in data.get("entities", []):
        entity = _validate_entity(e_data, chunk_id, page_start, page_end)
        if entity is not None:
            valid_entities.append(entity)
            valid_entities_map[entity.canonical_name] = entity
            valid_entities_map[entity.name] = entity  # Fallback

    # Validate and normalize relationships
    valid_relationships = []
    for r_data in data.get("relationships", []):
        rel = _validate_relationship(
            r_data, valid_entities_map, chunk_id, page_start, page_end
        )
        if rel is not None:
            valid_relationships.append(rel)

    logger.info(
        f"Chunk {chunk_id}: extracted {len(valid_entities)} entities, "
        f"{len(valid_relationships)} relationships"
    )

    return ExtractionResult(
        entities=valid_entities,
        relationships=valid_relationships,
    )


def extract_from_image(
    image_bytes: bytes,
    page_num: int,
    client: LLMClient = None,
) -> ExtractionResult:
    """Extract knowledge from an image using a vision-language model.
    
    Args:
        image_bytes: Raw bytes of the image.
        page_num: Page number where the image was found.
        client: VLM client to use. Creates VLM client if None.
        
    Returns:
        ExtractionResult with validated entities and relationships.
    """
    if client is None:
        client = get_vlm_client()

    logger.info(f"Extracting from image on page {page_num}")

    try:
        from PIL import Image as PILImage
        image = PILImage.open(io.BytesIO(image_bytes))
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        img_b64 = base64.b64encode(buffered.getvalue()).decode()
    except Exception as e:
        logger.error(f"Failed to process image on page {page_num}: {e}")
        return ExtractionResult()

    prompt = _build_image_prompt()

    try:
        data = client.call_vision(prompt, img_b64)
    except Exception as e:
        logger.error(f"Image extraction failed on page {page_num}: {e}")
        return ExtractionResult()

    # Validate entities and relationships
    valid_entities = []
    valid_entities_map = {}
    for e_data in data.get("entities", []):
        entity = _validate_entity(e_data, chunk_id=-1, page_start=page_num, page_end=page_num)
        if entity is not None:
            valid_entities.append(entity)
            valid_entities_map[entity.canonical_name] = entity
            valid_entities_map[entity.name] = entity

    valid_relationships = []
    for r_data in data.get("relationships", []):
        rel = _validate_relationship(
            r_data, valid_entities_map, chunk_id=-1, page_start=page_num, page_end=page_num
        )
        if rel is not None:
            valid_relationships.append(rel)

    logger.info(
        f"Image page {page_num}: extracted {len(valid_entities)} entities, "
        f"{len(valid_relationships)} relationships"
    )

    return ExtractionResult(
        entities=valid_entities,
        relationships=valid_relationships,
    )


# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION HELPERS
# ══════════════════════════════════════════════════════════════════════════════


def _slugify(text: str) -> str:
    import re
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    return re.sub(r'[\s_-]+', '-', text)


def _validate_entity(
    data: dict,
    chunk_id: int,
    page_start: int,
    page_end: int,
) -> Optional[Entity]:
    """Validate and normalize a raw entity dict from LLM output.
    
    Returns a validated Entity or None if invalid.
    """
    canonical_name = data.get("canonical_name", data.get("name", "")).strip()
    name = data.get("name", canonical_name).strip()
    if not canonical_name or _is_noise_entity(canonical_name):
        return None

    # Skip URLs, emails, etc. in entity names
    if canonical_name.startswith("http") or canonical_name.startswith("www.") or "@" in canonical_name:
        return None

    entity_type = data.get("type", "Concept")
    entity_type = _normalize_entity_type(entity_type)

    # Ensure aliases is a list
    aliases = data.get("aliases", [])
    if isinstance(aliases, str):
        aliases = [aliases]
    aliases = [a.strip() for a in aliases if a and a.strip()]

    # Ensure attributes is a dict
    attributes = data.get("attributes", {})
    if not isinstance(attributes, dict):
        attributes = {}

    entity_id = f"{_slugify(canonical_name)}-{_slugify(entity_type)}"

    try:
        entity = Entity(
            id=entity_id,
            canonical_name=canonical_name,
            name=name,
            type=entity_type,
            description=data.get("description", ""),
            aliases=aliases,
            attributes=attributes,
            confidence=float(data.get("confidence", 0.5)),
            evidence=data.get("evidence", data.get("source_text")),
            # CONSTRUCTION FIX: stamp the FULL page range the chunk spans,
            # not just the chunk's first page. Entities extracted from a chunk
            # covering pages 8-13 must be linked to ALL of pages 8-13, otherwise
            # pages beyond page_start are unreachable in retrieval (they never
            # appear in source_pages, so the retriever can never attach them).
            source_pages=list(range(page_start, page_end + 1)) if page_start else [],
            source_chunks=[chunk_id] if chunk_id != -1 else [],
            frequency=1
        )
        return entity
    except Exception as e:
        logger.debug(f"Invalid entity data: {data} — {e}")
        return None


def _validate_relationship(
    data: dict,
    valid_entities: dict,
    chunk_id: int,
    page_start: int,
    page_end: int,
) -> Optional[Relationship]:
    """Validate and normalize a raw relationship dict from LLM output.
    
    CRITICAL: Unlike the original version, this function does NOT drop
    relationships whose endpoints weren't extracted in this chunk.
    Instead, it creates a lightweight placeholder entity so the
    relationship survives for later cross-chunk resolution during merge.
    
    Returns a validated Relationship or None if truly invalid.
    """
    source = data.get("source", "").strip()
    target = data.get("target", "").strip()
    relation = data.get("relation", data.get("type", "")).strip()

    if not source or not target or not relation:
        return None
    
    # Fuzzy matching: try canonical_name, then name, then case-insensitive
    source_entity = valid_entities.get(source)
    if not source_entity:
        # Try case-insensitive match
        for k, v in valid_entities.items():
            if k.lower() == source.lower():
                source_entity = v
                break
    
    target_entity = valid_entities.get(target)
    if not target_entity:
        for k, v in valid_entities.items():
            if k.lower() == target.lower():
                target_entity = v
                break
    
    # Build the source/target entity IDs
    if source_entity:
        source_id = source_entity.id
    else:
        # Create a stable ID from the name — will be resolved during merge
        source_id = _slugify(source) + "-cross-chunk"
    
    if target_entity:
        target_id = target_entity.id
    else:
        target_id = _slugify(target) + "-cross-chunk"

    # Self-loops are usually noise (only if same name, not resolved IDs)
    if source_id == target_id:
        return None

    relation = _normalize_relation(relation)

    try:
        rel = Relationship(
            source=source_id,
            relation=relation,
            target=target_id,
            description=data.get("description", ""),
            confidence=float(data.get("confidence", 0.5)),
            evidence=data.get("evidence", data.get("source_text")),
            implicit=bool(data.get("implicit", data.get("is_implicit", False))),
            # CONSTRUCTION FIX: full page range (see _validate_entity).
            source_pages=list(range(page_start, page_end + 1)) if page_start else [],
            source_chunks=[chunk_id] if chunk_id != -1 else [],
            frequency=1
        )
        return rel
    except Exception as e:
        logger.debug(f"Invalid relationship data: {data} — {e}")
        return None
