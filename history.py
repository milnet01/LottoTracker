#!/usr/bin/env python3
"""One view of every draw, across both eras.

Two sources, because neither alone covers the ticket history:
  - official Sizekhaya API  2026-06-01 onward (authoritative, has payouts)
  - za.national-lottery.com archive, earlier   (scraped, numbers only)
    back to backfill.FIRST_YEAR, the year of the earliest purchase SMS

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

from backfill import ARCHIVE
from results import draws as api_draws
from tickets import HANDOVER

# winPoolName as the API reports it, per (game, plusFlag)
POOL_NAMES = {
    ("lotto", 0): "LOTTO",
    ("lotto", 1): "LOTTO PLUS 1",
    ("lotto", 2): "LOTTO 5 MAX",
    ("powerball", 0): "PowerBall",
    ("powerball", 1): "PowerBall XTRA",
    ("daily", 0): "DAILY LOTTO",
    ("daily", 1): "DAILY LOTTO PLUS",  # none from the handover on: ARCHIVE_ONLY
}

# Pools the official feed never carried from the handover on, whose draws and
# prizes come from the scraped archive alone. Declared rather than inferred,
# because a pool with no feed rows is otherwise a renamed pool, which must stay
# loud (ADR-0014).
ARCHIVE_ONLY = {("daily", 1)}

# The feed is read only from the licence handover on; the archive owns every
# earlier draw. Seen 2026-11-11 (LOTTO-0098): the feed began listing Daily Lotto
# and Daily Lotto Plus for 2026-02 to 2026-05, every one dated a day before its
# own draw number says, and "official wins on overlap" let them replace the
# archive's correct draws. The user chose this cut over judging each record.
FEED_FROM = HANDOVER.date().isoformat()


def in_feed_era(row):
    """True for a feed record dated on or after the handover."""
    return str(row.get("drawTime"))[:10] >= FEED_FROM

_cache: dict = {}


def all_draws(game, plus_flag):
    """Every known draw for one game/pool, oldest first."""
    key = (game, plus_flag)
    if key in _cache:
        return _cache[key]

    by_date = {}

    if os.path.exists(ARCHIVE):
        with open(ARCHIVE, encoding="utf-8") as fh:
            archive = json.load(fh).get(f"{game}:{plus_flag}", {})
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
        if r["winPoolName"].upper() != want.upper() or not in_feed_era(r):
            continue
        # A draw the feed lists before it happens carries no numbers, and a
        # malformed one carries numbers that will not parse. Neither is a draw,
        # and int() raising here takes out every consumer of this module at
        # once - check.py, the page's build and six verifiers.
        try:
            nums = [int(n) for n in r.get("winNumList") or []]
        except (TypeError, ValueError):
            print(f"  SKIPPED {want} {str(r.get('drawTime'))[:10]}: winNumList "
                  f"{r.get('winNumList')!r} is not a list of numbers")
            continue
        if not nums:
            continue  # listed, not yet drawn
        special = nums[-1] if game in ("lotto", "powerball") else None
        main = nums[:-1] if special is not None else nums
        if not main:
            # One number for a game that has a special leaves no mains.
            # backfill.parse_page() drops the same shape for the same reason.
            continue
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


def scorable(ticket, plus_flag):
    """False when no source reaches back to this ticket's draws in this pool.

    Without this, a ticket bought before the archive reaches back silently
    takes the first N draws it does reach -- real draws, wrong ones -- and
    every check downstream reports it as fine because the count matches.
    LOTTO-0006 pushed the archive back to the earliest purchase SMS, so the
    window is now empty of whole tickets; what remains is a few daily/1 entries
    older than that pool's first listed draw. The guard stays: the window reopens
    the moment an older ticket is imported, which is the safe failure this
    exists for.

    The pool is passed in rather than read off the ticket: a ticket is entered
    in every tier its price paid for, and one of them can be checkable while
    another is not. A Daily Lotto Plus ticket older than daily/1's first listed
    draw is exactly that: its daily/0 entry still scores normally.
    """
    # A board too big for one line of its game makes every entry of the
    # ticket unscorable, whatever its draws (LOTTO-0001 INV-67). getattr, so a
    # stand-in ticket a verifier builds without the attribute is not oversized.
    if getattr(ticket, "oversized", None):
        return False
    rows = all_draws(ticket.game, plus_flag)
    return bool(rows) and ticket.start.strftime("%Y-%m-%d") >= rows[0]["date"]


def covered(ticket, plus_flag):
    """The draws one entry actually covers: first N on or after its start.

    Empty for an entry predating all known draws -- see scorable(). Callers
    must treat empty as "cannot be checked", never as "did not win".
    """
    if not scorable(ticket, plus_flag):
        return []
    start = ticket.start.strftime("%Y-%m-%d")
    rows = [d for d in all_draws(ticket.game, plus_flag) if d["date"] >= start]
    return rows[: ticket.ndraws]
