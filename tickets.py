#!/usr/bin/env python3
"""Parse Standard Bank lottery ticket SMSes into tickets. Scoring is check.py.

Two SMS eras exist, because the bank changed its wording when Sizekhaya took
over the licence on 2026-06-01:

  old  Played R99.00 Lotto Plus 2 for 1 draw(s)      new  Played R99.00 Powerball
       Date 01/01/2020 to 01/01/2020                      Date 01 Jan 2020 (for 10 draws)
       A: 07 11 19 23 31 44                               A: 08 14 27 33 41 -07

The trap: in the OLD format a PowerBall ticket's final number is the PowerBall
itself with nothing to mark it, while the NEW format prefixes it with "-".
Treating that last number as a main number scores every PowerBall ticket wrong.

The second trap is what the game name does NOT say. A PLUS game cannot be
bought on its own: the operator runs a separate draw with its own prize pool
for each tier and requires the tiers below it, so "Lotto Plus 2" is three
entries with three prize pools, not one. The name states only the highest tier
- and after the 2026-06-01 handover the bank stopped printing even that - so
the tiers are derived from what the ticket cost. See entered_pools().

Prize divisions are read from the API rather than hardcoded, so a rule change
upstream doesn't silently produce wrong answers here.
"""

import re
from datetime import datetime
from itertools import combinations


MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

# SMS game name -> (API game key, plusFlag, winPoolId)
GAME_MAP = {
    "lotto": ("lotto", 0, 100),
    "lotto game": ("lotto", 0, 100),
    "lotto plus 1": ("lotto", 1, 101),
    "lotto plus 2": ("lotto", 2, 102),
    "powerball": ("powerball", 0, 100),
    "powerball plus": ("powerball", 1, 101),
    "daily lotto": ("daily", 0, 100),
    # No results source carries this pool, so it resolves to a pool with no
    # draws and is reported as uncheckable. Aliasing it onto plain Daily
    # Lotto would score 11 tickets against a different game.
    "daily lotto plus": ("daily", 1, 101),
}

# Sizekhaya replaced Ithuba as licence holder here and PowerBall's board price
# changed with it. A datetime rather than a date because `bought` is built from
# an epoch, and the two types do not compare.
HANDOVER = datetime(2026, 6, 1)

# What each tier ADDS to the board price, in whole cents, cheapest tier first,
# per (game, era). A ticket's price per board per draw is the running sum of
# the tiers it bought, and every running sum is distinct within a game and era
# - which is what makes the price a complete statement of what was bought.
# Not published in any results feed, so unlike prize divisions there is nothing
# to read these from at runtime; tools/verify_pools.py is the guard that makes
# a price change loud instead of silent.
TIER_PRICES = {
    ("lotto", "ithuba"): [(0, 100, 500), (1, 101, 250), (2, 102, 250)],
    ("lotto", "sizekhaya"): [(0, 100, 500), (1, 101, 250), (2, 102, 250)],
    ("powerball", "ithuba"): [(0, 100, 500), (1, 101, 250)],
    ("powerball", "sizekhaya"): [(0, 100, 1000), (1, 101, 500)],
    ("daily", "ithuba"): [(0, 100, 300), (1, 101, 150)],
    # Daily Lotto Plus ran 2025-09-21 to 2026-05-31 only, then was withdrawn.
    ("daily", "sizekhaya"): [(0, 100, 300)],
}


def entered_pools(game, bought, cost, paid_lines, ndraws):
    """Which pools this ticket's price paid for, base tier first.

    -> ([(plus_flag, pool_id), ...], resolved), or (None, False) when the price
    matches no tier. It never guesses: a price that does not divide evenly over
    the lines and draws, or whose unit matches no running total, comes back
    unresolved for the caller to report. Rounding one onto a valid tier is
    exactly the silent wrong answer this derivation exists to replace.
    """
    tiers = TIER_PRICES[(game, "sizekhaya" if bought >= HANDOVER else "ithuba")]
    # A message with no board lines, or one claiming zero draws, must never
    # reach the divide - both are unresolved, not a crash.
    if paid_lines and ndraws:
        # Whole cents on both sides. A quotient taken in floats can arrive as
        # 7.499999... and miss its tier, which would degrade the ticket to
        # name-only scoring - the behaviour being fixed here.
        unit, remainder = divmod(round(cost * 100), paid_lines * ndraws)
        if remainder == 0:
            cumulative, pools = 0, []
            for plus_flag, pool_id, increment in tiers:
                cumulative += increment
                pools.append((plus_flag, pool_id))
                if cumulative == unit:
                    return pools, True
    return None, False


