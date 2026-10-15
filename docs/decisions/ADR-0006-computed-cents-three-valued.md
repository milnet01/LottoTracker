# ADR-0006 — `computed_cents` is three-valued

**Status:** Accepted, 2026-08-19 (first recorded in `CLAUDE.md`, commit ac21c52; LOTTO-0029).
**Enforced by:** LOTTO-0009 INV-11; LOTTO-0029's reconciliation cases in `tools/verify_payouts.py`.

## Context

Recorded 2026-10-15 for LOTTO-0056. The decision was already in force and
lived only as a bullet in `.claude/rules/architecture.md` § Load-bearing
decisions, which now keeps a one-line rule and a link here. The decision
below is that bullet, moved verbatim.

## Decision

**`computed_cents` is three-valued and the three must not converge** — the
cardinal rule again, one layer below the page. `None` is *not checkable*
(nothing could be scored), `0` is *checked, total prize zero*, and a positive
integer is the summed prize. So `computed_cents` never answers "did it win?";
`first_win` does. A reference that is only **partly** scorable carries an
integer, never `None`, or LOTTO-0009 INV-11 is breached from the other side.
