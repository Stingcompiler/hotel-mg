# Sky Towers — working rules for Claude Code sessions

Read this first in every session. The full spec is `docs/spec/SkyTowers-System-Build-Spec.md`; section numbers below refer to it.
Decisions made in a session are appended to `docs/decisions.md` in the same PR.

## What this is

Offline Windows desktop hotel management system, Arabic RTL UI. Two PCs run the same stack: **reception** (all operations) and **owner** (read-only, imports encrypted backups). Django 5 + DRF service on `127.0.0.1:8471`, SQLite (WAL), Tauri 2 shell loading the SPA.

## Build order (§12)

Backend first. Track B phases B0 → B4, then **API freeze** (`v1.0-api` tag), then the frontend (F1–F3) from `design-package/`.
**No custom React code before the API freeze.** One phase item per session, one PR per session, tests green in CI.
Windows-only work (service wrapper, PyInstaller, NSIS installer, WebView2 print, power-cut test) is Track W and cannot be done in a Linux cloud session; cloud sessions may write and lint it.

## Repo layout (§4)

- `server/` — Django project. `config/` (settings per role, `runtime.py` reads `config.json`), `apps/<app>/`, `service/`.
- `design-package/` — Claude Design export. **Read-only input**: never edit; copy from it. Needed design changes go to `docs/design-gaps.md`.
- `docs/` — spec, decisions, design gaps.
- Later: `web/` (F1), `desktop/` (Track W), `build/` (Track W).

## Backend rules

- **Business logic lives only in Django.** Each app: `models.py`, `rules.py` (pure functions, no ORM, 100 % covered), `services.py` (one function per use case, one `transaction.atomic()`, writes one `AuditLog` row), `serializers.py`, `views.py`, `tests/`.
- Every hotel model inherits `apps.core.models.BaseModel` (UUID pk, `hotel_id`, `created_at`, `updated_at`, `version`, `created_by`). Append-only tables (§5) inherit `AppendOnlyModel`: corrections are new rows, never updates/deletes.
- **Money** is `apps.core.fields.MoneyField` (int, minor units = piasters ×100). API uses `MoneyMinorField`. Never `float` or `Decimal` for money. Formatting is the frontend's job.
- **Dates**: stay periods are date-only in `Africa/Khartoum`; `check_out_date` is exclusive. Timestamps are UTC.
- **Portability**: ORM only, no SQLite-specific SQL; switching `DATABASES` to PostgreSQL must be the only change.
- **Concurrency**: PUT/PATCH send `version`; load rows with `apps.core.concurrency.get_for_update()` inside the service transaction → HTTP 409 `version_conflict` when stale.
- **Errors**: raise `apps.core.errors.ApiError(code, status)`; responses are `{"code", "detail"}` with Arabic `detail` from `errors.MESSAGES`. Codes are stable machine strings.
- **Clock guard**: `ClockGuardMiddleware` refuses writes with HTTP 423 `clock_rollback` while blocked (§6.7).
- Owner PC: every mutating request except `/api/v1/owner/…` is refused (middleware lands in B4). The owner PC never creates hotel rows.
- User-facing strings (errors, exports, prints) are Arabic; code, identifiers, logs, comments are English.

## Commands (from `server/`)

```
pip install -r requirements-dev.txt        # Python 3.12
python -m pytest                           # tests (settings: config.settings.test)
ruff check . && ruff format --check .      # lint
python manage.py makemigrations --check --dry-run
python manage.py spectacular --validate --fail-on-warn --file openapi.yml
python manage.py migrate && python manage.py seed_demo   # dev data (DEBUG only)
python -m service.run_waitress             # serve on 127.0.0.1:8471
```

`SKYTOWERS_HOME` picks the data directory (default: `%ProgramData%\SkyTowers` on Windows, `server/.devdata` elsewhere). `manage.py` uses `config.settings.dev`.

## Frontend rules (for F1+, §10)

Tokens only (CI fails on hex colours outside `tokens.css`); Tailwind logical utilities only (CI fails on `ml-/mr-/pl-/pr-/left-/right-`); strings from `ar.json`, copied verbatim from the design; `stateColor(status)` is the only user of state colours; no business logic in the SPA.
