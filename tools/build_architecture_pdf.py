#!/usr/bin/env python3
"""Render ARCHITECTURE.md as the submission PDF.

The Markdown remains the editable source of truth. This renderer handles only
the small set of structures used by that document so the output stays
deterministic and dependency-light.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
import re
import sys

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfbase.ttfonts import TTFError


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ARCHITECTURE.md"
OUTPUT = ROOT / "output" / "pdf" / "architecture-and-trade-offs.pdf"

NAVY = HexColor("#14283D")
TEAL = HexColor("#087F7A")
TEAL_DARK = HexColor("#075E5B")
TEAL_DARK_HEX = "#075E5B"
PALE_TEAL = HexColor("#E9F5F3")
PALE_BLUE = HexColor("#EFF4F8")
PALE_GOLD = HexColor("#FFF5D8")
PALE_CORAL = HexColor("#FCEBE6")
GOLD = HexColor("#D49312")
CORAL = HexColor("#C9553D")
INK = HexColor("#1C2733")
MUTED = HexColor("#5C6975")
LINE = HexColor("#CBD5DE")
WHITE = colors.white

PAGE_BREAK_HEADINGS = {
    "Append-only at 100x",
    "Value-dated entries in production",
    "What I cut and why",
}


def ascii_punctuation(text: str) -> str:
    """Keep built-in PDF fonts predictable and avoid non-ASCII dash glyphs."""

    substitutions = {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u00a0": " ",
    }
    return "".join(substitutions.get(character, character) for character in text)


def inline_markup(text: str) -> str:
    """Convert the limited inline Markdown used by the source to ReportLab XML."""

    marked_up = escape(ascii_punctuation(text), quote=False)
    marked_up = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        rf'<link href="\2" color="{TEAL_DARK_HEX}"><u>\1</u></link>',
        marked_up,
    )
    marked_up = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", marked_up)
    marked_up = re.sub(
        r"`([^`]+)`",
        rf'<font name="Courier" color="{TEAL_DARK_HEX}">\1</font>',
        marked_up,
    )
    marked_up = re.sub(r"\[\^(\d+)\]", r"<super>\1</super>", marked_up)
    return marked_up


def build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "DocumentTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=23,
            leading=26,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=2 * mm,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=12,
            textColor=MUTED,
            spaceAfter=4 * mm,
        ),
        "h2": ParagraphStyle(
            "SectionHeading",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14.2,
            leading=16.5,
            textColor=NAVY,
            spaceBefore=2.3 * mm,
            spaceAfter=1.8 * mm,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "SubsectionHeading",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10.2,
            leading=12.2,
            textColor=TEAL_DARK,
            spaceBefore=1.8 * mm,
            spaceAfter=1.1 * mm,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.0,
            leading=11.7,
            textColor=INK,
            spaceAfter=1.7 * mm,
            allowWidows=0,
            allowOrphans=0,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.55,
            leading=10.6,
            textColor=INK,
            leftIndent=5 * mm,
            firstLineIndent=0,
            bulletIndent=0,
            bulletFontName="Helvetica-Bold",
            bulletFontSize=7.2,
            bulletColor=TEAL,
            spaceAfter=0.65 * mm,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=8.7,
            textColor=WHITE,
        ),
        "table_body": ParagraphStyle(
            "TableBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.2,
            leading=8.55,
            textColor=INK,
        ),
        "source": ParagraphStyle(
            "Source",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=6.8,
            leading=8.2,
            textColor=MUTED,
            leftIndent=3.5 * mm,
            firstLineIndent=-3.5 * mm,
            spaceAfter=0.9 * mm,
        ),
        "diagram": ParagraphStyle(
            "Diagram",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.0,
            leading=8.2,
            textColor=NAVY,
            alignment=1,
        ),
        "diagram_arrow": ParagraphStyle(
            "DiagramArrow",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=10,
            textColor=TEAL,
            alignment=1,
        ),
        "visual_title": ParagraphStyle(
            "VisualTitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.0,
            leading=9.3,
            textColor=NAVY,
            alignment=1,
        ),
        "visual_title_white": ParagraphStyle(
            "VisualTitleWhite",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.0,
            leading=9.3,
            textColor=WHITE,
            alignment=1,
        ),
        "visual_body": ParagraphStyle(
            "VisualBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.4,
            leading=8.7,
            textColor=INK,
            alignment=1,
        ),
        "visual_value": ParagraphStyle(
            "VisualValue",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=13,
            textColor=NAVY,
            alignment=1,
        ),
        "visual_caption": ParagraphStyle(
            "VisualCaption",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.0,
            leading=8.4,
            textColor=MUTED,
            alignment=1,
        ),
    }


def page_chrome(canvas: object, document: object) -> None:
    """Draw restrained running furniture without changing story layout."""

    del document
    width, height = A4
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(15 * mm, 12 * mm, width - 15 * mm, 12 * mm)
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(15 * mm, 8.2 * mm, "Felipe Sabino | 02 September 2026")
    canvas.drawRightString(
        width - 15 * mm,
        8.2 * mm,
        f"Page {canvas.getPageNumber()}",
    )
    canvas.restoreState()


def diagram(styles: dict[str, ParagraphStyle]) -> Table:
    labels = [
        "1  TRIGGER<br/><font name='Helvetica'>Input or close</font>",
        "2  DECIDE<br/><font name='Helvetica'>Pure policy</font>",
        "3  VALIDATE<br/><font name='Helvetica'>Complete fact batch</font>",
        "4  APPEND<br/><font name='Helvetica'>Immutable journal</font>",
        "5  PROJECT<br/><font name='Helvetica'>Balance, holds, reports</font>",
    ]
    cells: list[Paragraph] = []
    for index, label in enumerate(labels):
        cells.append(Paragraph(label, styles["diagram"]))
        if index < len(labels) - 1:
            cells.append(Paragraph(">", styles["diagram_arrow"]))

    widths = [24 * mm, 5 * mm, 29 * mm, 5 * mm, 29 * mm, 5 * mm, 26 * mm, 5 * mm, 46 * mm]
    result = Table([cells], colWidths=widths, rowHeights=[18 * mm], hAlign="LEFT")
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), PALE_BLUE),
                ("BACKGROUND", (2, 0), (2, 0), PALE_TEAL),
                ("BACKGROUND", (4, 0), (4, 0), PALE_BLUE),
                ("BACKGROUND", (6, 0), (6, 0), PALE_TEAL),
                ("BACKGROUND", (8, 0), (8, 0), PALE_BLUE),
                ("BOX", (0, 0), (0, 0), 0.7, LINE),
                ("BOX", (2, 0), (2, 0), 0.7, TEAL),
                ("BOX", (4, 0), (4, 0), 0.7, LINE),
                ("BOX", (6, 0), (6, 0), 0.7, TEAL),
                ("BOX", (8, 0), (8, 0), 0.7, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return result


def visual_cell(
    title: str,
    body: str,
    styles: dict[str, ParagraphStyle],
    *,
    value: str | None = None,
) -> list[Paragraph]:
    content = [Paragraph(inline_markup(title), styles["visual_title"])]
    if value is not None:
        content.append(Paragraph(inline_markup(value), styles["visual_value"]))
    body_markup = inline_markup(body).replace("&lt;br/&gt;", "<br/>")
    content.append(Paragraph(body_markup, styles["visual_body"]))
    return content


def scale_visual(styles: dict[str, ParagraphStyle]) -> Table:
    cells: list[object] = [
        visual_cell("TODAY", "Small enough to inspect", styles, value="10 events"),
        Paragraph(">", styles["diagram_arrow"]),
        visual_cell("100x INPUT", "Same rules and fact shape", styles, value="1,000 events"),
        Paragraph(">", styles["diagram_arrow"]),
        visual_cell("REPEATED WORK", "Copy tuples and rescan history", styles),
        Paragraph(">", styles["diagram_arrow"]),
        visual_cell("QUADRATIC PART", "Approximate growth, not a benchmark", styles, value="~10,000x"),
    ]
    result = Table(
        [cells],
        colWidths=[34 * mm, 6 * mm, 38 * mm, 6 * mm, 41 * mm, 6 * mm, 43 * mm],
        rowHeights=[24 * mm],
        hAlign="LEFT",
    )
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), PALE_BLUE),
                ("BACKGROUND", (2, 0), (2, 0), PALE_TEAL),
                ("BACKGROUND", (4, 0), (4, 0), PALE_GOLD),
                ("BACKGROUND", (6, 0), (6, 0), PALE_CORAL),
                ("BOX", (0, 0), (0, 0), 0.8, LINE),
                ("BOX", (2, 0), (2, 0), 0.8, TEAL),
                ("BOX", (4, 0), (4, 0), 0.8, GOLD),
                ("BOX", (6, 0), (6, 0), 0.8, CORAL),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return result


def clocks_visual(styles: dict[str, ParagraphStyle]) -> Table:
    top = [
        visual_cell("BOOKING DATE", "When the bank records it", styles),
        visual_cell("VALUE DATE", "When the financial effect applies", styles),
        visual_cell("JOURNAL SEQUENCE", "Its exact append order", styles),
    ]
    ripple = Paragraph(
        inline_markup(
            "APPEND NOW  >  earlier value date  >  recalculated past result  >  linked replacement"
        ),
        styles["visual_title"],
    )
    result = Table(
        [top, [ripple, "", ""]],
        colWidths=[58 * mm, 58 * mm, 58 * mm],
        rowHeights=[18 * mm, 10 * mm],
        hAlign="LEFT",
    )
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), PALE_BLUE),
                ("BACKGROUND", (1, 0), (1, 0), PALE_GOLD),
                ("BACKGROUND", (2, 0), (2, 0), PALE_TEAL),
                ("BOX", (0, 0), (0, 0), 0.8, LINE),
                ("BOX", (1, 0), (1, 0), 0.8, GOLD),
                ("BOX", (2, 0), (2, 0), 0.8, TEAL),
                ("SPAN", (0, 1), (2, 1)),
                ("BACKGROUND", (0, 1), (2, 1), PALE_CORAL),
                ("BOX", (0, 1), (2, 1), 0.8, CORAL),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return result


def authorization_visual(styles: dict[str, ParagraphStyle]) -> Table:
    outcomes = [
        Paragraph("<b>NO</b> - Declined. No hold; this path ends.", styles["visual_body"]),
        Paragraph(
            "<b>YES</b> - Approved hold, then settle, expire, or void.",
            styles["visual_body"],
        ),
    ]
    row = [
        visual_cell("REQUEST", "Reserve this amount", styles),
        Paragraph(">", styles["diagram_arrow"]),
        visual_cell("BALANCE CHECK", "Would available stay at or above zero?", styles),
        Paragraph(">", styles["diagram_arrow"]),
        outcomes,
    ]
    result = Table(
        [row],
        colWidths=[34 * mm, 7 * mm, 53 * mm, 7 * mm, 73 * mm],
        rowHeights=[24 * mm],
        hAlign="LEFT",
    )
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), PALE_BLUE),
                ("BACKGROUND", (2, 0), (2, 0), PALE_GOLD),
                ("BACKGROUND", (4, 0), (4, 0), PALE_TEAL),
                ("BOX", (0, 0), (0, 0), 0.8, LINE),
                ("BOX", (2, 0), (2, 0), 0.8, GOLD),
                ("BOX", (4, 0), (4, 0), 0.8, TEAL),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return result


def double_entry_visual(styles: dict[str, ParagraphStyle]) -> Table:
    title = Paragraph(
        "CONCEPTUAL BANK VIEW - CUSTOMER DEPOSITS AED 1,200",
        styles["visual_title_white"],
    )
    debit = visual_cell(
        "DEBIT",
        "Cash / settlement asset<br/>What the bank controls",
        styles,
        value="AED 1,200",
    )
    credit = visual_cell(
        "CREDIT",
        "Customer deposit liability<br/>What the bank owes",
        styles,
        value="AED 1,200",
    )
    equals = Paragraph("=", styles["visual_value"])
    balance = Paragraph(
        "TOTAL DEBITS AED 1,200  =  TOTAL CREDITS AED 1,200",
        styles["visual_title"],
    )
    note = Paragraph(
        "Both legs share one transaction identity and commit together. The counterpart shown here is illustrative.",
        styles["visual_caption"],
    )
    result = Table(
        [
            [title, "", ""],
            [debit, equals, credit],
            [balance, "", ""],
            [note, "", ""],
        ],
        colWidths=[82 * mm, 10 * mm, 82 * mm],
        rowHeights=[9 * mm, 27 * mm, 9 * mm, 8 * mm],
        hAlign="LEFT",
    )
    result.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (2, 0)),
                ("SPAN", (0, 2), (2, 2)),
                ("SPAN", (0, 3), (2, 3)),
                ("BACKGROUND", (0, 0), (2, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (2, 0), WHITE),
                ("BACKGROUND", (0, 1), (0, 1), PALE_GOLD),
                ("BACKGROUND", (2, 1), (2, 1), PALE_TEAL),
                ("BACKGROUND", (0, 2), (2, 2), PALE_BLUE),
                ("BOX", (0, 0), (2, 3), 0.9, NAVY),
                ("BOX", (0, 1), (0, 1), 0.8, GOLD),
                ("BOX", (2, 1), (2, 1), 0.8, TEAL),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return result


def named_visual(name: str, styles: dict[str, ParagraphStyle]) -> Table:
    visuals = {
        "scale": scale_visual,
        "clocks": clocks_visual,
        "authorization": authorization_visual,
        "double-entry": double_entry_visual,
    }
    try:
        visual = visuals[name](styles)
    except KeyError as error:
        raise ValueError(f"unknown visual: {name}") from error
    return visual


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def markdown_table(
    lines: list[str], styles: dict[str, ParagraphStyle]
) -> Table:
    raw_rows = [split_table_row(line) for line in lines]
    rows = [raw_rows[0], *raw_rows[2:]]
    rendered: list[list[Paragraph]] = []
    for row_index, row in enumerate(rows):
        style = styles["table_header"] if row_index == 0 else styles["table_body"]
        rendered.append([Paragraph(inline_markup(cell), style) for cell in row])

    first_header = raw_rows[0][0]
    if first_header == "Ending or boundary":
        column_widths = [34 * mm, 48 * mm, 92 * mm]
    elif first_header == "Active customer accounts":
        column_widths = [25 * mm, 25 * mm, 25 * mm, 99 * mm]
    else:
        column_widths = [40 * mm, 48 * mm, 86 * mm]

    result = Table(
        rendered,
        colWidths=column_widths,
        repeatRows=1,
        hAlign="LEFT",
        splitByRow=True,
    )
    commands: list[tuple[object, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]
    for row_index in range(1, len(rendered)):
        if row_index % 2 == 0:
            commands.append(("BACKGROUND", (0, row_index), (-1, row_index), PALE_BLUE))
    result.setStyle(TableStyle(commands))
    return result


def parse_markdown(styles: dict[str, ParagraphStyle]) -> list[object]:
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    story: list[object] = []
    index = 0
    sources_started = False

    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue

        if line.startswith("# "):
            story.append(Spacer(1, 4 * mm))
            story.append(Paragraph(inline_markup(line[2:]), styles["title"]))
            story.append(
                Paragraph(
                    "Follow the money. Keep the history. Know what changes in production.",
                    styles["subtitle"],
                )
            )
            story.append(HRFlowable(width="100%", thickness=0.8, color=TEAL))
            story.append(Spacer(1, 2 * mm))
            index += 1
            continue

        if line.startswith("## "):
            heading = line[3:]
            if heading in PAGE_BREAK_HEADINGS:
                story.append(PageBreak())
            story.append(Paragraph(inline_markup(heading), styles["h2"]))
            index += 1
            continue

        if line.startswith("### "):
            story.append(Paragraph(inline_markup(line[4:]), styles["h3"]))
            index += 1
            continue

        if line.startswith("```mermaid"):
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                index += 1
            index += 1
            story.append(Spacer(1, 1.3 * mm))
            story.append(diagram(styles))
            story.append(Spacer(1, 2.2 * mm))
            continue

        visual_match = re.fullmatch(r"<!-- VISUAL: ([a-z-]+) -->", line)
        if visual_match is not None:
            story.append(Spacer(1, 1.2 * mm))
            story.append(named_visual(visual_match.group(1), styles))
            story.append(Spacer(1, 2.4 * mm))
            index += 1
            continue

        if line.startswith("- "):
            while index < len(lines) and lines[index].strip().startswith("- "):
                item_text = lines[index].strip()[2:]
                story.append(
                    Paragraph(
                        inline_markup(item_text),
                        styles["bullet"],
                        bulletText="-",
                    )
                )
                index += 1
            story.append(Spacer(1, 1.0 * mm))
            continue

        if line.startswith("|"):
            table_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            story.append(markdown_table(table_lines, styles))
            story.append(Spacer(1, 1.6 * mm))
            continue

        if line.startswith("[^" ):
            if not sources_started:
                story.append(Spacer(1, 1.2 * mm))
                story.append(Paragraph("Sources and regulatory context", styles["h3"]))
                sources_started = True
            match = re.match(r"\[\^(\d+)\]:\s*(.*)", line)
            if match is None:
                raise ValueError(f"invalid footnote line: {line}")
            number, source_text = match.groups()
            story.append(
                Paragraph(
                    f"<b>{number}.</b> {inline_markup(source_text)}",
                    styles["source"],
                )
            )
            index += 1
            continue

        paragraph_lines = [line]
        index += 1
        while index < len(lines):
            candidate = lines[index].strip()
            if (
                not candidate
                or candidate.startswith("#")
                or candidate.startswith("- ")
                or candidate.startswith("|")
                or candidate.startswith("```")
                or candidate.startswith("[^")
                or candidate.startswith("<!-- VISUAL:")
            ):
                break
            paragraph_lines.append(candidate)
            index += 1
        story.append(
            Paragraph(
                inline_markup(" ".join(paragraph_lines)),
                styles["body"],
            )
        )

    return story


def main() -> int:
    if not SOURCE.exists():
        print(f"missing source: {SOURCE}", file=sys.stderr)
        return 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    styles = build_styles()
    document = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        title="Architecture & Trade-offs",
        author="Felipe Sabino",
        subject="Production evolution of the in-memory account ledger core",
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=17 * mm,
    )
    try:
        document.build(
            parse_markdown(styles),
            onFirstPage=page_chrome,
            onLaterPages=page_chrome,
        )
    except TTFError as error:
        print(f"font error: {error}", file=sys.stderr)
        return 1
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
