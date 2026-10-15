# ADR-0010 — `paying_combinations()` raises on a pool with no recent draw

**Status:** Accepted, 2026-08-01 (first recorded in `CLAUDE.md`, commit 57933a9).
**Enforced by:** no invariant is named in the decision's text.

## Context

Recorded 2026-10-15 for LOTTO-0056. The decision was already in force and
lived only as a bullet in `.claude/rules/architecture.md` § Load-bearing
decisions, which now keeps a one-line rule and a link here. The decision
below is that bullet, moved verbatim.

## Decision

**`paying_combinations()` raises** rather than returning `{}` when a pool has
no recent draw. An empty set would score the whole pool as losses with no
diagnostic.
