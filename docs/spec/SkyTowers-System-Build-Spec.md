# Sky Towers Hotel Management System — System Build Specification

**Audience of this document:** an AI coding model (or developer) implementing the system. A separate UI design package (design tokens, component library, screen designs, optionally React/Tailwind code) will be provided after the design phase; section 10 explains how to consume it.
**Product language:** Arabic, RTL. All UI strings, error messages, printed documents and exports are Arabic. Code, identifiers, logs and this document are English.
**Platform:** Windows 10/11 (64-bit) desktop, fully offline. Two roles installed from one installer: **reception** and **owner**.

---

## 1. Scope

### In scope (v1.0)

- Rooms, room types, room state machine, status history.
- Guests, companions, optional ID document images.
- Reservations, stays, check-in, extension, room change, checkout, cancellation, no-show.
- Daily / weekly (7 nights) / monthly (30 nights) stays; mixed durations by explicit staff choice.
- Folios, folio lines, payments (cash, Bankak, bank transfer), refunds, reversals, discounts with reasons.
- Cash shifts and expenses.
- Alert rules, follow-up tasks, actions, snooze limits, escalation to "neglected".
- Hash-chained audit log; clock-rollback guard.
- Encrypted backups (manual button + schedule), Google Drive upload/download button, additive merge import on the owner PC.
- Reports (HTML → PDF via embedded browser, Excel, CSV) with A4 and 80 mm receipt templates.
- One Windows installer with role selection; Windows service for the backend; tray application with notifications.

### Out of scope (v1.0)

Bank/OTA integrations, payroll, inventory, VAT, government guest reports, any real-time sync between PCs, SMS/WhatsApp, LAN multi-PC (architecture must not prevent it later), PostgreSQL (must remain possible without code rewrite).

---

## 2. Architecture

Each PC runs the same stack locally. The only difference is `role` in the config file.

```
┌──────────────────────────────── Windows PC ────────────────────────────────┐
│  Tauri 2 desktop shell (Rust, thin)                                        │
│   • window + system tray + autostart + native notifications + file dialogs  │
│   • launches/monitors nothing: the backend is an independent Windows service│
│   • loads http://127.0.0.1:8471/ (the SPA served by Django)                 │
│                                                                            │
│  Windows Service "SkyTowersServer" (Python, PyInstaller --onedir)           │
│   • Waitress → Django 5 + DRF, bound to 127.0.0.1:8471 only                 │
│   • scheduler thread: alert engine (60 s), scheduled backups, clock guard   │
│   • SQLite file: %ProgramData%\SkyTowers\data\hotel.db  (WAL)               │
│   • attachments: %ProgramData%\SkyTowers\data\attachments\                  │
│   • backups:     %ProgramData%\SkyTowers\backups\  (+ optional 2nd folder)  │
│   • config:      %ProgramData%\SkyTowers\config.json  {role, hotel_id,…}    │
└────────────────────────────────────────────────────────────────────────────┘
```

Rules:

- **Business logic lives only in Django** (`services.py` per app). The frontend never computes prices, balances, dates or permissions for anything other than instant preview; the server result is authoritative.
- **Owner role is enforced server-side**: a middleware rejects every mutating request (`POST/PUT/PATCH/DELETE`) except the allow-listed paths under `/api/v1/owner/` (import, drive sync, local settings) with HTTP 403 `{"code":"owner_read_only"}`.
- **No SQLite-specific SQL.** Use the ORM; where raw SQL is unavoidable, keep it ANSI. The system must run on PostgreSQL by changing `DATABASES` only.
- Server address is a frontend config value (`window.__SKYTOWERS__.apiBase`), not a constant, so a LAN client can be added later.

---

## 3. Technology stack (pinned at project start, do not substitute)

| Layer | Choice |
| --- | --- |
| Backend | Python 3.12, Django 5.x, djangorestframework, drf-spectacular (OpenAPI), waitress, pywin32 (service), pyinstaller |
| Database | SQLite 3 via Django; PRAGMAs: `journal_mode=WAL`, `synchronous=FULL`, `foreign_keys=ON`, `busy_timeout=20000`; Django `OPTIONS.transaction_mode="IMMEDIATE"` |
| Backup crypto | `pyrage` (age encryption): recipient = owner public key; `hashlib` SHA-256 manifests |
| Drive | `google-api-python-client`, `google-auth-oauthlib`; refresh token stored encrypted with Windows DPAPI (`win32crypt`) |
| Exports | `openpyxl` (sheet `rightToLeft=True`), `csv` with UTF-8 BOM; PDF via the embedded browser print path (see §8) |
| Frontend | React 18, TypeScript 5, Vite, Tailwind 3.4+ (logical utilities), shadcn/ui (Radix), TanStack Query v5, TanStack Table v8, react-hook-form + zod, `lucide-react`, `date-fns` |
| API client | Generated from the OpenAPI schema with `openapi-typescript` + a thin `fetch` wrapper |
| Desktop | Tauri 2 with plugins: `tray-icon`, `autostart`, `notification`, `dialog`, `single-instance`, `shell` (open folders) |
| Installer | Tauri bundler → NSIS; WebView2 `offlineInstaller` mode; custom NSIS hooks to install/start the service and write `config.json` |
| Tests | pytest + pytest-django (backend), Vitest + Testing Library (frontend), Hypothesis for the merge property test |

