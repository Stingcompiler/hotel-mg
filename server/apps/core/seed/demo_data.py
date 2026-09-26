"""Sample data from the UI Design Brief §10.3 and the design package, so the running app
looks like the approved artboards during review (spec §10.3).

Amounts are in minor units (piasters): 12,000 ج.س -> 1_200_000.
Dates are relative to the day the seed runs, so the board always looks like the artboard.
Each phase adds the loader for its own models.
"""


def sdg(pounds: int) -> int:
    return pounds * 100


# Dev-only credentials; seed_demo refuses to run on a production (non-DEBUG) install.
DEMO_PIN = "123456"  # six digits, as the login design draws it
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

# Occupied rooms on the Room Board artboard (18 of 30), with the brief's rows for 203, 204, 305, 411.
# ends_in: days from today to the last night («تنتهي اليوم» = 0, «متجاوزة منذ يومين» = -2).
# Kinds for rooms the design does not specify are chosen to fit the shown end date.
STAYS = [
    {"room": "103", "guest": "عمر خالد البشير", "kind": "daily", "count": 3, "ends_in": 1},
    {"room": "105", "guest": "هالة محمد يوسف", "kind": "weekly", "count": 1, "ends_in": 5},
    {"room": "107", "guest": "إبراهيم عوض الكريم", "kind": "monthly", "count": 1, "ends_in": 12},
    {"room": "108", "guest": "نادية صالح عبدالله", "kind": "daily", "count": 3, "ends_in": 0},
    {"room": "201", "guest": "يوسف الطاهر محمد", "kind": "weekly", "count": 1, "ends_in": 2},
    {
        "room": "203",
        "guest": "محمد عثمان الطيب",
        "kind": "monthly",
        "count": 1,
        "ends_in": 3,
        "phone": "+249 91 234 5678",
        "id_type": "national_id",
        "id_number": "211-8842-1023-7",
        "nationality": "سوداني",
    },
    {"room": "204", "guest": "فاطمة أحمد النور", "kind": "daily", "count": 2, "ends_in": 0},
    {"room": "206", "guest": "أمل عبدالله حامد", "kind": "weekly", "count": 2, "ends_in": 9},
    {"room": "207", "guest": "حسن آدم إسحق", "kind": "daily", "count": 4, "ends_in": -1},
    {"room": "208", "guest": "مصطفى الأمين الحاج", "kind": "monthly", "count": 1, "ends_in": 20},
    {"room": "301", "guest": "ليلى حامد الفكي", "kind": "weekly", "count": 1, "ends_in": 6},
    {"room": "303", "guest": "الصادق محمد الحسن", "kind": "daily", "count": 3, "ends_in": 1},
    {"room": "305", "guest": "عبدالله حسن موسى", "kind": "weekly", "count": 1, "ends_in": -2},
    {"room": "405", "guest": "رانيا عثمان بابكر", "kind": "weekly", "count": 1, "ends_in": 4},
    {"room": "407", "guest": "بشير حسين الطيب", "kind": "monthly", "count": 1, "ends_in": 14},
    {"room": "408", "guest": "وفاء الزين أحمد", "kind": "weekly", "count": 1, "ends_in": 2},
    {"room": "411", "guest": "سارة عمر الشيخ", "kind": "monthly", "count": 1, "ends_in": 18},
    {"room": "412", "guest": "طارق النور عبدالرحيم", "kind": "weekly", "count": 2, "ends_in": 7},
]
# «102 — حجز: خالد إبراهيم، غدًا، أسبوعي» with the warning note from artboard 6.4 B.
RESERVATIONS = [
    {
        "room": "102",
        "guest": "خالد إبراهيم عبدالله",
        "kind": "weekly",
        "count": 1,
        "starts_in": 1,
        "phone": "+249 12 876 5432",
        "warning_note": "دين سابق 8,000 ج.س سُدِّد متأخرًا",
    },
]
# Brief §10.3 balances (loaded with folios in B2): 203 owes 15,000, 305 owes 42,000.
BALANCES = {"203": sdg(15_000), "305": sdg(42_000)}

GUEST_PHONE = "+249 91 234 5678"
SHIFT = {"user": "ahmed.ali", "opened_at": "08:00", "opening": sdg(50_000)}
# Expenses artboard 6.8 — today's two cash expenses (12,500 in all).
EXPENSES = [
    {"category": "supplies", "amount": sdg(5_000), "note": "مواد تنظيف — 4 عبوات كلور + مناشف", "method": "cash"},
    {"category": "purchases", "amount": sdg(7_500), "note": "مياه شرب — 10 كراتين", "method": "cash"},
]
INVOICE_NO = "INV-000318"
