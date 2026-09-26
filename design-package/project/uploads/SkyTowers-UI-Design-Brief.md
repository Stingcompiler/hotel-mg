# Sky Towers Hotel Management System — UI Design Brief

**Audience of this document:** an AI design model (or a designer) producing the complete visual design of the application.
**Product language:** Arabic only, right-to-left (RTL). This brief is in English; every screen must be designed with real Arabic text, not placeholder Latin text.
**Platform:** Windows 10/11 desktop application (Tauri + React). Not mobile, not responsive web. Minimum window 1366×768, design target 1920×1080.

---

## 1. Product summary

Sky Towers is a small-to-medium hotel (15–60 rooms) in Khartoum, Sudan. The system runs fully offline on two Windows PCs:

- **Reception PC** — all daily operations: rooms, reservations, check-in/out, invoices, payments, expenses, cash shifts, alerts.
- **Owner PC** — read-only monitoring of an imported copy of the data, plus backup import. No hotel transactions are entered here.

Data flows one way (Reception → Owner) through encrypted backup files carried on a USB stick or synced via a Google Drive button. The owner primarily wants **accountability**: every alert, action and payment recorded with who did it and when.

### Users

| User | Context | Design implication |
| --- | --- | --- |
| Receptionist | Works 8–14 hour shifts at a desk, moderate computer skills, interrupted constantly by guests | Fast, dense, forgiving; large primary actions; state readable at a glance from across the desk |
| Manager | Same PC, configures prices, users, alert rules, backups | Settings screens can be denser and more text-heavy |
| Owner | Non-technical, checks his own PC every day or two | Big numbers, clear "data as of" date, zero jargon, nothing that looks editable |

### Stay model (drives many screens)

- Stays are **daily**, **weekly** (7 nights) or **monthly** (30 nights).
- A stay ends at the **end of its last recorded day**. A 30-night stay starting on the 1st ends at the end of the 30th.
- A room stays **occupied** after the end date until staff record checkout; it is then marked **overdue**.
- After checkout the room goes to **needs cleaning**, then a staff member confirms **ready**.
- **Maintenance** blocks a room from being assigned.
- Future reservations are shown on a calendar, separate from the room's current operational state. A room can be ready today and reserved tomorrow.

---

## 2. Design principles

1. **Colour has exactly one job: room/stay state.** Green, blue, amber, grey, red mean ready, occupied, cleaning, maintenance, overdue — everywhere, always. Never reuse these hues decoratively.
2. **Light theme only.** The reception desk is often brightly lit and the screen may be viewed at an angle by a guest. No dark mode in v1.
3. **Dense but calm.** Table rows 40 px, card padding 16 px, generous whitespace only around primary actions and headline numbers.
4. **Numbers are the content.** Tabular (monospaced-digit) figures in every table and money field. Money is the largest text on any stay screen.
5. **Nothing closes by being seen.** Alerts and banners disappear only through an explicit action; the design must never imply that dismissing equals resolving.
6. **Owner mode looks different at a glance.** A persistent amber banner and no write affordances, so a screenshot can never be mistaken for the live reception screen.

---

## 3. Visual system

### 3.1 Colour tokens

Use these exact values. Provide them as CSS variables / Tailwind theme tokens in deliverables.

**Neutrals**

| Token | Hex | Use |
| --- | --- | --- |
| `bg-page` | `#F6F7F9` | Application background |
| `bg-surface` | `#FFFFFF` | Cards, tables, panels, drawers |
| `bg-surface-2` | `#F1F3F6` | Table header rows, zebra striping, disabled fields |
| `border` | `#E3E6EB` | All borders and dividers |
| `border-strong` | `#C9CED6` | Focused table cells, input borders |
| `text-primary` | `#1B2430` | Body text, numbers |
| `text-secondary` | `#5B6674` | Labels, captions, helper text |
| `text-disabled` | `#9AA3AF` | Disabled controls |

**Brand / primary**