---

## 4. Repository layout

```
skytowers/
├── server/
│   ├── config/            settings/{base,reception,owner}.py, urls.py, wsgi.py, asgi.py
│   ├── apps/
│   │   ├── core/          BaseModel, Money field, ClockGuard, audit decorator, permissions
│   │   ├── accounts/      User, roles, PIN + password auth, login events
│   │   ├── rooms/         RoomType, Room, RoomStatusHistory, state machine
│   │   ├── guests/        Guest, Companion, GuestDocument
│   │   ├── stays/         Reservation, Stay, StaySegment, pricing rules
│   │   ├── billing/       Folio, FolioLine, Payment
│   │   ├── cash/          Shift, Expense
│   │   ├── followups/     AlertRule, FollowupTask, TaskAction, engine
│   │   ├── backup/        export, encrypt, drive, merge import
│   │   ├── reports/       report queries + HTML/Excel/CSV renderers
│   │   └── audit/         AuditLog, hash chain, verifier
│   ├── service/           win_service.py (pywin32), run_waitress.py, scheduler.py
│   ├── static_spa/        built frontend copied here at release time
│   └── tests/
├── web/                   React SPA (Vite)
│   ├── src/app/           router, providers, shell layouts (reception/owner)
│   ├── src/features/      one folder per screen (see §10.4)
│   ├── src/components/ui/ shadcn components (from the design package)
│   ├── src/design/        tokens.css, tailwind preset (from the design package)
│   ├── src/api/           generated types + client + query hooks
│   ├── src/i18n/          ar.json (all UI strings), digits.ts, money.ts, dates.ts
│   └── src/print/         invoice-a4.tsx, receipt-80mm.tsx, report-a4.tsx
├── desktop/               Tauri 2 project (src-tauri/, installer hooks)
├── build/                 release.ps1, pyinstaller.spec, fonts/, nsis/
└── docs/                  Arabic user guide, hotel policies
```

Conventions: every Django app has `models.py`, `rules.py` (pure functions, no ORM), `services.py` (one function per use case, one transaction each, writes one audit entry), `serializers.py`, `views.py`, `tests/`.

---

## 5. Data model

All models inherit `BaseModel`:

```python
class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    hotel_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)      # incremented on every save
    created_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT, related_name="+")
    class Meta: abstract = True
```

Money: `MoneyField = models.BigIntegerField` storing **minor units (piasters, ×100)**. Never use `FloatField`/`DecimalField` for money. Display formatting happens in the frontend (`money.ts`) using the hotel's digit and decimals settings.

Dates: stay periods are **date-only** fields in the hotel timezone (`Africa/Khartoum`). `check_out_date` is **exclusive** (the day after the last included night). Timestamps are stored UTC.

Append-only tables (never updated after insert; corrections are new rows): `login_events`, `room_status_history`, `folio_lines`, `payments`, `expenses`, `task_actions`, `audit_log`, `backup_runs`, `import_runs`.

