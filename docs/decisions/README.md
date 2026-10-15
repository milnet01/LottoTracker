# Decision records

One record per load-bearing decision: what was decided and why, frozen once
Accepted. A changed decision gets a new record that supersedes the old one.

Every rule here is also a one-line bullet in `.claude/rules/architecture.md`
§ Load-bearing decisions, which loads by itself when a session reads a `.py`
file. That bullet is the rule; the record is its reasoning.

- [ADR-0001 — An entry nothing can score is uncheckable, not a loss](ADR-0001-uncheckable-not-a-loss.md)
- [ADR-0002 — A ticket is entered in every tier its price paid for](ADR-0002-entered-in-every-tier.md)
- [ADR-0003 — The PowerBall is the final number on a board line](ADR-0003-powerball-is-last.md)
- [ADR-0004 — Lotto Multiplay expands; an oversized PowerBall or Daily board is uncheckable](ADR-0004-multiplay-and-oversized.md)
- [ADR-0005 — The bank's payout SMS never replaces a computed figure](ADR-0005-payout-never-replaces-computed.md)
- [ADR-0006 — `computed_cents` is three-valued](ADR-0006-computed-cents-three-valued.md)
- [ADR-0007 — No parsable payout means no category census](ADR-0007-no-payout-no-census.md)
- [ADR-0008 — The re-buy warning reads the calendar, never the results](ADR-0008-rebuy-reads-calendar.md)
- [ADR-0009 — Every date is South African time, read through `clock.py`](ADR-0009-dates-are-sast.md)
- [ADR-0010 — `paying_combinations()` raises on a pool with no recent draw](ADR-0010-paying-combinations-raises.md)
- [ADR-0011 — Daily Lotto Plus maps to a pool no source carries](ADR-0011-daily-plus-unmapped.md)
- [ADR-0012 — Source-agreement comparison is set-based](ADR-0012-source-agreement-set-based.md)
- [ADR-0013 — Payout slugs use the post-rebrand names for historic draws](ADR-0013-rebrand-slugs.md)