| Token | Hex | Use |
| --- | --- | --- |
| `primary` | `#0F766E` | Primary buttons, links, active nav item, focused input ring |
| `primary-hover` | `#115E59` | Hover/pressed state |
| `primary-soft` | `#CCFBF1` | Selected row, active tab background, soft badges |
| `primary-text-on` | `#FFFFFF` | Text on primary |

**Room / stay state (semantic, never decorative)**

| State | Arabic label | Solid | Soft background | Text on soft |
| --- | --- | --- | --- | --- |
| Ready | جاهزة | `#16A34A` | `#DCFCE7` | `#14532D` |
| Occupied | مشغولة | `#2563EB` | `#DBEAFE` | `#1E3A8A` |
| Needs cleaning | تحتاج تنظيف | `#D97706` | `#FEF3C7` | `#78350F` |
| Maintenance | صيانة | `#6B7280` | `#E5E7EB` | `#1F2937` |
| Overdue | متجاوزة | `#DC2626` | `#FEE2E2` | `#7F1D1D` |
| Reserved soon (outline only) | محجوزة قريبًا | `#7C3AED` | — | — |

**Feedback**

| Token | Hex |
| --- | --- |
| `success` | `#16A34A` |
| `warning` | `#D97706` |
| `danger` | `#DC2626` |
| `info` | `#2563EB` |

**Owner mode**

| Token | Hex | Use |
| --- | --- | --- |
| `owner-banner-bg` | `#FFEDD5` | Full-width persistent banner |
| `owner-banner-text` | `#B45309` | Banner text and icon |

Contrast: all text/background pairs above meet WCAG AA (≥ 4.5:1 for body text). Do not lighten them.

### 3.2 Typography

- **Typeface:** IBM Plex Sans Arabic (bundled with the app; no web fonts at runtime). Fallback for design tools: Noto Sans Arabic.
- **Digits:** Western digits (0-9) by default; the owner may switch the whole app to Arabic-Indic digits (٠-٩). Design both variants for money and dates once, on the stay screen and the invoice.
- **Numbers always use tabular figures** (`font-variant-numeric: tabular-nums`).

| Role | Size / weight | Line height |
| --- | --- | --- |
| Page title | 20 px / 600 | 28 px |
| Section title | 16 px / 600 | 24 px |
| Body | 14 px / 400 | 22 px |
| Table cell | 14 px / 400 | 20 px |
| Label / caption | 12 px / 500 | 16 px |
| Headline number (balance, KPI) | 28 px / 700 | 34 px |
| Room number on card | 22 px / 700 | 28 px |

### 3.3 Spacing, radius, elevation

- 4 px base grid. Common steps: 4, 8, 12, 16, 24, 32.
- Radius: 6 px controls, 8 px cards, 12 px modals/drawers.
- Elevation: cards use a 1 px `border` and no shadow. Drawers and modals use `0 8px 24px rgba(27,36,48,0.12)`.
- Focus ring: 2 px `primary` outside the control, 2 px offset. Keyboard use is common at reception; focus must be visible on every control.

### 3.4 Iconography

Lucide icon set, 20 px in controls, 16 px inline in text, 1.75 px stroke. Icons never replace text on primary actions; button labels are always Arabic text, optionally with a leading icon (icon appears on the right in RTL).

### 3.5 RTL rules

- Entire layout mirrored: navigation sidebar on the **right**, drawers slide in from the **left**, back-arrows point right, progress flows right-to-left.
- Tables: first column on the right. Numeric columns right-aligned within the cell; Latin identifiers (invoice numbers, reference codes) keep left-to-right glyph order but sit in RTL layout.
- Timeline (reservation calendar): days advance **leftwards** (today on the right edge). This is deliberate: confirm with the user in a note on the frame.
- Phone numbers and dates rendered as isolated LTR runs (`dir="ltr"` inline) so digit order never flips.
- Use logical properties in code deliverables (`margin-inline-start`, `padding-inline-end`, etc.), never `left/right`.

---

## 4. Application shell

Fixed shell shared by all reception screens.

