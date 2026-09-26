# Decisions log

Append-only. Newest last. Each entry: date, phase, decision, reason.

## 2026-09-26 — B0 Foundation

1. **Design package committed on `main` first**, unchanged, under `design-package/` (Claude Design handoff v1, 17 design files + `tokens.json` + brief + chat transcript). The build spec lives in `docs/spec/`.
2. **Pinned versions**: Django 5.2.17 (LTS), DRF 3.18.1, drf-spectacular 0.30.0, waitress 3.0.2, Python 3.12. See `server/requirements*.txt`.
3. **`config.json` location** is `SKYTOWERS_HOME` (default `%ProgramData%\SkyTowers` on Windows, `server/.devdata` elsewhere). Without a `config.json` the PC runs as reception with a fixed dev `hotel_id` (`5a7e0000-…-0001`), so seeded data stays stable. The installer always writes `config.json`. `secret_key` comes from `config.json` or is generated once into `secret.key`.
4. **Settings module must match `config.json` role**: `config.settings.reception|owner` refuse to start on a mismatch; `service/run_waitress.py` picks the module from the role.
5. **SQLite settings** use Django's `init_command` for the PRAGMAs and `transaction_mode="IMMEDIATE"` (spec §3). Covered by `apps/core/tests/test_database.py`.
6. **Custom `accounts.User` created in B0** (not B1): Django needs the custom user model before the first migration and `BaseModel.created_by` references it. It inherits `BaseModel`. The password hash is Django's `password` column (spec's `password_hash`). PIN rules (4–6 ASCII digits) are in `accounts/rules.py`; login endpoints, lockout and confirm tokens are B1.
7. **`AppendOnlyModel`** added to core: blocks instance save-after-insert, `delete()`, and queryset `update()/delete()`.
8. **`SystemClock` is device state**, not a `BaseModel`; it is excluded from backups' merge import. B0 ships the rule, the `observe_clock/approve_clock` services and the write-blocking middleware. The approve endpoint (password confirmation) and audit entries for rollback/approval come with auth (B1) and the scheduler (B3).
9. **Error shape** `{"code", "detail"}` for every API error via `apps.core.errors.api_exception_handler`; validation errors add `errors` with the field map.
10. **Authentication** is DRF session auth until B1 adds token login (§6.8). `/api/v1/system/status` is public so the SPA can pick the shell before login; it also returns `schema_version` and `data_as_of` (null until B4).
11. **Seed**: `manage.py seed_demo` loads the design's users (PIN `1234`, dev password) and refuses to run with `DEBUG` off unless `--allow-non-debug`. All brief/design sample data is kept in `apps/core/seed/demo_data.py`; each later phase adds the loader for its models. The spec's `fixtures/demo.json` for F-phase review will be generated from the same data.
12. **CI** runs on Ubuntu and Windows: ruff, migrations check, OpenAPI validation, pytest with coverage, seed.

## 2026-09-26 — Working method

13. **Standing instruction** from the repo owner: execute the recommended option, push, check CI, merge into `main`, continue with the next item. Captured in `CLAUDE.md` and the `phase-cycle` skill.
14. **Merging**: every branch goes through a pull request opened and merged with `gh api` (REST; GraphQL is blocked in cloud sessions), only after the branch's CI run is green. CI runs on every branch push; `build/ci-status.sh` reads the result.

## 2026-09-26 — B1.1 Audit chain and authentication

15. **AuditLog** is append-only with a per-hotel `seq`; `hash = sha256(prev_hash + canonical_json(payload))`, payload = seq, hotel_id, actor_id, action, entity, entity_id, before, after, at (UTC ISO). Canonical JSON: sorted keys, no spaces, UTF-8 kept. `before/after` are stored after a JSON round-trip, so verification hashes exactly what is stored. Unique (hotel_id, seq) makes a concurrent writer fail rather than fork the chain. Passwords and PIN hashes are never copied into audit rows.
16. **Action names** are `<entity>.<verb>` (`user.update`, `auth.login_pin`, `system.clock_rollback`). Every service calls `audit.record()` inside its transaction.
17. **Login** follows the login artboard: public `GET auth/users` for the user picker; wrong PIN returns 401 with `attempts_left`; the 5th failure locks for 5 minutes (423 `account_locked` with `locked_until`) and is audited; a manager can lift it (`POST users/:id/unlock`). PIN and password share the failure counter; password confirmation also counts.
18. **Session**: DRF token, one per user (new login replaces the old), expires 12 h after login (`token_expired`). Session auth stays on for the browsable API.
19. **Confirmation token**: `POST auth/confirm {password}` → signed, user-bound token valid 5 minutes, sent as `X-Confirm-Token`. Required for create/edit user, reset PIN, clock approval (and later: prices, checkout with debt, rule delete/disable, import, big discounts).
20. **Roles**: managers manage reception and manager accounts; only the owner manages owner accounts. Nobody can deactivate themselves or change their own role. Deactivating a user revokes their session. Manager and owner accounts need a password; reception accounts may be PIN-only.
21. **Clock guard**: detection and approval are audited (`system.clock_rollback`, `system.clock_approve`); `POST system/clock/approve` needs manager + confirmation. `/api/v1/auth/*` stays reachable while blocked so a manager can sign in.
22. **Coverage gate**: CI fails if any `apps/*/rules.py` is below 100 % line coverage.
