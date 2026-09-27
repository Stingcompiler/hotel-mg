"""Pure helpers for reports, exports and printed documents. No ORM."""

import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal

_ONES = [
    "",
    "واحد",
    "اثنان",
    "ثلاثة",
    "أربعة",
    "خمسة",
    "ستة",
    "سبعة",
    "ثمانية",
    "تسعة",
    "عشرة",
    "أحد عشر",
    "اثنا عشر",
    "ثلاثة عشر",
    "أربعة عشر",
    "خمسة عشر",
    "ستة عشر",
    "سبعة عشر",
    "ثمانية عشر",
    "تسعة عشر",
]
_TENS = ["", "", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون", "ثمانون", "تسعون"]
_HUNDREDS = ["", "مائة", "مائتان", "ثلاثمائة", "أربعمائة", "خمسمائة", "ستمائة", "سبعمائة", "ثمانمائة", "تسعمائة"]
# (one, two, plural 3-10, accusative 11+)
_SCALES = [
    ("ألف", "ألفان", "آلاف", "ألفًا"),
    ("مليون", "مليونان", "ملايين", "مليونًا"),
    ("مليار", "ملياران", "مليارات", "مليارًا"),
]


def _below_thousand(n: int) -> str:
    parts = []
    if n >= 100:
        parts.append(_HUNDREDS[n // 100])
        n %= 100
    if n >= 20:
        ones, tens = n % 10, _TENS[n // 10]
        parts.append(f"{_ONES[ones]} و{tens}" if ones else tens)
    elif n:
        parts.append(_ONES[n])
    return " و".join(parts)


def _scaled(n: int, forms: tuple[str, str, str, str]) -> str:
    one, two, few, many = forms
    if n == 1:
        return one
    if n == 2:
        return two
    words = _below_thousand(n)
    if 3 <= n % 100 <= 10:
        return f"{words} {few}"
    return f"{words} {many}"


def number_to_words(n: int) -> str:
    """Arabic words for a whole number: 15000 → «خمسة عشر ألف». 0 → «صفر»."""
    if n == 0:
        return "صفر"
    if n < 0:
        return "سالب " + number_to_words(-n)
    groups = []
    rest = n
    while rest:
        groups.append(rest % 1000)
        rest //= 1000
    parts = []
    for index in range(len(groups) - 1, -1, -1):
        g = groups[index]
        if not g:
            continue
        parts.append(_below_thousand(g) if index == 0 else _scaled(g, _SCALES[index - 1]))
    return " و".join(parts)


def amount_in_words(minor: int) -> str:
    """«خمسة عشر ألف جنيه» for 1,500,000 minor units; piasters are added when present."""
    pounds, piasters = divmod(abs(minor), 100)
    # Before the noun the counted word loses its tanween: «خمسة عشر ألف جنيه» (receipt 7.2).
    text = f"{number_to_words(pounds).removesuffix('ًا')} جنيه"
    if piasters:
        text += f" و{number_to_words(piasters)} قرشًا"
    return ("سالب " if minor < 0 else "") + text


def to_major(minor: int, decimals: int) -> Decimal:
    """Minor units → pounds for exports; 0 decimals rounds half up to whole pounds."""
    value = Decimal(minor) / 100
    return value.quantize(Decimal(1) if decimals == 0 else Decimal("0.01"), rounding="ROUND_HALF_UP")


def shift_label(opened_at: datetime) -> str:
    """«صباحية» before 14:00 local, «مسائية» after (receipt: «الوردية 26 سبتمبر · صباحية»)."""
    return "صباحية" if opened_at.hour < 14 else "مسائية"


def percent(part: int, whole: int) -> int:
    return round(100 * part / whole) if whole else 0


def days_between(start: date, end: date) -> int:
    return (end - start).days


def occupancy_percent(occupied_nights: int, available_nights: int, maintenance_nights: int) -> int:
    """الإشغال = الغرف المشغولة ÷ (إجمالي الغرف − غرف الصيانة) × 100 (spec §6.4)."""
    return percent(occupied_nights, available_nights - maintenance_nights)


PERIOD_LABELS = {"month": "هذا الشهر", "previous": "الشهر السابق", "90days": "آخر 90 يومًا"}


def dashboard_period(kind: str, today: date) -> tuple[date, date]:
    """Owner dashboard period, both ends included: month to date, the whole previous month, or the last 90 days."""
    first = today.replace(day=1)
    if kind == "previous":
        end = first - timedelta(days=1)
        return end.replace(day=1), end
    if kind == "90days":
        return today - timedelta(days=89), today
    return first, today


def comparison_period(kind: str, start: date, end: date) -> tuple[date, date]:
    """The period the revenue is compared with, of the same length: month to date → the same days of the previous
    month (clamped to its end), a whole month → the month before, 90 days → the 90 days before."""
    if kind == "90days":
        length = (end - start).days + 1
        return start - timedelta(days=length), start - timedelta(days=1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end.replace(day=1)
    if kind == "previous":
        return prev_start, prev_end
    return prev_start, prev_start.replace(day=min(end.day, calendar.monthrange(prev_start.year, prev_start.month)[1]))


def week_label(n: int, start: date, stop: date, one_month: bool) -> str:
    """«الأسبوع 2 (8–14)» inside one calendar month; «29/6–5/7» when the period spans months (90 days)."""
    if one_month:
        return f"الأسبوع {n} ({start.day}–{stop.day})"
    return f"{start.day}/{start.month}–{stop.day}/{stop.month}"


def pounds_text(minor: int) -> str:
    """Whole pounds with thousands separators and a sign for negatives: −1,500 (not -2 from floor division)."""
    whole = abs(minor) // 100
    return f"{'−' if minor < 0 and whole else ''}{whole:,}"


OCCUPANCY_FORMULA = (
    "الإشغال = الغرف المشغولة ÷ (إجمالي الغرف − غرف الصيانة) × 100. الغرفة تُحسب مشغولة عن الليلة إذا كانت فيها "
    "إقامة جارية عند منتصف الليل. الإيراد يُحتسب عند التسكين/التمديد؛ المحصّل عند استلام الدفعة."
)
CASH_FORMULA = "النقدي المتوقع = الافتتاحي + المقبوضات النقدية − المصروفات النقدية. البنكك والتحويل لا يدخلان الدرج."
