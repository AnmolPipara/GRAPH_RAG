"""
chunker.py — Semantic Chunking for Knowledge Graph Extraction.

Splits cleaned document text into semantically meaningful chunks
suitable for per-chunk knowledge extraction. Uses section-aware
splitting as the primary strategy, with recursive character splitting
as a fallback.

Each chunk carries metadata (chunk_id, page_range, section_title)
so that extracted entities/relationships can be traced back to their
source location in the document.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """A text chunk with provenance metadata."""
    chunk_id: int
    text: str
    page_start: int
    page_end: int
    section_title: Optional[str] = None
    char_count: int = 0

    def __post_init__(self):
        self.char_count = len(self.text)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION-AWARE CHUNKING (Primary Strategy)
# ══════════════════════════════════════════════════════════════════════════════

# Patterns for detecting section headings
HEADING_PATTERNS = [
    # Numbered sections: "1.2.3 Title", "1.2.3. Title"
    re.compile(r"^(\d+(?:\.\d+)*\.?\s+\S.*)$", re.MULTILINE),
    # "Chapter X", "Section X", "Appendix X"
    re.compile(r"^((?:Chapter|Section|Appendix|Part|Annex)\s+\S.*)$",
               re.MULTILINE | re.IGNORECASE),
    # ALL-CAPS headings (at least 3 words, no lowercase)
    re.compile(r"^([A-Z][A-Z\s\d\-&]{10,})$", re.MULTILINE),
]


def _detect_sections(text: str) -> List[Tuple[int, str, str]]:
    """Detect section boundaries in text.
    
    Returns:
        List of (char_position, heading_text, section_text) tuples.
    """
    # Find all heading positions
    heading_positions = []
    for pattern in HEADING_PATTERNS:
        for match in pattern.finditer(text):
            heading_positions.append((match.start(), match.group(1).strip()))

    # Sort by position and deduplicate nearby headings
    heading_positions.sort(key=lambda x: x[0])

    # Remove headings that are too close together (likely false positives)
    filtered = []
    for pos, heading in heading_positions:
        if not filtered or (pos - filtered[-1][0]) > 50:
            filtered.append((pos, heading))

    if not filtered:
        return []

    # Split text at heading positions
    sections = []
    for i, (pos, heading) in enumerate(filtered):
        end_pos = filtered[i + 1][0] if i + 1 < len(filtered) else len(text)
        section_text = text[pos:end_pos].strip()
        sections.append((pos, heading, section_text))

    return sections


def _build_page_positions(full_text: str) -> List[Tuple[int, int]]:
    """Map character offsets in full_text to page numbers via [PAGE N] markers.

    pdf_extractor inserts a ``[PAGE N]`` marker at the start of every page's
    text, so the largest marker offset <= a character position identifies the
    page that position belongs to.
    """
    return [(m.start(), int(m.group(1))) for m in re.finditer(r"\[PAGE (\d+)\]", full_text)]


def _page_at(pos: int, page_positions: List[Tuple[int, int]], default: int = 1) -> int:
    """Return the page number containing character offset ``pos``."""
    page = default
    for marker_pos, page_num in page_positions:
        if marker_pos <= pos:
            page = page_num
        else:
            break
    return page


def _extract_page_range(
    text: str,
    start_pos: int = 0,
    page_positions: List[Tuple[int, int]] = None,
) -> Tuple[int, int]:
    """Extract page range for a section of text using position-based detection.

    pdf_extractor inserts a ``[PAGE N]`` marker at the START of every page's
    text. A section heading can sit mid-page, so in-text markers are NOT
    authoritative (a section whose heading is mid-page-7 and whose text extends
    onto page 8 contains ``[PAGE 8]`` but not ``[PAGE 7]`` — reading markers
    alone would under-report the start as page 8). The section's offset in
    ``full_text`` is ground truth: the page containing ``start_pos`` and the
    page containing the section's end are the true range. This also guarantees
    page_start NEVER collapses to the default page 1 for markerless sections.

    Args:
        text: The section text (kept for API stability; not scanned).
        start_pos: Offset of the section within the full document text.
        page_positions: (marker_offset, page_number) map built from full text.

    Returns:
        (page_start, page_end) tuple.
    """
    if not page_positions:
        return 1, 1
    page_start = _page_at(start_pos, page_positions)
    page_end = _page_at(start_pos + max(0, len(text) - 1), page_positions)
    return page_start, max(page_start, page_end)


def _split_long_section(
    text: str,
    max_size: int,
    overlap: int,
) -> List[str]:
    """Split a long section into smaller chunks at paragraph boundaries.
    
    Tries to split at double-newlines (paragraph breaks) first, then
    falls back to single newlines, then to hard character splitting.
    """
    if len(text) <= max_size:
        return [text]

    chunks = []
    
    # Try splitting at paragraph boundaries
    paragraphs = re.split(r"\n\n+", text)
    
    current_chunk = ""
    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= max_size:
            current_chunk = (current_chunk + "\n\n" + para).strip()
        else:
            if current_chunk:
                chunks.append(current_chunk)
            # If a single paragraph exceeds max_size, split it
            if len(para) > max_size:
                # Split at sentence boundaries
                sentences = re.split(r"(?<=[.!?])\s+", para)
                current_chunk = ""
                for sent in sentences:
                    if len(current_chunk) + len(sent) + 1 <= max_size:
                        current_chunk = (current_chunk + " " + sent).strip()
                    else:
                        if current_chunk:
                            chunks.append(current_chunk)
                        current_chunk = sent
            else:
                current_chunk = para

    if current_chunk:
        chunks.append(current_chunk)

    # Add overlap between chunks
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_text = chunks[i - 1]
            overlap_text = prev_text[-overlap:] if len(prev_text) > overlap else prev_text
            overlapped.append(overlap_text + "\n" + chunks[i])
        chunks = overlapped

    return chunks


def chunk_by_sections(
    full_text: str,
    chunk_size: int = None,
    chunk_overlap: int = None,
) -> List[Chunk]:
    """Split text into chunks based on detected section boundaries.
    
    Primary chunking strategy:
    1. Detect section headings (numbered sections, chapter markers, ALL-CAPS)
    2. Split at section boundaries
    3. If a section exceeds chunk_size, split at paragraph boundaries
    4. Apply overlap between chunks
    
    Falls back to recursive splitting if no sections are detected.
    
    Args:
        full_text: Complete document text with [PAGE N] markers.
        chunk_size: Maximum characters per chunk. Defaults to settings.
        chunk_overlap: Overlap between chunks. Defaults to settings.
        
    Returns:
        List of Chunk objects with metadata.
    """
    if chunk_size is None:
        chunk_size = settings.CHUNK_SIZE_GRAPH
    if chunk_overlap is None:
        chunk_overlap = settings.CHUNK_OVERLAP_GRAPH

    sections = _detect_sections(full_text)

    if not sections:
        logger.info("No section headings detected, falling back to recursive chunking")
        return chunk_recursive(full_text, chunk_size, chunk_overlap)

    logger.info(f"Detected {len(sections)} sections in document")

    # Position-based page map so markerless sections never collapse to page 1.
    page_positions = _build_page_positions(full_text)

    chunks = []
    chunk_id = 0

    current_batch_text = ""
    current_page_start = None
    current_page_end = None
    current_section_titles = []

    def flush_batch():
        nonlocal chunk_id, current_batch_text, current_page_start, current_page_end, current_section_titles
        if current_batch_text.strip():
            # Combine section titles for context
            titles = " / ".join(dict.fromkeys(current_section_titles)) if current_section_titles else None
            chunks.append(Chunk(
                chunk_id=chunk_id,
                text=current_batch_text.strip(),
                page_start=current_page_start or 1,
                page_end=current_page_end or 1,
                section_title=titles,
            ))
            chunk_id += 1
        current_batch_text = ""
        current_page_start = None
        current_page_end = None
        current_section_titles = []

    for pos, heading, section_text in sections:
        if len(section_text.strip()) < 50:
            continue

        page_start, page_end = _extract_page_range(section_text, start_pos=pos, page_positions=page_positions)
        clean_section = re.sub(r"\[PAGE \d+\]\n?", "", section_text).strip()

        # If a single section is larger than max chunk size, flush current and split it
        if len(clean_section) > chunk_size:
            flush_batch()
            sub_chunks = _split_long_section(clean_section, chunk_size, chunk_overlap)
            for sub_text in sub_chunks:
                chunks.append(Chunk(
                    chunk_id=chunk_id,
                    text=sub_text,
                    page_start=page_start,
                    page_end=page_end,
                    section_title=heading,
                ))
                chunk_id += 1
            continue

        # If adding this section exceeds chunk_size, flush the current batch
        if len(current_batch_text) + len(clean_section) > chunk_size and current_batch_text:
            flush_batch()

        # Add to current batch
        if not current_batch_text:
            current_batch_text = clean_section
            current_page_start = page_start
            current_page_end = page_end
        else:
            current_batch_text += "\n\n" + clean_section
            current_page_end = max(current_page_end, page_end)
            
        if heading:
            current_section_titles.append(heading)

    # Flush any remaining text
    flush_batch()

    logger.info(f"Section-aware batching produced {len(chunks)} chunks")
    return chunks


# ══════════════════════════════════════════════════════════════════════════════
# RECURSIVE CHARACTER CHUNKING (Fallback)
# ══════════════════════════════════════════════════════════════════════════════


def chunk_recursive(
    full_text: str,
    chunk_size: int = None,
    chunk_overlap: int = None,
) -> List[Chunk]:
    """Split text into chunks using recursive character splitting.
    
    Fallback strategy when section-aware chunking can't find headings.
    Splits at paragraph boundaries (\n\n), then line boundaries (\n),
    then sentence boundaries, then raw characters.
    
    Args:
        full_text: Complete document text.
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Overlap between chunks.
        
    Returns:
        List of Chunk objects.
    """
    if chunk_size is None:
        chunk_size = settings.CHUNK_SIZE_GRAPH
    if chunk_overlap is None:
        chunk_overlap = settings.CHUNK_OVERLAP_GRAPH

    # Remove page markers and track page positions
    page_positions = []
    for match in re.finditer(r"\[PAGE (\d+)\]", full_text):
        page_positions.append((match.start(), int(match.group(1))))

    clean_text = re.sub(r"\[PAGE \d+\]\n?", "", full_text).strip()

    # Split into paragraphs
    separators = ["\n\n", "\n", ". ", " "]
    raw_chunks = _recursive_split(clean_text, separators, chunk_size)

    # Add overlap
    chunks = []
    chunk_id = 0
    for i, text in enumerate(raw_chunks):
        if not text.strip():
            continue

        # Apply overlap from previous chunk
        if i > 0 and chunk_overlap > 0:
            prev = raw_chunks[i - 1]
            overlap = prev[-chunk_overlap:] if len(prev) > chunk_overlap else prev
            text = overlap + "\n" + text

        # Determine page range (approximate)
        page_start = 1
        page_end = 1
        if page_positions:
            page_start = page_positions[0][1]
            page_end = page_positions[-1][1]

        chunks.append(Chunk(
            chunk_id=chunk_id,
            text=text.strip(),
            page_start=page_start,
            page_end=page_end,
        ))
        chunk_id += 1

    logger.info(f"Recursive chunking produced {len(chunks)} chunks")
    return chunks


def _recursive_split(
    text: str,
    separators: List[str],
    chunk_size: int,
) -> List[str]:
    """Recursively split text using a hierarchy of separators."""
    if len(text) <= chunk_size:
        return [text]

    if not separators:
        # Hard split at chunk_size
        result = []
        for i in range(0, len(text), chunk_size):
            result.append(text[i : i + chunk_size])
        return result

    sep = separators[0]
    remaining_seps = separators[1:]

    parts = text.split(sep)
    chunks = []
    current = ""

    for part in parts:
        candidate = (current + sep + part).strip() if current else part
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # If this part alone exceeds chunk_size, recurse with finer separator
            if len(part) > chunk_size:
                sub_chunks = _recursive_split(part, remaining_seps, chunk_size)
                chunks.extend(sub_chunks)
                current = ""
            else:
                current = part

    if current:
        chunks.append(current)

    return chunks


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════


def chunk_document(
    full_text: str,
    strategy: str = "section",
    chunk_size: int = None,
    chunk_overlap: int = None,
) -> List[Chunk]:
    """Split document text into chunks using the specified strategy.
    
    Args:
        full_text: Complete document text (with [PAGE N] markers from pdf_extractor).
        strategy: 'section' for section-aware chunking (default), 
                  'recursive' for fallback recursive splitting.
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Overlap between chunks.
        
    Returns:
        List of Chunk objects ready for knowledge extraction.
    """
    if strategy == "section":
        return chunk_by_sections(full_text, chunk_size, chunk_overlap)
    elif strategy == "recursive":
        return chunk_recursive(full_text, chunk_size, chunk_overlap)
    else:
        logger.warning(f"Unknown chunking strategy '{strategy}', using 'section'")
        return chunk_by_sections(full_text, chunk_size, chunk_overlap)
