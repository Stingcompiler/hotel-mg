"""Pure rules for guests: text normalization for search, ID masking, image size targets."""

import re

ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

# Letter variants that people type interchangeably; folded for search only.
_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي"})
_DIACRITICS = re.compile("[ً-ْٰـ]")  # harakat, superscript alef, tatweel
_SPACES = re.compile(r"\s+")

MAX_DOCUMENT_BYTES = 300 * 1024  # after compression (spec §5)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # before compression


def to_ascii_digits(text: str) -> str:
    return text.translate(ARABIC_INDIC)


def normalize_name(text: str) -> str:
    """Search key: no diacritics or tatweel, common letter variants folded, single spaces, lowercase."""
    text = _DIACRITICS.sub("", text).translate(_FOLD)
    return _SPACES.sub(" ", text).strip().lower()


def normalize_phone(text: str) -> str:
    """Keep a leading + and digits only: "+249 91 234 5678" -> "+249912345678"."""
    text = to_ascii_digits(text).strip()
    digits = re.sub(r"\D", "", text)
    return ("+" + digits) if text.startswith("+") and digits else digits


def is_valid_phone(text: str) -> bool:
    phone = normalize_phone(text)
    return 7 <= len(phone.lstrip("+")) <= 15


def mask_id_number(id_number: str) -> str:
    """Reception sees only the last 4 characters (spec §5: full number for manager/owner)."""
    if not id_number:
        return ""
    return "••••" + id_number[-4:] if len(id_number) > 4 else "••••"