- **Right sidebar** — 240 px, collapsible to 64 px icon rail. Items (top to bottom): لوحة الغرف · الحجوزات · النزلاء · المتابعة (red count badge) · الصندوق · المصروفات · التقارير · الإعدادات. Hotel name "Sky Towers" and logo placeholder at the top; current user name and role, plus "تسجيل الخروج" at the bottom.
- **Top bar** — 56 px. From right to left: global search input (placeholder: "ابحث برقم الغرفة أو الاسم أو الهاتف"), shift chip ("وردية مفتوحة · أحمد · منذ 08:00" green, or "لا توجد وردية مفتوحة" grey), alert bell with count, last-backup chip ("آخر نسخة: اليوم 14:00" green, or "لم تُنشأ نسخة منذ 26 ساعة" red), user avatar menu.
- **Overdue banner** — appears under the top bar only when overdue stays exist: `overdue-soft` background, red text "3 إقامات انتهت دون إجراء — عرض", cannot be dismissed.
- **Content area** — 24 px padding, page title on the right, primary page action on the left of the same row.
- **Side drawer** — 480 px, slides in from the left, used for quick details and actions without leaving the page.

### Owner shell differences

- Top bar is replaced by a full-width amber banner: "بيانات حتى 25 سبتمبر 2026 – 22:10 · للعرض فقط". No shift chip, no alert bell, no search of write actions.
- Sidebar items: لوحة المالك · التقارير · النزلاء · النسخ والاستيراد · الإعدادات (limited).
- No primary (teal) buttons anywhere except in the backup/import card and settings. Export buttons are secondary style.

---

## 5. Component inventory

Design each with all states (default, hover, focus, disabled, error, loading where relevant).

- Buttons: primary, secondary (outline), ghost, danger. Sizes 36 px and 44 px (44 px for check-in/checkout/payment actions).
- Inputs: text, number (money — shows currency suffix "ج.س"), date picker (Arabic month names, Gregorian calendar), time, select, combobox with search (guest lookup), textarea, PIN pad (large 3×4 numeric keypad for login).
- Chips/badges: state chip (uses the state palette), count badge, status chip for reservation status.
- Room card (see 6.1).
- Data table: sortable headers, sticky header, zebra rows, row hover, selected row (`primary-soft`), inline action buttons on hover, empty state, pagination footer with row count.
- KPI tile: label (12 px), value (28 px), optional delta line.
- Timeline bar (reservation calendar).
- Drawer, modal, confirmation dialog (danger variant), toast (bottom-left in RTL), inline alert banner.
- Alert task row (see 6.5).
- Print templates (see 7).
- Empty / error / "server unavailable" states.

---

## 6. Screens

For each screen, deliver the full frame at 1920×1080 and, where marked, a 1366×768 variant. Use realistic Arabic sample data: room numbers 101–420, guest names such as "محمد عثمان الطيب", phone "+249 91 234 5678", amounts in the tens of thousands of SDG (e.g. 45,000 ج.س).

### 6.1 Login (both roles)

Centered card 420 px wide on `bg-page`. Hotel name at top. User picker (avatars/names as large tiles), then a PIN pad with 4–6 dot indicators. Below the pad: a subtle link "الدخول بكلمة المرور". Above the card, when tasks are due: a red chip "5 مهام متابعة مستحقة" so the incoming shift sees the backlog before logging in.

### 6.2 Room board — الصفحة الرئيسية (Reception) — 1920 and 1366 variants

1. **KPI strip** (4 tiles): مشغولة 18/30 · وصول اليوم 3 · مغادرات اليوم 4 · متجاوزة 2. Clicking a tile filters the grid.
2. **Filter row**: segmented control الكل / جاهزة / مشغولة / تنظيف / صيانة, floor dropdown, view toggle (grid/list).
3. **Room grid**: cards 220×132 px, 8-per-row at 1920. Card anatomy:
   - 4 px right-edge stripe in the state colour; state chip top-left.
   - Room number 22 px bold top-right; room type below in `text-secondary`.
   - Occupied: guest name (truncate 1 line), then "تنتهي بعد 3 أيام" or red "متجاوزة منذ يومين".
   - Ready: "متاحة" and, if reserved within 48 h, a purple outline plus "محجوزة غدًا".
   - Cleaning: "منذ 1 س 20 د"; Maintenance: reason, "منذ 3 أيام".
