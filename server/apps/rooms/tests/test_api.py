import pytest

from apps.audit.models import AuditLog
from apps.rooms.models import Room, RoomStatusHistory, RoomType

pytestmark = pytest.mark.django_db

DOUBLE = {"name": "مزدوجة", "capacity": 2, "nightly_price": 1_500_000, "weekly_price": 9_500_000,
          "monthly_price": 30_000_000}  # fmt: skip


@pytest.fixture
def double(manager):
    return RoomType.objects.create(created_by=manager, **DOUBLE)


@pytest.fixture
def room(double):
    return Room.objects.create(number="203", floor=2, room_type=double)


class TestRoomTypes:
    def test_create_needs_manager_and_confirmation(self, reception_api, manager_api, confirm):
        assert reception_api.post("/api/v1/room-types/", DOUBLE, format="json").status_code == 403
        assert manager_api.post("/api/v1/room-types/", DOUBLE, format="json").status_code == 403
        confirm(manager_api)
        res = manager_api.post("/api/v1/room-types/", DOUBLE, format="json")
        assert res.status_code == 201
        assert res.json()["nightly_price"] == 1_500_000
        assert res.json()["room_count"] == 0

    def test_prices_must_be_integers(self, manager_api, confirm):
        confirm(manager_api)
        res = manager_api.post("/api/v1/room-types/", {**DOUBLE, "nightly_price": 15000.5}, format="json")
        assert res.status_code == 400
        assert "nightly_price" in res.json()["errors"]

    def test_duplicate_name_is_refused(self, manager_api, confirm, double):
        confirm(manager_api)
        res = manager_api.post("/api/v1/room-types/", DOUBLE, format="json")
        assert res.json()["errors"]["name"] == ["يوجد نوع غرفة بهذا الاسم."]

    def test_price_edit_needs_confirmation_but_rename_does_not(self, manager_api, confirm, double):
        url = f"/api/v1/room-types/{double.pk}"
        res = manager_api.patch(url, {"version": 1, "name": "مزدوجة كبيرة"}, format="json")
        assert res.status_code == 200
        res = manager_api.patch(url, {"version": 2, "nightly_price": 1_600_000}, format="json")
        assert res.json()["code"] == "confirmation_required"
        confirm(manager_api)
        res = manager_api.patch(url, {"version": 2, "nightly_price": 1_600_000}, format="json")
        assert res.status_code == 200
        assert res.json()["nightly_price"] == 1_600_000
        assert AuditLog.objects.filter(action="room_type.update_prices").exists()

    def test_reception_can_read(self, reception_api, double):
        assert [t["name"] for t in reception_api.get("/api/v1/room-types/").json()] == ["مزدوجة"]


class TestRooms:
    def test_create_and_list(self, manager_api, double):
        res = manager_api.post("/api/v1/rooms/", {"number": "205", "floor": 2, "room_type": str(double.pk)},
                               format="json")  # fmt: skip
        assert res.status_code == 201
        assert res.json()["status"] == "ready"
        res = manager_api.post("/api/v1/rooms/", {"number": "205", "floor": 2, "room_type": str(double.pk)},
                               format="json")  # fmt: skip
        assert res.json()["errors"]["number"] == ["يوجد غرفة بهذا الرقم."]
        rooms = manager_api.get("/api/v1/rooms/", {"floor": 2}).json()
        assert [r["number"] for r in rooms] == ["205"]
        assert rooms[0]["room_type_name"] == "مزدوجة"

    def test_reception_cannot_create(self, reception_api, double):
        res = reception_api.post("/api/v1/rooms/", {"number": "1", "floor": 1, "room_type": str(double.pk)},
                                 format="json")  # fmt: skip
        assert res.status_code == 403

    def test_occupied_room_cannot_leave_service(self, manager_api, room):
        Room.objects.filter(pk=room.pk).update(status="occupied")
        res = manager_api.patch(f"/api/v1/rooms/{room.pk}", {"version": 1, "in_service": False}, format="json")
        assert res.status_code == 409
        assert res.json()["code"] == "room_occupied"

    def test_take_out_of_service(self, manager_api, room):
        payload = {"version": 1, "in_service": False, "note": "تجديد كامل حتى نوفمبر"}
        res = manager_api.patch(f"/api/v1/rooms/{room.pk}", payload, format="json")
        assert res.status_code == 200
        assert res.json()["in_service"] is False


class TestSetStatus:
    def url(self, room):
        return f"/api/v1/rooms/{room.pk}/set-status"

    def test_maintenance_needs_a_reason(self, reception_api, room):
        res = reception_api.post(self.url(room), {"status": "maintenance"}, format="json")
        assert res.status_code == 400
        assert res.json()["code"] == "reason_required"

    def test_maintenance_round_trip_writes_history_and_audit(self, reception_api, room, reception):
        res = reception_api.post(self.url(room), {"status": "maintenance", "reason": "تسرب مياه"}, format="json")
        assert res.status_code == 200
        assert res.json()["maintenance_reason"] == "تسرب مياه"
        res = reception_api.post(self.url(room), {"status": "ready"}, format="json")
        assert res.json()["maintenance_reason"] == ""
        history = RoomStatusHistory.objects.filter(room=room).order_by("at")
        history = list(history.values_list("from_status", "to_status"))
        assert history == [("ready", "maintenance"), ("maintenance", "ready")]
        row = AuditLog.objects.filter(action="room.set_status").first()
        assert row.actor == reception
        assert row.before == {"id": str(room.pk), "status": "ready", "maintenance_reason": ""}

        hist = reception_api.get(f"/api/v1/rooms/{room.pk}/history").json()["results"]
        assert hist[0]["to_status"] == "ready" and hist[0]["by_name"] == "أحمد علي"

    def test_occupied_room_cannot_be_changed_by_hand(self, reception_api, room):
        Room.objects.filter(pk=room.pk).update(status="occupied")
        res = reception_api.post(self.url(room), {"status": "maintenance", "reason": "x"}, format="json")
        assert res.status_code == 409
        body = res.json()
        assert body["code"] == "invalid_room_transition"
        assert body["allowed"] == []
        assert "203" in body["detail"]

    def test_confirm_cleaned(self, reception_api, room):
        Room.objects.filter(pk=room.pk).update(status="cleaning")
        res = reception_api.post(self.url(room), {"status": "ready", "version": 1}, format="json")
        assert res.status_code == 200 and res.json()["status"] == "ready"

    def test_stale_version(self, reception_api, room):
        res = reception_api.post(self.url(room), {"status": "maintenance", "reason": "x", "version": 9}, format="json")
        assert res.status_code == 409 and res.json()["code"] == "version_conflict"
