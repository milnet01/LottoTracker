#!/usr/bin/env python3
"""One view of every draw, across both eras.

Two sources, because neither alone covers the ticket history:
  - official Sizekhaya API  2026-06-01 onward (authoritative, has payouts)
  - za.national-lottery.com archive, earlier   (scraped, numbers only)

Where they overlap the two agree exactly (148 draws across all six pools --
`python3 tools/verify_sources.py`), so the official one wins on conflict and
the archive fills in behind it.

Every draw is normalised to:
    {"date": "YYYY-MM-DD", "main": [int...], "special": int|None,
     "issue": int|None, "source": "api"|"archive"}
`issue` is the draw number, present only for API draws - it is what the
payout lookup needs, which is why archive-era wins cannot price themselves.
"""

import json
import os

from results import draws as api_draws

ARCHIVE = "archive_results.json"

# winPoolName as the API reports it, per (game, plusFlag)
POOL_NAMES = {
    ("lotto", 0): "LOTTO",
    ("lotto", 1): "LOTTO PLUS 1",
    ("lotto", 2): "LOTTO 5 MAX",
    ("powerball", 0): "PowerBall",
    ("powerball", 1): "PowerBall XTRA",
    ("daily", 0): "DAILY LOTTO",
    ("daily", 1): "DAILY LOTTO PLUS",  # no source carries it; always empty
}

_cache = {}


def all_draws(game, plus_flag):
    """Every known draw for one game/pool, oldest first."""
    key = (game, plus_flag)
    if key in _cache:
        return _cache[key]

    by_date = {}

    if os.path.exists(ARCHIVE):
        archive = json.load(open(ARCHIVE)).get(f"{game}:{plus_flag}", {})
        for date, row in archive.items():
            by_date[date] = {
                "date": date,
                "main": row["main"],
                "special": row["special"],
                "issue": None,
                "source": "archive",
            }

    want = POOL_NAMES[key]
    for r in api_draws(game, 400):
        if r["winPoolName"].upper() != want.upper():
            continue
        nums = [int(n) for n in r["winNumList"]]
        special = nums[-1] if game in ("lotto", "powerball") else None
        main = nums[:-1] if special is not None else nums
        date = r["drawTime"][:10]
        by_date[date] = {  # official wins on overlap
            "date": date,
            "main": main,
            "special": special,
            "issue": r["wagerIssue"],
            "source": "api",
        }

    _cache[key] = sorted(by_date.values(), key=lambda d: d["date"])
    return _cache[key]


def scorable(ticket):
    """False when no source reaches back to this ticket's draws.

    Without this, a 2022 ticket silently takes the first N draws of 2025 --
    real draws, wrong ones -- and every check downstream reports it as fine
    because the count matches. 426 of 558 tickets fall in this window.
    """
    rows = all_draws(ticket.game, ticket.plus_flag)
    return bool(rows) and ticket.start.strftime("%Y-%m-%d") >= rows[0]["date"]


def covered(ticket):
    """The draws a ticket actually covers: first N on or after its start.

    Empty for a ticket predating all known draws -- see scorable(). Callers
    must treat empty as "cannot be checked", never as "did not win".
    """
    if not scorable(ticket):
        return []
    start = ticket.start.strftime("%Y-%m-%d")
    rows = [d for d in all_draws(ticket.game, ticket.plus_flag) if d["date"] >= start]
    return rows[: ticket.ndraws]
