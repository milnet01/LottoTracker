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

# Main balls drawn per game, which bounds INV-26's reach domain below.
MAINS = {"lotto": 6, "powerball": 5, "daily": 5}

_struct = {}
_retired = {}


def paying_combinations(game, plus_flag=0, pool_id=100):
    """Match combinations that pay, read from a live draw rather than hardcoded.

    Per pool, not per game: Lotto 5 Max and PowerBall XTRA do not share the
    base pool's division set, so one lookup applied to all of them would drop
    a genuine win whose division exists only in the pool it was won in.

    Raises on both ways this can fail to be a complete answer: no draw to read
    the divisions from, and a division read but unnameable (INV-26).
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
        table = {
            lvl["matches"].upper().strip(): lvl["winLevelName"]
            for lvl in divisions(game, rows[0]["wagerIssue"], pool_id, plus_flag)
        }
        # INV-26. check()'s pay gate is a string join, so a division no label
        # this project can build will ever equal is a hole that scores exactly
        # its own winners as losers and leaves every other division looking
        # healthy - the same silent drop as the empty set above, one step
        # finer. A table with a hole in it is not a partial answer to return.
        if strays := sorted(set(table) - buildable_labels(game)):
            raise RuntimeError(
                f"{game} plusFlag={plus_flag} pool {pool_id} pays "
                f"{', '.join(repr(s) for s in strays)}, which no label this "
                f"project builds can equal: the feed's division grammar moved, "
                f"so every win in those divisions would be scored as a loss"
            )
        _struct[key] = table
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
    """The API's own division label for this match, in the API's grammar.

    check() gates on this string, so a label the feed never publishes drops
    every win in that division with no error (LOTTO-0027). Two of the three
    forms below were wrong until 2026-08-03: the feed spells the PowerBall out
    in full where this built an abbreviation, and it names the PowerBall-only
    division with no digit and no plus sign at all, where this built both. 53
    wins read as losses. tools/verify_pools.py asserts that every division the
    feed publishes is reachable from here, which is what caught it, and
    paying_combinations() now raises on one that is not (INV-26).
    """
    if not special:
        return f"MATCH {hits}"
    if game == "lotto":
        return f"MATCH {hits} + BONUS"
    return "MATCH POWERBALL" if hits == 0 else f"MATCH {hits} + POWERBALL"


def buildable_labels(game):
    """Every division label api_label() can return for this game (INV-26).

    The domain is bounded on purpose, and both bounds carry weight: sweeping
    wider than the game's main-ball count weakens the guard silently, and
    trying a special hit for Daily Lotto would too - match() returns
    special=False for it unconditionally, so "MATCH 3 + POWERBALL" is a label
    daily can never produce in production and must not count as buildable.
    """
    specials = (False, True) if game in ("lotto", "powerball") else (False,)
    return {
        api_label(game, hits, special)
        for hits in range(MAINS[game] + 1)
        for special in specials
    }


def site_label(game, hits, special):
    tag = " + Bonus" if game == "lotto" else " + PowerBall"
    return f"{hits}" + (tag if special else "")


def retired_divisions(game, plus_flag=0, pool_id=100):
    """Divisions this pool's ARCHIVE era paid that the current set cannot name.

    paying_combinations() reads the division set from the pool's NEWEST draw,
    and check() drops any line whose label is absent from it. A division that
    existed before the June 2026 handover and has no current equivalent takes
    every one of its winners with it, silently: the cardinal rule in its
    omission form, one step earlier than INV-22's money path, where the line
    never reaches pricing at all (INV-31, LOTTO-0023).

    **Per pool, and one payout page - not one per draw.** What moves at a
    handover is the pool's division STRUCTURE, so the last archive draw before
    the break samples the era that ended. Asking the question per line instead
    would scrape a payout page per (pool, draw) scored, because every LOSING
    line reaches this same branch: hundreds of fetches to answer a structural
    question six of them settle.

    **The plain "<n>" key is the one thing the page does not say plainly, and
    reading it wrong is worse than not asking.** Lotto archive pages spell
    Division 8 as "2 + Bonus" on some draws and a bare "2" on others; both
    shapes state "eight prize divisions" in prose and carry exactly eight
    rows, so it is one division inconsistently labelled rather than two
    (measured 2026-08-12 across 26 cached Lotto pages - amount() already leans
    on the same equivalence from the other direction). A plain key whose
    bonus-qualified sibling is absent is therefore read as whichever tier the
    current set does carry, and only a key that no reading can place is
    reported. Read the other way it would flag every match-2-without-bonus
    line in the archive era as a possible win, which is this project's
    cardinal failure inverted - a loss reading as a win.
    """
    key = (game, plus_flag, pool_id)
    if key not in _retired:
        old = [d for d in all_draws(game, plus_flag) if d["source"] == "archive"]
        if not old:
            _retired[key] = []
            return _retired[key]
        table = payouts(game, plus_flag, old[-1]["date"])
        pays = paying_combinations(game, plus_flag, pool_id)
        specials = (False, True) if game in ("lotto", "powerball") else (False,)
        gap = set()
        for hits in range(MAINS[game] + 1):
            for special in specials:
                if site_label(game, hits, special) not in table:
                    continue
                label = api_label(game, hits, special)
                if label in pays:
                    continue
                # The ambiguous plain key: with no bonus-qualified sibling on
                # the page, it names the tier the current set does carry.
                if (
                    not special
                    and site_label(game, hits, True) not in table
                    and api_label(game, hits, True) in pays
                ):
                    continue
                gap.add(label)
        _retired[key] = sorted(gap)
    return _retired[key]


def amount(ticket, plus_flag, pool_id, draw, hits, special):
    """What this match paid, in rands. Raises if the price cannot be read.

    The pool comes from the entry being scored, never from the ticket's top
    tier: each tier runs its own draw with its own prize pool, so pricing a
    lotto/0 win off a Lotto Plus 2 ticket's pool 102 table is wrong money in
    both directions.

    **There is no "did not win" answer here** (INV-22). check() calls this only
    after the combination matched a paying division, so every call prices a line
    already known to have won. A lookup that finds nothing therefore means the
    source could not be read - not that the prize was zero - and returning 0.0
    for it is the "no data reads as no win" failure on the money path itself,
    landing as a figure indistinguishable from a real losing line. A division
    that genuinely paid nothing is a different thing and still returns its own
    0.0, because the source stated it.
    """
    where = f"{ticket.game}/{plus_flag} pool {pool_id} draw {draw['date']}"
    if draw["issue"] is not None:
        want = api_label(ticket.game, hits, special)
        rows = divisions(ticket.game, draw["issue"], pool_id, plus_flag)
        for lvl in rows:
            if lvl["matches"].upper().strip() == want:
                return lvl["winAmount"] / 100
        raise RuntimeError(
            f"{where}: won {want!r} but the API's division table "
            f"{'is empty' if not rows else 'does not carry that label'} - "
            f"cannot price a known win"
        )
    table = payouts(ticket.game, plus_flag, draw["date"])
    if (exact := site_label(ticket.game, hits, special)) in table:
        return table[exact]
    # Pre-handover draws did not all share one division structure: some list a
    # bottom tier of "2 + Bonus", others a plain "2". When the bonus-qualified
    # label is absent, the plain match is the tier that actually paid.
    if (plain := str(hits)) in table:
        return table[plain]
    raise RuntimeError(
        f"{where}: won {exact!r} but the payout page "
        f"{'could not be parsed' if not table else f'carries no {exact!r} or {plain!r} row'}"
        f" - cannot price a known win"
    )


def check(tickets=None, today=None):
    """-> list of win dicts, oldest first.

    One ticket is one entry per pool it was entered in, not one entry: a PLUS
    game cannot be bought alone, and each tier draws separately for its own
    prize pool. Scoring only the top tier checked 558 of 1,233 paid entries.
    """
    tickets = tickets if tickets is not None else load()
    today = today or datetime.now()
    wins = []
    for t in tickets:
        for plus_flag, pool_id in t.pools:
            if not scorable(t, plus_flag):
                continue  # reported per entry; never scored, never a loss
            pays = paying_combinations(t.game, plus_flag, pool_id)
            for board in t.boards:
                for d in covered(t, plus_flag):
                    hits, special = match(t, board, d)
                    label = api_label(t.game, hits, special)
                    if label not in pays:
                        continue
                    drawn = datetime.strptime(d["date"], "%Y-%m-%d")
                    wins.append(
                        {
                            "ref": t.ref,
                            "game": t.game,
                            "plus_flag": plus_flag,
                            "pool_id": pool_id,
                            "line": board[0],
                            "date": d["date"],
                            "division": pays[label],
                            "matched": site_label(t.game, hits, special),
                            "amount": amount(t, plus_flag, pool_id, d, hits, special),
                            "source": d["source"],
                            "expired": (today - drawn).days > CLAIM_DAYS,
                            "expires": (drawn + timedelta(days=CLAIM_DAYS)).date().isoformat(),
                        }
                    )
    return sorted(wins, key=lambda w: w["date"])


def uncheckable_report(tickets):
    """-> (lines, counts) for the entries nothing can score.

    Never let "no results available" read as "did not win". At entry
    granularity that rule has a case it did not have before: a ticket can be
    checkable in one pool and not another, so the count of uncheckable ENTRIES
    is reported, and the tickets behind it are split into wholly and partly
    uncheckable. A partly uncheckable ticket is still scored on its remaining
    pools and must never be counted as excluded.

    counts["wholly"] and counts["partly"] are the ticket lists themselves, so
    a caller can check that they do not overlap without recomputing them.
    """
    entries = [(t, pf) for t in tickets for pf, _ in t.pools]
    bad = [(t, pf) for t, pf in entries if not scorable(t, pf)]
    no_pool = [(t, pf) for t, pf in bad if not all_draws(t.game, pf)]
    too_old = [(t, pf) for t, pf in bad if all_draws(t.game, pf)]

    hurt = [t for t in tickets if any(not scorable(t, pf) for pf, _ in t.pools)]
    partly = [t for t in hurt if any(scorable(t, pf) for pf, _ in t.pools)]
    wholly = [t for t in hurt if not any(scorable(t, pf) for pf, _ in t.pools)]

    lines = []
    if bad:
        lines.append(
            f"{len(bad)} of {len(entries)} ENTRIES CANNOT BE CHECKED. "
            f"They are not counted below, and are NOT losses."
        )
        if too_old:
            earliest = min(all_draws(t.game, pf)[0]["date"] for t, pf in too_old)
            lines.append(
                f"  {len(too_old)} predate all draw data for their pool "
                f"(earliest: {earliest})"
            )
        if no_pool:
            # Per entry, not per ticket: the ticket's own plus_flag is its top
            # paid tier, so a ticket uncheckable only in lotto/1 would name
            # lotto/2 here.
            pools = sorted({f"{t.game}/{pf}" for t, pf in no_pool})
            lines.append(
                f"  {len(no_pool)} in a pool no results source carries: "
                f"{', '.join(pools)}"
            )
        lines.append(
            f"  affecting {len(wholly)} tickets wholly and {len(partly)} "
            f"tickets partly"
        )
        lines.append("    a partly-checkable ticket IS scored on its remaining pools, below")

    counts = {
        "entries": len(entries),
        "uncheckable": len(bad),
        "too_old": len(too_old),
        "no_pool": len(no_pool),
        "wholly": wholly,
        "partly": partly,
    }
    return lines, counts


def retired_report(tickets):
    """-> lines naming any pool whose archive era paid a division now unnameable.

    Pool-level rather than line-level, and deliberately so: the pool and the
    division label are what a reader can act on, and with no gap there are no
    dropped lines to count. If a gap ever does appear, counting the lines it
    swallows is the follow-up this makes possible - and it is only worth
    building once there is something to count (LOTTO-0023).

    A pool no source carries is skipped rather than reported here: nothing can
    be compared against an absent division set, and uncheckable_report() already
    owns that case (INV-11).
    """
    pools = sorted({(t.game, pf, pid) for t in tickets for pf, pid in t.pools})
    lines = []
    for game, plus_flag, pool_id in pools:
        if not all_draws(game, plus_flag):
            continue
        if gone := retired_divisions(game, plus_flag, pool_id):
            lines.append(
                f"  {game}/{plus_flag} pool {pool_id}: archive draws paid "
                f"{', '.join(repr(g) for g in gone)}, which the current "
                f"division set does not name"
            )
    if lines:
        lines.insert(
            0,
            "SOME ARCHIVE-ERA DIVISIONS HAVE NO CURRENT EQUIVALENT. Wins in "
            "them are dropped below, and are NOT losses.",
        )
    return lines


if __name__ == "__main__":
    all_tickets = load()
    wins = check(all_tickets)
    live = [w for w in wins if not w["expired"]]

    # A price matching no known board price means the tiers could not be
    # derived and the ticket fell back to its printed name - the behaviour this
    # scoring replaced. Loud, because the fallback is invisible otherwise.
    unresolved = [t for t in all_tickets if not t.resolved]
    if unresolved:
        print(
            f"{len(unresolved)} tickets have a price matching no board price on "
            f"record, so only the pool their name states is scored. Check the "
            f"price table in tickets.py against the operator's current prices."
        )
        print()

    lines, _ = uncheckable_report(all_tickets)
    if lines:
        print("\n".join(lines))
        print()

    # Silent today by design: it prints only when a division actually went
    # missing, and none has (INV-31).
    gone_lines = retired_report(all_tickets)
    if gone_lines:
        print("\n".join(gone_lines))
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
