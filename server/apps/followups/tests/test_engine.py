"""Spec §12 B3 gate: engine tests with a frozen clock — fire, restart, extend, snooze, neglect; guard blocks."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.core.management import call_command

from apps.accounts.models import User
from apps.accounts.services import login_with_password
from apps.cash import services as cash
from apps.followups import engine
from apps.followups.models import AlertRule, FollowupTask, TaskAction, Toast
from apps.stays.models import Stay
from conftest import PASSWORD

pytestmark = pytest.mark.django_db
TZ = ZoneInfo("Africa/Khartoum")


def at(day, hour=9, minute=0, month=10):
    return datetime(2026, month, day, hour, minute, tzinfo=TZ)


@pytest.fixture
def monthly_stay(reception_api, guest, double, rooms):
    """Walk-in 26 Sep, monthly: last night 25 Oct → first alert 20 Oct 09:00, second 23 Oct 09:00."""
    payload = {
        "guest": str(guest.pk),
        "room_type": str(double.pk),
        "room": str(rooms["202"].pk),
        "check_in_date": "2026-09-26",
        "duration_kind": "monthly",
        "count": 1,
        "check_in_now": True,
    }
    res = reception_api.post("/api/v1/reservations/", payload, format="json")
    assert res.status_code == 201, res.json()
    return Stay.objects.get(reservation_id=res.json()["id"])


def tick(now):
    with time_machine.travel(now, tick=False):
        return engine.tick(now)


def signed_in(api, user):
    """Sessions last 12 h and these tests jump weeks ahead: sign in again at the simulated time."""
    token = login_with_password(user.username, PASSWORD).token
    api.credentials(HTTP_AUTHORIZATION=f"Token {token}")
    return api


def act(api, task, action, when, **body):
    with time_machine.travel(when, tick=False):
        signed_in(api, User.objects.get(username="ahmed.ali"))
        return api.post(f"/api/v1/followups/tasks/{task.pk}/actions", {"action": action, **body}, format="json")


def the_task():
    return FollowupTask.objects.get(rule__duration_kind="monthly")


def test_default_rules_seeded_once(monthly_stay):
    tick(at(1))
    tick(at(2))
    rules = {(r.trigger_kind, r.duration_kind): r for r in AlertRule.objects.all()}
    assert len(rules) == 10
    monthly = rules[("stay_ending", "monthly")]
    assert (monthly.days_before, monthly.second_days_before, monthly.repeat_hours) == (5, 2, 12)


def test_fires_on_time_and_restart_never_duplicates(monthly_stay):
    assert tick(at(20, 8, 59))["created"] == 0
    assert tick(at(20, 9, 0))["created"] == 1
    assert tick(at(20, 9, 0))["created"] == 0  # restart / repeated tick
    assert tick(at(20, 9, 5))["created"] == 0
    task = the_task()
    assert task.due_at == at(20) and task.status == "open"
    assert task.title == "غرفة 202 — تنتهي بعد 5 أيام"
    assert Toast.objects.count() == 1


def test_catch_up_keeps_original_due_time(monthly_stay):
    tick(at(1))  # PC switched off from 1 to 21 October
    tick(at(21, 8, 0))
    task = the_task()
    assert task.due_at == at(20)  # created late, due when it should have been
    assert Toast.objects.filter(task=task).count() == 1  # one notification, not one per missed slot


def test_toast_schedule_first_second_then_repeat(monthly_stay):
    tick(at(20))
    tick(at(21))  # between first and second: no repeat
    assert Toast.objects.count() == 1
    tick(at(23))
    assert Toast.objects.count() == 2
    tick(at(23, 20))
    assert Toast.objects.count() == 2
    tick(at(23, 21))
    assert Toast.objects.count() == 3
    toast = Toast.objects.order_by("seq").last()
    assert toast.body == "خالد إبراهيم · شهري · انقر للفتح"


def test_snooze_limit_and_wake_up(monthly_stay, reception_api):
    tick(at(20))
    task = the_task()
    for n in range(1, 4):
        res = act(reception_api, task, "snooze", at(20, 9 + n), until=at(20, 9 + n, 30).isoformat())
        assert res.status_code == 200, res.json()
        assert res.json()["snooze_label"] == f"تأجيل ({n} من 3)"
        assert tick(at(20, 9 + n, 29))["woke"] == 0
        assert tick(at(20, 9 + n, 30))["woke"] == 1
    res = act(reception_api, task, "snooze", at(20, 13), until=at(20, 14).isoformat())
    assert res.status_code == 409 and res.json()["code"] == "snooze_limit"
    assert TaskAction.objects.filter(task=task, action="snooze").count() == 3


def test_waiting_needs_note_and_returns(monthly_stay, reception_api):
    tick(at(20))
    task = the_task()
    res = act(reception_api, task, "waiting", at(20, 11), until=at(20, 17).isoformat())
    assert res.json()["code"] == "reason_required"
    res = act(reception_api, task, "waiting", at(20, 11), note="سيؤكد التمديد بعد الظهر", until=at(20, 17).isoformat())
    assert res.json()["status"] == "waiting" and res.json()["note"] == "سيؤكد التمديد بعد الظهر"
    tick(at(20, 17))
    task.refresh_from_db()
    assert task.status == "open"
    assert Toast.objects.filter(task=task).count() == 2  # notified again when the follow-up time came


def test_neglect_records_the_responsible_shift(monthly_stay, reception):
    with time_machine.travel(at(20, 8), tick=False):
        shift = cash.open_shift(reception, opening=0)
    tick(at(20))
    tick(at(21, 8, 59))
    assert the_task().status == "open"
    assert tick(at(21, 9))["escalated"] == 1
    task = the_task()
    assert task.status == "neglected" and task.shift == shift
    board = _board_at(at(21, 10))
    assert board["today"][0]["neglected_shift_user"] == "أحمد علي"


def _board_at(now):
    from apps.followups.services import board

    with time_machine.travel(now, tick=False):
        return board(now)


def test_extend_from_the_task_closes_it_and_replans(monthly_stay, reception_api):
    tick(at(20))
    task = the_task()
    res = act(reception_api, task, "extend", at(20, 10), stay={"duration_kind": "monthly", "count": 1})
    assert res.status_code == 200, res.json()
    assert res.json()["status"] == "done"
    monthly_stay.reservation.refresh_from_db()
    assert str(monthly_stay.reservation.check_out_date) == "2026-11-25"
    assert tick(at(21))["created"] == 0  # next first alert: 19 Nov
    assert tick(at(19, 9, month=11))["created"] == 1
    assert FollowupTask.objects.filter(stay=monthly_stay, status="open").count() == 1


def test_direct_extension_supersedes_pending_task(monthly_stay, reception_api):
    tick(at(20))
    with time_machine.travel(at(20, 12), tick=False):
        signed_in(reception_api, User.objects.get(username="ahmed.ali"))
        res = reception_api.post(
            f"/api/v1/stays/{monthly_stay.pk}/extend", {"duration_kind": "daily", "count": 3}, format="json"
        )
    assert res.status_code == 200, res.json()
    task = the_task()
    assert task.status == "superseded" and task.note.startswith("تمديد حتى")


def test_confirm_checkout_from_the_task(monthly_stay, reception_api, reception):
    tick(at(20))
    task = the_task()
    with time_machine.travel(at(20, 10), tick=False):
        signed_in(reception_api, reception)
        cash.open_shift(reception, opening=0)
        folio = monthly_stay.reservation.folio
        reception_api.post(
            f"/api/v1/folios/{folio.pk}/payments", {"amount": 30_000_000, "method": "cash"}, format="json"
        )
    res = act(reception_api, task, "confirm_checkout", at(20, 11))
    assert res.status_code == 200 and res.json()["status"] == "done"
    monthly_stay.reservation.refresh_from_db()
    assert monthly_stay.reservation.status == "checked_out"
    assert act(reception_api, task, "done", at(20, 12), note="x").json()["code"] == "task_closed"


def test_overdue_stay_shows_once_in_late_group(reception_api, guest, single, rooms):
    payload = {
        "guest": str(guest.pk),
        "room_type": str(single.pk),
        "room": str(rooms["101"].pk),
        "check_in_date": "2026-09-26",
        "duration_kind": "daily",
        "count": 1,
        "check_in_now": True,
    }
    reception_api.post("/api/v1/reservations/", payload, format="json")
    tick(at(26, 10, month=9))  # daily rule: day of end 09:00 → due (from check-in time)
    tick(at(27, 0, 1, month=9))  # overdue rule fires right after the last night
    kinds = sorted(FollowupTask.objects.values_list("rule__trigger_kind", flat=True))
    assert kinds == ["stay_ending", "stay_overdue"]
    board = _board_at(at(27, 8, month=9))
    assert board["counts"]["late"] == 1 and board["late"][0]["when"] == "متجاوزة منذ يوم"


def test_system_triggers(reception, rooms):
    from apps.rooms.models import Room

    with time_machine.travel(at(26, 6, month=9), tick=False):
        cash.open_shift(reception, opening=0)
        Room.objects.filter(number="101").update(status="cleaning", status_changed_at=at(26, 6, month=9))
    assert tick(at(26, 10, month=9))["created"] == 1  # cleaning > 4 h
    assert tick(at(26, 20, 1, month=9))["created"] == 1  # shift open > 14 h
    board = _board_at(at(26, 21, month=9))
    assert board["counts"]["system"] == 2
    assert {row["title"] for row in board["system"]} == {
        "غرفة 101 — تحتاج تنظيف منذ مدة طويلة",
        "وردية مفتوحة منذ أكثر من 14 ساعة",
    }


def test_clock_rollback_blocks_the_engine(monthly_stay):
    tick(at(20))
    assert tick(at(20, 7)) == {"blocked": True}
    assert tick(at(21)) == {"blocked": True}  # stays blocked until a manager approves


def test_toasts_api_and_rules_api(monthly_stay, reception_api, manager_api, confirm):
    tick(at(20))
    with time_machine.travel(at(20, 9, 1), tick=False):
        signed_in(reception_api, User.objects.get(username="ahmed.ali"))
        signed_in(manager_api, User.objects.get(username="manager"))
        batch = reception_api.get("/api/v1/followups/toasts", {"after": 0}).json()
        assert len(batch["toasts"]) == 1 and batch["cursor"] == batch["toasts"][0]["seq"]
        assert reception_api.get("/api/v1/followups/toasts", {"after": batch["cursor"]}).json()["toasts"] == []

        rule = AlertRule.objects.get(duration_kind="monthly")
        url = f"/api/v1/followups/rules/{rule.pk}"
        assert reception_api.patch(url, {"version": rule.version, "days_before": 7}, format="json").status_code == 403
        res = manager_api.patch(url, {"version": rule.version, "days_before": 7}, format="json")
        assert res.status_code == 200 and res.json()["days_before"] == 7
        res = manager_api.patch(url, {"version": res.json()["version"], "is_active": False}, format="json")
        assert res.json()["code"] == "confirmation_required"
        confirm(manager_api)
        assert manager_api.patch(url, {"version": 2, "is_active": False}, format="json").status_code == 200

        preview = reception_api.post(
            "/api/v1/followups/rules/preview",
            {
                "last_night": "2026-10-30",
                "duration_kind": "monthly",
                "days_before": 5,
                "second_days_before": 2,
                "at_time": "09:00",
                "repeat_hours": 12,
            },
            format="json",
        ).json()
        assert preview["first_at"].startswith("2026-10-25T09:00") and preview["second_at"].startswith("2026-10-28")
        assert preview["affected_stays"] == 1
        assert len(preview["stays"]) == 1 and set(preview["stays"][0]) == {"room", "guest", "last_night"}
        counts = reception_api.get("/api/v1/followups/tasks", {"count": "1"}).json()
        assert counts["count"] == 1
        assert reception_api.get("/api/v1/followups/tasks/count").json() == counts


def test_seeded_board_matches_artboard(db):
    call_command("seed_demo", "--allow-non-debug")
    from django.utils import timezone

    tick(timezone.now())
    board = _board_at(timezone.now())
    assert [r["room"] for r in board["late"]] == ["305", "207"]
    assert {"108", "204", "203"} <= {r["room"] for r in board["today"]}
    assert "411" in {r["room"] for r in board["upcoming"]}
    row_411 = next(r for r in board["upcoming"] if r["room"] == "411")
    assert row_411["rule"] == "قاعدة: شهري – قبل 5 أيام · 09:00"


def test_alert_response_report(monthly_stay, reception_api, manager_api):
    tick(at(20))
    task = the_task()
    act(reception_api, task, "snooze", at(20, 9, 30), until=at(20, 12).isoformat())
    act(reception_api, task, "done", at(20, 12, 5), note="النزيل سيغادر في موعده")
    with time_machine.travel(at(21), tick=False):
        signed_in(manager_api, User.objects.get(username="manager"))
        report = manager_api.get("/api/v1/reports/alert_response", {"date_from": "2026-10-01"}).json()
    row = report["rows"][0]
    assert (row["first_action"], row["response_minutes"], row["snoozes"], row["final"], row["by"]) == (
        "تأجيل",
        30,
        1,
        "تم",
        "أحمد علي",
    )
    assert report["meta"]["tiles"][1]["value"] == 30


def test_change_room_replans_the_stay_alerts(monthly_stay, reception_api, rooms):
    """Spec §6.6: a room change supersedes pending tasks *and generates new ones* (same due date)."""
    tick(at(20))
    before = the_task()
    assert before.status == "open"
    with time_machine.travel(at(20, 10), tick=False):
        signed_in(reception_api, User.objects.get(username="ahmed.ali"))
        res = reception_api.post(
            f"/api/v1/stays/{monthly_stay.pk}/change-room",
            {"room": str(rooms["205"].pk), "reason": "عطل في التكييف", "old_room_status": "cleaning"},
            format="json",
        )
        assert res.status_code == 200, res.json()
    before.refresh_from_db()
    assert before.status == "superseded"
    tick(at(20, 10, 5))
    open_tasks = FollowupTask.objects.filter(stay=monthly_stay, rule__duration_kind="monthly", status="open")
    assert open_tasks.count() == 1
    assert open_tasks.get().room.number == "205"
    # Re-running never duplicates the replacement either.
    tick(at(20, 11))
    assert FollowupTask.objects.filter(stay=monthly_stay, rule__duration_kind="monthly").count() == 2