4. **Click → drawer**: header (room number, type, state chip), body varies by state: quick actions as 44 px buttons — تسكين مباشر / فتح الإقامة / تم التنظيف / إدخال في الصيانة / إعادة للخدمة — followed by the room's status history list.

### 6.3 Reservations — الحجوزات

- Toolbar: primary "حجز جديد", date jump, "اليوم", segmented "خط زمني / قائمة".
- **Timeline**: rows = rooms grouped by floor (sticky right column with room number and type), columns = days (14 visible, 96 px each, today column tinted `primary-soft`, weekends slightly darker header). Bars: `confirmed` outline blue, `checked_in` solid blue, `overdue` solid red, `cancelled` not shown, `checked_out` grey at 40 % opacity. Bar label: guest name; bars snap to day cells; drag is not required in v1.
- Empty cell click → opens "New reservation" pre-filled with room and date.
- **List view**: table with columns الغرفة · النزيل · الوصول · النهاية · النوع · الحالة · المتبقي · إجراءات.

### 6.4 New reservation / check-in — حجز جديد

Full-page form, single scroll, three numbered sections, with a **sticky summary bar** (72 px) at the bottom.

1. **النزيل** — combobox search by phone/name; "نزيل جديد" expands fields: الاسم الكامل, الهاتف, الجنسية, نوع الهوية (select), رقم الهوية, صورة الهوية (optional upload tile, max 300 KB note), المرافقون (repeatable row: name, relation).
2. **الإقامة** — نوع الغرفة → shows only rooms free for the whole period as selectable chips; تاريخ الوصول (date); نوع المدة segmented يومي / أسبوعي / شهري; العدد (number); computed line in 16 px semibold: "تنتهي بنهاية يوم الخميس 30 أكتوبر 2026 (30 ليلة)". If the count produces a mixed duration, show a radio pair: "أسبوع + 3 ليالٍ" / "10 ليالٍ بسعر الليلة", each with its computed total.
3. **المال** — السعر (from rate plan, read-only with an "تعديل" link requiring a reason), الخصم (amount + mandatory reason), العربون (amount), طريقة الدفع (نقدي / بنكك / تحويل), المرجع (shown for non-cash).

Sticky summary: الإجمالي · المدفوع · المتبقي (28 px), and two 44 px buttons: primary "تسكين الآن", secondary "حفظ كحجز".

### 6.5 Stay detail — تفاصيل الإقامة

- **Header card**: room number + type, guest name and phone, period "1 – 30 أكتوبر · 30 ليلة · شهري", state chip, and on the far left the balance as a 28 px number: green when 0, red when owed ("المتبقي 15,000 ج.س").
- **Action bar** (44 px buttons): تمديد · تغيير الغرفة · إضافة دفعة · تسجيل خروج · إلغاء (danger, ghost).
- **Tabs**: الفاتورة (ledger table: التاريخ · البيان · مدين · دائن · الرصيد · بواسطة; reversal lines shown with a ↩ icon and linked to their original), الدفعات, المرافقون, الملاحظات, السجل (audit trail: time, user, action).
- **Checkout modal**: if balance ≠ 0, a red notice "لا يمكن تسجيل الخروج بدين" with a manager-override section (password field + reason) collapsed by default.
- **Extend modal**: duration type + count, shows old end → new end, price delta, and a line "سيُعاد حساب التنبيهات".

### 6.6 Follow-ups — المتابعة (the owner's top priority)

