"""Every error code the services raise has an Arabic message (review 2026-09-29, A-13 / F-14)."""

import re
from pathlib import Path

from apps.core.errors import MESSAGES

APPS = Path(__file__).resolve().parents[2]


def test_every_raised_code_has_an_arabic_message():
    raised = set()
    for path in APPS.rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        raised |= set(re.findall(r'ApiError\(\s*"([a-z_]+)"', path.read_text(encoding="utf-8")))
    assert raised, "no ApiError found — the scan is broken"
    assert sorted(raised - MESSAGES.keys()) == []
