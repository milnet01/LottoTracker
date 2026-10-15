# ADR-0005 — The bank's payout SMS never replaces a computed figure

**Status:** Accepted, 2026-08-13 (the user's decision, LOTTO-0029).
**Enforced by:** LOTTO-0029 INV-43 (`tools/verify_payouts.py`).

## Context

Recorded 2026-10-15 for LOTTO-0056. The decision was already in force and
lived only as a bullet in `.claude/rules/architecture.md` § Load-bearing
decisions, which now keeps a one-line rule and a link here. The decision
below is that bullet, moved verbatim.

## Decision

**The bank's payout SMS never replaces a computed figure.** `check.py::reconcile()`
joins the bank's own record to tickets on the `VAS` reference and reports both
figures side by side; a disagreement is flagged, never resolved in the SMS's
favour (user decision 2026-08-13, LOTTO-0029 INV-43). Adopting it would price
the archive era for free — and erase the 15 references where the app computes
LOW, which are the evidence that something in pricing is wrong. Three things
not to "simplify": the unit is the **reference**, not the payment (77 of 225
are paid more than once); money is compared in **whole cents**, never float
rands; and the seven categories are decided in a fixed **order**, because as
an unordered set they overlap — a reference with no purchase SMS has no
entries, so "every entry is scorable" is vacuously true of it and it would
match `unexplained` as well as `no_ticket`.
