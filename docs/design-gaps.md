# Design gaps

Items missing or inconsistent in `design-package/` that need an answer from Claude Design (or the owner). Implementation uses the noted fallback until resolved.

| # | Where | Gap | Fallback used |
| --- | --- | --- | --- |
| 1 | Settings → Room types & prices (Gap Fill) | Room type capacity is not shown; the data model has `RoomType.capacity`. | Seed data leaves capacity unset; to be confirmed before B1 seeds rooms. |
| 2 | Brief §10.3 vs Stay Detail / V2 cancel modal | Room 203's monthly stay is "1–30 October, ends in 3 days" in the brief, but the V2 cancel modal says "started 1 October, 12 nights passed", and the V2 reports are dated 26 September 2026. The artboards disagree on "today". | Seed uses `DEMO_TODAY = 2026-09-26`; stay dates are fixed when the B1 stays loader is written. |
