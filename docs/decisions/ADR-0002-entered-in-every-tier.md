# ADR-0002 — A ticket is entered in every tier its price paid for

**Status:** Accepted, 2026-08-01 (first recorded in `CLAUDE.md`, commit 13bd21b; LOTTO-0009).
**Enforced by:** LOTTO-0009 INV-7, INV-8, INV-9 (`tools/verify_pools.py`).

## Context

Recorded 2026-10-15 for LOTTO-0056. The decision was already in force and
lived only as a bullet in `.claude/rules/architecture.md` § Load-bearing
decisions, which now keeps a one-line rule and a link here. The decision
below is that bullet, moved verbatim.

## Decision

**A ticket is entered in every tier its price paid for**, base game first,
because a PLUS game cannot be bought alone (INV-8). The tiers come from the
price in whole cents, not from the printed name, which states only the top
tier and since 2026-06-01 states none (INV-9). A price matching no tier is
reported, never guessed at (INV-7) — `tickets.py::TIER_PRICES` is hardcoded
because no feed publishes it, so `tools/verify_pools.py` is the only thing
that makes a price change loud.
