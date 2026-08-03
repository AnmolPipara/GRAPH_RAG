"""
pdf_extractor.py — PDF Text & Image Extraction with Cleaning.

Extracts text and images from PDF files using PyMuPDF, then applies
comprehensive text cleaning and normalization to produce high-quality
input for the knowledge extraction pipeline.

Text cleaning preserves document structure (headings, sections, lists)
while removing noise (headers, footers, watermarks, excessive whitespace).
"""

import io
import os
import re
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

import fitz  # PyMuPDF
from PIL import Image, ImageStat

from config.settings import settings

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════════════════════


@dataclass
class ImageInfo:
    """Metadata and bytes for an extracted image."""
    image_bytes: bytes
    page_num: int
    width: int
    height: int


@dataclass
class PageContent:
    """Extracted content from a single PDF page."""
    page_num: int
    text: str
    images: List[ImageInfo] = field(default_factory=list)


@dataclass
class DocumentContent:
    """Complete extracted content from a PDF document."""
    filename: str
    total_pages: int
    pages: List[PageContent]
    full_text: str  # Cleaned, concatenated text across all pages


# ══════════════════════════════════════════════════════════════════════════════
# PDF LOADING
# ══════════════════════════════════════════════════════════════════════════════


def load_pdf(path: str) -> Optional[fitz.Document]:
    """Open a PDF file and return the document object.
    
    Args:
        path: Path to the PDF file.
        
    Returns:
        PyMuPDF Document object, or None on failure.
    """
    try:
        if not os.path.exists(path):
            logger.error(f"PDF not found at: {path}")
            return None
        doc = fitz.open(path)
        logger.info(f"Loaded PDF: {path} ({len(doc)} pages)")
        return doc
    except Exception as e:
        logger.error(f"Failed to load PDF: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# TEXT EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════


def extract_text_from_page(page: fitz.Page) -> str:
    """Extract raw text from a single PDF page.
    
    Uses PyMuPDF's text extraction which preserves reading order.
    """
    try:
        return page.get_text("text").strip()
    except Exception as e:
        logger.error(f"Failed to extract text from page: {e}")
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# TEXT CLEANING & NORMALIZATION
# ══════════════════════════════════════════════════════════════════════════════


def clean_text(text: str) -> str:
    """Apply comprehensive text cleaning while preserving document structure.
    
    Cleaning steps:
    1. Normalize Unicode characters (smart quotes, dashes, etc.)
    2. Remove page headers/footers (repetitive single-line patterns)
    3. Remove excessive whitespace while preserving paragraph breaks
    4. Remove decorative lines (═══, ---, *** etc.)
    5. Normalize bullet points and list markers
    6. Collapse multiple blank lines to a single separator
    7. Strip control characters except newlines and tabs
    
    Args:
        text: Raw extracted text from PDF.
        
    Returns:
        Cleaned and normalized text.
    """
    if not text:
        return ""

    # Step 1: Normalize Unicode
    text = _normalize_unicode(text)

    # Step 2: Strip control characters (except \n, \t, \r)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)

    # Step 3: Remove decorative lines
    text = re.sub(r"^[═━─\-_=~*]{3,}\s*$", "", text, flags=re.MULTILINE)

    # Step 4: Normalize whitespace within lines (preserve newlines)
    text = re.sub(r"[^\S\n]+", " ", text)

    # Step 5: Remove likely page numbers (standalone numbers on a line)
    text = re.sub(r"^\s*\d{1,3}\s*$", "", text, flags=re.MULTILINE)

    # Step 6: Normalize bullet points
    text = re.sub(r"^[\s]*[•●◦▪▸►‣⁃]\s*", "• ", text, flags=re.MULTILINE)

    # Step 7: Collapse multiple blank lines to double newline (paragraph break)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Step 8: Strip leading/trailing whitespace on each line
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    # Step 9: Final trim
    text = text.strip()

    return text


def _normalize_unicode(text: str) -> str:
    """Normalize common Unicode variants to ASCII equivalents."""
    replacements = {
        "\u2018": "'",   # Left single quote
        "\u2019": "'",   # Right single quote
        "\u201c": '"',   # Left double quote
        "\u201d": '"',   # Right double quote
        "\u2013": "-",   # En dash
        "\u2014": " - ", # Em dash
        "\u2026": "...", # Ellipsis
        "\u00a0": " ",   # Non-breaking space
        "\u200b": "",    # Zero-width space
        "\u200c": "",    # Zero-width non-joiner
        "\u200d": "",    # Zero-width joiner
        "\ufeff": "",    # Byte order mark
        "\u00ad": "",    # Soft hyphen
        "\u2212": "-",   # Minus sign
        "\u00d7": "x",   # Multiplication sign
        "\u2022": "•",   # Bullet
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def remove_headers_footers(pages_text: List[str], threshold: int = 3) -> List[str]:
    """Remove recurring headers and footers across pages.
    
    Detects lines that appear on multiple pages (near the top or bottom)
    and removes them, as these are typically page headers/footers.
    
    Args:
        pages_text: List of raw text strings, one per page.
        threshold: Minimum number of pages a line must appear on to be
                   considered a header/footer.
                   
    Returns:
        List of cleaned text strings with headers/footers removed.
    """
    if len(pages_text) < threshold:
        return pages_text

    # Count first and last lines across pages
    first_lines = {}
    last_lines = {}

    for text in pages_text:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if not lines:
            continue

        # Check first 2 and last 2 lines
        for line in lines[:2]:
            normalized = line.lower().strip()
            if len(normalized) > 5:  # Ignore very short lines
                first_lines[normalized] = first_lines.get(normalized, 0) + 1

        for line in lines[-2:]:
            normalized = line.lower().strip()
            if len(normalized) > 5:
                last_lines[normalized] = last_lines.get(normalized, 0) + 1

    # Lines appearing on >= threshold pages are headers/footers
    header_patterns = {k for k, v in first_lines.items() if v >= threshold}
    footer_patterns = {k for k, v in last_lines.items() if v >= threshold}
    all_patterns = header_patterns | footer_patterns

    if all_patterns:
        logger.info(f"Detected {len(all_patterns)} header/footer patterns to remove")

    cleaned = []
    for text in pages_text:
        lines = text.split("\n")
        filtered = [
            line for line in lines
            if line.strip().lower().strip() not in all_patterns
        ]
        cleaned.append("\n".join(filtered))

    return cleaned


# ══════════════════════════════════════════════════════════════════════════════
# IMAGE EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════


def is_image_valid(pil_image: Image.Image, min_size: int = None) -> bool:
    """Check if an image is valid — not too small and not blank.
    
    Args:
        pil_image: PIL Image object.
        min_size: Minimum pixel dimension. Defaults to settings.MIN_IMAGE_SIZE.
        
    Returns:
        True if the image passes validation.
    """
    if min_size is None:
        min_size = settings.MIN_IMAGE_SIZE

    width, height = pil_image.size
    if width < min_size or height < min_size:
        return False

    try:
        stat = ImageStat.Stat(pil_image)
        # Very low variance = nearly blank image
        if sum(stat.var) < 10:
            return False
    except Exception:
        pass

    return True


def extract_images_from_page(page: fitz.Page, page_num: int) -> List[ImageInfo]:
    """Extract valid images from a PDF page.
    
    Args:
        page: PyMuPDF Page object.
        page_num: 0-indexed page number.
        
    Returns:
        List of ImageInfo objects for valid images.
    """
    images = []
    try:
        image_list = page.get_images(full=True)
        for img_idx, img_info in enumerate(image_list):
            xref = img_info[0]
            try:
                base_image = page.parent.extract_image(xref)
                if base_image is None:
                    continue
                image_bytes = base_image["image"]
                pil_image = Image.open(io.BytesIO(image_bytes))
                if not is_image_valid(pil_image):
                    continue
                images.append(ImageInfo(
                    image_bytes=image_bytes,
                    page_num=page_num + 1,  # 1-indexed
                    width=pil_image.width,
                    height=pil_image.height,
                ))
            except Exception as e:
                logger.warning(
                    f"Could not extract image {img_idx} from page {page_num + 1}: {e}"
                )
    except Exception as e:
        logger.error(f"Error reading images on page {page_num + 1}: {e}")
    return images


# ══════════════════════════════════════════════════════════════════════════════
# MAIN EXTRACTION FUNCTION
# ══════════════════════════════════════════════════════════════════════════════


def extract_document(pdf_path: str, extract_images: bool = True) -> Optional[DocumentContent]:
    """Extract and clean all content from a PDF document.
    
    This is the main entry point for Step 1 + Step 2 of the pipeline:
    1. Load PDF with PyMuPDF
    2. Extract text per page
    3. Remove headers/footers
    4. Clean and normalize text
    5. Optionally extract images
    
    Args:
        pdf_path: Path to the PDF file.
        extract_images: Whether to extract images from pages.
        
    Returns:
        DocumentContent with cleaned text and images, or None on failure.
    """
    doc = load_pdf(pdf_path)
    if doc is None:
        return None

    filename = os.path.basename(pdf_path)
    total_pages = len(doc)

    # Extract raw text from each page
    raw_texts = []
    page_images = []

    logger.info("Extracting text and images from PDF...")
    for page_num in range(total_pages):
        try:
            page = doc[page_num]
            text = extract_text_from_page(page)
            raw_texts.append(text)

            if extract_images:
                imgs = extract_images_from_page(page, page_num)
                page_images.append(imgs)
            else:
                page_images.append([])

            logger.debug(
                f"Page {page_num + 1}: {len(text)} chars, "
                f"{len(page_images[-1])} images"
            )
        except Exception as e:
            logger.error(f"Failed to process page {page_num + 1}: {e}")
            raw_texts.append("")
            page_images.append([])

    # Remove headers/footers across pages
    cleaned_texts = remove_headers_footers(raw_texts)

    # Clean each page's text
    cleaned_texts = [clean_text(t) for t in cleaned_texts]

    # Build page contents
    pages = []
    for page_num in range(total_pages):
        pages.append(PageContent(
            page_num=page_num + 1,  # 1-indexed
            text=cleaned_texts[page_num],
            images=page_images[page_num],
        ))

    # Concatenate full text with page markers
    full_text_parts = []
    for p in pages:
        if p.text:
            full_text_parts.append(f"[PAGE {p.page_num}]\n{p.text}")
    full_text = "\n\n".join(full_text_parts)

    total_chars = sum(len(p.text) for p in pages)
    total_images = sum(len(p.images) for p in pages)
    logger.info(
        f"Extraction complete: {total_pages} pages, "
        f"{total_chars} chars, {total_images} images"
    )

    doc.close()

    return DocumentContent(
        filename=filename,
        total_pages=total_pages,
        pages=pages,
        full_text=full_text,
    )
