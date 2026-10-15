# ADR-0009 — Every date is South African time, read through `clock.py`

**Status:** Accepted, 2026-09-25 (first recorded in `CLAUDE.md`, commit 3c11027; LOTTO-0066).
**Enforced by:** LOTTO-0034 INV-64 (`tools/verify_expiry.py`).

## Context

Recorded 2026-10-15 for LOTTO-0056. The decision was already in force and
lived only as a bullet in `.claude/rules/architecture.md` § Load-bearing
decisions, which now keeps a one-line rule and a link here. The decision
below is that bullet, moved verbatim.

## Decision

**Every date is South African time, read through `clock.py`** (LOTTO-0066,
INV-64): a fixed UTC+2, because SAST has no daylight saving, returned naive
because `HANDOVER` and every draw date are naive. **Never call
`date.today()`, `datetime.now()` or `fromtimestamp()` directly** — each
reads the machine's own zone, which put a draw on the wrong day on any
machine not set to SAST. `expiry.py` still takes `today` from its caller
(INV-50); the caller gets it from `clock.today()`.
