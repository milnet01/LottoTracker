#!/usr/bin/env python3
"""LOTTO-0009 INV-7 and INV-11: every ticket's price resolves to real tiers,
and a ticket checkable in one pool is never reported as wholly uncheckable.

A PLUS game cannot be bought alone - each tier draws separately for its own
prize pool - so a ticket's price per board per draw is the running sum of the
tiers it bought. That makes the price a complete statement of what was bought,
where the printed game name states only the top tier and, after the 2026-06-01
handover, not even that.

The price table below is transcribed independently rather than imported from
tickets.py. This check exists to catch a wrong derivation there, and importing
the thing under test makes the check agree with the bug -- the same lesson
verify_coverage.py already carries about history.scorable().

Two failures it must catch, both silent otherwise:

  1. the operator changes a board price, so prices match no tier and every
     affected ticket quietly reverts to name-only scoring
  2. the uncheckable report is written per ticket again, so the 11 Daily Lotto
     Plus tickets are declared uncheckable in the same run that scores their
     Daily Lotto entries

Counts move as messages arrive; what this asserts is the zero-terms and the
exit code. The name/price disagreement figure is reported, not asserted: it is
a property of the bank's wording, not of this code. It is split by era because
a post-handover disagreement means something different -- the bank stopped
printing the tier at all, so the name cannot state it even in principle.
"""

import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from check import uncheckable_report  # noqa: E402
from history import all_draws  # noqa: E402
from tickets import GAME_MAP, load  # noqa: E402

DUMP = os.path.join(os.path.dirname(__file__), "..", "lotto_sms_raw.txt")

HANDOVER = datetime(2026, 6, 1)

# CUMULATIVE cost per board per draw, in whole cents: what a ticket topping out
# at that tier was charged. Not the per-tier increment -- conflating the two
# prices a R10.00 Lotto ticket at R22.50. Cheapest tier first.
CUMULATIVE = {
    ("lotto", "ithuba"): [(0, 100, 500), (1, 101, 750), (2, 102, 1000)],
    ("lotto", "sizekhaya"): [(0, 100, 500), (1, 101, 750), (2, 102, 1000)],
    ("powerball", "ithuba"): [(0, 100, 500), (1, 101, 750)],
    ("powerball", "sizekhaya"): [(0, 100, 1000), (1, 101, 1500)],
    ("daily", "ithuba"): [(0, 100, 300), (1, 101, 450)],
    ("daily", "sizekhaya"): [(0, 100, 300)],  # Daily Lotto Plus was withdrawn
}


def expected_pools(game, bought, cost, paid_lines, ndraws):
    """The pools this price paid for, or None when it matches no tier."""
    tiers = CUMULATIVE[(game, "sizekhaya" if bought >= HANDOVER else "ithuba")]
    if not paid_lines:
        return None
    unit, remainder = divmod(round(cost * 100), paid_lines * ndraws)
    if remainder:
        return None  # not an exact multiple: never round onto a valid tier
    for i, (_, _, total) in enumerate(tiers):
        if total == unit:
            return [(pf, pool) for pf, pool, _ in tiers[: i + 1]]
    return None


def printed_names():
    """{ticket ref: the game name its SMS printed}, read from the dump.

    The parsed Ticket cannot answer this any more: its plus_flag is the top
    tier the PRICE paid for, which is the very thing being cross-checked.
    """
    out = {}
    if not os.path.exists(DUMP):
        return out
    raw = open(DUMP, errors="replace").read()
    for row in re.split(r"^Row: \d+ address=", raw, flags=re.M)[1:]:
        if not (m := re.match(r"([^,]*), date=(\d+), body=(.*)", row, re.S)):
            continue
        body = m.group(3).strip()
        head = re.search(
            r"Played R[\d,.]+ ([A-Za-z0-9 ]+?)(?: for \d+ draw\(?s?\)?)?\s*$",
            body.split("\n")[0].strip(),
        )
        ref = re.search(r"Ref:(VAS\d+)", body)
        if head and ref:
            out[ref.group(1)] = head.group(1).strip().lower()
    return out


def reaches(ticket, plus_flag):
    """Whether any source reaches back to this entry's first draw.

    Recomputed here rather than imported from history.scorable(): the report
    under test is built on that predicate, so importing it would let a
    regressed one pass this check as well.
    """
    rows = all_draws(ticket.game, plus_flag)
    return bool(rows) and ticket.start.strftime("%Y-%m-%d") >= rows[0]["date"]


def main():
    tickets = load()
    names = printed_names()
    bad = unresolved = 0
    disagree = {"pre": 0, "post": 0}

    for t in tickets:
        want = expected_pools(t.game, t.bought, t.cost, len(t.boards), t.ndraws)
        if want is None:
            print(
                f"  UNRESOLVED {t.ref}: {t.game} priced over {len(t.boards)} "
                f"line(s) x {t.ndraws} draw(s) matches no tier total"
            )
            unresolved += 1
            bad += 1
            continue
        if t.pools != want:
            print(f"  POOLS {t.ref}: parser says {t.pools}, price says {want}")
            bad += 1
        elif not t.resolved:
            # The right pools reached by the wrong road: a fallback that
            # happens to agree still means the price did not resolve.
            print(f"  UNFLAGGED {t.ref}: pools correct but reported unresolved")
            bad += 1

        named = GAME_MAP.get(names.get(t.ref, ""))
        if named and named[1] != want[-1][0]:
            disagree["post" if t.bought >= HANDOVER else "pre"] += 1

    entries = sum(len(t.pools) for t in tickets)
    print(
        f"{len(tickets)} tickets, {entries} entries, {unresolved} unresolved, "
        f"{disagree['pre'] + disagree['post']} name/price disagreements "
        f"({disagree['pre']} pre-handover, {disagree['post']} post-handover)"
    )

    # INV-11, asserted against check.py's actual report rather than against the
    # derivation: a ticket with one checkable pool and one uncheckable one must
    # be reported as partly uncheckable and still scored on the rest.
    _, counts = uncheckable_report(tickets)
    partly = [
        t
        for t in tickets
        if any(reaches(t, pf) for pf, _ in t.pools)
        and not all(reaches(t, pf) for pf, _ in t.pools)
    ]
    wrong = [t for t in partly if t in counts["wholly"]]
    double = [t for t in counts["wholly"] if t in counts["partly"]]
    for t in wrong:
        print(f"  WHOLLY {t.ref}: checkable in one pool, reported as excluded")
    for t in double:
        print(f"  DOUBLE-COUNTED {t.ref}: reported both wholly and partly")

    print(
        f"{len(partly)} partly-uncheckable tickets, {len(wrong)} reported as "
        f"wholly uncheckable, {len(double)} double-counted"
    )
    return 0 if bad == 0 and not wrong and not double else 1


if __name__ == "__main__":
    sys.exit(main())
