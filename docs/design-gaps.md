# Design gaps

Items missing or inconsistent in `design-package/` that need an answer from Claude Design (or the owner). Implementation uses the noted fallback until resolved.

| # | Where | Gap | Fallback used |
| --- | --- | --- | --- |
| 1 | Settings → Room types & prices (Gap Fill) | Room type capacity is not shown; the data model has `RoomType.capacity`. | Assumed 1 / 2 / 3 (single / double / suite), editable in settings. |
| 2 | Brief §10.3 vs Stay Detail / V2 cancel modal | Room 203's monthly stay is "1–30 October, ends in 3 days" in the brief, but the V2 cancel modal says "started 1 October, 12 nights passed", and the V2 reports are dated 26 September 2026. The artboards disagree on "today". | Seed dates are relative to the day it runs, reproducing the Room Board (203 ends in 3 days, 305 overdue 2 days, 411 ends in 18 days). Tests freeze today at 2026-09-26. |
| 3 | Room Board vs Settings → Room types | The board shows 107 and 108 as doubles; Settings says singles are 101–108 (8 rooms). | Settings wins (room types are configuration): 101–108 single. |
| 4 | Room Board vs V2 Settings → Rooms | Room 412 is occupied on the board but "out of service" in V2 settings, which the same artboard says is impossible for an occupied room. | Board wins: 412 in service. |
| 5 | Room Board KPIs | «وصول اليوم 3 / مغادرات اليوم 4» are fixed numbers that do not match the board's rooms (2 rooms show «تنتهي اليوم», no arrivals are drawn). | Computed from data. Board summary: departures = stays whose last night is today (2 in the seed); the arrivals/departures report also lists overdue stays and shows 4, as on the artboard. |
| 6 | Room Board — stay kinds | Only 203, 204, 305, 411 have a duration kind in the brief. | Seed picks kinds that fit each shown end date (see `STAYS` in `apps/core/seed/demo_data.py`). |
| 7 | Backup card (6.13) | The run log shows files named `ST-2026-09-26-1402.stbk`; spec §9.1 names them `skytowers-<hotel8>-<seq>-<YYYYMMDD-HHMM>.age`. | Spec naming (hotel and sequence in the name let the owner PC list candidates without decrypting). The file picker should filter `.age`. |
| 8 | tokens.json vs artboards | Only the solid feedback colours (success/warning/danger/info) are tokens, but the artboards also use soft backgrounds and text-on-soft for chips and banners (shift chip, backup chip, system bars). | The values equal the room-state shades (RTL notes exception 2), so the generator derives `--color-{success,warning,danger,info}-{soft,text}` from ready / cleaning / overdue / occupied. |
