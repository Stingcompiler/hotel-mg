import pytest

from apps.core.arabic import days


@pytest.mark.parametrize(
    ("n", "text"),
    [(0, "أقل من يوم"), (1, "يوم"), (-2, "يومين"), (3, "3 أيام"), (10, "10 أيام"), (11, "11 يومًا"), (30, "30 يومًا")],
)
def test_days(n, text):
    assert days(n) == text
