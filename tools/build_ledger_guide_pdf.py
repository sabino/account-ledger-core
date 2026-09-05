#!/usr/bin/env python3
"""Build the separate Go guide. Never writes the submitted assessment PDF.

Supports the deliberately small Markdown subset in docs/ledger-lab-guide.md:
headings, paragraphs, bullets, tables, text diagrams, images and page markers.
"""

from html import escape
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, PageBreak, Paragraph, Preformatted, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/ledger-lab-guide.md"
OUTPUT = ROOT / "output/pdf/ledger-lab-implementation-guide.pdf"
WIDTH = A4[0] - 36 * mm
INK = colors.HexColor("#182B45")
BLUE = colors.HexColor("#365B9B")
MUTED = colors.HexColor("#54647B")
PALE = colors.HexColor("#EDF2FA")
LINE = colors.HexColor("#D7E0EE")
REPO_URL = "https://github.com/sabino/account-ledger-core/blob/feat/go-ledger-service/"


def inline(text):
    text = text.translate(str.maketrans({"–": "-", "—": "-", "−": "-", "’": "'", "“": '"', "”": '"'}))
    text = escape(text, quote=False)

    def link(match):
        label, target = match.groups()
        if not target.startswith(("https://", "http://")):
            path = (SOURCE.parent / target).resolve().relative_to(ROOT)
            target = REPO_URL + path.as_posix()
        return f'<link href="{escape(target, quote=True)}" color="#365B9B"><u>{label}</u></link>'

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', text)


def styles():
    base = ParagraphStyle("body", fontName="Helvetica", fontSize=9.3, leading=13,
                          textColor=INK, spaceAfter=7, alignment=TA_LEFT)
    return {
        "body": base,
        "title": ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=34, leading=39, spaceAfter=14),
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=24, spaceAfter=14, keepWithNext=True),
        "h3": ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=11.5, leading=15, spaceBefore=7, spaceAfter=6, keepWithNext=True),
        "bullet": ParagraphStyle("bullet", parent=base, leftIndent=11, firstLineIndent=0, bulletIndent=0),
        "cell": ParagraphStyle("cell", parent=base, fontSize=8, leading=10.5, spaceAfter=0),
        "code": ParagraphStyle("code", fontName="Courier", fontSize=8.3, leading=11.5, textColor=INK, backColor=PALE, borderPadding=10, spaceBefore=4, spaceAfter=14),
        "caption": ParagraphStyle("caption", parent=base, fontSize=8, leading=11, textColor=MUTED),
    }


def markdown_table(lines, style):
    rows = [line.strip().strip("|").split("|") for line in lines]
    rows = [row for row in rows if not all(re.fullmatch(r"\s*:?-+:?\s*", cell) for cell in row)]
    if not rows or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError("Inconsistent table columns")
    cells = [[Paragraph(inline(cell.strip()), style["cell"]) for cell in row] for row in rows]
    table = Table(cells, colWidths=[WIDTH / len(cells[0])] * len(cells[0]), repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, BLUE),
        ("LINEBELOW", (0, 1), (-1, -1), 0.35, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def story_from_markdown():
    style = styles()
    lines = SOURCE.read_text().splitlines()
    story = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        if line == "<!-- page -->":
            story.append(PageBreak())
            continue
        if line.startswith("```"):
            code = []
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            if i == len(lines):
                raise ValueError("Unclosed code fence")
            i += 1
            story.append(Preformatted("\n".join(code), style["code"]))
            continue
        picture = re.fullmatch(r"!\[([^]]*)\]\(([^)]+)\)", line)
        if picture:
            caption, relative = picture.groups()
            asset = (SOURCE.parent / relative).resolve()
            asset.relative_to(ROOT)
            img = Image(str(asset))
            ratio = min(WIDTH / img.imageWidth, 110 * mm / img.imageHeight)
            img.drawWidth, img.drawHeight = img.imageWidth * ratio, img.imageHeight * ratio
            img.hAlign = "LEFT"
            story.extend([img, Spacer(1, 5), Paragraph(inline(caption), style["caption"])])
            continue
        if line.startswith("|"):
            table_lines = [line]
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            story.extend([markdown_table(table_lines, style), Spacer(1, 10)])
            continue
        for prefix, key in [("### ", "h3"), ("## ", "h2"), ("# ", "title"), ("- ", "bullet")]:
            if line.startswith(prefix):
                story.append(Paragraph(inline(line[len(prefix):]), style[key], bulletText="-" if key == "bullet" else None))
                break
        else:
            paragraph = [line]
            while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", "- ", "|", "```", "<!--", "![")):
                paragraph.append(lines[i].strip())
                i += 1
            story.append(Paragraph(inline(" ".join(paragraph)), style["body"]))
    return story


def chrome(canvas, document):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(18 * mm, A4[1] - 15 * mm, A4[0] - 18 * mm, A4[1] - 15 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(18 * mm, A4[1] - 11 * mm, "Ledger Lab / Implementation and scaling")
    canvas.drawString(18 * mm, 11 * mm, "Local proof of concept - observed facts and proposed next steps")
    canvas.drawRightString(A4[0] - 18 * mm, 11 * mm, str(document.page))
    canvas.restoreState()


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=18 * mm,
        rightMargin=18 * mm, topMargin=22 * mm, bottomMargin=20 * mm,
        title="Ledger Lab - Implementation and scaling", author="Felipe Sabino",
        subject="Go ledger service, measured limitations and a staged scaling plan")
    document.build(story_from_markdown(), onFirstPage=chrome, onLaterPages=chrome)
    print(OUTPUT)


if __name__ == "__main__":
    main()
