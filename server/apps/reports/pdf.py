"""PDF export of a Report (owner request 2026-10-02): A4 landscape, right to left, like the printed report — title,
hotel, period, filters, tiles, table with a heading on every page, totals, formula, page numbers.

Written in-process with fpdf2: HarfBuzz shapes the Arabic (IBM Plex Sans Arabic, the app's font, embedded) and the
columns run from the right. A headless browser was tried first; it did not run under the SYSTEM service account.
"""

import logging
from datetime import date, datetime
from pathlib import Path

from django.utils import timezone
from fpdf import FPDF
from fpdf.fonts import FontFace

from . import rules
from .framework import Column, Report

FONTS = Path(__file__).resolve().parent / "fonts"
logging.getLogger("fontTools").setLevel(logging.WARNING)  # its font subsetting logs every glyph at INFO
NUMERIC = ("money", "int", "percent")
INK, MUTED, RULE = (27, 36, 48), (85, 85, 85), (201, 206, 214)


def _text(value, column_type: str, decimals: int) -> str:
    if value is None or value == "":
        return "—"
    if column_type == "money" and isinstance(value, int):
        return f"{rules.to_major(value, decimals):,}"
    if column_type == "percent" and isinstance(value, (int, float)):
        return f"{value}٪"
    if column_type == "int" and isinstance(value, (int, float)):
        return f"{value:,}"
    if isinstance(value, datetime):
        return f"{timezone.localtime(value):%Y-%m-%d %H:%M}"
    if isinstance(value, date):
        return f"{value:%Y-%m-%d}"
    return str(value)


class _Sheet(FPDF):
    def footer(self):
        self.set_y(-10)
        self.set_font("Plex", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 5, f"صفحة {self.page_no()} من {{nb}}", align="C")


def _sheet() -> _Sheet:
    pdf = _Sheet(orientation="L", unit="mm", format="A4")
    pdf.set_margins(12, 12, 12)
    pdf.set_auto_page_break(True, margin=14)
    pdf.add_font("Plex", "", str(FONTS / "IBMPlexSansArabic-Regular.ttf"))
    pdf.add_font("Plex", "B", str(FONTS / "IBMPlexSansArabic-Bold.ttf"))
    pdf.set_text_shaping(use_shaping_engine=True)  # Arabic letter forms and right-to-left runs
    pdf.set_draw_color(*RULE)
    return pdf


def _widths(columns: list[Column]) -> list[float]:
    return [1.0 if c.type in NUMERIC else 1.6 for c in columns]


def to_pdf(report: Report, *, decimals: int, hotel_name: str) -> bytes:
    pdf = _sheet()
    pdf.add_page()

    pdf.set_text_color(*INK)
    pdf.set_font("Plex", "B", 16)
    pdf.cell(0, 9, report.title, align="R", new_x="LMARGIN", new_y="NEXT")
    period = f"الفترة: {report.period[0]:%Y-%m-%d} – {report.period[1]:%Y-%m-%d}" if report.period else ""
    subtitle = " · ".join(
        [hotel_name, *([period] if period else []), *(f"{f['label']}: {f['value']}" for f in report.filters)]
    )
    pdf.set_font("Plex", "", 9.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, subtitle, align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"بيانات حتى {timezone.localtime():%Y-%m-%d %H:%M}", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*INK)
    pdf.line(pdf.l_margin, pdf.get_y() + 1, pdf.w - pdf.r_margin, pdf.get_y() + 1)
    pdf.set_draw_color(*RULE)
    pdf.ln(4)

    if report.tiles:
        pdf.set_text_color(*INK)
        with pdf.table(
            borders_layout="ALL",
            text_align="RIGHT",
            first_row_as_headings=False,
            line_height=5.5,
            width=min(len(report.tiles) * 55, pdf.epw),
            align="RIGHT",
        ) as tiles:
            row = tiles.row()
            for tile in reversed(report.tiles):  # the first tile on the right
                value = _text(tile["value"], tile.get("type") or "text", decimals)
                row.cell(f"{tile['label']}\n{value}")
        pdf.ln(3)

    columns = list(reversed(report.columns))  # the first column on the right
    align = ["LEFT" if c.type in NUMERIC else "RIGHT" for c in columns]
    pdf.set_text_color(*INK)
    pdf.set_font("Plex", "", 9)
    with pdf.table(
        col_widths=_widths(columns),
        text_align=align,
        borders_layout="HORIZONTAL_LINES",
        headings_style=FontFace(emphasis="BOLD", color=INK),
        line_height=5.5,
        repeat_headings=1,
    ) as table:
        head = table.row()
        for c in columns:
            head.cell(c.label)
        for item in report.rows:
            row = table.row()
            for c in columns:
                row.cell(_text(item.get(c.key), c.type, decimals))
        if report.totals:
            row = table.row(style=FontFace(emphasis="BOLD"))
            first = report.columns[0].key
            for c in columns:
                if c.key in report.totals:
                    row.cell(_text(report.totals[c.key], c.type, decimals))
                else:
                    row.cell("الإجمالي" if c.key == first else "")
    if not report.rows:
        pdf.ln(2)
        pdf.set_text_color(*MUTED)
        pdf.cell(0, 6, "لا توجد بيانات في هذه الفترة.", align="R", new_x="LMARGIN", new_y="NEXT")
    if report.formula:
        pdf.ln(3)
        pdf.set_font("Plex", "", 8.5)
        pdf.set_text_color(*MUTED)
        pdf.multi_cell(0, 4.5, report.formula, align="R")
    return bytes(pdf.output())
