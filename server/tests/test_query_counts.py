"""Query counts that must not grow with the data (review 2026-09-29, F-13).

Before batch 10 these endpoints ran queries per row: two per reservation or folio, three per shift, one per guest's
companions — 80 s for the owner dashboard on five years of data. The demo hotel has 18 guests in house; each cap
below is well under one query per row, so a per-row query anywhere fails the test.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

CASES = [
    ("reservations list", "/api/v1/reservations/", 8),
    ("guests in house", "/api/v1/stays/", 14),
    ("guests list", "/api/v1/guests/", 10),
    ("guests owing", "/api/v1/guests/?debt=true", 12),
    ("shift history", "/api/v1/shifts/", 8),
    ("reports index", "/api/v1/reports/", 12),
    ("debts report", "/api/v1/reports/debts?status=all", 16),
    ("cash shifts report", "/api/v1/reports/cash_shifts", 10),
    ("room status report", "/api/v1/reports/room_status", 12),
    ("occupancy report", "/api/v1/reports/occupancy", 14),
    ("owner dashboard", "/api/v1/reports/owner-dashboard", 60),
]


@pytest.mark.parametrize(("name", "url", "cap"), CASES, ids=[c[0] for c in CASES])
def test_the_query_count_does_not_grow_with_the_rows(api_as_manager, name, url, cap):
    with CaptureQueriesContext(connection) as ctx:
        res = api_as_manager.get(url)
    assert res.status_code == 200, (name, res.content[:300])
    print(f"{name}: {len(ctx.captured_queries)} queries")
    assert len(ctx.captured_queries) <= cap, (name, len(ctx.captured_queries))


def test_grouped_totals_match_the_lines_and_payments(seeded):
    """The grouped queries give each folio what its own lines and payments add up to."""
    from django.db.models import Sum

    from apps.billing.models import Folio
    from apps.billing.services import balances_by_folio, balances_by_reservation, totals_by_folio
    from apps.cash.models import Shift
    from apps.cash.services import ShiftTotals
    from apps.stays.models import Reservation

    totals, balances = totals_by_folio(), balances_by_folio()
    assert totals
    for folio in Folio.objects.all():
        charged = folio.lines.aggregate(s=Sum("amount"))["s"] or 0
        paid = folio.payments.aggregate(s=Sum("amount"))["s"] or 0
        t = totals.get(folio.pk)
        got = (t.total, t.paid, t.balance) if t else (0, 0, 0)
        assert got == (charged, paid, charged - paid), folio.pk
        assert balances.get(folio.pk, 0) == charged - paid
    by_reservation = balances_by_reservation(Reservation.objects.all())
    assert by_reservation == balances_by_reservation(list(Reservation.objects.values_list("pk", flat=True)))
    shifts = list(Shift.objects.all())
    assert shifts
    grouped = ShiftTotals.for_shifts(shifts)
    for shift in shifts:
        assert grouped[shift.pk] == ShiftTotals.of(shift)
