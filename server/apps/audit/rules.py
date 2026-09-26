"""Pure hash-chain rules (spec §6.9). No ORM access here."""

import hashlib
import json
import re
from datetime import datetime
from uuid import UUID

GENESIS_HASH = "0" * 64
PAYLOAD_FIELDS = ("seq", "hotel_id", "actor_id", "action", "entity", "entity_id", "before", "after", "at")


def _default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"not JSON-serializable in audit rows: {type(value).__name__}")


def canonical_json(payload: dict) -> str:
    """Stable text form: sorted keys, no whitespace, UTF-8 text kept as-is."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_default)


def chain_hash(prev_hash: str, payload: dict) -> str:
    return hashlib.sha256((prev_hash + canonical_json(payload)).encode("utf-8")).hexdigest()


def row_payload(
    *,
    seq: int,
    hotel_id,
    actor_id,
    action: str,
    entity: str,
    entity_id: str,
    before,
    after,
    at: datetime,
) -> dict:
    """The hashed fields of a row. ``at`` must be timezone-aware UTC."""
    return {
        "seq": seq,
        "hotel_id": str(hotel_id),
        "actor_id": str(actor_id) if actor_id else None,
        "action": action,
        "entity": entity,
        "entity_id": entity_id,
        "before": before,
        "after": after,
        "at": at,
    }


def first_broken(rows) -> int | None:
    """Walk rows (dicts with payload fields + prev_hash + hash) in seq order; return the first bad seq."""
    expected_prev = GENESIS_HASH
    expected_seq = 1
    for row in rows:
        payload = {k: row[k] for k in PAYLOAD_FIELDS}
        if row["seq"] != expected_seq or row["prev_hash"] != expected_prev:
            return row["seq"]
        if chain_hash(row["prev_hash"], payload) != row["hash"]:
            return row["seq"]
        expected_prev = row["hash"]
        expected_seq += 1
    return None


# --- Categories for Settings → سجل التدقيق (artboard 6.11 E) ---------------------------------------

CATEGORIES = {
    "payment": "دفعة",
    "stay": "إقامة",
    "reversal": "عكس",
    "override": "تجاوز مدير",
    "settings": "إعدادات",
    "login": "دخول",
    "sensitive": "عرض حساس",
    "other": "أخرى",
}
CATEGORY_KEYS = list(CATEGORIES)
_SENSITIVE = {"guest.view_document"}
_SETTINGS_PREFIXES = ("settings.", "room_type.", "room.", "user.", "backup.", "followup.rule_", "system.")


def category(action: str, after: dict | None) -> str:
    """One category per row. Most specific first: a reversed payment is «عكس», an overridden checkout
    is «تجاوز مدير»."""
    if action in _SENSITIVE:
        return "sensitive"
    if isinstance(after, dict) and any(after.get(k) for k in ("approved_by", "override_by", "override_reason")):
        return "override"
    if "revers" in action or action == "payment.refund":
        return "reversal"
    if action.startswith("auth."):
        return "login"
    if action.startswith(("payment.", "folio.")):
        return "payment"
    if action.startswith(("stay.", "reservation.")):
        return "stay"
    if action.startswith(_SETTINGS_PREFIXES):
        return "settings"
    return "other"


# Arabic wording of actions for activity logs (stay «السجل» tab, Settings → سجل التدقيق).
ACTION_LABELS = {
    "reservation.create": "إنشاء الحجز",
    "reservation.assign_room": "تخصيص غرفة للحجز",
    "reservation.cancel": "إلغاء الحجز",
    "reservation.no_show": "لم يحضر",
    "stay.check_in": "تسكين",
    "stay.extend": "تمديد الإقامة",
    "stay.change_room": "تغيير الغرفة",
    "stay.checkout": "تسجيل خروج",
    "stay.cancel": "إلغاء الإقامة",
    "folio.room": "قيد إقامة",
    "folio.service": "إضافة خدمة",
    "folio.discount": "خصم",
    "folio.adjustment": "تسوية",
    "folio.tax": "ضريبة",
    "folio.reversal": "قيد عكس",
    "folio.reverse_line": "عكس قيد",
    "payment.deposit": "عربون",
    "payment.payment": "دفعة",
    "payment.refund": "ردّ مبلغ",
    "payment.reversal": "عكس دفعة",
    "payment.reverse": "عكس دفعة",
    "guest.create": "تسجيل نزيل",
    "guest.update": "تعديل بيانات النزيل",
    "guest.add_document": "إضافة صورة هوية",
    "guest.view_document": "عرض صورة هوية",
    "auth.login_pin": "دخول بالرمز",
    "auth.login_password": "دخول بكلمة المرور",
    "auth.logout": "تسجيل خروج من النظام",
    "auth.locked": "قفل الحساب بعد محاولات خاطئة",
    "user.create": "إنشاء مستخدم",
    "user.update": "تعديل مستخدم",
    "user.reset_pin": "إعادة تعيين الرمز",
    "user.unlock": "فك قفل مستخدم",
    "room.create": "إضافة غرفة",
    "room.update": "تعديل غرفة",
    "room.set_status": "تغيير حالة الغرفة",
    "room_type.create": "إضافة نوع غرفة",
    "room_type.update_prices": "تعديل أسعار النوع",
    "settings.update": "تعديل بيانات الفندق",
    "backup.settings": "تعديل إعدادات النسخ",
    "followup.rule_create": "إضافة قاعدة تنبيه",
    "followup.rule_update": "تعديل قاعدة تنبيه",
    "shift.open": "فتح وردية",
    "shift.close": "إغلاق وردية",
    "expense.create": "تسجيل مصروف",
    "expense.attach": "إرفاق إيصال مصروف",
    "expense.reverse": "عكس مصروف",
    "system.clock_rollback": "رجوع ساعة الجهاز",
    "system.clock_approve": "موافقة على ساعة الجهاز",
}

# Field names shown in «التفاصيل (قبل ← بعد)»; unknown keys are shown as they are.
FIELD_LABELS = {
    "amount": "المبلغ",
    "method": "الطريقة",
    "reason": "السبب",
    "status": "الحالة",
    "role": "الدور",
    "is_active": "مفعّل",
    "full_name": "الاسم",
    "number": "الرقم",
    "floor": "الطابق",
    "note": "ملاحظة",
    "in_service": "في الخدمة",
    "room": "الغرفة",
    "room_type": "النوع",
    "name": "الاسم",
    "nightly_price": "يومي",
    "weekly_price": "أسبوعي",
    "monthly_price": "شهري",
    "days_before": "التنبيه الأول",
    "second_days_before": "التنبيه الثاني",
    "at_time": "الوقت",
    "repeat_hours": "التكرار",
    "planned_end": "النهاية",
    "opening_float": "الرصيد الافتتاحي",
    "counted": "المعدود",
    "opening": "الرصيد الافتتاحي",
    "expected": "المتوقع",
    "category": "الفئة",
    "threshold": "الحد",
    "threshold_hours": "الحد بالساعات",
    "is_active_rule": "مفعّلة",
    "phone": "الهاتف",
    "price": "السعر",
    "discount": "الخصم",
    "difference": "الفرق",
}
# Money fields are integer minor units (spec §5); shown in currency units in the log.
MONEY_FIELDS = {
    "amount", "opening", "opening_float", "expected", "counted", "price", "discount", "difference", "threshold",
    "nightly_price", "weekly_price", "monthly_price", "total", "paid", "balance", "deposit",
}  # fmt: skip
_SKIP_FIELDS = {
    "id",
    "version",
    "updated_at",
    "created_at",
    "hotel_id",
    "device",
    "hash",
    "is_staff",
    "is_superuser",
    "password",
}
VALUE_LABELS = {
    "role": {"reception": "موظف استقبال", "manager": "مدير", "owner": "مالك"},
    "method": {"cash": "نقدي", "bankak": "بنكك", "transfer": "تحويل"},
    "status": {"ready": "جاهزة", "occupied": "مشغولة", "cleaning": "تحتاج تنظيف", "maintenance": "صيانة"},
}
_SKIP_SUFFIXES = ("_at", "_by", "_id")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _money(value: int) -> str:
    units, cents = divmod(abs(value), 100)
    text = f"{units:,}" + (f".{cents:02d}" if cents else "")
    return f"{'-' if value < 0 else ''}{text} ج.س"


def _text(key: str, value) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "نعم" if value else "لا"
    if key in MONEY_FIELDS and isinstance(value, int):
        return _money(value)
    return VALUE_LABELS.get(key, {}).get(value, str(value)) if isinstance(value, str) else str(value)


def _shown(key: str, value) -> bool:
    if key in _SKIP_FIELDS or key.endswith(_SKIP_SUFFIXES) or isinstance(value, (dict, list)):
        return False
    return not (isinstance(value, str) and _UUID.match(value))


def summary(before, after, limit: int = 4) -> str:
    """«field: old ← new» for changed keys, or «field: value» for a new row; at most ``limit`` parts."""
    before = before if isinstance(before, dict) else {}
    after = after if isinstance(after, dict) else {}
    parts = []
    for key in after:
        if not _shown(key, after[key]):
            continue
        label = FIELD_LABELS.get(key, key)
        if key in before:
            if before[key] != after[key]:
                parts.append(f"{label}: {_text(key, before[key])} ← {_text(key, after[key])}")
        else:
            parts.append(f"{label}: {_text(key, after[key])}")
    return " · ".join(parts[:limit])


def action_label(action: str) -> str:
    return ACTION_LABELS.get(action, action)
