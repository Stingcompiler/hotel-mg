"""Pure rules for accounts. No ORM access here."""

import re

_PIN = re.compile(r"[0-9]{4,6}")


def is_valid_pin(pin: str) -> bool:
    """PIN is 4-6 ASCII digits (spec §5)."""
    return isinstance(pin, str) and _PIN.fullmatch(pin) is not None
