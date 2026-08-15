#!/usr/bin/env python3
"""Convert PROJECT_REPORT.md into a PDF matching the style of docs/Final_Project_Report.pdf.

Reproduces the Freebuff report-generator look: A4 pages, Arial fonts, a title page,
a dot-leader Table of Contents, ArialBold 15/12 headings with an accent underline,
justified 10.5pt body text, tables with a light-blue header row and gray borders,
Consolas code blocks, and centered "Page N" footers.

Usage:  python scripts/md_to_pdf.py [path/to/PROJECT_REPORT.md] [path/to/output.pdf]
"""

import os
import sys

from fpdf import FPDF
from markdown_it import MarkdownIt

FONT_DIR = "C:/Windows/Fonts"
ARIAL = os.path.join(FONT_DIR, "arial.ttf")
ARIAL_B = os.path.join(FONT_DIR, "arialbd.ttf")
ARIAL_I = os.path.join(FONT_DIR, "ariali.ttf")
ARIAL_BI = os.path.join(FONT_DIR, "arialbi.ttf")
CONSOLAS = os.path.join(FONT_DIR, "consola.ttf")
SEGUIEMJ = os.path.join(FONT_DIR, "seguiemj.ttf")
SEGUISYM = os.path.join(FONT_DIR, "seguisym.ttf")

# ---- page geometry (from Final_Project_Report.pdf) ----
PAGE_W, PAGE_H = 595.28, 841.89  # A4
ML = 59.5                        # left margin
TEXT_W = 476.28                  # usable text width
TOP = 60.0                       # top margin
BOTTOM = 788.0                   # content bottom limit (before footer)
TABLE_X = 56.7                   # tables are a touch wider than the text column
TABLE_W = 481.9
TABLE_HEADER_FILL = (0.871, 0.906, 0.961)  # light blue
TABLE_BORDER = (0.588, 0.588, 0.588)       # gray
ACCENT = (0.184, 0.439, 0.690)             # blue H1 underline

BODY = 10.5
BODY_LH = 15.6
H1 = 15.0
H2 = 12.0
INLINE_CODE = 9.5
TABLE_FONT = 8.0
TABLE_ROW = 18.7
TABLE_PAD = 6.2
CODE = 8.5
CODE_LH = 11.9
FOOTER_Y = 816.2

TITLE_PAGE = 1
TOC_PAGE = 2


def register_fonts(pdf):
    pdf.add_font("Arial", "", ARIAL)
    pdf.add_font("Arial", "B", ARIAL_B)
    pdf.add_font("Arial", "I", ARIAL_I)
    pdf.add_font("Arial", "BI", ARIAL_BI)
    pdf.add_font("Consolas", "", CONSOLAS)
    pdf.add_font("SegoeUIEmoji", "", SEGUIEMJ)
    pdf.add_font("SegoeUISymbol", "", SEGUISYM)
    pdf.set_fallback_fonts(["SegoeUIEmoji", "SegoeUISymbol"])


class ReportPDF(FPDF):
    def footer(self):
        if self.page_no() >= 3:
            self.set_font("Arial", "", 9.0)
            t = f"Page {self.page_no()}"
            self.set_text_color(0, 0, 0)
            self.text(PAGE_W / 2 - self.get_string_width(t) / 2, FOOTER_Y, t)


# --------------------------------------------------------------------------
# markdown -> block/token model
# --------------------------------------------------------------------------

def inline_runs(tokens):
    """Flatten markdown-it inline children into [(text, style)] runs."""
    runs = []
    stack = {"b": False, "i": False}
    in_code = False

    def current_style():
        if in_code:
            return "c" + ("b" if stack["b"] else "") + ("i" if stack["i"] else "")
        return ("b" if stack["b"] else "") + ("i" if stack["i"] else "") or "n"

    def emit(text):
        if not text:
            return
        style = current_style()
        if runs and runs[-1][1] == style:
            runs[-1] = (runs[-1][0] + text, style)
        else:
            runs.append((text, style))

    for tk in tokens:
        if tk.type == "text":
            emit(tk.content)
        elif tk.type == "code_inline":
            in_code = True
            emit(tk.content)
            in_code = False
        elif tk.type == "softbreak":
            emit(" ")
        elif tk.type == "hardbreak":
            emit(" ")
        elif tk.type in ("strong_open", "em_open"):
            stack[tk.type[0]] = True
        elif tk.type in ("strong_close", "em_close"):
            stack[tk.type[0]] = False
    return runs


def plain_text(runs):
    return "".join(t for t, _ in runs)


