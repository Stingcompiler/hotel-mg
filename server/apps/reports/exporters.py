"""Excel and CSV exports of a Report (spec §8)."""

import csv
import io
from datetime import date, datetime

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from . import rules
from .framework import Column, Report

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _cell(value, column: Column, decimals: int):
    """Value as stored in a cell: money in pounds (numbers, not text), local dates, «—» for empty."""
    if value is None:
        return None
    if column.type == "money":
        return rules.to_major(value, decimals)
    if column.type == "percent":
        return value / 100
    if column.type == "datetime" and isinstance(value, datetime):
        return timezone.localtime(value).replace(tzinfo=None)
    return value


def to_xlsx(report: Report, *, decimals: int, hotel_name: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = report.title[:31]
    ws.sheet_view.rightToLeft = True

    ws.append([f"{report.title} — {hotel_name}"])
    ws["A1"].font = Font(bold=True, size=14)
    period = ""
    if report.period:
        period = f"الفترة: {report.period[0]:%Y-%m-%d} – {report.period[1]:%Y-%m-%d} · "
    ws.append([f"{period}بيانات حتى: {timezone.localtime():%Y-%m-%d %H:%M}"])
    ws.append([])
    ws.append([c.label for c in report.columns])
    header_row = ws.max_row
    for cell in ws[header_row]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    money_format = "#,##0" if decimals == 0 else "#,##0.00"
    for row in report.rows:
        ws.append([_cell(row.get(c.key), c, decimals) for c in report.columns])
    if report.totals:
        ws.append(
            [
                _cell(report.totals.get(c.key), c, decimals)
                if c.key in report.totals
                else ("الإجمالي" if i == 0 else None)
                for i, c in enumerate(report.columns)
            ]
        )
        for cell in ws[ws.max_row]:
            cell.font = Font(bold=True)

    for index, column in enumerate(report.columns, start=1):
        letter = get_column_letter(index)
        fmt = {"money": money_format, "percent": "0%", "date": "yyyy-mm-dd", "datetime": "yyyy-mm-dd hh:mm"}.get(
            column.type
        )
        for cell in ws[letter][header_row:]:
            if fmt:
                cell.number_format = fmt
        ws.column_dimensions[letter].width = max(12, len(column.label) + 4)
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    if report.formula:
        ws.append([])
        ws.append([report.formula])

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _csv_value(value, column: Column, decimals: int) -> str:
    value = _cell(value, column, decimals)
    if value is None:
        return ""
    if column.type == "percent":
        return f"{round(value * 100)}%"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def to_csv(report: Report, *, decimals: int) -> bytes:
    """UTF-8 with BOM (Excel opens Arabic correctly), comma-separated, CRLF (spec §8)."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow([c.label for c in report.columns])
    for row in report.rows:
        writer.writerow([_csv_value(row.get(c.key), c, decimals) for c in report.columns])
    return ("﻿" + out.getvalue()).encode("utf-8")
