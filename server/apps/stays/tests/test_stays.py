from datetime import date, timedelta

import pytest
import time_machine
from django.utils import timezone

from apps.accounts.services import login_with_password
from apps.audit.models import AuditLog
from apps.rooms.models import Room, RoomStatusHistory
from apps.stays.models import Reservation, Stay
from conftest import PASSWORD

pytestmark = pytest.mark.django_db


def book(api, guest, room_type, room, **extra):
    payload = {
        "guest": str(guest.pk),
        "room_type": str(room_type.pk),
        "room": str(room.pk),
        "check_in_date": "2026-09-26",
        "duration_kind": "daily",
        "count": 3,
        **extra,
    }
    res = api.post("/api/v1/reservations/", payload, format="json")
    assert res.status_code == 201, res.json()
    return res.json()


def walk_in(api, guest, room_type, room, **extra):
    return book(api, guest, room_type, room, check_in_now=True, **extra)


def stay_of(reservation_json) -> Stay:
    return Stay.objects.get(reservation_id=reservation_json["id"])


def room_status(number):
    return Room.objects.get(number=number).status


class TestCheckIn:
    def test_check_in_occupies_room(self, reception_api, guest, single, rooms, reception):
        r = book(reception_api, guest, single, rooms["101"])
        res = reception_api.post("/api/v1/stays/check-in", {"reservation": r["id"]}, format="json")
        assert res.status_code == 201, res.json()
        body = res.json()
        assert body["reservation"]["status"] == "checked_in"
        assert body["last_night"] == "2026-09-28"
        assert [(s["room_number"], s["from_date"], s["to_date"]) for s in body["segments"]] == [
            ("101", "2026-09-26", "2026-09-29")
        ]
        assert room_status("101") == "occupied"
        assert AuditLog.objects.filter(action="stay.check_in", actor=reception).exists()

    def test_walk_in_books_and_checks_in_atomically(self, reception_api, guest, single, rooms):
        r = walk_in(reception_api, guest, single, rooms["101"])
        assert r["status"] == "checked_in"
        Room.objects.filter(number="102").update(status="cleaning")
        payload = {
            "guest": str(guest.pk),
            "room_type": str(single.pk),
            "room": str(rooms["102"].pk),
            "check_in_date": "2026-09-26",
            "duration_kind": "daily",
            "count": 1,
            "check_in_now": True,
        }
        res = reception_api.post("/api/v1/reservations/", payload, format="json")
        assert res.status_code == 409 and res.json()["code"] == "room_not_ready"
        assert not Reservation.objects.filter(room=rooms["102"]).exists()  # rolled back with the check-in

    def test_future_booking_cannot_check_in_yet(self, reception_api, guest, single, rooms):
        r = book(reception_api, guest, single, rooms["101"], check_in_date="2026-09-27")
        res = reception_api.post("/api/v1/stays/check-in", {"reservation": r["id"]}, format="json")
        assert res.json()["code"] == "check_in_not_allowed"

    def test_room_required(self, reception_api, guest, single, rooms):
        payload = {
            "guest": str(guest.pk),
            "room_type": str(single.pk),
            "check_in_date": "2026-09-26",
            "duration_kind": "daily",
            "count": 2,
        }
        rid = reception_api.post("/api/v1/reservations/", payload, format="json").json()["id"]
        assert reception_api.post("/api/v1/stays/check-in", {"reservation": rid}, format="json").json()["code"] == (
            "room_required"
        )
        res = reception_api.post(
            "/api/v1/stays/check-in", {"reservation": rid, "room": str(rooms["106"].pk)}, format="json"
        )
        assert res.status_code == 201