class Ticket:
    def __init__(self, game, plus_flag, pool_id, start, ndraws, boards, ref,
                 cost, pools, bought, resolved):
        self.game, self.plus_flag, self.pool_id = game, plus_flag, pool_id
        self.start, self.ndraws, self.boards, self.ref = start, ndraws, boards, ref
        # cost is the total the SMS charged for the whole ticket - every board,
        # draw and tier - and is canonical. pools is what scoring iterates.
        self.cost, self.pools, self.bought = cost, pools, bought
        # False when the price matched no tier, so pools fell back to the game
        # name alone. Counted and printed rather than quietly accepted.
        self.resolved = resolved

    def __repr__(self):
        return f"<{self.ref} {self.game} x{self.ndraws} from {self.start.date()}>"


def parse(body, bought=None):
    """Return a Ticket, or None if this SMS is not a ticket purchase.

    `bought` is when the ticket was paid for, which selects the price era. It
    falls back to the first draw date for callers holding a message without its
    dump row - but the two differ by 1-4 days on most tickets, so load() passes
    the real thing rather than relying on the fallback.
    """
    # Old format ends "... for 1 draw(s)"; new format ends at the game name.
    # All three groups are named and read by name: Python numbers named groups
    # alongside unnamed ones, so a positional read here breaks silently the
    # moment another capture is added ahead of it - and a parse() that returns
    # None for every message costs all 558 tickets with no error.
    head = re.search(
        r"Played R(?P<cost>[\d,.]+) (?P<name>[A-Za-z0-9 ]+?)"
        r"(?: for (?P<ndraws>\d+) draw\(?s?\)?)?\s*$",
        body.split("\n")[0].strip(),
    )
    if not head:
        return None

    name = head["name"].strip().lower()
    if name not in GAME_MAP:
        return None
    game, plus_flag, pool_id = GAME_MAP[name]
    cost = float(head["cost"].replace(",", ""))

    if m := re.search(r"Date (\d{2})/(\d{2})/(\d{4})", body):  # old format
        start = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        ndraws = int(head["ndraws"] or 1)
    elif m := re.search(r"Date (\d{2}) (\w{3}) (\d{4}) \(for (\d+) draws?\)", body):
        start = datetime(int(m.group(3)), MONTHS.index(m.group(2)) + 1, int(m.group(1)))
        ndraws = int(m.group(4))
    else:
        return None

    # Board lines "A: 08 14 27 33 41 -07". Indented Multiplay combinations are
    # derived from the board, so skip them and re-derive below instead.
    boards = []
    for line in body.split("\n"):
        if bm := re.match(r"^([A-Z]): ((?:-?\d+\s*)+)$", line.strip()):
            label, nums = bm.group(1), bm.group(2).split()
            if game == "powerball":
                # New format marks the PowerBall with "-"; old format doesn't,
                # but it is always the final number either way.
                boards.append(
                    (label, [int(n) for n in nums[:-1]], int(nums[-1].lstrip("-")))
                )
            elif game == "lotto" and len(nums) > 6:
                # Multiplay: 7 picks played as every 6-number combination of
                # them, each a separate paid line that wins independently.
                picks = [int(n) for n in nums]
                for i, combo in enumerate(combinations(picks, 6), 1):
                    boards.append((f"{label}{i}", list(combo), None))
            else:
                boards.append((label, [int(n) for n in nums], None))

    bought = start if bought is None else bought
    # Multiplay is already expanded above, so one board here is one paid line -
    # which is what the price was charged per, and what it must be divided by.
    pools, resolved = entered_pools(game, bought, cost, len(boards), ndraws)
    if pools is None:
        pools = [(plus_flag, pool_id)]  # unresolved: fall back to the name
    # The top tier the PRICE paid for, which is not always the tier the SMS
    # names. These two are for display and per-ticket summaries; scoring
    # iterates pools, never these.
    plus_flag, pool_id = pools[-1]

    ref = m.group(0) if (m := re.search(r"Ref:(VAS\d+)", body)) else "?"
    return Ticket(
        game, plus_flag, pool_id, start, ndraws, boards,
        ref.replace("Ref:", ""), cost, pools, bought, resolved,
    )


def load(path="lotto_sms_raw.txt"):
    raw = open(path, errors="replace").read()
    out = []
    for row in re.split(r"^Row: \d+ address=", raw, flags=re.M)[1:]:
        if m := re.match(r"([^,]*), date=(\d+), body=(.*)", row, re.S):
            # Android's SMS timestamp, in milliseconds since the epoch. Local
            # time on both sides of the era comparison: HANDOVER is a naive
            # local datetime, and reading this as UTC would put a ticket bought
            # between 00:00 and 02:00 SAST on handover day in the wrong era -
            # the one case this field exists to get right.
            bought = datetime.fromtimestamp(int(m.group(2)) / 1000)
            if t := parse(m.group(3).strip(), bought):
                out.append(t)
    return out