| App | Model | Key fields | Rules |
| --- | --- | --- | --- |
| accounts | `User` | username, full_name, role ∈ {owner, manager, reception}, pin_hash, password_hash, is_active | PIN 4–6 digits for daily login; password re-entry for sensitive actions (see §6.8). 5 failed attempts → 5-minute lock |
| accounts | `LoginEvent` | user, at, kind ∈ {pin, password, failed} | |
| rooms | `RoomType` | name, capacity, nightly_price, weekly_price, monthly_price | Price edits never touch existing reservations |
| rooms | `Room` | number, floor, room_type, status ∈ {ready, occupied, cleaning, maintenance}, maintenance_reason | Status is operational; independent from future reservations |
| rooms | `RoomStatusHistory` | room, from_status, to_status, at, by, reason | Source for vacancy-period report |
| guests | `Guest` | full_name, phone, nationality, id_type, id_number, warning_note | `id_number` visible to manager/owner only |
| guests | `Companion` | guest, name, relation | |
| guests | `GuestDocument` | guest, file_path, size, sha256 | Files under `attachments/`, max 300 KB after server-side compression |
| stays | `Reservation` | guest, room_type, room (nullable until assignment), check_in_date, check_out_date, duration_kind ∈ {daily, weekly, monthly, mixed}, duration_count, status ∈ {confirmed, checked_in, checked_out, cancelled, no_show}, rate_snapshot (JSON), notes | Overlap forbidden for the same room among statuses {confirmed, checked_in} |
| stays | `Stay` | reservation (1:1), checked_in_at, checked_out_at | Created at check-in |
| stays | `StaySegment` | stay, room, from_date, to_date, reason | Room change closes the current segment and opens a new one |
| billing | `Folio` | stay (1:1), invoice_no (per-hotel sequence, gap-free), status ∈ {open, closed} | Balance is computed, never stored |
| billing | `FolioLine` | folio, kind ∈ {room, service, discount, tax, reversal}, description, amount_minor (signed), reverses (self FK, nullable), reason, by | Reversal = negative line pointing to the original |
| billing | `Payment` | folio, shift, method ∈ {cash, bankak, transfer}, amount_minor (signed), reference, verified, reverses (nullable), by | Requires an open shift on the device |
| cash | `Shift` | user, opened_at, closed_at, opening_minor, expected_minor, counted_minor, difference_reason | Exactly one open shift per device |
| cash | `Expense` | shift, category, amount_minor, note, method, reverses (nullable), by | |
| followups | `AlertRule` | name, trigger_kind (see §6.6), duration_kind (nullable), days_before, at_time, repeat_hours, max_snoozes, escalate_after_hours, threshold_minor (nullable), is_active | |
| followups | `FollowupTask` | rule, stay (nullable), room (nullable), shift (nullable), due_at, status ∈ {open, snoozed, waiting, done, superseded, neglected}, snooze_count, next_at, unique(rule, stay, due_date) | Closed only by an action |
| followups | `TaskAction` | task, action ∈ {extend, confirm_checkout, waiting, snooze, done}, by, at, note, next_at | |
| backup | `BackupRun` | kind ∈ {manual, scheduled}, seq (per hotel), path, size, sha256, status, drive_file_id, error | |
| backup | `ImportRun` | source ∈ {drive, file}, backup_seq, status, counts (JSON: table → {inserted, updated, ignored}), error | |
| core | `SystemClock` | singleton: last_seen_at | Clock guard |
| audit | `AuditLog` | actor, action, entity, entity_id, before (JSON), after (JSON), at, prev_hash, hash | `hash = sha256(prev_hash + canonical_json(row))` |

---

## 6. Business rules (implement in `rules.py`, cover with unit tests)

### 6.1 Duration and dates

- `nights = (check_out_date - check_in_date).days`; weekly = 7 nights, monthly = 30 nights.
- End of stay = end of `check_out_date - 1 day` in `Africa/Khartoum`.
- Mixed durations: the server returns all valid decompositions (e.g. 10 nights → `[weekly×1 + daily×3, daily×10]`) with totals; the client must send the chosen one; it is stored in `rate_snapshot`.

### 6.2 Overlap

Reject if any reservation on the same room with status in `{confirmed, checked_in}` satisfies `a.check_in_date < b.check_out_date AND a.check_out_date > b.check_in_date`. Perform the check and the insert inside one `transaction.atomic()`; with `transaction_mode=IMMEDIATE` this is serializable on SQLite. Add a DB-level `CheckConstraint(check_out_date > check_in_date)`.

### 6.3 Room state machine

```
ready ──check_in──▶ occupied ──checkout──▶ cleaning ──confirm_ready──▶ ready
ready ⇄ maintenance ; cleaning ⇄ maintenance     (never from occupied)
```

Overdue is derived: `status == occupied AND today >= check_out_date`. Nothing automatic happens at the end date.

### 6.4 Money

- `balance = Σ folio_lines.amount_minor − Σ payments.amount_minor` (reversals carry negative amounts, so no special-casing).
- Checkout with `balance != 0` requires `manager_override = {password, reason}`; the remaining balance becomes a debt visible in reports.
- Discounts require a non-empty reason and the `discount` permission; a max-discount setting is enforced server-side.
- Expected cash for a shift = `opening + Σ cash payments − Σ cash expenses`.
- Occupancy % = occupied room-nights ÷ (available room-nights − maintenance room-nights); the formula string is returned with the report.

### 6.5 Shifts

