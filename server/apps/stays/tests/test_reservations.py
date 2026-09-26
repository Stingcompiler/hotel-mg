import threading
from datetime import date

import pytest
from django.db import connection

from apps.audit.models import AuditLog
from apps.core.errors import ApiError
from apps.rooms.models import Room
from apps.stays import services
from apps.stays.models import Reservation

pytestmark = pytest.mark.django_db


def book(api, guest, room_type, room=None, **extra):
    payload = {"guest": str(guest.pk), "room_type": str(room_type.pk), "check_in_date": "2026-09-27",
               "duration_kind": "daily", "count": 3, **extra}  # fmt: skip
    if room is not None:
        payload["room"] = str(room.pk)
    return api.post("/api/v1/reservations/", payload, format="json")


class TestQuote:
    def test_daily_ten_offers_two_prices(self, reception_api, single):
        res = reception_api.post(
            "/api/v1/reservations/quote",
            {"room_type": str(single.pk), "check_in_date": "2026-09-27", "duration_kind": "daily", "count": 10},
            format="json",
        )
        body = res.json()
        assert body["nights"] == 10
        assert body["check_out_date"] == "2026-10-07"
        assert body["last_night"] == "2026-10-06"
        assert [(o["label"], o["total"]) for o in body["options"]] == [
            ("أسبوع + 3 ليالٍ", 11_300_000),
            ("10 ليالٍ", 12_000_000),
        ]

    def test_monthly(self, reception_api, double):
        res = reception_api.post(
            "/api/v1/reservations/quote",
            {"room_type": str(double.pk), "check_in_date": "2026-10-01", "duration_kind": "monthly", "count": 1},
            format="json",
        )
        assert res.json()["last_night"] == "2026-10-30"
        assert res.json()["options"][0]["total"] == 30_000_000


class TestCreate:
    def test_books_room_with_snapshot_and_audit(self, reception_api, guest, single, rooms, reception):
        res = book(reception_api, guest, single, rooms["101"], count=10, option_key="m0w1d3")
        assert res.status_code == 201, res.json()
        body = res.json()
        assert body["duration_kind"] == "mixed" and body["duration_count"] == 10
        assert body["total"] == 11_300_000
        assert body["rate_snapshot"]["prices"]["nightly"] == 1_200_000
        assert body["rate_snapshot"]["label"] == "أسبوع + 3 ليالٍ"
        assert AuditLog.objects.get(action="reservation.create").actor == reception

    def test_several_options_need_a_choice(self, reception_api, guest, single):
        res = book(reception_api, guest, single, count=10)
        assert res.status_code == 400
        assert res.json()["code"] == "pricing_choice_required"
        assert res.json()["options"] == ["m0w1d3", "m0w0d10"]

    def test_price_override_needs_reason(self, reception_api, guest, single):
        res = book(reception_api, guest, single, count=10, option_key="m0w1d3", final_total=10_500_000)
        assert res.json()["code"] == "reason_required"
        res = book(reception_api, guest, single, count=10, option_key="m0w1d3", final_total=10_500_000,
                   override_reason="اتفاق مسبق مع المدير — شركة النيل للمقاولات")  # fmt: skip
        assert res.status_code == 201
        snap = res.json()["rate_snapshot"]
        assert (snap["base_total"], snap["override_total"]) == (11_300_000, 10_500_000)
        assert res.json()["total"] == 10_500_000

    def test_price_edits_later_do_not_touch_booking(self, reception_api, guest, single):
        rid = book(reception_api, guest, single).json()["id"]
        single.nightly_price = 9_900_000
        single.save()
        assert Reservation.objects.get(pk=rid).total == 3 * 1_200_000

    def test_past_date_and_type_mismatch(self, reception_api, guest, single, rooms):
        assert book(reception_api, guest, single, check_in_date="2026-09-25").json()["code"] == "date_in_past"
        assert book(reception_api, guest, single, rooms["205"]).json()["code"] == "room_type_mismatch"

    def test_overlap_is_refused_back_to_back_is_fine(self, reception_api, guest, single, rooms):
        assert book(reception_api, guest, single, rooms["101"]).status_code == 201  # 27 → 30 Sep
        res = book(reception_api, guest, single, rooms["101"], check_in_date="2026-09-29")
        assert res.status_code == 409 and res.json()["code"] == "room_unavailable"
        assert "101" in res.json()["detail"]
        assert book(reception_api, guest, single, rooms["101"], check_in_date="2026-09-30").status_code == 201

    def test_out_of_service_and_maintenance_today(self, reception_api, guest, single, rooms):
        Room.objects.filter(number="101").update(in_service=False)
        assert book(reception_api, guest, single, rooms["101"]).status_code == 409
        Room.objects.filter(number="102").update(status="maintenance")
        assert book(reception_api, guest, single, rooms["102"], check_in_date="2026-09-26").status_code == 409
        assert book(reception_api, guest, single, rooms["102"]).status_code == 201  # tomorrow: may be fixed by then


