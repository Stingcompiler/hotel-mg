import pytest

from apps.guests import rules


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("محمد عثمان الطيب", "محمد عثمان الطيب"),
        ("أحمد  إبراهيم", "احمد ابراهيم"),  # hamza forms folded, spaces collapsed
        ("فاطمة", "فاطمه"),  # taa marbuta
        ("مُصْطَفَى", "مصطفي"),  # diacritics removed, alef maqsura folded
        ("عبـــدالله", "عبدالله"),  # tatweel
        ("  Omar KHALID ", "omar khalid"),
    ],
)
def test_normalize_name(raw, expected):
    assert rules.normalize_name(raw) == expected


def test_to_ascii_digits():
    assert rules.to_ascii_digits("٠٩١٢٣٤ ۵۶") == "091234 56"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+249 91 234 5678", "+249912345678"),
        ("٠٩١٢-٣٤٥-٦٧٨", "0912345678"),
        ("(091) 234 5678", "0912345678"),
        ("", ""),
        ("+", ""),
    ],
)
def test_normalize_phone(raw, expected):
    assert rules.normalize_phone(raw) == expected


def test_is_valid_phone():
    assert rules.is_valid_phone("+249 91 234 5678")
    assert not rules.is_valid_phone("12345")
    assert not rules.is_valid_phone("1" * 16)


def test_mask_id_number():
    assert rules.mask_id_number("211-8842-1023-7") == "••••23-7"
    assert rules.mask_id_number("1234") == "••••"
    assert rules.mask_id_number("") == ""