One open shift per device. Every payment and expense references the open shift; recording one with no open shift returns HTTP 409 `{"code":"no_open_shift"}`. Closing requires `counted_minor`, and `difference_reason` when `counted != expected`.

### 6.6 Alert engine (scheduler, every 60 s)

Trigger kinds and default rules seeded on first run (manager-editable):

| trigger_kind | Default |
| --- | --- |
| `stay_ending` (daily) | day of end, 09:00 |
| `stay_ending` (weekly) | 2 days before, 09:00 |
| `stay_ending` (monthly) | 5 days before, 09:00 |
| `stay_overdue` | at end, repeat every 24 h |
| `checkout_debt` | immediate when balance > threshold |
| `shift_open_too_long` | > 14 h |
| `room_cleaning_too_long` | > 4 h |
| `room_maintenance_too_long` | > 7 days |
| `no_backup` | > 24 h |
| `no_drive_upload` | > 3 days |

Engine behaviour:

- Idempotent: `FollowupTask` unique on `(rule, stay, due_date)`; re-runs never duplicate.
- Missed tasks (PC was off) are created on the next tick with their original `due_at`; UI shows "late since".
- Extension/room change/cancellation marks pending tasks `superseded` and generates new ones. No deletion.
- Snooze increments `snooze_count`; refuse when `>= max_snoozes`.
- A task still `open` after `escalate_after_hours` becomes `neglected` and records the shift open at that moment.
- Tasks are surfaced to the frontend via `GET /api/v1/followups/tasks?status=open` and to the tray via `GET /api/v1/followups/toasts` (new since last poll). The tray polls every 30 s and shows native notifications.

### 6.7 Clock guard

On every write and every tick: `if now < SystemClock.last_seen_at - 5 min` → set `clock_blocked = True`, refuse writes with HTTP 423 `{"code":"clock_rollback"}` until a manager posts `/api/v1/system/clock/approve` with password; log an audit entry either way. Otherwise update `last_seen_at`.

### 6.8 Authentication and permissions

- Login: `POST /auth/pin` `{user_id, pin}` → session token (DRF token, 12 h). `POST /auth/password` for full login.
- Sensitive actions require a fresh password confirmation token (`POST /auth/confirm` → 5-minute `X-Confirm-Token`): create/edit user, edit prices, checkout with debt, delete/disable alert rule, import backup, approve clock, manual discount above threshold.
- Roles: `reception` (operations), `manager` (+ settings, users, overrides), `owner` (everything; on the owner PC everything is read-only anyway).
- Owner PC middleware (§2) is independent of roles.

### 6.9 Audit

Every service function writes one `AuditLog` row inside the same transaction with `before/after` JSON of the touched entity. Hash chain per hotel. `GET /api/v1/audit/verify` walks the chain and returns the first broken row, if any.

---

## 7. API (DRF, `/api/v1/`, JSON, Arabic error messages in `detail`, stable machine `code`)

Generate the OpenAPI schema with drf-spectacular; the frontend client is generated from it. Main resources:

```
auth/        pin, password, confirm, logout, me
users/       CRUD (manager+), reset-pin
room-types/  CRUD (manager+)
rooms/       list (board view: ?view=board returns state + current stay + next reservation), set-status
guests/      search ?q=, CRUD, documents (upload multipart, 300 KB max after compression)
reservations/ list ?from&to&status, create, availability ?room_type&from&to,
              quote (returns nights, decompositions, totals), cancel, no-show
stays/       check-in, detail (folio, payments, segments, tasks, audit), extend, change-room,
             checkout (optional manager_override), add-line, reverse-line
payments/    create (requires open shift), reverse
shifts/      current, open, close, list, detail
expenses/    create, reverse, list
followups/   rules CRUD + preview (?date), tasks list, actions (extend|confirm_checkout|waiting|snooze|done), toasts
reports/     <name>?filters → {columns, rows, meta{formula, as_of}} ; /export?format=xlsx|csv ; /print?format=html
backup/      run, list, settings, drive/auth-url, drive/callback, drive/sync
owner/       import/candidates, import/run (multipart or drive_file_id), import/runs, settings
system/      status (role, hotel_id, last_backup, clock_blocked, version), clock/approve
audit/       list ?entity&id, verify
```

Conventions: list endpoints paginate (`?page&page_size`, default 50); mutations return the updated entity plus `version`; a stale `version` in a `PUT/PATCH` returns HTTP 409 `{"code":"version_conflict"}`.

---

## 8. Printing and exports

