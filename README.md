# Sky Towers Hotel Management System

Offline Windows desktop hotel management system (Arabic, RTL) for Sky Towers Hotel, Khartoum.
A reception PC records every operation; an owner PC imports encrypted backups and reads.

- **Download the installer:** <https://github.com/Stingcompiler/hotel-mg/releases/latest> · guide: [`docs/windows.md`](docs/windows.md).
- `docs/spec/SkyTowers-System-Build-Spec.md` — system build specification (source of truth for architecture, rules, phases).
- `design-package/` — UI design package exported from Claude Design. **Read-only**: never edit in place.
- `docs/decisions.md` — decisions log; `docs/design-gaps.md` — where the design package and the spec disagree, and what was built.

## Layout

| Folder | What |
| --- | --- |
| `server/` | Django 5 + DRF backend, Waitress service, scheduler (alerts, clock guard, backups). See `CLAUDE.md`. |
| `api/` | Frozen API contract: `openapi.yml`, generated `schema.d.ts`, Postman collection (additive changes only). |
| `web/` | React 18 + Vite + Tailwind SPA (every screen of the design package, print templates). |
| `desktop/` | Tauri 2 shell and NSIS installer hooks. |
| `build/` | Build helpers: SPA build/copy, PyInstaller spec, token generator, CI helpers. |

## Quick start (development, Linux or Windows)

```
cd server
python3.12 -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python manage.py migrate && python manage.py seed_demo
cd .. && python build/build_spa.py && cd server           # needs Node.js 20+
python -m service.run_waitress                           # open http://127.0.0.1:8471/
```

Demo users: `manager`, `ahmed.ali`, `salma.h` — password `skytowers-dev`, PIN `123456`.

Frontend development: `cd web && npm ci && npm run dev` → `http://localhost:5173/` (proxies `/api` to the
Django server above).

## Checks

`server`: `ruff check . && ruff format --check . && python -m pytest` · `web`: `npm run check:ui && npm run typecheck && npm test` ·
CI runs both on every branch (Linux and Windows) plus the API-contract check; the *Windows release* workflow
builds the service bundle and the installer on `windows-latest`.
