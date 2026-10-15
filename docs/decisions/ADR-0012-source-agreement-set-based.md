# ADR-0012 — Source-agreement comparison is set-based

**Status:** Accepted, 2026-08-01 (first recorded in `CLAUDE.md`, commit 57933a9).
**Enforced by:** LOTTO-0001 INV-3 (`tools/verify_sources.py`).

## Context

Recorded 2026-10-15 for LOTTO-0056. The decision was already in force and
lived only as a bullet in `.claude/rules/architecture.md` § Load-bearing
decisions, which now keeps a one-line rule and a link here. The decision
below is that bullet, moved verbatim.

## Decision

**Source-agreement comparison is set-based**: the archive sorts numbers
ascending, the API preserves drawn order.