- Reports and invoices are rendered by the SPA as print-only React pages (`/print/invoice/:id?format=a4|80mm`, `/print/report/:name?…`) using the templates from the design package.
- PDF path A: `window.print()` inside the Tauri webview → Windows print dialog; "Microsoft Print to PDF" gives the file. Ship this first.
- PDF path B (Phase 1 spike): a Tauri Rust command calling WebView2 `PrintToPdf` for silent export. Adopt only if the spike is stable on Windows 10 and 11.
- Excel: `openpyxl`, `ws.sheet_view.rightToLeft = True`, numbers as numbers (minor units converted to major with 2 decimals or 0 per setting), header row bold, freeze panes.
- CSV: UTF-8 with BOM, comma separated, CRLF.
- Fonts: IBM Plex Sans Arabic bundled in `web/public/fonts/` and referenced via `@font-face`; no network font loading.

---

## 9. Backup, Drive and merge import

### 9.1 Backup (`backup/run`, scheduler default every 6 h)

1. `VACUUM INTO '<tmp>/hotel.db'` on the live connection.
2. Collect attachments changed since the last **full** backup (weekly full, otherwise incremental).
3. Write `manifest.json`: `{hotel_id, seq, created_at, schema_version, app_version, files:[{name,size,sha256}]}`.
4. Zip → encrypt with age to the owner recipient → `skytowers-<hotel8>-<seq:06d>-<YYYYMMDD-HHMM>.age`.
5. Save to `backups/` and, if configured, the second folder; record `BackupRun`; apply retention (count and age).
6. Restore-after-failure of the reception PC is a separate CLI/maintenance action (`manage.py restore_full <file>`), never mixed with the owner import.

### 9.2 Drive (`backup/drive/sync`)

- Reception: upload every `BackupRun` with `drive_file_id IS NULL` to folder `SkyTowers/backups`; set the id on success.
- Owner: list files whose `seq` > last imported; download to `incoming/`; return candidates.
- No internet → HTTP 503 `{"code":"offline"}`; nothing else in the app depends on connectivity.

### 9.3 Merge import (owner PC only, `owner/import/run`)

Additive merge; **nothing is ever deleted** on the owner PC.

1. Decrypt with the owner private key; verify every `sha256` in the manifest.
2. `PRAGMA integrity_check` on the imported `hotel.db`.
3. `hotel_id` must match `config.json` (first import sets it). `schema_version` newer than the app → refuse with `{"code":"upgrade_required"}`.
4. Attach the imported DB as a second Django database alias (`incoming`); run `migrate --database=incoming` to bring it to the current schema.
5. Verify the incoming audit hash chain; store the result in the run.
6. In one transaction on the main DB, for each model in dependency order:
   - append-only models: `INSERT` rows whose `id` is absent (bulk, ignore conflicts);
   - mutable models: `INSERT` absent rows; `UPDATE` existing rows only where `incoming.updated_at > current.updated_at`.
7. Copy attachments that are absent locally.
8. Record `ImportRun.counts` per table; any exception → rollback, status `failed`, main DB untouched.
9. Importing an older `seq` is allowed with a warning; the `updated_at` rule prevents regressions.

Property test (Hypothesis): generate random operation sequences → produce backups at random points → import in random order (with repeats) → all report totals on the owner DB equal the reception DB.

---

## 10. Consuming the UI design package (made with Claude Design)

The UI is designed in **Claude Design** in parallel with the backend and delivered as a finished package **before frontend work starts**. The frontend phase does not design anything: it takes the package as the single source of truth for visuals and implements behaviour and data wiring around it. If an item is missing, implement it from the UI Design Brief (companion document) rather than inventing new values, and record the gap in `docs/design-gaps.md`.

### 10.1 Expected contents

The package is committed to the repo under `design-package/` exactly as exported, and never edited in place; integration copies from it.

| Item | Format (as exported from Claude Design) | Destination in repo |
| --- | --- | --- |
| Design system | Design System artifact export: tokens (colours, typography, spacing, radius, shadows) as JSON/CSS, component specs | `web/src/design/tokens.css` (CSS variables) + `web/tailwind.preset.ts` generated by `build/tokens-to-tailwind.ts` |
| Component library | HTML/CSS artboards and/or React + Tailwind source for every component with its states | `web/src/components/ui/` (shadcn-style; one file per component) |
| Screen designs | One artboard per screen and state (1920×1080; 1366×768 for room board and new reservation), HTML/CSS and/or React source | `web/src/features/<screen>/` |
| Print templates | Artboards for invoice A4, receipt 80 mm, report A4 landscape | `web/src/print/` |
| RTL notes | One page | `docs/rtl-notes.md`; every listed decision becomes a comment in the corresponding component |
| Arabic UI copy | Strings used in the artboards | `web/src/i18n/ar.json` — the design strings are canonical; do not paraphrase |
| Screenshots | PNG of every approved artboard | `design-package/screens/*.png` — used for pixel review of the implemented screens |