def parse_md(path):
    """Return a list of block dicts understood by the renderer."""
    md = MarkdownIt("commonmark", {"html": True}).enable("table")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    tokens = md.parse(text)
    blocks = []
    i = 0
    n = len(tokens)

    def skip_block(depth_close_types):
        nonlocal i
        depth = 0
        while i < n:
            t = tokens[i]
            if t.type in depth_close_types:
                depth -= 1
                if depth == 0:
                    i += 1
                    return
            elif t.type in depth_open_types:
                depth += 1
            i += 1

    while i < n:
        t = tokens[i]
        if t.type == "heading_open":
            level = int(t.tag[1])
            i += 1
            runs = inline_runs(tokens[i].children) if i < n and tokens[i].type == "inline" else []
            i += 1
            while i < n and tokens[i].type == "heading_close":
                i += 1
            blocks.append({"type": "heading", "level": level, "runs": runs})
        elif t.type == "paragraph_open":
            i += 1
            runs = inline_runs(tokens[i].children) if i < n and tokens[i].type == "inline" else []
            i += 1
            while i < n and tokens[i].type == "paragraph_close":
                i += 1
            blocks.append({"type": "paragraph", "runs": runs})
        elif t.type == "bullet_list_open":
            items = []
            i += 1
            while i < n and tokens[i].type != "bullet_list_close":
                if tokens[i].type == "list_item_open":
                    i += 1
                    runs = []
                    while i < n and tokens[i].type != "list_item_close":
                        if tokens[i].type == "paragraph_open":
                            i += 1
                            if i < n and tokens[i].type == "inline":
                                runs = inline_runs(tokens[i].children)
                            i += 1
                            while i < n and tokens[i].type == "paragraph_close":
                                i += 1
                        else:
                            i += 1
                    items.append(runs)
                    i += 1
                else:
                    i += 1
            i += 1  # bullet_list_close
            blocks.append({"type": "list", "ordered": False, "items": items})
        elif t.type == "ordered_list_open":
            items = []
            i += 1
            while i < n and tokens[i].type != "ordered_list_close":
                if tokens[i].type == "list_item_open":
                    i += 1
                    runs = []
                    while i < n and tokens[i].type != "list_item_close":
                        if tokens[i].type == "paragraph_open":
                            i += 1
                            if i < n and tokens[i].type == "inline":
                                runs = inline_runs(tokens[i].children)
                            i += 1
                            while i < n and tokens[i].type == "paragraph_close":
                                i += 1
                        else:
                            i += 1
                    items.append(runs)
                    i += 1
                else:
                    i += 1
            i += 1  # ordered_list_close
            blocks.append({"type": "list", "ordered": True, "items": items})
        elif t.type == "blockquote_open":
            runs = []
            i += 1
            while i < n and tokens[i].type != "blockquote_close":
                if tokens[i].type == "paragraph_open":
                    i += 1
                    if i < n and tokens[i].type == "inline":
                        runs = inline_runs(tokens[i].children)
                    i += 1
                    while i < n and tokens[i].type == "paragraph_close":
                        i += 1
                else:
                    i += 1
            i += 1
            blocks.append({"type": "quote", "runs": runs})
        elif t.type == "fence":
            blocks.append({"type": "code", "content": t.content.rstrip("\n")})
            i += 1
        elif t.type == "table_open":
            header = []
            body = []
            i += 1
            in_header = False
            while i < n and tokens[i].type != "table_close":
                tt = tokens[i].type
                if tt == "thead_open":
                    in_header = True
                elif tt == "thead_close":
                    in_header = False
                elif tt == "tr_open":
                    row = []
                    i += 1
                    while i < n and tokens[i].type != "tr_close":
                        if tokens[i].type in ("th_open", "td_open"):
                            i += 1
                            cell_runs = inline_runs(tokens[i].children) if i < n and tokens[i].type == "inline" else []
                            i += 1
                            while i < n and tokens[i].type in ("th_close", "td_close"):
                                i += 1
                            row.append(cell_runs)
                        else:
                            i += 1
                    if in_header:
                        header = row
                    else:
                        body.append(row)
                    i += 1
                else:
                    i += 1
            i += 1
            if header or body:
                blocks.append({"type": "table", "header": header, "rows": body})
        elif t.type == "hr":
            i += 1  # skip horizontal rules (no visible rule in the reference PDF)
        elif t.type in ("code_block",):
            blocks.append({"type": "code", "content": t.content.rstrip("\n")})
            i += 1
        else:
            i += 1
    return blocks


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def set_font_for(pdf, style, size):
    """Map a run style (n/b/i/bi/c/bc/ic/bic) to an Arial variant + size."""
    bold = "b" in style
    ital = "i" in style
    variant = "BI" if (bold and ital) else ("B" if bold else ("I" if ital else ""))
    if "c" in style:
        pdf.set_font("Arial", variant, INLINE_CODE if size is None else size)
    else:
        pdf.set_font("Arial", variant, size)


