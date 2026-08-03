#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gen_final_docs.py — Generate Final_Report.pdf and Final_Report.docx from
docs/Final_Report.md using only fpdf2 (PDF) and the Python standard library
(DOCX written as a minimal OOXML package with zipfile).

Usage:  python gen_final_docs.py
Output: docs/Final_Report.pdf, docs/Final_Report.docx
"""
import re
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
MD_PATH = ROOT / "docs" / "Final_Report.md"
PDF_OUT = ROOT / "docs" / "Final_Report.pdf"
DOCX_OUT = ROOT / "docs" / "Final_Report.docx"

FONT_DIR = Path(r"C:\Windows\Fonts")
ARIAL = FONT_DIR / "arial.ttf"
ARIAL_B = FONT_DIR / "arialbd.ttf"
ARIAL_I = FONT_DIR / "ariali.ttf"
ARIAL_BI = FONT_DIR / "arialbi.ttf"
CONSOLAS = FONT_DIR / "consola.ttf"
CONSOLAS_B = FONT_DIR / "consolab.ttf"


# --------------------------------------------------------------------------
# 1. Markdown block parsing (subset: headings, tables, code, bullets, hr, p)
# --------------------------------------------------------------------------

def parse_inline(text):
    """Split '**bold** `code` *italic* plain' into (text, style) runs."""
    runs = []
    pos = 0
    pattern = re.compile(r"(\*\*.*?\*\*|`[^`]*`|\*[^*]*?\*)")
    for m in pattern.finditer(text):
        if m.start() > pos:
            runs.append((text[pos:m.start()], "n"))
        token = m.group(0)
        if token.startswith("**"):
            runs.append((token[2:-2], "b"))
        elif token.startswith("`"):
            runs.append((token[1:-1], "c"))
        else:
            runs.append((token[1:-1], "i"))
        pos = m.end()
    if pos < len(text):
        runs.append((text[pos:], "n"))
    return runs


def strip_inline(text):
    return "".join(t for t, _ in parse_inline(text))


def parse_blocks(lines):
    """Yield (kind, payload) tuples."""
    blocks = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            # code fence
            code = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code.append(lines[i].rstrip("\n"))
                i += 1
            i += 1  # skip closing fence
            blocks.append(("code", "\n".join(code)))
            continue

        if stripped.startswith("#"):
            m = re.match(r"^(#+)\s+(.*)$", stripped)
            level = len(m.group(1))
            blocks.append((f"h{min(level, 4)}", strip_inline(m.group(2))))
            i += 1
            continue

        if stripped.startswith("|"):
            # table: consecutive pipe lines, skip separator row
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                blocks.append(("table", rows))
            continue

        if stripped.startswith("---") and len(stripped) >= 3:
            blocks.append(("hr", None))
            i += 1
            continue

        if stripped.startswith("- "):
            items = []
            while i < n and lines[i].strip().startswith("- "):
                items.append(lines[i].strip()[2:])
                i += 1
            blocks.append(("ul", items))
            continue

        if stripped == "":
            i += 1
            continue

        # paragraph (may span lines)
        para = []
        while i < n and lines[i].strip() != "" and not lines[i].strip().startswith(("```", "#", "|", "- ", "---")):
            para.append(lines[i].strip())
            i += 1
        blocks.append(("p", " ".join(para)))
    return blocks


# --------------------------------------------------------------------------
# 2. PDF rendering (fpdf2)
# --------------------------------------------------------------------------

def render_pdf(blocks):
    from fpdf import FPDF
    from fpdf.fonts import FontFace
    # fpdf2 >= 2.7 guarantees FontFace; None is the table() default if ever needed
    headings_style = FontFace(emphasis="BOLD")

    class ReportPDF(FPDF):
        def header(self):
            if self.page_no() > 1:
                self.set_font("Arial", "I", 8)
                self.set_text_color(140, 140, 140)
                self.cell(0, 6, "GraphRAG vs VectorRAG for PDF Question Answering — Final Report",
                          align="R")
                self.ln(4)

        def footer(self):
            self.set_y(-15)
            self.set_font("Arial", "", 8)
            self.set_text_color(140, 140, 140)
            self.cell(0, 10, f"Page {self.page_no()}", align="C")

    pdf = ReportPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(16, 16, 16)
    for path, style in ((ARIAL, ""), (ARIAL_B, "B"), (ARIAL_I, "I"), (ARIAL_BI, "BI")):
        if path.exists():
            pdf.add_font("Arial", style, str(path))
    for path, style in ((CONSOLAS, ""), (CONSOLAS_B, "B")):
        if path.exists():
            pdf.add_font("Consolas", style, str(path))

    pdf.add_page()
    usable = 210 - 32  # A4 width minus margins (mm)

    for kind, payload in blocks:
        if kind == "h1":
            pdf.set_font("Arial", "B", 19)
            pdf.set_text_color(25, 55, 110)
            pdf.multi_cell(0, 9, payload)
            pdf.ln(1)
        elif kind == "h2":
            pdf.ln(2)
            pdf.set_font("Arial", "B", 14)
            pdf.set_text_color(25, 55, 110)
            pdf.multi_cell(0, 8, payload)
            pdf.set_draw_color(25, 55, 110)
            pdf.line(pdf.l_margin, pdf.get_y() + 0.5, pdf.w - pdf.r_margin, pdf.get_y() + 0.5)
            pdf.ln(2)
        elif kind == "h3":
            pdf.set_font("Arial", "B", 12)
            pdf.set_text_color(40, 40, 40)
            pdf.multi_cell(0, 7, payload)
            pdf.ln(1)
        elif kind == "h4":
            pdf.set_font("Arial", "BI", 11)
            pdf.set_text_color(60, 60, 60)
            pdf.multi_cell(0, 7, payload)
            pdf.ln(1)
        elif kind == "p":
            pdf.set_font("Arial", "", 10.5)
            pdf.set_text_color(30, 30, 30)
            for text, style in parse_inline(payload):
                fstyle = {"b": "B", "i": "I", "c": ""}.get(style, "")
                if style == "c":
                    pdf.set_font("Consolas", "", 9.5)
                else:
                    pdf.set_font("Arial", fstyle, 10.5)
                pdf.write(5.5, text)
            pdf.ln(6)
        elif kind == "ul":
            pdf.set_font("Arial", "", 10.5)
            pdf.set_text_color(30, 30, 30)
            for item in payload:
                x0 = pdf.get_x()
                pdf.set_x(pdf.l_margin + 5)
                pdf.write(5.5, "\u2022  ")
                for text, style in parse_inline(item):
                    fstyle = {"b": "B", "i": "I"}.get(style, "")
                    if style == "c":
                        pdf.set_font("Consolas", "", 9.5)
                    else:
                        pdf.set_font("Arial", fstyle, 10.5)
                    pdf.write(5.5, text)
                pdf.ln(6)
        elif kind == "code":
            pdf.set_font("Consolas", "", 8.5)
            pdf.set_text_color(40, 60, 90)
            pdf.set_fill_color(244, 247, 252)
            lines = payload.split("\n")
            for ln_ in lines:
                pdf.cell(0, 4.4, ln_, fill=True, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
        elif kind == "table":
            rows = payload
            ncols = len(rows[0])
            # proportional column widths by content length
            lens = [max(len(strip_inline(r[c])) if c < len(r) else 1 for r in rows)
                    for c in range(ncols)]
            total = sum(lens) or 1
            widths = [max(18, usable * (l / total)) for l in lens]
            # rescale to usable
            scale = usable / sum(widths)
            widths = [w * scale for w in widths]
            pdf.set_font("Arial", "", 9)
            pdf.set_text_color(25, 25, 25)
            # headings_style resolved once per render_pdf() call above (None = fpdf2 default)
            with pdf.table(col_widths=widths, line_height=5.6,
                           headings_style=headings_style,
                           text_align="LEFT", padding=1.2) as table:
                for row in rows:
                    cells = table.row()
                    for ci in range(ncols):
                        txt = strip_inline(row[ci]) if ci < len(row) else ""
                        cells.cell(txt)
            pdf.ln(4)
        elif kind == "hr":
            pdf.set_draw_color(150, 150, 150)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(3)

    pdf.output(str(PDF_OUT))
    return pdf.pages_count


# --------------------------------------------------------------------------
# 3. DOCX rendering (minimal OOXML package, stdlib only)
# --------------------------------------------------------------------------

def inline_runs_to_ooxml(text, base_style=""):
    """Return list of (xml_rpr, text) run tuples for a paragraph."""
    out = []
    for t, style in parse_inline(text):
        rpr = []
        if style == "b":
            rpr.append("<w:b/>")
        elif style == "i":
            rpr.append("<w:i/>")
        if style == "c":
            rpr.append('<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>')
            rpr.append('<w:sz w:val="18"/>')
        out.append((rpr, t))
    return out


def para_ooxml(text, style=None, keep_bullet=False):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else "<w:pPr/>"
    runs = []
    if keep_bullet:
        runs.append(("<w:rFonts w:ascii=\"Arial\" w:hAnsi=\"Arial\"/>", "\u2022  "))
    for rpr, t in inline_runs_to_ooxml(text):
        rpr_xml = "".join(rpr)
        runs.append((rpr_xml, t))
    xml = f"<w:p>{ppr}" + "".join(
        f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{escape(t)}</w:t></w:r>'
        for rpr, t in runs) + "</w:p>"
    return xml


def code_para_ooxml(line):
    return ('<w:p><w:pPr><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>'
            f'<w:sz w:val="16"/></w:rPr></w:pPr>'
            f'<w:r><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="16"/></w:rPr>'
            f'<w:t xml:space="preserve">{escape(line)}</w:t></w:r></w:p>')


def table_ooxml(rows):
    ncols = len(rows[0])
    grid = "".join('<w:gridCol w:w="2400"/>' for _ in range(ncols))
    body = []
    for row in rows:
        cells = []
        for ci in range(ncols):
            txt = row[ci] if ci < len(row) else ""
            ppr = '<w:pPr><w:pStyle w:val="TableText"/></w:pPr>'
            runs = "".join(
                f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{escape(t)}</w:t></w:r>'
                for rpr, t in inline_runs_to_ooxml(txt))
            cells.append(
                f'<w:tc><w:tcPr><w:tcW w:w="2400" w:type="dxa"/></w:tcPr>'
                f'<w:p>{ppr}{runs}</w:p></w:tc>')
        body.append(f"<w:tr>{''.join(cells)}</w:tr>")
    return ('<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>'
            '<w:tblW w:w="0" w:type="auto"/></w:tblPr>'
            f'<w:tblGrid>{grid}</w:tblGrid>{"".join(body)}</w:tbl>'
            '<w:p><w:pPr><w:rPr><w:sz w:val="6"/></w:rPr></w:pPr></w:p>')


def render_docx(blocks):
    body = []
    for kind, payload in blocks:
        if kind == "h1":
            body.append(para_ooxml(payload, style="Title"))
        elif kind == "h2":
            body.append(para_ooxml(payload, style="Heading1"))
        elif kind == "h3":
            body.append(para_ooxml(payload, style="Heading2"))
        elif kind == "h4":
            body.append(para_ooxml(payload, style="Heading3"))
        elif kind == "p":
            body.append(para_ooxml(payload))
        elif kind == "ul":
            for item in payload:
                body.append(para_ooxml(item, keep_bullet=True))
        elif kind == "code":
            for line in payload.split("\n"):
                body.append(code_para_ooxml(line))
        elif kind == "table":
            body.append(table_ooxml(payload))
        elif kind == "hr":
            body.append('<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" '
                        'w:space="1" w:color="999999"/></w:pBdr></w:pPr></w:p>')

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>'
        + "".join(body) +
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr>'
        '</w:body></w:document>'
    )

    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/>'
        '<w:sz w:val="22"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/>'
        '<w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="120" w:after="240"/></w:pPr>'
        '<w:rPr><w:b/><w:sz w:val="36"/><w:color w:val="193951"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
        '<w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="360" w:after="120"/></w:pPr>'
        '<w:rPr><w:b/><w:sz w:val="28"/><w:color w:val="193951"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/>'
        '<w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="80"/></w:pPr>'
        '<w:rPr><w:b/><w:sz w:val="24"/><w:color w:val="2F5496"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/>'
        '<w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="160" w:after="60"/></w:pPr>'
        '<w:rPr><w:b/><w:i/><w:sz w:val="22"/><w:color w:val="404040"/></w:rPr></w:style>'
        '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/>'
        '<w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:color="BFBFBF"/>'
        '<w:left w:val="single" w:sz="4" w:color="BFBFBF"/>'
        '<w:bottom w:val="single" w:sz="4" w:color="BFBFBF"/>'
        '<w:right w:val="single" w:sz="4" w:color="BFBFBF"/>'
        '<w:insideH w:val="single" w:sz="4" w:color="BFBFBF"/>'
        '<w:insideV w:val="single" w:sz="4" w:color="BFBFBF"/></w:tblBorders></w:tblPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="TableText"><w:name w:val="Table Text"/>'
        '<w:basedOn w:val="Normal"/><w:rPr><w:sz w:val="19"/></w:rPr></w:style>'
        '</w:styles>'
    )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '</Types>'
    )

    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>'
    )

    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>'
    )

    with zipfile.ZipFile(str(DOCX_OUT), "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document_xml)
        z.writestr("word/styles.xml", styles_xml)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
    return True


# --------------------------------------------------------------------------
# 4. Main
# --------------------------------------------------------------------------

def main():
    if not MD_PATH.exists():
        print(f"ERROR: {MD_PATH} not found")
        return 1
    md_text = MD_PATH.read_text(encoding="utf-8")
    lines = md_text.splitlines()
    blocks = parse_blocks(lines)
    kinds = {}
    for k, _ in blocks:
        kinds[k] = kinds.get(k, 0) + 1
    print("Parsed blocks:", dict(sorted(kinds.items())))

    pages = render_pdf(blocks)
    print(f"PDF OK -> {PDF_OUT.name} ({pages} pages)")
    render_docx(blocks)
    print(f"DOCX OK -> {DOCX_OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