Rule of dependence: an implemented screen is compared side by side with its artboard PNG before it is accepted. Visual differences are fixed in the implementation, never by arguing the design should change; a real design problem goes back to Claude Design and a new package version is committed.

### 10.2 Token integration rules

- Map every token 1:1 to a CSS variable (`--color-primary`, `--color-state-ready`, …) and expose it to Tailwind through the preset (`colors.primary = "var(--color-primary)"`).
- No hex values in components; only tokens. A lint rule (`stylelint` or a simple grep in CI) fails the build on `#[0-9a-f]{3,6}` outside `tokens.css`.
- State colours (`ready, occupied, cleaning, maintenance, overdue`) are exposed as a `stateColor(status)` helper; nothing else may use them.

### 10.3 Component integration rules

- Root: `<html dir="rtl" lang="ar">`. Radix/shadcn components receive `dir="rtl"` through the provider.
- Only Tailwind logical utilities: `ms-*, me-*, ps-*, pe-*, start-*, end-*, text-start, text-end`. Fail CI on `\b(ml|mr|pl|pr|left|right)-` in `web/src`.
- If the design package ships React code, keep its markup and class names; replace hard-coded strings with `t("key")` from `ar.json`, wire data through props, and add missing states (loading, empty, error) using the package's own patterns.
- If the package ships HTML/CSS artboards only, port each artboard's markup into a React component one-to-one (same DOM structure, same class names mapped to Tailwind tokens); take spacing and type sizes from the tokens, not from eyeballing the PNG.
- Sample data baked into the artboards (rooms 101–411, guest names, amounts) is replaced by API data; it must also become the seed fixture (`server/apps/core/fixtures/demo.json`) so the running app looks exactly like the design during review.

### 10.4 Screen → route → API mapping

| Screen (design) | Route | Primary data hooks |
| --- | --- | --- |
| Login | `/login` | `POST auth/pin`, `GET followups/tasks?status=open&count` |
| Room board | `/` | `GET rooms?view=board` (poll 15 s), `POST rooms/:id/set-status` |
| Reservations | `/reservations` | `GET reservations?from&to`, `GET rooms` |
| New reservation | `/reservations/new` | `GET guests?q`, `GET reservations/availability`, `POST reservations/quote`, `POST reservations`, `POST stays/check-in` |
| Stay detail | `/stays/:id` | `GET stays/:id`, `POST stays/:id/{extend,change-room,checkout,add-line}`, `POST payments` |
| Follow-ups | `/followups` | `GET followups/tasks`, `POST followups/tasks/:id/actions` |
| Cash & shift | `/cash` | `GET shifts/current`, `POST shifts/{open,close}`, `GET shifts` |
| Expenses | `/expenses` | `GET/POST expenses`, `POST expenses/:id/reverse` |
| Guests | `/guests` | `GET guests`, `GET guests/:id`, `PATCH guests/:id` |
| Reports | `/reports/:name` | `GET reports/:name`, `GET reports/:name/export`, `/print/report/:name` |
| Settings | `/settings/*` | users, room-types, rooms, followups/rules (+preview), backup/settings, system/status, audit |
| Owner dashboard | `/owner` | `GET reports/owner-dashboard`, `GET system/status`, `GET owner/import/runs` |
| Backup card | shared component | `POST backup/run`, `POST backup/drive/sync`, owner import stepper |
| Print templates | `/print/*` | data from the corresponding `GET`, rendered print-only |

Shell selection: `GET system/status.role` decides `ReceptionShell` vs `OwnerShell` at app start. In `owner` role the API client also blocks mutations client-side and shows the amber banner with `system/status.data_as_of`.

### 10.5 Frontend data layer

- TanStack Query with `staleTime` 10 s; board and follow-ups refetch on interval (15 s / 30 s) and on window focus.
- All mutations invalidate the affected queries and surface `code` → Arabic message via `ar.json` (`errors.<code>`).
- Money: `formatMoney(minor, {digits, decimals})` and `parseMoney(text)`; never pass floats to the API.
- Dates: `date-fns` with `ar` locale for display; API values are ISO strings.
- Digit setting (Western vs Arabic-Indic) applied through one formatter used everywhere, including print templates.

### 10.6 Acceptance for the UI integration

- Every screen in the design package exists at its route with real API data and all designed states.
- No hard-coded colours, no physical-direction utilities, no Latin UI strings (CI greps).
- Room board and new reservation render correctly at 1366×768.
- Invoice A4 and receipt 80 mm print from the app with correct Arabic shaping and digits setting.
- Keyboard-only completion of login, new reservation, add payment, close shift.