- Header with counts: متأخرة (red) · اليوم (amber) · القادمة (grey). Filter by rule and stay type.
- Three grouped lists, each row 64 px: right side — room number chip, guest name, stay type chip; middle — "تنتهي بعد يومين (الخميس 30 أكتوبر)" and the rule name in `text-secondary` ("قاعدة: شهري – قبل 5 أيام"); left side — four inline buttons: تمديد · تأكيد المغادرة · بانتظار الرد · تأجيل. Snooze shows remaining snoozes ("تأجيل (1 من 3)") and is disabled when exhausted.
- Row states: overdue rows have `overdue-soft` background; "waiting" rows show the follow-up time and note; "neglected" rows (escalated with no action) show a red label "مُهمَلة — وردية: أحمد".
- **Windows toast** design (native notification content): title "غرفة 305 — تنتهي بعد يومين", body "محمد عثمان · شهري · انقر للفتح". Provide as a small spec, not a frame.

### 6.7 Cash & shift — الصندوق

- **Current shift card** (two columns): right — الرصيد الافتتاحي, المقبوضات (broken down: نقدي / بنكك / تحويل), المصروفات النقدية, النقدي المتوقع (bold); left — input المعدود, computed الفرق (green if 0, red otherwise), textarea سبب الفرق (required when ≠ 0), primary "إغلاق الوردية". When no shift is open the card collapses to an opening-balance input and "فتح وردية".
- **Movements table** below: الوقت · النوع · البيان · المبلغ · الطريقة · بواسطة.
- Tab "سجل الورديات": table of closed shifts with الفرق column colour-coded.

### 6.8 Expenses — المصروفات

Single-row quick-add form at the top (المبلغ · الفئة select · البيان · الطريقة · "حفظ"), then a filterable table. Reversal via a "تصحيح" action that adds a red reversal row; no edit/delete.

### 6.9 Guests — النزلاء

Search table (الاسم · الهاتف · الجنسية · آخر إقامة · إجمالي الإقامات · دين). Row click → drawer: profile, "ملاحظة تحذيرية" field displayed in a `warning` banner when non-empty, stay history list, ID document thumbnail (blurred by default with "عرض" requiring the manager role).

### 6.10 Reports — التقارير

Right column list of report types (حالة الغرف وفترات الخلو · الإشغال · النزلاء الحاليون · الوصول والمغادرة · الإقامات القريبة من الانتهاء والمتجاوزة · الإيرادات والتحصيل · الديون · المصروفات · حركة الصندوق والورديات · التعديلات والخصومات والإلغاءات · الاستجابة للتنبيهات). Top filter bar (الفترة with presets اليوم/هذا الأسبوع/هذا الشهر, الغرفة, نوع الإقامة, طريقة الدفع). Preview area = table; export buttons PDF · Excel · CSV (secondary). An info line under the table states the occupancy formula.

### 6.11 Settings — الإعدادات (manager)

Left-of-content vertical tab list (rendered on the right in RTL): المستخدمون · أنواع الغرف والأسعار · الغرف · قواعد التنبيه · النسخ الاحتياطي · بيانات الفندق · سجل التدقيق.

- **Users**: table + "مستخدم جديد" (name, username, role, PIN, password). Owner/manager can create receptionists here. Sensitive actions open a password re-entry modal (design once, reuse).
- **Room types & prices**: table with three price columns; editing shows the note "لن يتغير سعر الحجوزات السابقة".
- **Alert rules**: table (الاسم · النوع · قبل النهاية بـ · الساعة · التكرار · الحد الأقصى للتأجيل · مفعّلة toggle) + rule editor drawer + a "معاينة: ما سيُنبَّه غدًا" panel listing the stays that would trigger.
- **Backup**: the three-button card (see 6.13), schedule (every N hours), retention, second destination folder, run history table with green/red status.

### 6.12 Owner dashboard — لوحة المالك (Owner PC)

Under the amber banner:

1. KPI strip: الإشغال اليوم · إيراد الشهر · المحصّل · الديون المستحقة · تنبيهات مُهمَلة (red if > 0).
2. Two charts side by side: occupancy % over the last 30 days (line), revenue vs collected per week (grouped bars). Chart colours: `primary` and `#94A3B8`; no state colours in charts.
3. "يحتاج انتباهك" list: overdue stays, debts above threshold, neglected alerts, shift discrepancies, rooms in maintenance > 7 days — each row links to its report.
4. "الاستجابة للتنبيهات" summary table per staff member: عدد التنبيهات · تُصرِّف فيها · مُهمَلة · متوسط التأخير.
5. Owner-device alerts as inline banners: "لم تُستورد نسخة جديدة منذ 3 أيام", "توجد نسخة أحدث على Drive".