class TestExtend:
    def test_quote_and_extend_monthly(self, reception_api, guest, double, rooms):
        r = walk_in(reception_api, guest, double, rooms["202"], duration_kind="monthly", count=1)
        stay = stay_of(r)
        q = reception_api.post(
            f"/api/v1/stays/{stay.pk}/extend/quote", {"duration_kind": "monthly", "count": 1}, format="json"
        ).json()
        assert q["current_check_out"] == "2026-10-26"
        assert q["quote"]["last_night"] == "2026-11-24"
        assert q["total_nights"] == 60 and q["room_available"] is True
        assert q["quote"]["options"][0]["total"] == 30_000_000

        res = reception_api.post(
            f"/api/v1/stays/{stay.pk}/extend", {"duration_kind": "monthly", "count": 1}, format="json"
        )
        body = res.json()
        assert body["reservation"]["check_out_date"] == "2026-11-25"
        assert body["reservation"]["duration_kind"] == "monthly" and body["reservation"]["duration_count"] == 2
        assert body["reservation"]["total"] == 60_000_000
        assert body["segments"][0]["to_date"] == "2026-11-25"

    def test_extension_blocked_by_next_booking(self, reception_api, guest, single, rooms):
        stay = stay_of(walk_in(reception_api, guest, single, rooms["101"]))  # until 29th
        book(reception_api, guest, single, rooms["101"], check_in_date="2026-09-30")
        q = reception_api.post(
            f"/api/v1/stays/{stay.pk}/extend/quote", {"duration_kind": "daily", "count": 2}, format="json"
        ).json()
        assert q["room_available"] is False
        res = reception_api.post(
            f"/api/v1/stays/{stay.pk}/extend", {"duration_kind": "daily", "count": 2}, format="json"
        )
        assert res.status_code == 409 and res.json()["code"] == "room_unavailable"
        ok = reception_api.post(
            f"/api/v1/stays/{stay.pk}/extend", {"duration_kind": "daily", "count": 1}, format="json"
        )
        assert ok.json()["reservation"]["duration_count"] == 4


class TestChangeRoom:
    def test_same_type_move(self, reception_api, guest, single, rooms, reception):
        stay = stay_of(walk_in(reception_api, guest, single, rooms["101"]))
        options = reception_api.get(f"/api/v1/stays/{stay.pk}/change-room").json()
        assert [(o["room"]["number"], o["difference"]) for o in options][:2] == [("102", 0), ("106", 0)]
        assert options[-1]["room"]["number"] in ("202", "205")  # other types after

        res = reception_api.post(
            f"/api/v1/stays/{stay.pk}/change-room",
            {
                "room": str(rooms["102"].pk),
                "reason": "عطل في التكييف",
                "old_room_status": "maintenance",
                "maintenance_reason": "عطل في التكييف",
            },
            format="json",
        )
        assert res.status_code == 200, res.json()
        segments = [(s["room_number"], s["from_date"], s["to_date"]) for s in res.json()["segments"]]
        assert segments == [("101", "2026-09-26", "2026-09-26"), ("102", "2026-09-26", "2026-09-29")]
        assert room_status("101") == "maintenance" and room_status("102") == "occupied"
        hist = RoomStatusHistory.objects.filter(room=rooms["101"]).order_by("at").values_list("to_status", flat=True)
        assert list(hist) == ["occupied", "cleaning", "maintenance"]
        assert res.json()["reservation"]["total"] == 3_600_000

    def test_cheaper_type_needs_manager(self, reception_api, guest, single, double, rooms, manager):
        stay = stay_of(walk_in(reception_api, guest, double, rooms["202"]))
        url = f"/api/v1/stays/{stay.pk}/change-room"
        body = {"room": str(rooms["101"].pk), "reason": "طلب النزيل"}
        res = reception_api.post(url, body, format="json")
        assert res.status_code == 403 and res.json()["code"] == "override_required"
        assert res.json()["difference"] == -900_000  # 3 nights × (12,000 − 15,000)
        res = reception_api.post(url, {**body, "override_password": "wrong", "override_reason": "x"}, format="json")
        assert res.json()["code"] == "override_invalid"
        res = reception_api.post(
            url, {**body, "override_password": PASSWORD, "override_reason": "خصم للنزيل"}, format="json"
        )
        assert res.status_code == 200
        assert res.json()["reservation"]["total"] == 4_500_000 - 900_000
        assert res.json()["reservation"]["room_type_name"] == "مفردة"
        row = AuditLog.objects.get(action="stay.change_room")
        assert row.after["approved_by"] == str(manager.pk)