def _word_items(runs, size, prefix=""):
    """Flatten runs into [(word, style, width)] plus the space width."""
    words = []
    if prefix:
        words.append((prefix, "n"))
    for text, style in runs:
        for part in text.split(" "):
            if part:
                words.append((part, style))
    widths = []
    for word, style in words:
        set_font_for(pdf if False else _SIZER, style, size)
        widths.append(_SIZER.get_string_width(word))
    return words, widths


# module-level measuring pdf (fonts are the same, measuring doesn't need pages)
_SIZER = None


def ensure_sizer(pdf):
    global _SIZER
    if _SIZER is None:
        s = ReportPDF(format="A4")
        register_fonts(s)
        _SIZER = s


def render_paragraph(pdf, runs, size=BODY, lh=BODY_LH, x=ML, w=TEXT_W,
                     prefix="", justify=True, italic=False):
    """Draw a wrapped, justified paragraph of styled runs."""
    ensure_sizer(pdf)
    words = []
    if prefix:
        words.append((prefix, "n"))
    for text, style in runs:
        for part in text.split(" "):
            if part:
                words.append((part, style))
    if not words:
        return
    widths = []
    for word, style in words:
        if italic and style == "n":
            style = "i"
        if italic and style == "c":
            style = "ic"
        set_font_for(_SIZER, style, size)
        widths.append(_SIZER.get_string_width(word))
    set_font_for(_SIZER, "n", size)
    space_w = _SIZER.get_string_width(" ")

    # greedy line building
    lines = []
    cur, cur_w = [], 0.0
    for (word, style), wd in zip(words, widths):
        need = wd if not cur else wd + space_w
        if cur and cur_w + need > w:
            lines.append((cur, cur_w))
            cur, cur_w = [], 0.0
            need = wd
        cur.append((word, style, wd))
        cur_w += need
    if cur:
        lines.append((cur, cur_w))

    for li, (lwords, lw) in enumerate(lines):
        if pdf.get_y() + lh > BOTTOM:
            pdf.add_page()
            pdf.set_y(TOP + 4)
        pdf.set_x(x)
        last = li == len(lines) - 1
        if len(lwords) == 1 or (last and not justify):
            for word, style, wd in lwords:
                set_font_for(pdf, style, size)
                pdf.cell(wd, lh, word)
                pdf.cell(space_w, lh, " ")
            pdf.ln(lh)
        elif last:
            # last line of a justified paragraph: left aligned
            for word, style, wd in lwords:
                set_font_for(pdf, style, size)
                pdf.cell(wd, lh, word)
                pdf.cell(space_w, lh, " ")
            pdf.ln(lh)
        else:
            slack = w - lw
            extra = slack / (len(lwords) - 1)
            for k, (word, style, wd) in enumerate(lwords):
                set_font_for(pdf, style, size)
                pdf.cell(wd, lh, word)
                if k < len(lwords) - 1:
                    pdf.cell(space_w + extra, lh, " ")
            pdf.ln(lh)


def render_heading(pdf, level, runs, headings=None):
    text = plain_text(runs)
    if level == 2:
        if headings is not None:
            headings.append({"level": 2, "text": text, "page": pdf.page_no()})
        size, lh, before = H1, 18.0, 14.0
        after = 6.0
    else:
        if headings is not None:
            headings.append({"level": 3, "text": text, "page": pdf.page_no()})
        size, lh, before = H2, 14.4, 11.0
        after = 3.0

    if pdf.get_y() + before + lh + after + 4 > BOTTOM:
        pdf.add_page()
        pdf.set_y(TOP + 4)
        pdf.ln(before * 0.5)
    else:
        pdf.ln(before)

    pdf.set_x(ML)
    set_font_for(pdf, "n" if level == 2 else "n", size)
    pdf.set_font("Arial", "B", size)
    pdf.cell(TEXT_W, lh, text)
    if level == 2:
        # accent underline just below the heading baseline
        pdf.set_draw_color(*[int(c * 255) for c in ACCENT])
        pdf.set_line_width(1.0)
        y = pdf.get_y() + 3.0
        pdf.line(TABLE_X, y, TABLE_X + TABLE_W, y)
    pdf.ln(after + 1)


