# ADR-0008 — The re-buy warning reads the calendar, never the results

**Status:** Accepted, 2026-08-22 (first recorded in `CLAUDE.md`, commit 425049b; LOTTO-0034).
**Enforced by:** LOTTO-0034 INV-49 and INV-50 (`tools/verify_expiry.py`).

## Context

Recorded 2026-10-15 for LOTTO-0056. The decision was already in force and
lived only as a bullet in `.claude/rules/architecture.md` § Load-bearing
decisions, which now keeps a one-line rule and a link here. The decision
below is that bullet, moved verbatim.

## Decision

**The re-buy warning reads the CALENDAR, never the results.** `expiry.py`
imports nothing of the project's and touches no file (INV-50), because a
ticket's last draw is fixed at purchase — the ndraws-th calendar draw on or
after its start — so the warning is right with the server stopped and the
machine offline. `draws_left` (calendar: has it *happened*) and
`draws_remaining` (results: has it been *scored*) are different quantities
that coincide only while results are current, which is exactly when the
warning does not need help. **Do not unify them** — same cardinal rule as
`_money_cell()`, one layer out. Both boundaries are pinned and moving either
shifts every date by one: `start` is inclusive, and a draw falling *today*
has not yet happened. `DRAW_DAYS` is hardcoded like `TIER_PRICES` and rots
the same way, so INV-49 checks it against
observed history in **both** directions — a one-directional check passes a
*removed* draw day forever.
