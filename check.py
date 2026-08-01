#!/usr/bin/env python3
"""Score every ticket against every draw it covers, across both eras.

Prize lookup differs by era, which is the only real complexity here:
  - API draws (2026-06-01 on) carry a draw number, so divisions() prices them
  - archive draws do not, so the payout page for that date is scraped instead

Both are cached, so a re-run is cheap.
"""

from datetime import datetime, timedelta

from backfill import payouts
from history import all_draws, covered, scorable
from results import divisions, draws
from tickets import load

CLAIM_DAYS = 365  # SA prizes expire a year after the draw

_struct = {}


def paying_combinations(game, plus_flag=0, pool_id=100):
    """Match combinations that pay, read from a live draw rather than hardcoded.

    Per pool, not per game: Lotto 5 Max and PowerBall XTRA do not share the
    base pool's division set, so one lookup applied to all of them would drop
    a genuine win whose division exists only in the pool it was won in.
    """
    key = (game, plus_flag, pool_id)
    if key not in _struct:
        rows = [x for x in draws(game, 50) if x["plusFlag"] == plus_flag]
        if not rows:
            # Returning {} here would score every line in the pool as a loss
            # with no diagnostic - the "no data reads as no win" failure this
            # project exists to avoid.
            raise RuntimeError(
                f"no recent draw for {game} plusFlag={plus_flag}: cannot "
                f"establish which divisions pay, so nothing can be scored"
            )
        _struct[key] = {
            lvl["matches"].upper().strip(): lvl["winLevelName"]
            for lvl in divisions(game, rows[0]["wagerIssue"], pool_id, plus_flag)
        }
    return _struct[key]


def match(ticket, board, draw):
    """-> (main hits, special hit)"""
    nums = board[1]
    if ticket.game == "powerball":
        return len(set(nums) & set(draw["main"])), board[2] == draw["special"]
    if ticket.game == "lotto":
        return len(set(nums) & set(draw["main"])), draw["special"] in nums
    return len(set(nums) & set(draw["main"])), False


def api_label(game, hits, special):
    tag = " + BONUS" if game == "lotto" else " + PB"
    return f"MATCH {hits}" + (tag if special else "")


def site_label(game, hits, special):
    tag = " + Bonus" if game == "lotto" else " + PowerBall"
    return f"{hits}" + (tag if special else "")


def amount(ticket, draw, hits, special):
    """What this match paid, in rands. 0.0 if it did not win."""
    if draw["issue"] is not None:
        want = api_label(ticket.game, hits, special)
        for lvl in divisions(
            ticket.game, draw["issue"], ticket.pool_id, ticket.plus_flag
        ):
            if lvl["matches"].upper().strip() == want:
                return lvl["winAmount"] / 100
        return 0.0
    table = payouts(ticket.game, ticket.plus_flag, draw["date"])
    if (exact := site_label(ticket.game, hits, special)) in table:
        return table[exact]
    # Pre-handover draws did not all share one division structure: some list a
    # bottom tier of "2 + Bonus", others a plain "2". When the bonus-qualified
    # label is absent, the plain match is the tier that actually paid.
    return table.get(str(hits), 0.0)


def check(tickets=None, today=None):
    """-> list of win dicts, oldest first."""
    tickets = tickets if tickets is not None else load()
    today = today or datetime.now()
    wins = []
    for t in tickets:
        if not scorable(t):
            continue  # reported separately; never scored, never a loss
        pays = paying_combinations(t.game, t.plus_flag, t.pool_id)
        for board in t.boards:
            for d in covered(t):
                hits, special = match(t, board, d)
                if api_label(t.game, hits, special) not in pays:
                    continue
                drawn = datetime.strptime(d["date"], "%Y-%m-%d")
                wins.append(
                    {
                        "ref": t.ref,
                        "game": t.game,
                        "plus_flag": t.plus_flag,
                        "line": board[0],
                        "date": d["date"],
                        "division": pays[api_label(t.game, hits, special)],
                        "matched": site_label(t.game, hits, special),
                        "amount": amount(t, d, hits, special),
                        "source": d["source"],
                        "expired": (today - drawn).days > CLAIM_DAYS,
                        "expires": (drawn + timedelta(days=CLAIM_DAYS)).date().isoformat(),
                    }
                )
    return sorted(wins, key=lambda w: w["date"])


if __name__ == "__main__":
    all_tickets = load()
    wins = check(all_tickets)
    live = [w for w in wins if not w["expired"]]

    # Never let "no results available" read as "did not win". Two distinct
    # reasons, reported separately so neither hides behind the other.
    unscorable = [t for t in all_tickets if not scorable(t)]
    no_pool = [t for t in unscorable if not all_draws(t.game, t.plus_flag)]
    too_old = [t for t in unscorable if t not in no_pool]
    if unscorable:
        print(
            f"{len(unscorable)} of {len(all_tickets)} tickets CANNOT BE CHECKED. "
            f"They are not counted below, and are NOT losses."
        )
        if too_old:
            earliest = min(
                all_draws(t.game, t.plus_flag)[0]["date"] for t in too_old
            )
            print(f"  {len(too_old)} predate all draw data (earliest: {earliest})")
        if no_pool:
            pools = sorted({f"{t.game}/{t.plus_flag}" for t in no_pool})
            print(f"  {len(no_pool)} in a pool no results source carries: {', '.join(pools)}")
        print()

    print(f"{len(wins)} winning lines total; {len(live)} still claimable\n")
    for w in live:
        print(
            f"  {w['date']}  {w['ref']}  {w['game']}/{w['plus_flag']}  "
            f"line {w['line']:3}  {w['division']:6} (match {w['matched']})  "
            f"R{w['amount']:>9,.2f}  expires {w['expires']}"
        )
    print(f"\nSTILL CLAIMABLE: R{sum(w['amount'] for w in live):,.2f}")
    print(f"(lifetime total incl. expired: R{sum(w['amount'] for w in wins):,.2f})")