def render_table(pdf, header, rows):
    ensure_sizer(pdf)
    ncols = max(len(header), max((len(r) for r in rows), default=0))
    header = header + [[]] * (ncols - len(header))
    rows = [r + [[]] * (ncols - len(r)) for r in rows]
    all_rows = [header] + rows

    # measure raw column widths
    set_font_for(_SIZER, "n", TABLE_FONT)
    raws = [0.0] * ncols
    for row in all_rows:
        for c in range(ncols):
            txt = plain_text(row[c])
            raws[c] = max(raws[c], _SIZER.get_string_width(txt))
    total_raw = sum(raws) or 1.0
    target = TABLE_W - 2 * TABLE_PAD * ncols
    ws = [max(raw / total_raw * target, 40.0) for raw in raws]
    scale = target / sum(ws)
    ws = [w * scale for w in ws]

    # compute row heights (wrapped lines)
    row_heights = []
    for row in all_rows:
        max_lines = 1
        for c in range(ncols):
            lines = _wrap_count(row[c], ws[c] - 2 * TABLE_PAD, TABLE_FONT)
            max_lines = max(max_lines, lines)
        row_heights.append(max_lines * TABLE_ROW)

    if pdf.get_y() + sum(row_heights) + 10 > BOTTOM:
        pdf.add_page()
        pdf.set_y(TOP + 4)

    pdf.ln(2)
    for ri, row in enumerate(all_rows):
        h = row_heights[ri]
        for c in range(ncols):
            x0 = TABLE_X + sum(ws[:c])
            fill = TABLE_HEADER_FILL if ri == 0 else (1, 1, 1)
            pdf.set_fill_color(*[int(v * 255) for v in fill])
            pdf.set_draw_color(*[int(v * 255) for v in TABLE_BORDER])
            pdf.set_line_width(0.3)
            pdf.rect(x0, pdf.get_y(), ws[c], h, style="FD")
        _draw_cell_text(pdf, row, ws, h)
        pdf.set_y(pdf.get_y() + h)
    pdf.ln(4)


def _wrap_count(runs, w, size):
    ensure_sizer(pdf if False else _SIZER)
    words = []
    for text, style in runs:
        for part in text.split(" "):
            if part:
                words.append((part, style))
    if not words:
        return 1
    widths = []
    for word, style in words:
        set_font_for(_SIZER, style, size)
        widths.append(_SIZER.get_string_width(word))
    set_font_for(_SIZER, "n", size)
    space_w = _SIZER.get_string_width(" ")
    lines = 1
    cur_w = 0.0
    for wd in widths:
        need = wd if cur_w == 0 else wd + space_w
        if cur_w + need > w:
            lines += 1
            cur_w = wd
        else:
            cur_w += need
    return lines


def _draw_cell_text(pdf, row, ws, h):
    set_font_for(pdf, "n", TABLE_FONT)
    max_lines = h // TABLE_ROW
    for c, cell in enumerate(row):
        words = []
        for text, style in cell:
            for part in text.split(" "):
                if part:
                    words.append((part, style))
        if not words:
            continue
        widths = []
        for word, style in words:
            set_font_for(_SIZER, style, TABLE_FONT)
            widths.append(_SIZER.get_string_width(word))
        set_font_for(_SIZER, "n", TABLE_FONT)
        space_w = _SIZER.get_string_width(" ")
        avail = ws[c] - 2 * TABLE_PAD
        # wrap into lines
        lines = []
        cur, cur_w = [], 0.0
        for (word, style), wd in zip(words, widths):
            need = wd if not cur else wd + space_w
            if cur and cur_w + need > avail:
                lines.append(cur)
                cur, cur_w = [], 0.0
                need = wd
            cur.append((word, style, wd))
            cur_w += need
        if cur:
            lines.append(cur)
        x0 = TABLE_X + sum(ws[:c]) + TABLE_PAD
        for li, lwords in enumerate(lines[:max_lines]):
            pdf.set_xy(x0, pdf.get_y() + li * TABLE_ROW)
            for word, style, wd in lwords:
                set_font_for(pdf, style, TABLE_FONT)
                pdf.cell(wd, TABLE_ROW, word)
                pdf.cell(space_w, TABLE_ROW, " ")


def render_code(pdf, content):
    lines = content.split("\n")
    need = len(lines) * CODE_LH + 8
    if pdf.get_y() + need > BOTTOM:
        pdf.add_page()
        pdf.set_y(TOP + 4)
    pdf.ln(2)
    pdf.set_font("Consolas", "", CODE)
    for line in lines:
        pdf.set_x(ML + 8.5)
        pdf.cell(TEXT_W - 17, CODE_LH, line)
        pdf.ln(CODE_LH)
    pdf.ln(2)


