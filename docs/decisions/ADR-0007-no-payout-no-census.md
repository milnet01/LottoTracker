# ADR-0007 — No parsable payout means no category census

**Status:** Accepted, 2026-08-19 (first recorded in `CLAUDE.md`, commit ac21c52; LOTTO-0029).
**Enforced by:** LOTTO-0029 INV-47 (`tools/verify_payouts.py::no_payouts_is_not_agreement`).

## Context

Recorded 2026-10-15 for LOTTO-0056. The decision was already in force and
lived only as a bullet in `.claude/rules/architecture.md` § Load-bearing
decisions, which now keeps a one-line rule and a link here. The decision
below is that bullet, moved verbatim.

## Decision

**A dump with no parsable payout reports that, and emits no category census.**
If the bank changes its wording, `parse_payout()` matches nothing and every
scored reference would otherwise satisfy `unpaid` — announcing prizes nobody
was ever paid. The guard is in `reconcile()` itself, not only in the report,
so the page cannot render the fictions either (INV-47). Same class as
LOTTO-0031, where a rebranded game name parsed to `None` and a ticket was
silently never scored.