### 6.13 Backup / Drive / Import card (both roles; import only on Owner PC)

Three equal 44 px buttons in a card:

- "نسخة احتياطية الآن" — result line under the card: "تمت · 14:02 · 12.4 MB · محفوظة في D:\SkyTowersBackups".
- "مزامنة مع Drive" — spinner while running; result "رُفعت 2 نسخ" / "نُزّلت نسخة جديدة (رقم 118)" / error "لا يوجد اتصال بالإنترنت" in `danger`.
- "استيراد نسخة" (owner PC only, manager role) — opens a stepper modal: 1 اختيار الملف (from Drive list or local file) → 2 التحقق (checks shown as a list with ticks: التوقيع، سلامة القاعدة، معرف الفندق، الإصدار، سلسلة التدقيق) → 3 الدمج (progress) → 4 النتيجة (table: الجدول · أُضيف · حُدِّث · تُجاهل). Warning variant when the file is older than the current data.

### 6.14 System states (design once)

- **Server unavailable** (reception): full-width red banner "الخادم المحلي غير متاح — العمليات معطلة مؤقتًا" with a retry button; all write buttons disabled.
- **Clock guard**: blocking modal "تم اكتشاف رجوع في ساعة الجهاز. الكتابة موقوفة حتى موافقة المدير" with password field.
- **Empty states** for every table (icon + one Arabic sentence + primary action).
- **Loading skeletons** for room grid and tables.

---

## 7. Print templates

