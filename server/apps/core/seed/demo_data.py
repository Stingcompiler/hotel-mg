"""Sample data from the UI Design Brief §10.3 and the design package, so the running app
looks like the approved artboards during review (spec §10.3).

Amounts are in minor units (piasters): 12,000 ج.س -> 1_200_000.
Only ``USERS`` is loaded in B0; each later phase adds the loader for its own models.
"""

from datetime import date


def sdg(pounds: int) -> int:
    return pounds * 100


# The design's reports are dated Saturday 26 September 2026.
DEMO_TODAY = date(2026, 9, 26)

# Dev-only credentials; seed_demo refuses to run on a production (non-DEBUG) install.
DEMO_PIN = "1234"
DEMO_PASSWORD = "skytowers-dev"

# Settings → Users (Gap Fill artboard).
USERS = [
    {"username": "manager", "full_name": "المدير", "role": "manager", "is_active": True},
    {"username": "ahmed.ali", "full_name": "أحمد علي", "role": "reception", "is_active": True},
    {"username": "salma.h", "full_name": "سلمى حسن", "role": "reception", "is_active": True},
    {"username": "khalid.m", "full_name": "خالد (سابق)", "role": "reception", "is_active": False},
]

# Settings → Room types & prices (Gap Fill artboard). weekly = 7 nights, monthly = 30 nights.
# Capacity is not given by the design; assumed 1/2/3 (see docs/design-gaps.md #1).
ROOM_TYPES = [
    {"name": "مفردة", "capacity": 1, "nightly": sdg(12_000), "weekly": sdg(77_000), "monthly": sdg(280_000)},
    {"name": "مزدوجة", "capacity": 2, "nightly": sdg(15_000), "weekly": sdg(95_000), "monthly": sdg(300_000)},
    {"name": "جناح", "capacity": 3, "nightly": sdg(25_000), "weekly": sdg(160_000), "monthly": sdg(520_000)},
]

# 30 rooms on 4 floors: singles 101-108, doubles 201-208 and 405-412, suites 301-306.
ROOMS = (
    [{"number": str(n), "floor": 1, "type": "مفردة"} for n in range(101, 109)]
    + [{"number": str(n), "floor": 2, "type": "مزدوجة"} for n in range(201, 209)]
    + [{"number": str(n), "floor": 3, "type": "جناح"} for n in range(301, 307)]
    + [{"number": str(n), "floor": 4, "type": "مزدوجة"} for n in range(405, 413)]
)

# Non-occupied states that differ from "ready" (Room Board artboard). Occupied rooms come
# from checked-in stays, which the stays loader creates.
ROOM_STATES = {
    "104": {"status": "cleaning"},
    "306": {"status": "cleaning"},
    "410": {"status": "maintenance", "maintenance_reason": "تسرب مياه — فني السباكة 26 سبتمبر"},
}

# Brief §10.3 core sample. Exact dates are fixed when the stays loader is written (B1);
# the artboards disagree on "today" for room 203 (see docs/design-gaps.md).
STAYS = [
    {"room": "203", "guest": "محمد عثمان الطيب", "duration_kind": "monthly", "balance": sdg(15_000)},
    {"room": "204", "guest": "فاطمة أحمد النور", "duration_kind": "daily", "nights": 2, "balance": 0},
    {"room": "305", "guest": "عبدالله حسن موسى", "duration_kind": "weekly", "overdue": True, "balance": sdg(42_000)},
    {"room": "411", "guest": "سارة عمر الشيخ", "duration_kind": "monthly", "balance": 0},
]
RESERVATIONS = [
    {"room": "102", "guest": "خالد إبراهيم", "duration_kind": "weekly", "starts": "tomorrow"},
]

GUEST_PHONE = "+249 91 234 5678"
SHIFT = {"user": "ahmed.ali", "opened_at": "08:00", "opening": sdg(50_000)}
INVOICE_NO = "INV-000318"
