"""Pure hash-chain rules (spec §6.9). No ORM access here."""

import hashlib
import json
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
}


def action_label(action: str) -> str:
    return ACTION_LABELS.get(action, action)
