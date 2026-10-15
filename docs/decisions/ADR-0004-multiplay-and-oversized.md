# ADR-0004 — Lotto Multiplay expands; an oversized PowerBall or Daily board is uncheckable

**Status:** Accepted, 2026-08-01 for Multiplay (commit 57933a9); 2026-10-15 for oversized boards (commit ac6b0bc, LOTTO-0007 (d)).
**Enforced by:** LOTTO-0001 INV-2 and INV-67 (`tools/verify_boards.py`).

## Context

Recorded 2026-10-15 for LOTTO-0056. The decision was already in force and
lived only as a bullet in `.claude/rules/architecture.md` § Load-bearing
decisions, which now keeps a one-line rule and a link here. The decision
below is that bullet, moved verbatim.

## Decision

**A Lotto board with >6 numbers is Multiplay** and expands to one line per
6-number combination, each winning independently (INV-2). **On PowerBall
and Daily Lotto a board bigger than one line — six numbers counting the
PowerBall, five on Daily — is oversized, not Multiplay** (INV-67,
`tickets.LINE_SIZE`): its price per line is unknown, so every entry of the
ticket is uncheckable, reported first as `odd_board` and named by
`serve.entry_reason()`. `verify_coverage.py` and `verify_pools.py` keep their
own copy of the line sizes on purpose; do not point them at `LINE_SIZE`.