def render_quote(pdf, runs):
    # italic, indented
    render_paragraph(pdf, runs, x=ML + 17, w=TEXT_W - 17, italic=True, justify=False)


def layout_content(pdf, blocks, headings=None):
    """Render all content blocks. If headings is a list, append TOC entries."""
    for b in blocks:
        if b["type"] == "paragraph":
            text = plain_text(b["runs"])
            if text.startswith("Project:") or text.startswith("Document:") or text.startswith("Date:"):
                continue  # title-page meta block
            render_paragraph(pdf, b["runs"])
        elif b["type"] == "heading":
            render_heading(pdf, b["level"], b["runs"], headings)
        elif b["type"] == "list":
            for idx, item in enumerate(b["items"]):
                prefix = ("  •  " if not b["ordered"] else f"  {idx + 1}. ")
                render_paragraph(pdf, item, prefix=prefix)
        elif b["type"] == "table":
            render_table(pdf, b["header"], b["rows"])
        elif b["type"] == "code":
            render_code(pdf, b["content"])
        elif b["type"] == "quote":
            render_quote(pdf, b["runs"])
        elif b["type"] == "hr":
            pass
    return headings


# --------------------------------------------------------------------------
# front matter: title page + TOC
# --------------------------------------------------------------------------

def title_page(pdf):
    pdf.add_page()
    pdf.set_text_color(0, 0, 0)

    def centered(text, y, font, style, size):
        pdf.set_font(font, style, size)
        pdf.text(PAGE_W / 2 - pdf.get_string_width(text) / 2, y, text)

    centered("Vector RAG vs GraphRAG", 223.2, "Arial", "B", 26)
    centered("Complete Project Report", 257.2, "Arial", "B", 26)
    subtitle = [
        "A comparative study of two retrieval-augmented generation (RAG) paradigms",
        "on a single-source technical document",
        "ISO 20022 Payments Guide 2025 (61 pages, PDF)",
        "August 2026",
    ]
    for k, line in enumerate(subtitle):
        centered(line, 470.7 + k * 17.0, "Arial", "I", 10)


def toc_page(pdf, entries):
    pdf.add_page()
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", "B", 16)
    pdf.set_xy(ML, 75.7)
    pdf.cell(TEXT_W, 18, "Table of Contents")
    y = 108.2
    for level, text, page in entries:
        if y > BOTTOM:
            pdf.add_page()
            pdf.set_y(TOP + 4)
            y = pdf.get_y()
        if level == 2:
            pdf.set_font("Arial", "B", 11)
            x0, lh = ML, 19.9
        else:
            pdf.set_font("Arial", "", 10.5)
            x0, lh = ML + 17, 19.9
        pdf.set_xy(x0, y - 13.9)
        pdf.cell(pdf.get_string_width(text), lh, text)
        x_after = pdf.get_x()
        dot_end = 522.2
        gap = dot_end - x_after
        if gap > 4:
            dot_w = pdf.get_string_width(".")
            n_dots = max(1, int(gap / dot_w))
            pdf.cell(gap, lh, "." * n_dots, align="R")
        pdf.set_x(524.2)
        pdf.cell(pdf.get_string_width(str(page)), lh, str(page))
        y += lh
        pdf.set_y(y - lh)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def build(md_path, out_path):
    blocks = parse_md(md_path)

    # pass 1: layout content alone to learn heading page numbers
    p1 = ReportPDF(format="A4")
    register_fonts(p1)
    p1.set_auto_page_break(False)
    p1.set_margins(0, 0, 0)
    headings = layout_content(p1, blocks, headings=[])
    toc_entries = []
    for h in headings:
        toc_entries.append((h["level"], h["text"], h["page"] + 2))  # + title + TOC pages

    # pass 2: final document
    pdf = ReportPDF(format="A4")
    register_fonts(pdf)
    pdf.set_auto_page_break(False)
    pdf.set_margins(0, 0, 0)
    pdf.set_title("Vector RAG vs GraphRAG - Complete Project Report")
    pdf.set_creator("Freebuff report generator")
    title_page(pdf)
    toc_page(pdf, toc_entries)
    layout_content(pdf, blocks)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    pdf.output(out_path)
    print(f"Wrote {out_path} ({pdf.page_no()} pages)")


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    md_in = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "PROJECT_REPORT.md")
    pdf_out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(root, "docs", "PROJECT_REPORT.pdf")
    build(md_in, pdf_out)