---

## 11. Desktop shell (Tauri) and installer

- Tauri window loads `http://127.0.0.1:8471/`; if the service is not reachable, show a local fallback page "الخادم المحلي غير متاح" with a retry button and a "فتح سجل الأخطاء" link.
- Close button hides to tray; tray menu: فتح · نسخة احتياطية الآن · خروج. Autostart enabled at install.
- Tray polls `followups/toasts` every 30 s and shows native notifications; clicking opens the task.
- Rust commands: `open_folder(path)`, `print_to_pdf(url, path)` (path B only). Nothing else in Rust.
- Installer (NSIS via Tauri): role selection page (استقبال / مالك) → writes `config.json` (`role`, new `hotel_id` for reception; owner PC leaves `hotel_id` empty until first import) → installs service (`sc create SkyTowersServer … start= auto`), sets ACLs so only Administrators and the service account write to `%ProgramData%\SkyTowers` → adds a Defender exclusion for the program folder (documented) → starts the service → offers to launch. Uninstall never deletes `%ProgramData%\SkyTowers`.
- Updates: a newer installer run over an existing install stops the service, takes an automatic pre-upgrade backup, runs `migrate`, restarts. The build number and `schema_version` are shown in Settings → بيانات الفندق.

---

## 12. Build order and gates — backend first, then the ready UI

The build is **backend-first**. Phases B0–B4 produce a complete, tested Django backend with no custom frontend; the UI is designed in Claude Design in parallel and committed as a package. Frontend work (F1–F3) starts only when both the backend API is frozen and the design package is approved. Windows-specific work (W) runs alongside on a Windows machine because it cannot be done in a Linux cloud session.

### Track B — backend (Claude Code cloud sessions, Linux)

| Phase | Deliverable | Gate |
| --- | --- | --- |
| B0 Foundation (1 wk) | Repo layout, pinned deps, `CLAUDE.md`, BaseModel/Money/ClockGuard, SQLite settings, OpenAPI generation, pytest + CI, seed command with the design brief's sample data | `pytest` green in CI; `GET /api/v1/schema` served; seed loads |
| B1 Rooms & stays (3 wk) | accounts (PIN/password/confirm token), rooms + state machine + history, guests + documents, reservations (quote, availability, overlap), stays (check-in, extend, change room, checkout, cancel), audit chain | Overlap blocked under concurrent requests; date rules exact in Khartoum time; 100 % of `rules.py` covered |
| B2 Money (3 wk) | rate plans + mixed durations, folios, lines, reversals, discounts, payments, shifts, expenses, invoice/report **data** endpoints, Excel/CSV exports | Balances equal across all endpoints; shift close reconciles; no floats anywhere; exports open in Arabic Excel |
| B3 Follow-ups & guard (2 wk) | alert rules + defaults, engine (idempotent, catch-up, supersede), tasks, actions, snooze limit, escalation, toasts endpoint, clock guard, rule preview | Engine tests with a frozen clock: fire, restart, extend, snooze, neglect; guard blocks on rollback |
| B4 Backup, Drive, merge (3 wk) | VACUUM INTO + manifest + age encryption, retention, scheduled runs, Drive upload/download, owner middleware, merge import with `incoming` alias + migrate, Hypothesis property test | Three sequential imports reproduce reception totals; repeat import is a no-op; corrupt/foreign file rejected with no side effects; owner role refuses every mutation |
| **API freeze** | OpenAPI schema tagged `v1.0-api`; generated TS client committed; Postman/Bruno collection | Design package screen→API mapping (§10.4) verified against the schema: every screen's data exists |

During Track B the only UI is the DRF browsable API, Swagger UI and Django admin (read-only, staff only) for verification. No custom React code is written before the API freeze.

### Track D — design (Claude Design, parallel with B1–B3)

Produce the design package per the UI Design Brief §10 (design system → room board → the rest, with states and sample data). Commit each approved version under `design-package/` with a version tag. Gate: every screen in Brief §6 approved, RTL self-check passed, PNGs exported.

### Track W — Windows runtime (user's Windows PC or a `windows-latest` CI runner, parallel from B1)

| Item | Gate |
| --- | --- |
| PyInstaller `--onedir` bundle of the Django service + pywin32 service wrapper | Service starts before login on a clean Windows VM offline |
| Tauri shell: tray, autostart, notifications, fallback page | Toast appears with window closed |
| Print spike: A4 and 80 mm Arabic from WebView2 (path A; try path B) | Correct shaping and digits on Windows 10 and 11 |
| NSIS installer with role selection, ACLs, WebView2 offline installer, Defender exclusion | Installer runs offline; uninstall keeps data |
| Power-cut test on the real service | DB consistent after cut mid-write |

