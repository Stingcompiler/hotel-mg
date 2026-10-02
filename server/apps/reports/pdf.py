"""PDF export of a Report (owner request 2026-10-02): an A4 landscape RTL page like the printed report, written as
HTML and turned into PDF by Microsoft Edge (every Windows 10/11 has it). The browser shapes the Arabic and lays out the
right-to-left table; a PDF library would need its own Arabic shaping and would not match the print."""

import logging
import os
import re
import subprocess
import tempfile
from datetime import date, datetime
from html import escape
from pathlib import Path

from django.utils import timezone

from apps.core.errors import ApiError

from . import rules
from .framework import Column, Report

EDGE_TIMEOUT = 60
log = logging.getLogger("skytowers.pdf")
# Tried in order. The service runs as SYSTEM in session 0: the second set is for that case (the old headless mode,
# no crash reporter, no de-elevation relaunch, no GPU process).
EDGE_MODES = (
    ["--headless=new", "--disable-gpu"],
    [
        "--headless",
        "--disable-gpu",
        "--do-not-de-elevate",
        "--disable-crash-reporter",
        "--no-zygote",
        "--single-process",
    ],
)


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


ARABIC = re.compile("[؀-ۿ]")


def _cell(value, column: Column, decimals: int) -> str:
    numeric = column.type in ("money", "int", "percent")
    text = escape(_text(value, column.type, decimals))
    if not numeric and not ARABIC.search(text):
        text = f'<span dir="ltr">{text}</span>'  # «28/09 – 30/09» would read backwards in a right-to-left cell
    return f'<td class="{"num" if numeric else ""}">{text}</td>'


def to_html(report: Report, *, decimals: int, hotel_name: str) -> str:
    period = f"{report.period[0]:%Y-%m-%d} – {report.period[1]:%Y-%m-%d}" if report.period else ""
    subtitle = " · ".join(
        [escape(hotel_name)]
        + ([f"الفترة: {period}"] if period else [])
        + [escape(f"{f['label']}: {f['value']}") for f in report.filters]
    )
    tiles = "".join(
        f'<div class="tile"><div class="label">{escape(str(t["label"]))}</div>'
        f'<div class="value">{escape(_text(t["value"], t.get("type") or "text", decimals))}</div></div>'
        for t in report.tiles
    )
    head = "".join(
        f'<th class="{"num" if c.type in ("money", "int", "percent") else ""}">{escape(c.label)}</th>'
        for c in report.columns
    )
    rows = "".join(
        "<tr>" + "".join(_cell(row.get(c.key), c, decimals) for c in report.columns) + "</tr>" for row in report.rows
    )
    totals = ""
    if report.totals:
        cells = []
        for i, c in enumerate(report.columns):
            if c.key in report.totals:
                cells.append(_cell(report.totals[c.key], c, decimals))
            else:
                cells.append(f"<td>{'الإجمالي' if i == 0 else ''}</td>")
        totals = f'<tfoot><tr class="totals">{"".join(cells)}</tr></tfoot>'
    empty = "" if report.rows else '<p class="empty">لا توجد بيانات في هذه الفترة.</p>'
    return f"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>{escape(report.title)}</title>
<style>
  @page {{ size: A4 landscape; margin: 12mm; }}
  body {{ font-family: "Segoe UI", Tahoma, Arial, sans-serif; font-size: 10.5pt; color: #1B2430; margin: 0; }}
  header {{ display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 2px solid #1B2430;
           padding-bottom: 6px; margin-bottom: 8px; }}
  h1 {{ font-size: 16pt; margin: 0; }}
  .sub {{ color: #555; font-size: 9.5pt; }}
  .tiles {{ display: flex; gap: 8px; margin: 8px 0; flex-wrap: wrap; }}
  .tile {{ border: 1px solid #c9ced6; border-radius: 4px; padding: 4px 10px; min-width: 120px; }}
  .tile .label {{ color: #555; font-size: 9pt; }}
  .tile .value {{ font-weight: 700; font-size: 12pt; }}
  table {{ width: 100%; border-collapse: collapse; }}
  thead {{ display: table-header-group; }}
  tr {{ page-break-inside: avoid; }}
  th {{ text-align: start; border-top: 1.5px solid #1B2430; border-bottom: 1.5px solid #1B2430; padding: 4px 6px;
        font-size: 9.5pt; }}
  td {{ border-bottom: 1px solid #d8dce2; padding: 3px 6px; }}
  .num {{ text-align: left; direction: ltr; white-space: nowrap; }}
  tr.totals td {{ font-weight: 700; border-top: 1.5px solid #1B2430; }}
  .formula {{ margin-top: 8px; color: #555; font-size: 9pt; white-space: pre-line; }}
  .empty {{ color: #555; }}
</style></head>
<body>
<header>
  <div><h1>{escape(report.title)}</h1>
    <div class="sub">{subtitle}</div></div>
  <div class="sub">بيانات حتى {timezone.localtime():%Y-%m-%d %H:%M}</div>
</header>
{f'<div class="tiles">{tiles}</div>' if tiles else ""}
<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody>{totals}</table>
{empty}
{f'<div class="formula">{escape(report.formula)}</div>' if report.formula else ""}
</body></html>"""


def edge_path() -> Path | None:
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base:
            candidate = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if candidate.is_file():
                return candidate
    return None


def to_pdf(html: str) -> bytes:
    """Print the page with Edge in headless mode; 503 ``pdf_unavailable`` when it cannot (no Edge, a failure)."""
    edge = edge_path()
    if edge is None:
        log.warning("PDF: Microsoft Edge not found (ProgramFiles=%s)", os.environ.get("ProgramFiles"))
        raise ApiError("pdf_unavailable", 503)
    with tempfile.TemporaryDirectory(prefix="skytowers-pdf-") as tmp:
        page = Path(tmp) / "report.html"
        page.write_text(html, encoding="utf-8")
        for attempt, mode in enumerate(EDGE_MODES, start=1):
            out = Path(tmp) / f"report-{attempt}.pdf"
            command = [
                str(edge),
                *mode,
                "--no-sandbox",  # the service runs as SYSTEM
                "--no-first-run",
                "--no-pdf-header-footer",
                f"--user-data-dir={Path(tmp) / f'profile-{attempt}'}",
                f"--print-to-pdf={out}",
                page.as_uri(),
            ]
            try:
                done = subprocess.run(command, capture_output=True, timeout=EDGE_TIMEOUT, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                log.warning("PDF: Edge attempt %s did not finish: %r", attempt, exc)
                continue
            if out.is_file() and out.stat().st_size > 0:
                return out.read_bytes()
            log.warning(
                "PDF: Edge attempt %s wrote nothing (exit %s): %s",
                attempt,
                done.returncode,
                (done.stderr or done.stdout or b"")[-800:].decode("utf-8", "replace"),
            )
        raise ApiError("pdf_unavailable", 503)
