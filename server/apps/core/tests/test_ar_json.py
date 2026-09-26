"""The SPA's Arabic error messages (web/src/i18n/ar.json → errors) match the API's (spec §10.5)."""

import json
from pathlib import Path

from apps.core.errors import MESSAGES

AR_JSON = Path(__file__).resolve().parents[4] / "web" / "src" / "i18n" / "ar.json"


def test_every_api_error_code_has_the_same_arabic_message_in_the_spa():
    assert json.loads(AR_JSON.read_text(encoding="utf-8"))["errors"] == MESSAGES
