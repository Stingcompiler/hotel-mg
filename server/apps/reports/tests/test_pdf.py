"""PDF export of reports (owner request 2026-10-02)."""

from unittest import mock

import pytest

from apps.reports import pdf
from apps.reports.framework import Column, Report

pytestmark = pytest.mark.django_db

REPORT = Report(
    "revenue",
    "الإيرادات والتحصيل",
    [Column("day", "اليوم", "date"), Column("revenue", "صافي الإيراد", "money"), Column("note", "البيان")],
    [{"day": None, "revenue": 1_500_050, "note": "<b>نزيل</b>"}, {"day": None, "revenue": 0, "note": "28/09 – 30/09"}],
    None,
    totals={"revenue": 1_500_050},
    tiles=[{"label": "المحصّل", "value": 2_000_000, "type": "money"}],
    formula="الإيراد عند التسكين",
)


def test_the_html_is_an_arabic_landscape_page():
    html = pdf.to_html(REPORT, decimals=0, hotel_name="سكاي تاورز")
    assert 'dir="rtl"' in html and "A4 landscape" in html
    assert "الإيرادات والتحصيل" in html and "سكاي تاورز" in html
    assert "15,001" in html and "20,000" in html  # money in pounds with separators
    assert "الإجمالي" in html and "الإيراد عند التسكين" in html
    assert "&lt;b&gt;" in html  # text is escaped
    assert '<span dir="ltr">28/09 – 30/09</span>' in html  # a date range reads left to right


def test_no_edge_is_a_clear_message(manager_api):
    with mock.patch.object(pdf, "edge_path", return_value=None):
        res = manager_api.get("/api/v1/reports/occupancy/export", {"format": "pdf"})
    assert res.status_code == 503 and res.json()["code"] == "pdf_unavailable"
    assert manager_api.get("/api/v1/reports/occupancy/export", {"format": "doc"}).status_code == 400


@pytest.mark.skipif(pdf.edge_path() is None, reason="Microsoft Edge is on Windows only")
def test_edge_writes_the_pdf(manager_api):
    res = manager_api.get("/api/v1/reports/occupancy/export", {"format": "pdf"})
    assert res.status_code == 200 and res["Content-Type"] == "application/pdf"
    assert res.content.startswith(b"%PDF") and res["Content-Disposition"].endswith('.pdf"')
