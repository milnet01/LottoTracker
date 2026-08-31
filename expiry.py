#!/usr/bin/env python3
"""When a ticket's draws run out, from the calendar alone (LOTTO-0034 §4.1).

One table and two pure functions. This module imports NOTHING from the project
and touches no file (INV-50), and that is the whole point of it: a ticket's
last draw is decided the moment it is bought - the ndraws-th calendar draw on
or after its start - so the re-buy warning is correct with the server stopped,
with `archive_results.json` absent, and with the machine offline. Consulting
known draws to "improve" the projection reintroduces exactly the dependency
this module exists to remove.

Two boundaries, both pinned, because leaving either open shifts every date by
one (INV-51):

  * `start` is INCLUSIVE - a ticket bought on a draw day is entered in that
    day's draw.
  * a draw falling on `today` has NOT yet happened - so a ticket reads
    `draws_left == 1` on its own final draw day and 0 the day after.

Accuracy is one-directional in practice, not by construction, and it was
measured rather than assumed. A weekly pattern cannot express a schedule
change, so a draw CANCELLED or moved LATER makes this name an EARLY date - the
safe side, since the warning still arrives before the ticket runs out. A draw
moved EARLIER, or an extra draw on an unlisted day, would make it name a LATE
one, which is not safe. INV-51 asserts that sign and an exactness floor.
Enumerated over the whole archive: every irregularity is a cancellation or a
later move (six Christmas cancellations and one Wednesday-to-Thursday move), so
nothing projects late today - but that is a measurement, and LOTTO-0034 §4.2
and §6 carry it as a live exposure rather than an impossibility.
"""

import datetime

# Weekday numbers as datetime.date.weekday() reports them: Monday is 0.
#
# Hardcoded because no feed publishes a draw schedule. That is the position
# tickets.py::TIER_PRICES is in and it carries the same risk - CLAUDE.md calls
# that one "the one hardcoded table in the project and the one most likely to
# rot" - so the answer here is the answer there: tools/verify_expiry.py checks
# it against observed history in BOTH directions (INV-49), because a check that
# only asks "do the draws land on listed days" passes a REMOVED day forever.
DRAW_DAYS = {
    "lotto": {2, 5},           # Wednesday, Saturday
    "powerball": {1, 4},       # Tuesday, Friday
    "daily": set(range(7)),    # every day
}

# Deliberately NOT history.POOL_NAMES. That table exists to match the API's
# winPoolName field, is keyed per pool rather than per game, and changes when
# the wire format changes - a sentence the user reads must not. Keeping the
# names here also keeps this module free of project imports (INV-50).
DISPLAY_NAME = {"lotto": "Lotto", "powerball": "PowerBall", "daily": "Daily Lotto"}


def _as_date(value):
    """A datetime.date from either a date or a datetime.

    Ticket.start is a datetime; the calendar only ever asks about the day.
    """
    return value.date() if isinstance(value, datetime.datetime) else value


def draw_dates(game, start, ndraws):
    """This ticket's draw dates, oldest first. Pure.

    A game absent from DRAW_DAYS raises KeyError, and that is deliberate:
    check.py::paying_combinations() raises for the same reason, and LOTTO-0031
    is what a silent None costs - a rebranded game name parsed to None and the
    ticket was never scored again. INV-56 is what stops it being swallowed.
    """
    if ndraws < 1:
        raise ValueError(f"a ticket runs for at least one draw, not {ndraws!r}")
    days = DRAW_DAYS[game]
    day = _as_date(start)
    dates = []
    while len(dates) < ndraws:
        if day.weekday() in days:
            dates.append(day)
        day += datetime.timedelta(days=1)
    return dates


def final_draw_date(game, start, ndraws):
    """The date of the ndraws-th draw on or after `start`. Pure."""
    return draw_dates(game, start, ndraws)[-1]


def draws_left(game, start, ndraws, today):
    """How many of this ticket's draws have not happened yet, as of `today`.

    A draw ON `today` counts as not yet happened, so this is `1` on the final
    draw day itself and `0` from the day after.
    """
    today = _as_date(today)
    return sum(1 for d in draw_dates(game, start, ndraws) if d >= today)
