from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from apps.followups import rules

TZ = ZoneInfo("Africa/Khartoum")
T0 = datetime(2026, 10, 20, 9, 0, tzinfo=TZ)


def test_first_alert_at_matches_rule_preview():
    # Artboard 6.11: monthly stay ending Fri 30 Oct → first alert Sun 25 Oct 09:00 (5 days before)
    assert rules.first_alert_at(date(2026, 10, 30), 5, time(9), TZ) == datetime(2026, 10, 25, 9, 0, tzinfo=TZ)


def test_notification_times():
    second = T0 + timedelta(days=3)
    assert rules.notification_times(T0, second, 12, T0 - timedelta(minutes=1)) == []
    assert rules.notification_times(T0, second, 12, T0 + timedelta(days=1)) == [T0]
    until = second + timedelta(hours=25)
    assert rules.notification_times(T0, second, 12, until) == [
        T0,
        second,
        second + timedelta(hours=12),
        second + timedelta(hours=24),
    ]
    assert rules.notification_times(T0, None, 0, T0 + timedelta(days=5)) == [T0]
    assert rules.notification_times(T0, None, 6, T0 + timedelta(hours=13)) == [
        T0,
        T0 + timedelta(hours=6),
        T0 + timedelta(hours=12),
    ]


def test_escalation_snooze_and_wake():
    assert rules.should_escalate("open", T0, 24, T0 + timedelta(hours=24))
    assert not rules.should_escalate("open", T0, 24, T0 + timedelta(hours=23))
    assert not rules.should_escalate("waiting", T0, 24, T0 + timedelta(days=3))
    assert not rules.should_escalate("open", T0, 0, T0 + timedelta(days=3))
    assert rules.can_snooze(2, 3) and not rules.can_snooze(3, 3)
    assert rules.snooze_label(2, 3) == "تأجيل (2 من 3)"
    assert rules.wakes_up("snoozed", T0, T0) and not rules.wakes_up("snoozed", T0, T0 - timedelta(seconds=1))
    assert not rules.wakes_up("open", T0, T0) and not rules.wakes_up("waiting", None, T0)


def test_texts():
    today = date(2026, 9, 26)
    assert rules.when_text(date(2026, 9, 24), today) == "متجاوزة منذ يومين"
    assert rules.when_text(date(2026, 9, 25), today) == "متجاوزة منذ يوم"
    assert rules.when_text(date(2026, 9, 20), today) == "متجاوزة منذ 6 أيام"
    assert rules.when_text(today, today) == "تنتهي اليوم"
    assert rules.when_text(date(2026, 9, 27), today) == "تنتهي غدًا"
    assert rules.when_text(date(2026, 9, 28), today) == "تنتهي بعد يومين"
    assert rules.when_text(date(2026, 9, 29), today) == "تنتهي بعد 3 أيام"
    assert rules.when_text(date(2026, 10, 14), today) == "تنتهي بعد 18 يومًا"
    assert rules.toast_title("305", "متجاوزة منذ يومين") == "غرفة 305 — متجاوزة منذ يومين"
    assert len(rules.toast_title("305", "x" * 60)) == 40
    assert rules.toast_body("محمد عثمان الطيب", "شهري") == "محمد عثمان · شهري · انقر للفتح"
    assert [rules.days_label(d) for d in (0, 1, 2, 5, 14)] == [
        "يوم النهاية",
        "قبل يوم",
        "قبل يومين",
        "قبل 5 أيام",
        "قبل 14 يومًا",
    ]
    assert rules.local_at(date(2026, 9, 26), time(9), TZ).hour == 9
