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
    starved = []
    for (game, plus), pool in POOL_NAMES.items():
        before = overlap
        rows = archive.get(f"{game}:{plus}", {})
        for r in draws(game, 400):
            if r["winPoolName"].upper() != pool.upper():
                continue
            date = r["drawTime"][:10]
            if date not in rows:
                continue
            nums = [int(n) for n in r["winNumList"]]
            special = nums[-1] if game in ("lotto", "powerball") else None
            main = nums[:-1] if special is not None else nums
            overlap += 1
            got = rows[date]
            if sorted(got["main"]) == sorted(main) and got["special"] == special:
                agree += 1
            else:
                print(f"  DISAGREE {game}:{plus} {date} {got} vs {main}/{special}")

        # A pool contributing nothing is the "game naming changed" breakage
        # this check exists to catch. Without a per-pool floor the run still
        # passes on the strength of the other five.
        if overlap == before and (game, plus) not in EXPECTED_EMPTY:
            starved.append(f"{game}:{plus} ({pool})")

    for s in starved:
        print(f"  NO OVERLAP {s} - renamed pool, or archive missing this game")

    print(f"{overlap} overlapping draws, {agree} agree, {overlap - agree} disagree")
    return 0 if overlap and agree == overlap and not starved else 1


if __name__ == "__main__":
    sys.exit(main())