Designed as HTML pages (they are printed through the app's embedded browser). Deliver as separate frames.

- **Invoice A4** (210×297 mm, 15 mm margins): hotel name and address header, invoice number (LTR), date, guest and room block, line-item table (البيان · الكمية · السعر · الإجمالي), totals block (الإجمالي · الخصم · المدفوع · المتبقي), payment list, footer with cashier name and signature line. Black on white, `border` lines only, no colour fills except a light grey header row.
- **Receipt 80 mm thermal** (width 72 mm printable): single column, 12 px equivalent text, hotel name centred, invoice number, room, period, totals, payment method, timestamp, user. No borders; dashed separators.
- **Report A4 landscape**: title, filter summary line, "بيانات حتى" date, table, formula note, page numbers (RTL: page number on the left).

---

## 8. Accessibility and ergonomics

- Body text contrast ≥ 4.5:1; state chips use the soft/text pairs above.
- Minimum click target 36×36 px; primary flows 44 px.
- Complete keyboard path for: login, new reservation, add payment, close shift. Tab order follows RTL reading order.
- No information conveyed by colour alone: every state chip carries its Arabic label.
- Animations ≤ 150 ms; no motion required to understand state.

---

## 9. Deliverables required

1. **Design tokens** as a JSON file (colours, typography, spacing, radius, shadows) using the token names in section 3.
2. **Component library** frames with all states (section 5).
3. **Screen frames** for every screen in section 6 at 1920×1080; 6.2 and 6.4 also at 1366×768.
4. **Print template frames** (section 7).
5. If code is produced: React + TypeScript + Tailwind components, `dir="rtl"` on the root, Tailwind logical utilities only (`ms-`, `me-`, `ps-`, `pe-`, `start-`, `end-`), no hard-coded `left/right`, no external font or icon CDN, IBM Plex Sans Arabic loaded from a local `/fonts` folder, Lucide icons via the `lucide-react` package.
6. A one-page **RTL notes** document listing every place where mirroring was deliberate (timeline direction, drawer side, table alignment).

### Do

- Use real Arabic strings from this brief; keep them as the canonical UI copy.
- Keep the state palette exclusive to room/stay state.
- Show money as `45,000 ج.س` (space before the currency, thousands separator) unless the digit setting is Arabic-Indic.

### Don't

- No dark theme, no gradients, no illustrations, no marketing hero sections.
- No icon-only primary buttons.
- No hover-only affordances for actions the receptionist must find quickly.
- No English text anywhere in the UI, including placeholders and error messages, except identifiers (invoice numbers, reference codes) and the hotel name "Sky Towers".

---

## 10. Working process (how this brief will be used)

Follow this order. Do not skip to screens.

### 10.1 Design system first

Before any screen, produce a **design system** from section 3: colour tokens with the exact hex values, the type scale, spacing, radius, elevation, focus ring, iconography rules, and the five room-state chips. Every screen is then built against this system. A colour or size that is not in the system must not appear in a screen; if one is needed, add it to the system first and say so.

### 10.2 One screen per iteration, hardest first

Order of screens: **6.2 Room board → 6.4 New reservation → 6.5 Stay detail → 6.6 Follow-ups → 6.7 Cash → 6.13 Backup card → 6.12 Owner dashboard → the rest**. Each screen is reviewed and approved before the next starts. The room board comes first because it settles the decisions everything else inherits: RTL shell, state colours, density, sidebar, top bar.

### 10.3 Always use the sample data below

Screens must be populated with this data (or more of the same kind), never with generic placeholders. It deliberately covers every state.

| Room | Type | State | Guest | Stay | Shown text | Balance |
| --- | --- | --- | --- | --- | --- | --- |
| 101 | مفردة | جاهزة | — | — | متاحة | — |
| 102 | مفردة | جاهزة (محجوزة غدًا) | — | حجز: خالد إبراهيم، غدًا، أسبوعي | محجوزة غدًا | — |
| 203 | مزدوجة | مشغولة | محمد عثمان الطيب | شهري، 1–30 أكتوبر | تنتهي بعد 3 أيام | المتبقي 15,000 ج.س |
| 204 | مزدوجة | مشغولة | فاطمة أحمد النور | يومي، ليلتان | تنتهي اليوم | 0 ج.س |
| 305 | جناح | متجاوزة | عبدالله حسن موسى | أسبوعي، انتهت 24 سبتمبر | متجاوزة منذ يومين | المتبقي 42,000 ج.س |
| 306 | جناح | تحتاج تنظيف | — | — | منذ 1 س 20 د | — |
| 410 | مزدوجة | صيانة | — | — | تسرب مياه · منذ 3 أيام | — |
| 411 | مزدوجة | مشغولة | سارة عمر الشيخ | شهري، 15 سبتمبر – 14 أكتوبر | تنتهي بعد 18 يومًا | 0 ج.س |

Other fixed sample values: phone `+249 91 234 5678`; user "أحمد علي" (reception), "المدير" (manager); shift opened 08:00 with opening balance 50,000 ج.س; invoice number `INV-000318`; data-as-of banner "بيانات حتى 25 سبتمبر 2026 – 22:10".

### 10.4 Every screen ships with its states

A screen is not complete until it includes: default with the data above, empty, loading skeleton, error, "server unavailable" banner, owner-mode variant where the screen exists on the owner PC, and the 1366×768 variant where section 6 asks for it. Deliver them as separate frames next to the main one.

### 10.5 Review is rule-based

Feedback will quote this brief, e.g. "green is used on a save button; green is reserved for the ready state (§2.1) — use `primary`". Apply the quoted rule across the whole system, not only at the spot named.

### 10.6 RTL self-check before handing a screen over

Confirm each item and list any deliberate exception in the RTL notes:

- Sidebar is on the right; drawers open from the left.
- Leading icons sit to the right of button labels.
- Tables start at the right column; numeric cells right-aligned.
- Phone numbers, dates and codes read correctly (isolated LTR runs, no flipped digits).
- The reservation timeline advances to the left, today on the right edge.
- Arabic is rendered in IBM Plex Sans Arabic (or Noto Sans Arabic in the design tool), not a fallback system font.
- No English placeholders or labels remain.

### 10.7 Hand-over

When all screens are approved, export in one package: `tokens.json`, the design-system frames, all screen frames with states, the print templates, the RTL notes, and code if produced (under the rules in section 9). This package, together with this brief, is what the implementation team receives.
