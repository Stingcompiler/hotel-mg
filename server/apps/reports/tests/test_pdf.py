"""PDF export of reports (owner request 2026-10-02)."""

import pytest

from apps.reports import pdf
from apps.reports.framework import Column, Report

pytestmark = pytest.mark.django_db


def _report(rows: int) -> Report:
    return Report(
        "revenue",
        "الإيرادات والتحصيل",
        [Column("day", "اليوم", "date"), Column("revenue", "صافي الإيراد", "money"), Column("note", "البيان")],
        [{"day": None, "revenue": 1_500_050, "note": "نزيل 28/09 – 30/09"}] * rows,
        None,
        totals={"revenue": 1_500_050 * rows},
        tiles=[{"label": "المحصّل", "value": 2_000_000, "type": "money"}],
        formula="الإيراد عند التسكين",
        filters=[{"key": "method", "label": "الطريقة", "value": "نقدي"}],
    )


def test_a_report_becomes_a_pdf_with_its_pages():
    one = pdf.to_pdf(_report(3), decimals=0, hotel_name="سكاي تاورز")
    assert one.startswith(b"%PDF") and one.count(b"/Type /Page\n") == 1
    long = pdf.to_pdf(_report(120), decimals=2, hotel_name="سكاي تاورز")
    assert long.count(b"/Type /Page\n") > 1  # the table runs onto more pages
    assert pdf.to_pdf(_report(0), decimals=0, hotel_name="").startswith(b"%PDF")  # nothing in the period
    assert pdf._text(None, "money", 0) == "—" and pdf._text(42, "percent", 0) == "42٪"
    assert pdf._text(1500, "int", 0) == "1,500"


def test_the_export_is_a_pdf(manager_api):
    res = manager_api.get("/api/v1/reports/debts/export", {"format": "pdf"})
    assert res.status_code == 200 and res["Content-Type"] == "application/pdf"
    assert res.content.startswith(b"%PDF") and res["Content-Disposition"].endswith('.pdf"')
    assert manager_api.get("/api/v1/reports/debts/export", {"format": "doc"}).status_code == 400
