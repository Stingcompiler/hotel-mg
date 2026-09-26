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

## 2026-09-26 — B1.2 Rooms

23. **State machine** as a transition table keyed by (from, to) → the only trigger allowed: `check_in` (ready→occupied), `checkout` (occupied→cleaning), `manual` for the rest (cleaning→ready, ready⇄maintenance, cleaning⇄maintenance). Occupied is never changed by hand. Refusals return 409 `invalid_room_transition` with the Arabic detail naming the room and the `allowed` manual targets for the UI.
24. **Maintenance needs a reason** (400 `reason_required`); the reason is kept on the room while in maintenance and in the history row.
25. **Out of service** (`Room.in_service`, from the V2 Settings → Rooms artboard) is separate from status: it blocks booking and occupancy counts; an occupied room cannot be taken out (409 `room_occupied`).
26. **Price edits** (any of nightly/weekly/monthly, and creating a room type) need a password confirmation; renames do not. Audit action `room_type.update_prices` separates price changes in the trail.
27. **Room type capacity** assumed 1 / 2 / 3 (single / double / suite) until the design answers gap #1; editable in settings.
28. **Seed** follows the Room Board artboard for non-occupied states (104 and 306 cleaning, 410 maintenance) and the Settings artboard for room types (singles 101–108). Occupied rooms appear when the stays loader checks guests in.

## 2026-09-26 — B1.3 Guests

29. **Search** (`GET guests?q=`) matches a normalized name key (diacritics and tatweel removed; أ/إ/آ→ا, ة→ه, ى→ي folded), phone digits (a local `09…` matches the stored `+2499…`), or the exact ID number. Arabic-Indic digits are accepted everywhere and stored as ASCII.
30. **ID number** is returned in full to manager/owner and masked to the last 4 characters for reception (who can still enter it and search by the exact value).
31. **ID images**: any Pillow-readable image up to 10 MB is re-encoded server-side as JPEG ≤ 300 KB (orientation fixed, metadata stripped) under `attachments/guests/<guest>/`; `GuestDocument` is append-only with size and SHA-256. The unblurred image is served only to manager/owner with `Cache-Control: no-store`, and every view is audited (`guest.view_document`, the design's «عرض حساس»).
32. **No deletes for mutable hotel rows**: replaced companions are flagged `removed` so the owner PC's additive import stays correct. Rule added to `CLAUDE.md`.
33. Full name needs at least two words (the forms use full names for invoices and reports).

## 2026-09-26 — B1.4 Reservations

34. **Durations**: daily ×N = N nights, weekly ×N = 7N, monthly ×N = 30N; `check_out_date = check_in + nights` (exclusive); `last_night` is returned for the «تنتهي بنهاية يوم …» text. Max 366 nights.
35. **Pricing options** (spec §6.1): weekly and monthly are exact; daily stays of 7+ nights also offer months→weeks→nights and weeks→nights mixes, deduplicated and sorted cheapest first (10 nights → «أسبوع + 3 ليالٍ» 113,000 / «10 ليالٍ» 120,000, as on artboard 6.4 B). With several options the client must send `option_key` (400 `pricing_choice_required` lists them). Labels use Arabic number agreement (ليلة / ليلتان / 3 ليالٍ / 30 ليلة).
36. **Rate snapshot** stores the type name, the three prices, the chosen option and label, base total, and any override with its reason; `Reservation.total` is the agreed room charge. A price override needs a reason (artboard: «سبب تعديل السعر *»). Discounts, deposits and payments come with folios in B2.
37. **Overlap** (spec §6.2): confirmed and checked-in reservations block their room over [check_in, check_out); a checked-in stay also holds the room through today when overdue. Booking locks the room row (`select_for_update`, row lock on PostgreSQL; the IMMEDIATE transaction serializes on SQLite) before checking. Verified by a 6-thread race test on a real SQLite file: exactly one wins.
38. **Room checks at booking**: out-of-service rooms are refused; rooms under maintenance are refused only for arrivals today (a future booking may be made while repairs finish). Past arrival dates are refused (the opening-day migration will use `allow_past`).
39. **Tests use a SQLite file** (in the test `SKYTOWERS_HOME`) instead of in-memory, so they exercise WAL and real locking.
40. Reservation cancel (before check-in) needs a reason; no-show only from the arrival day; a room can be assigned later with the same overlap check.

## 2026-09-26 — B1.5 Stays and the room board

41. **Check-in** from a confirmed reservation between the arrival day and the last night (late arrivals keep their dates); the room must be ready and free; opens `Stay` + first `StaySegment`. **Walk-in** («تسكين الآن») is `check_in_now: true` on booking: reservation and check-in in one transaction.
42. **Extend** adds nights after the current end at the room type's *current* prices (artboard 6.5 D: «السعر الحالي»), with the same option/override rules as booking; same kind accumulates the count (monthly ×1 + ×1 = monthly ×2), otherwise the booking becomes `mixed`. The extension is appended to `rate_snapshot.extensions`.
43. **Change room** takes effect today: the current segment closes today, a new one opens; the vacated room goes occupied → cleaning (→ maintenance if chosen, with reason); the new room must be ready and free for the rest of the stay. Price difference = booking priced at the new type minus the old type, pro-rated over remaining nights, rounded to whole pounds; negative needs a manager override (V2 artboard 6.5 E). Candidates list same type first.
44. **Manager override** = the manager's password typed on the reception screen plus a reason (artboards 6.5 C and 6.5 F). The server matches it against active managers/owners and records the approver on the stay and in audit. Failed override attempts are not yet rate-limited (to add with B2 checkout-with-debt).
45. **Checkout** closes the segment on the actual departure day (early or overdue) and sends the room to cleaning or maintenance. The balance ≠ 0 rule and debt recording arrive with folios in B2; the override fields are already accepted and recorded.
46. **Cancel stay** needs a reason and a manager override; settlement options price the nights used (at least 1) at the booking's prices, same decomposition logic as booking (V2 artboard 6.5 F: «12 ليلة» vs «أسبوع + 5 ليالٍ»), or a manual total. Status becomes `cancelled`; nothing is deleted; the previous and new totals are kept in `rate_snapshot.cancellation`. Refunds come with payments in B2.
47. **Room board** is `GET rooms?view=board`: every room with its stored status, a derived `display_status` (overdue), current stay (guest, last night, `days_left`), next booking, and a summary (occupancy over in-service rooms, arrivals/departures today, overdue, counts by status). `balance` is null until B2.
48. **Seed** loads the 18 occupied rooms of the Room Board as checked-in stays and the 102 booking, dated relative to the day it runs; it reproduces «18/30 · 60٪», two overdue rooms and two departures today.
49. Removed `# fmt: skip` markers everywhere; code layout is left to `ruff format`.
