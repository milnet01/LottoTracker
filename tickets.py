#!/usr/bin/env python3
"""Parse Standard Bank lottery ticket SMSes and score them against real draws.

Two SMS eras exist, because the bank changed its wording when Sizekhaya took
over the licence on 2026-06-01:

  old  Played R10.00 Lotto Plus 2 for 1 draw(s)      new  Played R300.00 Powerball
       Date 09/11/2022 to 09/11/2022                      Date 12 Jun 2026 (for 10 draws)
       A: 02 03 26 36 45 52                               A: 02 18 22 32 48 -03

The trap: in the OLD format a PowerBall ticket's final number is the PowerBall
itself with nothing to mark it, while the NEW format prefixes it with "-".
Treating that last number as a main number scores every PowerBall ticket wrong.

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


class Ticket:
    def __init__(self, game, plus_flag, pool_id, start, ndraws, boards, ref):
        self.game, self.plus_flag, self.pool_id = game, plus_flag, pool_id
        self.start, self.ndraws, self.boards, self.ref = start, ndraws, boards, ref

    def __repr__(self):
        return f"<{self.ref} {self.game} x{self.ndraws} from {self.start.date()}>"


def parse(body):
    """Return a Ticket, or None if this SMS is not a ticket purchase."""
    # Old format ends "... for 1 draw(s)"; new format ends at the game name.
    head = re.search(
        r"Played R[\d,.]+ ([A-Za-z0-9 ]+?)(?: for (\d+) draw\(?s?\)?)?\s*$",
        body.split("\n")[0].strip(),
    )
    if not head:
        return None

    name = head.group(1).strip().lower()
    if name not in GAME_MAP:
        return None
    game, plus_flag, pool_id = GAME_MAP[name]

    if m := re.search(r"Date (\d{2})/(\d{2})/(\d{4})", body):  # old format
        start = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        ndraws = int(head.group(2) or 1)
    elif m := re.search(r"Date (\d{2}) (\w{3}) (\d{4}) \(for (\d+) draws?\)", body):
        start = datetime(int(m.group(3)), MONTHS.index(m.group(2)) + 1, int(m.group(1)))
        ndraws = int(m.group(4))
    else:
        return None

    # Board lines "A: 02 18 22 32 48 -03". Indented Multiplay combinations are
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

    ref = m.group(0) if (m := re.search(r"Ref:(VAS\d+)", body)) else "?"
    return Ticket(game, plus_flag, pool_id, start, ndraws, boards, ref.replace("Ref:", ""))


def load(path="lotto_sms_raw.txt"):
    raw = open(path, errors="replace").read()
    out = []
    for row in re.split(r"^Row: \d+ address=", raw, flags=re.M)[1:]:
        if m := re.match(r"([^,]*), date=(\d+), body=(.*)", row, re.S):
            if t := parse(m.group(3).strip()):
                out.append(t)
    return out
