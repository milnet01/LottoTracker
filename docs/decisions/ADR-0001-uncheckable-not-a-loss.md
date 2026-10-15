# ADR-0001 — An entry nothing can score is uncheckable, not a loss

**Status:** Accepted, 2026-08-01 (first recorded in `CLAUDE.md`, commit 57933a9).
**Enforced by:** LOTTO-0009 INV-11 (`tools/verify_pools.py`); `check.py::uncheckable_report()`.

## Context

Recorded 2026-10-15 for LOTTO-0056. The decision was already in force and
lived only as a bullet in `.claude/rules/architecture.md` § Load-bearing
decisions, which now keeps a one-line rule and a link here. The decision
below is that bullet, moved verbatim.

## Decision

**An entry nothing can score is *uncheckable*, not a loss.** `history.py::scorable()`
gates it out and `check.py::uncheckable_report()` reports the three reasons
separately (oversized board, decided first / predates all draw data / pool
no source publishes). Silently
scoring such an entry against the wrong draws is the bug this project was
built after hitting. **The unit is the entry**: a ticket checkable in one
pool and not another is *partly* uncheckable, still scored on the rest, and
must never be counted as wholly excluded (INV-11).
