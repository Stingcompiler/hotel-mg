"""Arabic wording shared by report and dashboard text (numbers stay Western; the SPA converts digits)."""


def days(n: int) -> str:
    """«يوم», «يومين», «3 أيام», «11 يومًا»; zero is «أقل من يوم»."""
    n = abs(n)
    if n == 0:
        return "أقل من يوم"
    if n == 1:
        return "يوم"
    if n == 2:
        return "يومين"
    if n <= 10:
        return f"{n} أيام"
    return f"{n} يومًا"
