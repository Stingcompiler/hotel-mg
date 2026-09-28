"""Review 2026-09-28, batch 2: neglected alerts and responses (BIZ-9…12)."""

from datetime import timedelta

import pytest
import time_machine

from apps.accounts.models import User
from apps.cash.models import Shift
from apps.followups.models import FollowupTask, TaskAction
from apps.followups.tests.test_engine import at, signed_in, the_task, tick
from apps.reports.dashboard import owner_dashboard

pytestmark = pytest.mark.django_db


def shift_of(user, opened, closed=None, device="reception"):
    return Shift.objects.create(device=device, opened_at=opened, closed_at=closed, opening=0, created_by=user)


def test_direct_extension_answers_a_neglected_alert_and_keeps_the_mark(monthly_stay, reception_api, manager_api):
    """BIZ-9: superseding no longer erases «مُهمَلة»; BIZ-12: extending from the stay screen is the response."""
    reception = User.objects.get(username="ahmed.ali")
    shift_of(reception, at(20, 8))
    tick(at(20))
    assert tick(at(21, 9))["escalated"] == 1
    with time_machine.travel(at(21, 10), tick=False):
        signed_in(reception_api, reception)
        res = reception_api.post(
            f"/api/v1/stays/{monthly_stay.pk}/extend", {"duration_kind": "monthly", "count": 1}, format="json"
        )
        assert res.status_code == 200, res.json()
    task = the_task()
    assert task.status == "superseded" and task.neglected_at is not None
    action = TaskAction.objects.get(task=task)
    assert (action.action, action.created_by, action.at) == ("extend", reception, at(21, 10))

    with time_machine.travel(at(22), tick=False):
        signed_in(manager_api, User.objects.get(username="manager"))
        report = manager_api.get("/api/v1/reports/alert_response", {"date_from": "2026-10-01"}).json()
    row = report["rows"][0]
    assert (row["final"], row["by"], row["neglected_shift"]) == ("تمديد", "أحمد علي", "أحمد علي")


def test_future_alerts_are_not_counted_as_answered(monthly_stay, reception_api):
    """Only alerts already due get the action; a task planned for later is just superseded."""
    tick(at(20))
    FollowupTask.objects.update(due_at=at(22))  # not due yet at the time of the extension
    with time_machine.travel(at(20, 10), tick=False):
        signed_in(reception_api, User.objects.get(username="ahmed.ali"))
        reception_api.post(
            f"/api/v1/stays/{monthly_stay.pk}/extend", {"duration_kind": "daily", "count": 1}, format="json"
        )
    assert the_task().status == "superseded" and not TaskAction.objects.exists()


def test_task_created_late_is_not_neglected_at_once(monthly_stay):
    """BIZ-11: the PC was off on the 20th; the task appears on the 22nd with its original due time."""
    tick(at(22))
    task = the_task()
    assert task.due_at == at(20)
    assert tick(at(22, 10))["escalated"] == 0
    assert tick(at(23, 9) + timedelta(minutes=1))["escalated"] == 1


def test_neglect_belongs_to_the_shift_it_fell_due_in(monthly_stay, reception, make_user):
    """BIZ-10: the engine and the owner's staff table name the same person."""
    sara = make_user("sara", full_name="سارة")
    shift_a = shift_of(reception, at(20, 12), at(20, 20))  # nobody at the desk at 09:00: waiting for Ahmed
    shift_of(sara, at(21, 8))  # Sara is at the desk when the task becomes neglected
    tick(at(20))
    tick(at(21, 9))
    assert the_task().shift == shift_a
    with time_machine.travel(at(21, 10), tick=False):
        staff = {row["name"]: row for row in owner_dashboard("month")["staff"]}
    assert staff["أحمد علي"]["neglected"] == 1 and "سارة" not in staff