### Track F — frontend from the ready UI (after API freeze and design approval)

| Phase | Deliverable | Gate |
| --- | --- | --- |
| F1 Foundation (1 wk) | Vite app, `dir="rtl"`, tokens → CSS variables → Tailwind preset, fonts, `ar.json` from the package, generated API client, shells (reception/owner) from the package, CI greps (hex, physical direction, Latin strings) | Shell matches artboard PNG; greps pass |
| F2 Screens (4 wk) | Screens in the Brief's order (room board → new reservation → stay → follow-ups → cash → backup card → owner dashboard → rest), each ported from its artboard and wired to the real API with all designed states; print templates | Each screen accepted only after side-by-side comparison with its PNG using the seed data; 1366×768 variants correct |
| F3 Desktop integration (1 wk) | SPA served by Django inside the Tauri shell; toasts open the task; print paths wired; owner banner from `system/status` | Full flows keyboard-only; installer from Track W carries the real SPA |

### Acceptance (2 wk)

Seed month of data, two-week parallel run beside the current ledger, training, Arabic guide, v1.0 installed on both PCs. Gate: owner performs create-user / import / print-report unaided; parallel run shows zero balance differences.

Indicative calendar for one developer: B0–B4 ≈ 12 weeks with Track D and W in parallel; F1–F3 ≈ 6 weeks; acceptance 2 weeks; total ≈ 20 weeks. Estimates, not contractual.

---

## 14. Working in Claude Code cloud sessions

Constraints and rules for building this repo with cloud sessions.

- **The repo is the only memory.** `CLAUDE.md` at the root holds: the rules in §2 and §6, the money/date conventions, the "no business logic in the SPA" rule, the CI grep rules, and a pointer to `docs/decisions.md`. Every session starts by reading it. Decisions taken in a session are appended to `docs/decisions.md` in the same PR.
- **One phase item per session, one PR per session.** A session receives: the phase row from §12, the relevant sections of this document, and the acceptance gate. It ends with tests green and a PR description listing what the gate needed and how it was verified.
- **Tests are the gate, not the chat.** No phase item is done until `pytest` (backend) or `vitest` + CI greps (frontend) pass in CI. Property tests (merge) and frozen-clock tests (engine) are mandatory, not optional.
- **Linux cloud cannot do Track W.** Windows service, PyInstaller Windows bundle, Tauri NSIS installer, WebView2 printing and the power-cut test need Windows. Use a GitHub Actions `windows-latest` workflow (`build/windows-release.yml`) triggered from the cloud session to produce the installer, then test it on the user's Windows PC. Cloud sessions may still write and lint the Rust and NSIS code.
- **Drive credentials never enter the repo or a session prompt.** `client_secret.json` is provided at install time on the Windows PC; cloud sessions test the Drive module against a mock.
- **Design package is read-only input.** Sessions copy from `design-package/` into `web/src`; they never modify the package. A needed design change is written to `docs/design-gaps.md` and taken back to Claude Design.
- **Frontend sessions start with the artboard.** Each F2 session receives the screen's PNG, its HTML/React export, its row in §10.4 and the seed data; it ends with a screenshot of the running screen committed next to the PNG under `docs/screens/` for review.
- **API freeze is enforced.** After the `v1.0-api` tag, any schema change requires a new tag, a regenerated client and a note in `docs/decisions.md`; frontend sessions pin the client to the tag.

---

## 13. Definition of done for v1.0

- Installs and runs on two clean Windows 10/11 PCs with no internet, no manual Python or WebView2 install.
- Service starts before login; shell minimises to tray; notifications appear with the window closed.
- Power loss during a write leaves the DB consistent (operation fully present or absent).
- Overlaps blocked; 7/30-night rules and end-of-day semantics exact in Khartoum time.
- Room stays occupied after end date until checkout, then cleaning, then ready.
- Balances identical in stay screen, printed invoice and debt report; shift close reconciles; reversals only.
- Alert tasks persist across restarts, close only by action, snooze limited, neglected tasks attributed to the shift.
- The three buttons work with clear Arabic results; Drive offline fails gracefully.
- Owner import is additive, idempotent, rejects corrupt/foreign files, verifies the audit chain, and the owner PC refuses all hotel writes at the API level.
- Arabic text, tables and digits correct in UI, PDF, Excel and CSV; all CI greps (colours, direction, Latin strings) pass.
