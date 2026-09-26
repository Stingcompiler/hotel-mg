"""Spec §9.3 property test: random operation sequences → backups at random points → import in random order
(with repeats) → all report totals on the owner DB equal the reception DB."""

import dataclasses
import tempfile
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from hypothesis import HealthCheck, given
from hypothesis import settings as hsettings
from hypothesis import strategies as st

from apps.accounts.models import User
from apps.backup import export, keys, merge
from apps.billing import services as billing
from apps.cash import services as cash
from apps.core.errors import ApiError
from apps.guests.models import Guest
from apps.reports.totals import snapshot
from apps.rooms.models import Room, RoomType
from apps.stays import services as reservations
from apps.stays import stay_services
from apps.stays.models import Stay

pytestmark = pytest.mark.django_db(transaction=True, databases=["default", "owner", "incoming"])

OPS = st.lists(
    st.one_of(
        st.tuples(st.just("book"), st.integers(1, 4), st.integers(0, 6_000_000)),
        st.tuples(st.just("pay"), st.integers(0, 10), st.integers(100, 3_000_000)),
        st.tuples(st.just("expense"), st.integers(100, 900_000), st.just(0)),
        st.tuples(st.just("extend"), st.integers(0, 10), st.integers(1, 3)),
        st.tuples(st.just("checkout"), st.integers(0, 10), st.just(0)),
        st.tuples(st.just("backup"), st.just(0), st.just(0)),
    ),
    min_size=2,
    max_size=10,
)


def _fresh_hotel(home: Path, public_key: str) -> User:
    for alias in ("default", "owner"):
        call_command("flush", database=alias, interactive=False, verbosity=0)
    settings.RUNTIME = dataclasses.replace(settings.RUNTIME, home=home)
    settings.RUNTIME.data_dir.mkdir(parents=True, exist_ok=True)
    manager = User.objects.create_user("manager", "المدير", role="manager", password="pw-123456", pin="1234")
    room_type = RoomType.objects.create(
        name="مزدوجة", nightly_price=1_500_000, weekly_price=9_500_000, monthly_price=30_000_000
    )
    for n in ("201", "202", "203", "204"):
        Room.objects.create(number=n, floor=2, room_type=room_type)
    cfg = export.backup_settings()
    cfg.owner_recipient = public_key
    cfg.save()
    cash.open_shift(manager, opening=5_000_000)
    return manager


def _in_house():
    return list(Stay.objects.filter(reservation__status="checked_in").select_related("reservation").order_by("pk"))


def _apply(actor, op, arg, value, names):
    kind = op
    try:
        if kind == "book":
            free = list(Room.objects.filter(status="ready").order_by("number"))
            if free:
                guest = Guest.objects.create(full_name=next(names), search_name="x")
                room = free[0]
                stay = stay_services.book_and_check_in(
                    actor,
                    guest=guest,
                    room_type=room.room_type,
                    room=room,
                    check_in_date=reservations.today(),
                    duration_kind="daily",
                    count=arg,
                )
                if value:
                    billing.record_payment(actor, billing.folio_of(stay.reservation).pk, amount=value, method="cash")
        elif kind in ("pay", "extend", "checkout"):
            stays = _in_house()
            if not stays:
                return
            stay = stays[arg % len(stays)]
            folio = billing.folio_of(stay.reservation)
            if kind == "pay":
                billing.record_payment(actor, folio.pk, amount=value, method="bankak", reference=f"R{value}")
            elif kind == "extend":
                stay_services.extend(actor, stay.pk, duration_kind="daily", count=value)
            else:
                due = billing.FolioTotals.of(folio).balance
                if due > 0:
                    billing.record_payment(actor, folio.pk, amount=due, method="cash")
                if due >= 0:
                    stay_services.checkout(actor, stay.pk)
        elif kind == "expense":
            cash.create_expense(actor, category="supplies", amount=arg, note="مواد", method="cash")
    except ApiError:
        pass  # e.g. an extension blocked by a later booking: a legitimate refusal, nothing written


@hsettings(
    max_examples=12, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
)
@given(ops=OPS, data=st.data())
def test_imports_in_any_order_reproduce_reception_totals(ops, data):
    original = settings.RUNTIME
    with tempfile.TemporaryDirectory() as tmp:
        identity_path = Path(tmp) / "owner.key"
        public = keys.generate(identity_path)
        identity = keys.load(identity_path)
        try:
            actor = _fresh_hotel(Path(tmp) / "reception", public)
            names = (f"نزيل رقم {i}" for i in range(1000))
            backups = []
            for op, arg, value in ops:
                if op == "backup":
                    backups.append(Path(export.run_backup(actor).path))
                else:
                    _apply(actor, op, arg, value, names)
            backups.append(Path(export.run_backup(actor).path))  # the reception's final state

            order = data.draw(st.lists(st.sampled_from(backups), min_size=1, max_size=6), label="import order")
            order.append(backups[-1])  # the newest must arrive at least once, at any position
            order = data.draw(st.permutations(order), label="shuffled")
            for path in order:
                result = merge.import_backup(
                    None,
                    path.read_bytes(),
                    source="file",
                    file_name=path.name,
                    target="owner",
                    identity=identity,
                    allow_older=True,
                )
                assert result.run.status == "ok", result.run.error
            assert snapshot("owner") == snapshot("default")
        finally:
            settings.RUNTIME = original
