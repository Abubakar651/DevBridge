"""Render the current DevBridge documentation as a PDF. Requires reportlab.

Run from any directory: python3 path/to/docs/build_project_plan_pdf.py
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "voice_coach_documentation.json"
OUTPUT = ROOT / "output" / "pdf" / "Voice_Coach_Project_Plan.pdf"
DOCUMENT_VERSION = "3.0"
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 45
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN
INK = colors.HexColor("#17324D")
BODY = colors.HexColor("#263C4E")
TEAL = colors.HexColor("#00857D")
MUTED = colors.HexColor("#607586")
PALE = colors.HexColor("#F0F6F8")
RULE = colors.HexColor("#D6E3E9")


def configure_fonts() -> None:
    font_dir = Path("/usr/share/fonts/truetype/lato")
    if (font_dir / "Lato-Regular.ttf").is_file():
        fonts = {
            "Doc": "Lato-Regular.ttf",
            "Doc-Bold": "Lato-Bold.ttf",
            "Doc-Italic": "Lato-Italic.ttf",
            "Doc-BoldItalic": "Lato-BoldItalic.ttf",
        }
        for name, filename in fonts.items():
            pdfmetrics.registerFont(TTFont(name, str(font_dir / filename)))
    else:
        for name, base in (
            ("Doc", "Helvetica"),
            ("Doc-Bold", "Helvetica-Bold"),
            ("Doc-Italic", "Helvetica-Oblique"),
            ("Doc-BoldItalic", "Helvetica-BoldOblique"),
        ):
            pdfmetrics.registerFont(pdfmetrics.Font(name, base, "WinAnsiEncoding"))
    pdfmetrics.registerFontFamily(
        "Doc", normal="Doc", bold="Doc-Bold", italic="Doc-Italic", boldItalic="Doc-BoldItalic"
    )


def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\[([^]]+)\]\((https?://[^)]+)\)", r'<link href="\2" color="#00857D">\1</link>', text)
    return text


def make_styles() -> dict[str, ParagraphStyle]:
    body = ParagraphStyle(
        "Body", fontName="Doc", fontSize=10, leading=13.5, textColor=BODY,
        spaceAfter=6, alignment=TA_LEFT, allowWidows=0, allowOrphans=0,
    )
    return {
        "body": body,
        "title": ParagraphStyle(
            "Title", parent=body, fontName="Doc-Bold", fontSize=23, leading=27,
            textColor=INK, spaceAfter=17, keepWithNext=True,
        ),
        "cover": ParagraphStyle(
            "Cover", parent=body, fontName="Doc-Bold", fontSize=32, leading=36,
            textColor=INK, spaceAfter=9, keepWithNext=True,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle", parent=body, fontSize=14, leading=19, textColor=TEAL,
            spaceAfter=9, keepWithNext=True,
        ),
        "meta": ParagraphStyle(
            "Meta", parent=body, fontSize=9, leading=12, textColor=MUTED,
            spaceAfter=12,
        ),
        "heading": ParagraphStyle(
            "Heading", parent=body, fontName="Doc-Bold", fontSize=12,
            leading=15, textColor=TEAL, spaceBefore=6, spaceAfter=5,
            keepWithNext=True,
        ),
        "list": ParagraphStyle(
            "List", parent=body, leftIndent=14, firstLineIndent=-12,
            spaceAfter=4,
        ),
        "table": ParagraphStyle(
            "Table", parent=body, fontSize=9.1, leading=12.1, spaceAfter=0,
        ),
        "table_header": ParagraphStyle(
            "TableHeader", parent=body, fontName="Doc-Bold", fontSize=9.3,
            leading=12.2, textColor=colors.white, spaceAfter=0,
        ),
        "code": ParagraphStyle(
            "Code", parent=body, fontName="Courier", fontSize=8.3, leading=11.5,
            backColor=PALE, borderColor=RULE, borderWidth=0.5, borderPadding=9,
            spaceBefore=3, spaceAfter=10,
        ),
        "reference": ParagraphStyle(
            "Reference", parent=body, fontSize=8.6, leading=11.2,
            spaceAfter=3, wordWrap="CJK",
        ),
        "callout": ParagraphStyle(
            "Callout", parent=body, fontSize=9.7, leading=13.3,
            spaceBefore=0, spaceAfter=0,
        ),
    }


class Pipeline(Flowable):
    """Small static architecture diagram for the shareable PDF."""

    def __init__(self) -> None:
        super().__init__()
        self.width = CONTENT_WIDTH
        self.height = 82

    def draw(self) -> None:
        labels = [
            ("01 / CAPTURE", "Browser", "Record answer"),
            ("02 / TRANSCRIBE", "Groq Whisper", "Audio to text"),
            ("03 / REASON", "Gemini", "Workplace reply"),
            ("04 / SPEAK", "Groq Orpheus", "Text to audio"),
        ]
        gap = 13
        box_width = (self.width - 3 * gap) / 4
        c = self.canv
        for index, (kicker, title, subtitle) in enumerate(labels):
            x = index * (box_width + gap)
            c.setFillColor(PALE)
            c.setStrokeColor(RULE)
            c.roundRect(x, 14, box_width, 62, 7, fill=1, stroke=1)
            c.setFillColor(TEAL)
            c.setFont("Doc-Bold", 7.2)
            c.drawString(x + 9, 60, kicker)
            c.setFillColor(INK)
            c.setFont("Doc-Bold", 11)
            c.drawString(x + 9, 42, title)
            c.setFillColor(MUTED)
            c.setFont("Doc", 8.3)
            c.drawString(x + 9, 27, subtitle)
            if index < 3:
                c.setStrokeColor(TEAL)
                right = x + box_width + gap - 3
                c.line(x + box_width + 3, 45, right, 45)
                c.line(right - 3, 48, right, 45)
                c.line(right - 3, 42, right, 45)


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.saved_pages = []

    def showPage(self) -> None:
        self.saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self.saved_pages)
        for state in self.saved_pages:
            self.__dict__.update(state)
            self.draw_footer(total)
            super().showPage()
        super().save()

    def draw_footer(self, total: int) -> None:
        self.saveState()
        self.setStrokeColor(RULE)
        self.line(MARGIN, 38, PAGE_WIDTH - MARGIN, 38)
        self.setFillColor(MUTED)
        self.setFont("Doc", 8)
        self.drawString(MARGIN, 24, "VOICE COACH  /  WORKPLACE COMMUNICATION  /  18 NOV 2026")
        self.setFont("Doc-Bold", 8)
        self.drawRightString(PAGE_WIDTH - MARGIN, 24, f"{self._pageNumber:02d} / {total:02d}")
        self.restoreState()


def page_header(c: canvas.Canvas, doc) -> None:
    c.saveState()
    c.setFillColor(INK)
    c.rect(0, PAGE_HEIGHT - 12, PAGE_WIDTH, 12, fill=1, stroke=0)
    c.setFillColor(TEAL)
    c.rect(0, PAGE_HEIGHT - 12, 105, 12, fill=1, stroke=0)
    c.setFont("Doc-Bold", 8.4)
    c.setFillColor(INK)
    c.drawString(MARGIN, PAGE_HEIGHT - 39, "NETSOL / INTERNSHIP PROJECT")
    c.setFillColor(MUTED)
    c.setFont("Doc", 8.2)
    c.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 39, f"VOICE COACH / V{DOCUMENT_VERSION}")
    c.restoreState()


def build_table(rows: list[list[str]], styles: dict[str, ParagraphStyle]) -> Table:
    first = rows[0][0]
    first_ratio = 0.29
    if first == "Route":
        first_ratio = 0.30
    elif first == "Check":
        first_ratio = 0.25
    elif first == "State":
        first_ratio = 0.23
    parsed = [
        [Paragraph(inline(cell), styles["table_header"] if index == 0 else styles["table"]) for cell in row]
        for index, row in enumerate(rows)
    ]
    table = Table(
        parsed, colWidths=[CONTENT_WIDTH * first_ratio, CONTENT_WIDTH * (1 - first_ratio)],
        repeatRows=1, hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 1), (-1, -1), 0.35, RULE),
    ]))
    table.spaceAfter = 8
    return table


def render_markdown(source: str, styles: dict[str, ParagraphStyle]) -> list:
    story = []
    sections = source.split("<!-- pagebreak -->")
    for section_index, section in enumerate(sections):
        if section_index:
            story.append(PageBreak())
        lines = section.strip().splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            if line.startswith("# "):
                style = "cover" if section_index == 0 else "title"
                story.append(Paragraph(inline(line[2:]), styles[style]))
                i += 1
                continue
            if line.startswith("## "):
                story.append(Paragraph(inline(line[3:]), styles["heading"]))
                i += 1
                continue
            if line.startswith("```"):
                code = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code.append(lines[i])
                    i += 1
                story.append(Preformatted("\n".join(code), styles["code"]))
                i += 1
                continue
            if line.startswith("|"):
                rows = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    row = [cell.strip() for cell in lines[i].strip().strip("|").split("|")]
                    if not all(re.fullmatch(r":?-+:?", cell.replace(" ", "")) for cell in row):
                        rows.append(row)
                    i += 1
                story.append(build_table(rows, styles))
                continue
            if line.startswith("**Learner speech ->"):
                story.append(Pipeline())
                i += 1
                continue
            if line.startswith("- **R") or line.startswith("- **Planning reference"):
                match = re.match(r"- \*\*(.+?):\*\* (https?://\S+)", line)
                if match:
                    label, url = match.groups()
                    body = f'<b>{html.escape(label)}</b><br/><link href="{html.escape(url)}" color="#00857D">{html.escape(url)}</link>'
                    story.append(Paragraph(body, styles["reference"]))
                else:
                    story.append(Paragraph(inline(line[2:]), styles["reference"]))
                i += 1
                continue
            match = re.match(r"(\d+)\.\s+(.+)", line)
            if match:
                story.append(Paragraph(f'<b>{match.group(1)}.</b> {inline(match.group(2))}', styles["list"]))
                i += 1
                continue
            if line.startswith("- "):
                story.append(Paragraph("&#8226; " + inline(line[2:]), styles["list"]))
                i += 1
                continue
            paragraph = [line]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||```|[-] |\d+\. )", lines[i].strip()):
                paragraph.append(lines[i].strip())
                i += 1
            value = " ".join(paragraph)
            style = "body"
            if value.startswith("Project documentation"):
                style = "subtitle"
            elif value.startswith("NETSOL internship"):
                style = "meta"
            elif value.startswith(("**Status:", "**Phase 1 deliverable:")):
                style = "callout"
            paragraph = Paragraph(inline(value), styles[style])
            if style == "callout":
                box = Table([[paragraph]], colWidths=[CONTENT_WIDTH], hAlign="LEFT")
                box.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), PALE),
                    ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 9),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]))
                box.spaceBefore = 5
                box.spaceAfter = 8
                story.append(box)
            else:
                story.append(paragraph)
    return story


def main() -> None:
    global DOCUMENT_VERSION
    rl_config.warnOnMissingFontGlyphs = 1
    document = json.loads(SOURCE.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1 or not document.get("pages"):
        raise ValueError("Expected documentation schema version 1 and non-empty pages.")
    DOCUMENT_VERSION = document["version"]
    configure_fonts()
    styles = make_styles()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=60, bottomMargin=50, title=document["title"],
        author="NETSOL Internship Project", subject=document["subject"],
        pageCompression=1,
    )
    story = render_markdown("\n\n<!-- pagebreak -->\n\n".join(document["pages"]), styles)
    doc.build(story, onFirstPage=page_header, onLaterPages=page_header, canvasmaker=NumberedCanvas)
    print(OUTPUT)


if __name__ == "__main__":
    main()
