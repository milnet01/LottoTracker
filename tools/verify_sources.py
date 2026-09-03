#!/usr/bin/env python3
"""LOTTO-0001 INV-3: the two results sources agree wherever they overlap.

Set-based on purpose. The archive sorts numbers ascending; the API preserves
drawn order. Comparing them as lists reports every single draw as a conflict.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from history import ARCHIVE, POOL_NAMES  # noqa: E402
from results import draws  # noqa: E402

# Pools that legitimately have no results anywhere, so zero overlap is the
# expected state and not the rot signal the floor below is looking for.
# Standard Bank sells "Daily Lotto Plus" but no source publishes such a pool.
EXPECTED_EMPTY = {("daily", 1)}


def main():
    if not os.path.exists(ARCHIVE):
        sys.exit(f"{ARCHIVE} missing - run `python3 backfill.py` first")
    archive = json.load(open(ARCHIVE))

    overlap = agree = 0
    starved, stale, unexpected = [], [], []
    # ONE fetch per GAME. draws() is not memoised (results.divisions is), and
    # POOL_NAMES has three lotto pools and two each for powerball and daily -
    # so the per-pool loop issued seven identical-per-game POSTs to a free
    # third-party endpoint for three distinct queries, and gave a transport
    # failure seven chances to abort the run instead of three.
    by_game = {}
    for (game, plus), pool in POOL_NAMES.items():
        before = overlap
        rows = archive.get(f"{game}:{plus}", {})
        if game not in by_game:
            by_game[game] = draws(game, 400)
        for r in by_game[game]:
            if r["winPoolName"].upper() != pool.upper():
                continue
            date = r["drawTime"][:10]
            if date not in rows:
                continue
            # Guarded the way history.all_draws() guards the same field, and
            # for its reason: a draw the feed lists before it happens carries
            # no numbers, and int() raising here aborts the run with a
            # traceback rather than a DISAGREE line.
            raw_nums = r.get("winNumList") or []
            try:
                nums = [int(n) for n in raw_nums]
            except (TypeError, ValueError):
                print(f"  SKIPPED {game}:{plus} {date}: winNumList "
                      f"{raw_nums!r} is not a list of numbers")
                continue
            if not nums:
                continue
            special = nums[-1] if game in ("lotto", "powerball") else None
            main = nums[:-1] if special is not None else nums
            overlap += 1
            got = rows[date]
            if sorted(got["main"]) == sorted(main) and got["special"] == special:
                agree += 1
            else:
                print(f"  DISAGREE {game}:{plus} {date} {got} vs {main}/{special}")

        if (game, plus) in EXPECTED_EMPTY:
            # The exemption is checked in BOTH directions. One-directional, an
            # entry here is never falsified: a pool silenced because it broke
            # stays silenced for good. This project forbids exactly that for
            # DRAW_DAYS and the same argument applies here.
            if overlap != before:
                unexpected.append(f"{game}:{plus} ({pool})")
            continue

        # A pool contributing nothing is the "game naming changed" breakage
        # this check exists to catch. Without a per-pool floor the run still
        # passes on the strength of the other five.
        if overlap == before:
            # Two causes, and they are not the same problem. The archive is
            # FROZEN until backfill.py is re-run by hand, while the API side is
            # the newest 400 records and slides forward with the calendar. Once
            # the window's oldest record passes the archive's newest draw the
            # two cannot overlap at all - so this gate eventually goes red as a
            # function of elapsed time since the last backfill, roughly a year
            # out, and "renamed pool" would name the wrong cause entirely.
            newest_archive = max(rows) if rows else None
            oldest_api = min(
                (r["drawTime"][:10] for r in by_game[game]
                 if r["winPoolName"].upper() == pool.upper()),
                default=None)
            if newest_archive and oldest_api and oldest_api > newest_archive:
                stale.append(f"{game}:{plus} (archive ends {newest_archive}, "
                             f"the API window starts {oldest_api})")
            else:
                starved.append(f"{game}:{plus} ({pool})")

    for s in stale:
        print(f"  NO OVERLAP {s} - the ARCHIVE IS STALE, not the pool: "
              f"re-run `python3 backfill.py`")
    for s in starved:
        print(f"  NO OVERLAP {s} - renamed pool, or archive missing this game")
    for s in unexpected:
        print(f"  UNEXPECTEDLY PRESENT {s} - EXPECTED_EMPTY says no source "
              f"carries this pool, and one now does: drop the exemption")

    print(f"{overlap} overlapping draws, {agree} agree, {overlap - agree} disagree")
    return (0 if overlap and agree == overlap
            and not starved and not stale and not unexpected else 1)


if __name__ == "__main__":
    sys.exit(main())