class TestCheckout:
    def test_checkout_frees_room_for_cleaning(self, reception_api, guest, single, rooms):
        stay = stay_of(walk_in(reception_api, guest, single, rooms["101"]))
        res = reception_api.post(f"/api/v1/stays/{stay.pk}/checkout", {}, format="json")
        assert res.status_code == 200
        assert res.json()["reservation"]["status"] == "checked_out"
        assert res.json()["checked_out_at"] is not None
        assert res.json()["segments"][0]["to_date"] == "2026-09-26"  # left on arrival day
        assert room_status("101") == "cleaning"
        again = reception_api.post(f"/api/v1/stays/{stay.pk}/checkout", {}, format="json")
        assert again.json()["code"] == "invalid_reservation_status"

    def test_overdue_checkout_keeps_actual_nights(self, reception_api, guest, single, rooms, reception):
        stay = stay_of(walk_in(reception_api, guest, single, rooms["101"], count=1))  # last night 26th
        with time_machine.travel(timezone.now() + timedelta(days=2)):
            token = login_with_password(reception.username, PASSWORD).token  # the 12 h session has expired
            reception_api.credentials(HTTP_AUTHORIZATION=f"Token {token}")
            board = reception_api.get("/api/v1/rooms/", {"view": "board"}).json()
            row = next(r for r in board["rooms"] if r["number"] == "101")
            assert row["display_status"] == "overdue" and row["stay"]["days_left"] == -2
            res = reception_api.post(f"/api/v1/stays/{stay.pk}/checkout", {"room_status": "cleaning"}, format="json")
        assert res.json()["segments"][0]["to_date"] == "2026-09-28"

    def test_manager_override_is_recorded(self, reception_api, guest, single, rooms, manager):
        stay = stay_of(walk_in(reception_api, guest, single, rooms["101"]))
        res = reception_api.post(
            f"/api/v1/stays/{stay.pk}/checkout",
            {"override_password": PASSWORD, "override_reason": "سيسدد غدًا"},
            format="json",
        )
        assert res.json()["override_by_name"] == "المدير"


class TestCancelStay:
    def test_cancel_settles_nights_used(self, reception_api, guest, double, rooms, manager):
        with time_machine.travel(timezone.now() - timedelta(days=12)):  # arrived 14 Sep, monthly
            r = walk_in(
                reception_api, guest, double, rooms["202"], check_in_date="2026-09-14", duration_kind="monthly", count=1
            )
        stay = stay_of(r)
        opts = reception_api.get(f"/api/v1/stays/{stay.pk}/cancel").json()
        assert opts["nights_used"] == 12
        assert [(o["label"], o["total"]) for o in opts["options"]] == [
            ("أسبوع + 5 ليالٍ", 9_500_000 + 5 * 1_500_000),
            ("12 ليلة", 12 * 1_500_000),
        ]
        url = f"/api/v1/stays/{stay.pk}/cancel"
        assert (
            reception_api.post(
                url, {"reason": "سفر مفاجئ", "option_key": "m0w0d12", "override_password": "x"}, format="json"
            ).json()["code"]
            == "override_invalid"
        )
        res = reception_api.post(
            url, {"reason": "سفر مفاجئ", "option_key": "m0w0d12", "override_password": PASSWORD}, format="json"
        )
        body = res.json()
        assert body["reservation"]["status"] == "cancelled"
        assert body["reservation"]["total"] == 18_000_000
        assert body["reservation"]["rate_snapshot"]["cancellation"]["previous_total"] == 30_000_000
        assert room_status("202") == "cleaning"
        assert AuditLog.objects.get(action="stay.cancel").after["approved_by"] == str(manager.pk)


def test_board(reception_api, guest, single, double, rooms):
    walk_in(reception_api, guest, single, rooms["101"])
    book(reception_api, guest, single, rooms["102"], check_in_date="2026-09-27", duration_kind="weekly", count=1)
    Room.objects.filter(number="205").update(status="maintenance", maintenance_reason="تسرب مياه")
    board = reception_api.get("/api/v1/rooms/", {"view": "board"}).json()
    assert board["date"] == "2026-09-26"
    rooms_by_no = {r["number"]: r for r in board["rooms"]}
    assert rooms_by_no["101"]["stay"]["guest_name"] == guest.full_name
    assert rooms_by_no["101"]["stay"]["days_left"] == 2
    assert rooms_by_no["102"]["next_reservation"]["check_in_date"] == "2026-09-27"
    assert rooms_by_no["205"]["maintenance_reason"] == "تسرب مياه"
    s = board["summary"]
    assert (s["rooms"], s["occupied"], s["occupancy_percent"]) == (5, 1, 20)
    assert s["by_status"] == {"ready": 3, "occupied": 1, "cleaning": 0, "maintenance": 1}
    assert date.fromisoformat(board["date"]) == date(2026, 9, 26)