class TestAvailability:
    def query(self, api, room_type, date_from, date_to):
        res = api.get("/api/v1/reservations/availability",
                      {"room_type": str(room_type.pk), "date_from": date_from, "date_to": date_to})  # fmt: skip
        return [r["number"] for r in res.json()]

    def test_excludes_booked_and_out_of_service(self, reception_api, guest, single, rooms):
        # Artboard 6.4 B: «102 محجوزة غدًا فلا تظهر»
        book(reception_api, guest, single, rooms["102"], check_in_date="2026-09-27")
        Room.objects.filter(number="106").update(in_service=False)
        assert self.query(reception_api, single, "2026-09-27", "2026-10-07") == ["101"]
        assert self.query(reception_api, single, "2026-09-30", "2026-10-02") == ["101", "102"]

    def test_overdue_guest_keeps_room_today(self, reception_api, guest, single, rooms):
        Reservation.objects.create(
            guest=guest, room_type=single, room=rooms["101"], check_in_date=date(2026, 9, 17),
            check_out_date=date(2026, 9, 24), duration_kind="weekly", duration_count=1, status="checked_in",
            rate_snapshot={}, total=7_700_000,
        )  # fmt: skip
        assert "101" not in self.query(reception_api, single, "2026-09-26", "2026-09-28")
        assert "101" in self.query(reception_api, single, "2026-09-27", "2026-09-28")

    def test_bad_range(self, reception_api, single):
        res = reception_api.get(
            "/api/v1/reservations/availability", {"date_from": "2026-10-02", "date_to": "2026-10-01"}
        )
        assert res.status_code == 400


class TestLifecycle:
    def test_cancel_needs_reason_and_frees_room(self, reception_api, guest, single, rooms):
        rid = book(reception_api, guest, single, rooms["101"]).json()["id"]
        res = reception_api.post(f"/api/v1/reservations/{rid}/cancel", {"reason": " "}, format="json")
        assert res.status_code == 400
        res = reception_api.post(f"/api/v1/reservations/{rid}/cancel", {"reason": "اعتذر النزيل"}, format="json")
        assert res.json()["status"] == "cancelled"
        assert book(reception_api, guest, single, rooms["101"]).status_code == 201
        res = reception_api.post(f"/api/v1/reservations/{rid}/cancel", {"reason": "مرة أخرى"}, format="json")
        assert res.json()["code"] == "invalid_reservation_status"

    def test_no_show_only_from_arrival_day(self, reception_api, guest, single):
        rid = book(reception_api, guest, single).json()["id"]  # arrives tomorrow
        assert reception_api.post(f"/api/v1/reservations/{rid}/no-show").status_code == 409
        today_id = book(reception_api, guest, single, check_in_date="2026-09-26").json()["id"]
        assert reception_api.post(f"/api/v1/reservations/{today_id}/no-show").json()["status"] == "no_show"

    def test_assign_room_later(self, reception_api, guest, single, rooms):
        rid = book(reception_api, guest, single).json()["id"]
        book(reception_api, guest, single, rooms["101"])
        res = reception_api.post(f"/api/v1/reservations/{rid}/assign-room", {"room": str(rooms["101"].pk)},
                                 format="json")  # fmt: skip
        assert res.status_code == 409
        res = reception_api.post(f"/api/v1/reservations/{rid}/assign-room", {"room": str(rooms["106"].pk)},
                                 format="json")  # fmt: skip
        assert res.json()["room_number"] == "106"

    def test_window_list(self, reception_api, guest, single, rooms):
        book(reception_api, guest, single, rooms["101"])
        book(reception_api, guest, single, rooms["102"], check_in_date="2026-10-20")
        res = reception_api.get("/api/v1/reservations/", {"date_from": "2026-09-26", "date_to": "2026-10-10"})
        assert [r["room_number"] for r in res.json()] == ["101"]


@pytest.mark.django_db(transaction=True)
def test_concurrent_bookings_of_one_room_admit_exactly_one(guest, single, rooms, reception):
    """Spec §12 B1 gate: overlap blocked under concurrent requests (real threads, one SQLite file)."""
    n = 6
    barrier = threading.Barrier(n)
    outcomes = []

    def attempt(i):
        try:
            barrier.wait()
            services.create_reservation(
                reception, guest=guest, room_type=single, room=rooms["101"],
                check_in_date=date(2026, 9, 27 + (i % 2)), duration_kind="daily", count=3,
            )  # fmt: skip
            outcomes.append("ok")
        except ApiError as exc:
            outcomes.append(exc.error_code)
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert outcomes.count("ok") == 1, outcomes
    assert outcomes.count("room_unavailable") == n - 1
    assert Reservation.objects.filter(room=rooms["101"]).count() == 1
