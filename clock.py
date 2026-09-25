"""South African time, whatever the machine is set to (LOTTO-0066, INV-64).

Every draw, ticket and deadline this project handles is a South African one.
Reading the machine's local zone made the whole calendar correct only while
that zone was SAST: on a laptop abroad, a server, or a container with TZ
unset, a draw falling today read as yesterday or tomorrow, and a ticket bought
just after midnight on 2026-06-01 landed in the wrong era.

A FIXED offset, not zoneinfo: South Africa has no daylight saving, so UTC+2 is
exact for every date this project can see and needs no tz database installed.

NAIVE results: every comparison in the project is between naive datetimes -
tickets.HANDOVER, the draw dates both results sources return - so the zone is
applied and then dropped. Handing back an aware datetime would make each of
those comparisons raise.

Imports nothing of the project's, so any module may import it.
"""

import datetime

SAST = datetime.timezone(datetime.timedelta(hours=2), "SAST")


def from_ms(ms):
    """An Android/KDE Connect timestamp (ms since the epoch) as naive SAST.

    Raises what datetime.fromtimestamp() raises on an unrepresentable value
    (ValueError, OverflowError, OSError); callers already skip on those.
    """
    return datetime.datetime.fromtimestamp(ms / 1000, SAST).replace(tzinfo=None)


def now():
    """The current moment as naive SAST."""
    return datetime.datetime.now(SAST).replace(tzinfo=None)


def today():
    """Today's date in South Africa."""
    return now().date()
