# Sky Towers Hotel Management System

Offline Windows desktop hotel management system (Arabic, RTL) for Sky Towers Hotel, Khartoum.

- `docs/spec/SkyTowers-System-Build-Spec.md` — system build specification (source of truth for architecture, rules, phases).
- `design-package/` — UI design package exported from Claude Design. **Read-only**: never edit in place; integration copies from it. The UI design brief is at `design-package/project/uploads/SkyTowers-UI-Design-Brief.md`.

## Layout

- `server/` — Django 5 + DRF backend (phase B0: foundation). See `CLAUDE.md` for commands and rules.
- `docs/decisions.md` — decisions log; `docs/design-gaps.md` — open questions about the design package.

## Quick start (development)

```
cd server
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest
python manage.py migrate && python manage.py seed_demo
python -m service.run_waitress   # http://127.0.0.1:8471/api/v1/system/status
```
