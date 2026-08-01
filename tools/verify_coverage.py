#!/usr/bin/env python3
"""LOTTO-0001 INV-6: every ticket is scored over exactly the draws it covers.

The obvious version of this check is a tautology and was one until 2026-08-01:
asking `len(covered(t)) == t.ndraws` compares a slice against the length it was
sliced to, so it passes for any implementation, including one returning ten
entirely wrong dates. It could not see that 426 tickets predating all known
draw data were being scored against January 2025.

So the properties below are asserted against the draw records directly, never
against the shape of what covered() returned:

  1. an unscorable ticket gets NO draws (not the wrong ones)
  2. every covered draw falls on or after the ticket's start date
  3. no known draw sits between the start date and the first covered draw
  4. the window is contiguous - no known draw is skipped inside its span
  5. the parsed ticket count matches the raw dump

Property 5 exists because a regex that quietly matched nothing once dropped
552 of 558 tickets while every downstream number still looked plausible.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from history import all_draws, covered  # noqa: E402
from tickets import load  # noqa: E402

DUMP = os.path.join(os.path.dirname(__file__), "..", "lotto_sms_raw.txt")


def main():
    tickets = load()
    bad = 0

    if os.path.exists(DUMP):
        expected = open(DUMP, errors="replace").read().count("Played R")
        if len(tickets) != expected:
            print(f"  PARSE GAP: {expected} purchase SMSes, {len(tickets)} parsed")
            bad += 1

    unscorable = 0
    for t in tickets:
        rows = covered(t)
        known = all_draws(t.game, t.plus_flag)
        start = t.start.strftime("%Y-%m-%d")

        # Recomputed here, NOT via history.scorable(). Importing the predicate
        # under test makes the check agree with the bug: a scorable() that
        # regressed to `bool(rows)` would hand a 2022 ticket the first draws of
        # 2025 and every property below would still pass.
        if not known or start < known[0]["date"]:
            unscorable += 1
            if rows:
                print(f"  {t.ref}: predates all draw data but got {len(rows)} draws")
                bad += 1
            continue

        if any(d["date"] < start for d in rows):
            print(f"  {t.ref}: covers a draw before its start date")
            bad += 1
            continue

        # Recomputed from the draw records, not from covered()'s output shape.
        after = [d for d in known if d["date"] >= start]
        if not after:
            continue  # bought since the last draw; nothing to score yet
        if not rows:
            print(f"  {t.ref}: no draws covered but {len(after)} available")
            bad += 1
            continue
        if rows and rows[0]["date"] != after[0]["date"]:
            print(f"  {t.ref}: skipped {after[0]['date']}, started {rows[0]['date']}")
            bad += 1
            continue
        span = [d for d in known if rows[0]["date"] <= d["date"] <= rows[-1]["date"]]
        if len(span) != len(rows):
            print(f"  {t.ref}: window has a gap ({len(span)} known, {len(rows)} used)")
            bad += 1
            continue
        if len(rows) != t.ndraws and rows[-1]["date"] != known[-1]["date"]:
            print(f"  {t.ref}: wants {t.ndraws} draws, got {len(rows)}, not at end")
            bad += 1

    # A floor, because "everything is unscorable" is what a missing
    # archive_results.json looks like, and it would otherwise report 0 bad.
    if tickets and unscorable / len(tickets) > 0.90:
        print(
            f"  FLOOR: {unscorable}/{len(tickets)} tickets unscorable — draw "
            f"data is probably missing; run `python3 backfill.py`"
        )
        bad += 1

    print(
        f"{len(tickets)} tickets, {unscorable} unscorable (excluded), "
        f"{bad} with wrong draw coverage"
    )
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
