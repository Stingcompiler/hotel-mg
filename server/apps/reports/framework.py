"""Report shape shared by the API, Excel/CSV exports and print pages (spec §7: {columns, rows, meta})."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.utils import timezone

from apps.core.errors import ApiError


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    type: str = "text"  # text | money | int | percent | date | datetime


@dataclass
class Report:
    name: str
    title: str
    columns: list[Column]
    rows: list[dict]
    period: tuple[date, date] | None = None  # inclusive
    tiles: list[dict] = field(default_factory=list)  # [{label, value, type, hint}]
    totals: dict = field(default_factory=dict)  # column key → total
    formula: str = ""
    note: str = ""
    filters: list[dict] = field(default_factory=list)  # [{key, label, value}] — the filters applied, for print

    def meta(self) -> dict:
        return {
            "title": self.title,
            "filters": self.filters,
            "as_of": timezone.now(),
            "date_from": self.period[0] if self.period else None,
            "date_to": self.period[1] if self.period else None,
            "formula": self.formula,
            "note": self.note,
            "tiles": self.tiles,
            "totals": self.totals,
        }

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "columns": [{"key": c.key, "label": c.label, "type": c.type} for c in self.columns],
            "rows": self.rows,
            "meta": self.meta(),
        }


@dataclass(frozen=True)
class Params:
    date_from: date
    date_to: date  # inclusive
    extra: dict

    def get(self, key, default=None):
        return self.extra.get(key, default)


@dataclass(frozen=True)
class ReportDef:
    name: str
    title: str
    build: Callable[[Params], Report]
    default_days: int  # 0 = today only; 30 = month to date
    badge: Callable[[], int] | None = None
    manager_only: bool = False  # also hidden from the reports index (e.g. the audit log lives in Settings)


REGISTRY: dict[str, ReportDef] = {}


def report(name: str, title: str, *, default_days: int = 30, badge=None, manager_only: bool = False):
    def register(fn):
        REGISTRY[name] = ReportDef(name, title, fn, default_days, badge, manager_only)
        return fn

    return register


def parse_params(name: str, query) -> Params:
    definition = REGISTRY.get(name)
    if definition is None:
        raise ApiError("not_found", 404)
    today = timezone.localdate()
    try:
        date_to = date.fromisoformat(query["date_to"]) if query.get("date_to") else today
        if query.get("date_from"):
            date_from = date.fromisoformat(query["date_from"])
        elif definition.default_days >= 30:
            date_from = today.replace(day=1)
        else:
            date_from = date_to - timedelta(days=definition.default_days)
    except ValueError:
        raise ApiError("validation_error", 400, detail="صيغة التاريخ غير صحيحة (YYYY-MM-DD).") from None
    if date_to < date_from:
        raise ApiError("validation_error", 400, detail="نهاية الفترة قبل بدايتها.")
    extra = {k: v for k, v in query.items() if k not in ("date_from", "date_to", "format")}
    return Params(date_from, date_to, extra)


def build(name: str, query, *, is_manager: bool = True) -> Report:
    params = parse_params(name, query)
    if REGISTRY[name].manager_only and not is_manager:
        raise ApiError("permission_denied", 403)
    return REGISTRY[name].build(params)
