# ADR-0011 — Daily Lotto Plus maps to a pool no source carries

**Status:** Accepted, 2026-08-01 (first recorded in `CLAUDE.md`, commit 57933a9).
**Enforced by:** `tools/verify_sources.py`'s `EXPECTED_EMPTY` exemption.

## Context

Recorded 2026-10-15 for LOTTO-0056. The decision was already in force and
lived only as a bullet in `.claude/rules/architecture.md` § Load-bearing
decisions, which now keeps a one-line rule and a link here. The decision
below is that bullet, moved verbatim.

## Decision

**`daily/1` (Daily Lotto Plus) is deliberately mapped to a pool no source
carries**, so those 11 *entries* read as uncheckable while the same tickets'
`daily/0` entries score normally — they are the project's only partly
uncheckable tickets. Aliasing them onto plain Daily Lotto would score them
against a different game. `tools/verify_sources.py` exempts it via
`EXPECTED_EMPTY`.
