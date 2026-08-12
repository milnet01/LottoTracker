#!/usr/bin/env python3
"""LOTTO-0009 INV-7 and INV-11: every ticket's price resolves to real tiers,
and a ticket checkable in one pool is never reported as wholly uncheckable.

A PLUS game cannot be bought alone - each tier draws separately for its own
prize pool - so a ticket's price per board per draw is the running sum of the
tiers it bought. That makes the price a complete statement of what was bought,
where the printed game name states only the top tier and, after the 2026-06-01
handover, not even that.

The price table below is transcribed independently rather than imported from
tickets.py. This check exists to catch a wrong derivation there, and importing
the thing under test makes the check agree with the bug -- the same lesson
verify_coverage.py already carries about history.scorable().

Two failures it must catch, both silent otherwise:

  1. the operator changes a board price, so prices match no tier and every
     affected ticket quietly reverts to name-only scoring
  2. the uncheckable report is written per ticket again, so the 11 Daily Lotto
     Plus tickets are declared uncheckable in the same run that scores their
     Daily Lotto entries

Counts move as messages arrive; what this asserts is the zero-terms and the
exit code. The name/price disagreement figure is reported, not asserted: it is
a property of the bank's wording, not of this code. It is split by era because
a post-handover disagreement means something different -- the bank stopped
printing the tier at all, so the name cannot state it even in principle.
"""

import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import check  # noqa: E402
from check import uncheckable_report  # noqa: E402
from history import all_draws  # noqa: E402
from tickets import GAME_MAP, load  # noqa: E402

DUMP = os.path.join(os.path.dirname(__file__), "..", "lotto_sms_raw.txt")

HANDOVER = datetime(2026, 6, 1)

# CUMULATIVE cost per board per draw, in whole cents: what a ticket topping out
# at that tier was charged. Not the per-tier increment -- conflating the two
# prices a R10.00 Lotto ticket at R22.50. Cheapest tier first.
CUMULATIVE = {
    ("lotto", "ithuba"): [(0, 100, 500), (1, 101, 750), (2, 102, 1000)],
    ("lotto", "sizekhaya"): [(0, 100, 500), (1, 101, 750), (2, 102, 1000)],
    ("powerball", "ithuba"): [(0, 100, 500), (1, 101, 750)],
    ("powerball", "sizekhaya"): [(0, 100, 1000), (1, 101, 1500)],
    ("daily", "ithuba"): [(0, 100, 300), (1, 101, 450)],
    ("daily", "sizekhaya"): [(0, 100, 300)],  # Daily Lotto Plus was withdrawn
}


def expected_pools(game, bought, cost, paid_lines, ndraws):
    """The pools this price paid for, or None when it matches no tier."""
    tiers = CUMULATIVE[(game, "sizekhaya" if bought >= HANDOVER else "ithuba")]
    if not paid_lines:
        return None
    unit, remainder = divmod(round(cost * 100), paid_lines * ndraws)
    if remainder:
        return None  # not an exact multiple: never round onto a valid tier
    for i, (_, _, total) in enumerate(tiers):
        if total == unit:
            return [(pf, pool) for pf, pool, _ in tiers[: i + 1]]
    return None


def dump_facts():
    """{ticket ref: (printed game name, purchase datetime)}, read from the dump.

    Both are re-read here rather than taken from the parsed Ticket, because on
    this ticket both are the thing under test: `plus_flag` is the top tier the
    PRICE paid for, which the name cross-checks, and `bought` is what selects
    the era. Reading the parser's own answer for either would agree with a
    regression instead of catching it.
    """
    out = {}
    if not os.path.exists(DUMP):
        return out
    raw = open(DUMP, errors="replace").read()
    for row in re.split(r"^Row: \d+ address=", raw, flags=re.M)[1:]:
        if not (m := re.match(r"([^,]*), date=(\d+), body=(.*)", row, re.S)):
            continue
        body = m.group(3).strip()
        head = re.search(
            r"Played R[\d,.]+ ([A-Za-z0-9 ]+?)(?: for \d+ draw\(?s?\)?)?\s*$",
            body.split("\n")[0].strip(),
        )
        ref = re.search(r"Ref:(VAS\d+)", body)
        if head and ref:
            bought = datetime.fromtimestamp(int(m.group(2)) / 1000)
            out[ref.group(1)] = (head.group(1).strip().lower(), bought)
    return out


def reaches(ticket, plus_flag):
    """Whether any source reaches back to this entry's first draw.

    Recomputed here rather than imported from history.scorable(): the report
    under test is built on that predicate, so importing it would let a
    regressed one pass this check as well.
    """
    rows = all_draws(ticket.game, plus_flag)
    return bool(rows) and ticket.start.strftime("%Y-%m-%d") >= rows[0]["date"]


def main(argv=()):
    tickets = load()
    facts = dump_facts()
    bad = unresolved = 0
    disagree = {"pre": 0, "post": 0}

    for t in tickets:
        name, bought = facts.get(t.ref, (None, None))
        # The era decides the tier table, so a parser that stopped reading the
        # SMS timestamp - falling back to the first DRAW date, which is 1-4
        # days later on most tickets - would price a handover-week ticket in
        # the wrong era. Compared against the dump, not against itself.
        if bought is not None and bought != t.bought:
            print(f"  ERA {t.ref}: parser has {t.bought}, dump says {bought}")
            bad += 1

        want = expected_pools(t.game, t.bought, t.cost, len(t.boards), t.ndraws)
        if want is None:
            print(
                f"  UNRESOLVED {t.ref}: {t.game} priced over {len(t.boards)} "
                f"line(s) x {t.ndraws} draw(s) matches no tier total"
            )
            unresolved += 1
            bad += 1
            continue
        if t.pools != want:
            print(f"  POOLS {t.ref}: parser says {t.pools}, price says {want}")
            bad += 1
        elif not t.resolved:
            # The right pools reached by the wrong road: a fallback that
            # happens to agree still means the price did not resolve.
            print(f"  UNFLAGGED {t.ref}: pools correct but reported unresolved")
            bad += 1

        named = GAME_MAP.get(name or "")
        if named and named[1] != want[-1][0]:
            disagree["post" if t.bought >= HANDOVER else "pre"] += 1

    entries = sum(len(t.pools) for t in tickets)
    print(
        f"{len(tickets)} tickets, {entries} entries, {unresolved} unresolved, "
        f"{disagree['pre'] + disagree['post']} name/price disagreements "
        f"({disagree['pre']} pre-handover, {disagree['post']} post-handover)"
    )

    if "--era-audit" in argv:
        # Why the era comes from the purchase moment rather than Ticket.start:
        # most tickets are bought days before their first draw, so the two
        # readings can straddle a price change. They agree on every ticket in
        # the dump today, which makes this a latent boundary case, not a live
        # miscount - and this is what says so.
        lag = [
            (t.start.date() - t.bought.date()).days
            for t in tickets
            if t.start.date() != t.bought.date()
        ]
        differ = sum(
            1 for t in tickets
            if (t.bought >= HANDOVER) != (t.start >= HANDOVER)
        )
        # Reported as a difference with its signed range, not as "later": the
        # comparison is an inequality, and a negative day count would mean a
        # start date BEFORE the purchase, which is a different anomaly.
        span = f" (by {min(lag)} to {max(lag)} days)" if lag else ""
        print(
            f"era audit: {len(lag)} of {len(tickets)} tickets have a start date "
            f"differing from the purchase date{span}, {differ} where the two "
            f"readings select different eras"
        )

    # INV-11, asserted against check.py's actual report rather than against the
    # derivation: a ticket with one checkable pool and one uncheckable one must
    # be reported as partly uncheckable and still scored on the rest.
    _, counts = uncheckable_report(tickets)
    partly = [
        t
        for t in tickets
        if any(reaches(t, pf) for pf, _ in t.pools)
        and not all(reaches(t, pf) for pf, _ in t.pools)
    ]
    wrong = [t for t in partly if t in counts["wholly"]]
    double = [t for t in counts["wholly"] if t in counts["partly"]]
    for t in wrong:
        print(f"  WHOLLY {t.ref}: checkable in one pool, reported as excluded")
    for t in double:
        print(f"  DOUBLE-COUNTED {t.ref}: reported both wholly and partly")

    print(
        f"{len(partly)} partly-uncheckable tickets, {len(wrong)} reported as "
        f"wholly uncheckable, {len(double)} double-counted"
    )

    # INV-22 (LOTTO-0007a): a known win whose price cannot be looked up must
    # RAISE, never price as R0.00. check.py::amount() is called only after the
    # combination matched a paying division, so there is no "did not win"
    # answer for it to return - an empty or unrecognised division table means
    # the source could not be read, and R0.00 for that is indistinguishable
    # from a real losing line in every consumer, the page included.
    #
    # Driven with doubles rather than against real data on purpose: today all
    # 67 archive draws parse and no win prices at R0.00 (measured 2026-08-02),
    # so real data cannot exercise this at all. That is exactly why it needs a
    # case - the failure arrives the day a payout page changes shape.
    unpriceable = 0
    real_payouts, real_divisions = check.payouts, check.divisions

    class _T:
        game = "lotto"

    archive = {"date": "2025-03-01", "issue": None, "source": "archive"}
    api = {"date": "2026-07-01", "issue": 2500, "source": "api"}
    probes = [
        ("archive payout page unparseable", lambda: {}, None, archive),
        ("archive table lacks the won label", lambda: {"6": 1.0}, None, archive),
        ("API division table empty", None, lambda: [], api),
        ("API table lacks the won label", None,
         lambda: [{"matches": "MATCH 6", "winAmount": 100}], api),
    ]
    try:
        for name, pay, div, draw in probes:
            check.payouts = (lambda *a, **k: pay()) if pay else real_payouts
            check.divisions = (lambda *a, **k: div()) if div else real_divisions
            try:
                got = check.amount(_T(), 0, 100, draw, 5, True)
                print(f"  PRICED A BLIND WIN at R{got:,.2f}: {name}")
                unpriceable += 1
            except RuntimeError:
                pass
        # The converse, and it must not be broken by the guard: a division the
        # source DOES carry and states as zero is a real answer, not a gap.
        check.payouts, check.divisions = lambda *a, **k: {"5 + Bonus": 0.0}, real_divisions
        if check.amount(_T(), 0, 100, archive, 5, True) != 0.0:
            print("  a division the source states as R0.00 no longer prices as 0.0")
            unpriceable += 1
    finally:
        check.payouts, check.divisions = real_payouts, real_divisions

    print(f"unpriceable-win guard: {len(probes)} blind-lookup probes, {unpriceable} mispriced")

    # LOTTO-0027: every division the feed publishes must be REACHABLE by a
    # label check.py can build. check()'s pay gate is a string join --
    # `if api_label(...) not in pays: continue` -- so a division this project
    # can never name is one whose wins are all scored as losses, silently.
    # Not hypothetical: the feed pays "MATCH 5 + PowerBall" and "MATCH
    # PowerBall", api_label() built "MATCH 5 + PB" and "MATCH 0 + PB", and 53
    # PowerBall wins read as losses until this case was written.
    #
    # The direction is the whole check and must not be reversed: every FEED
    # division must be constructible. The converse is false -- for Daily Lotto
    # api_label() builds "MATCH 0" and "MATCH 1" while its published divisions
    # start at two matches, and "MATCH 0" is unpublished on every game.
    # ("MATCH 6" is NOT the example to reach for: mains caps daily at five, so
    # that label is never built for it in the first place.)
    #
    # Live pools only, derived from the tickets rather than listed here, which
    # is also what keeps daily/1 out: no source publishes it, so
    # paying_combinations() would (correctly) raise for it.
    unreachable = vacuous = 0
    mains = {"lotto": 6, "powerball": 5, "daily": 5}
    pools = sorted(
        {(t.game, pf, pool) for t in tickets for pf, pool in t.pools if reaches(t, pf)}
    )
    # Anti-vacuity floor, the same shape INV-3 and INV-6 carry. The pool set is
    # derived, so a partial archive shrinks what is checked without failing,
    # and every division in an EMPTY division set is trivially reachable -- so
    # a feed that returned no divisions at all would report 0 unreachable and
    # pass. Both are asserted rather than left to the printed count, which §7
    # of the spec has already demoted to a non-asserted figure.
    if not pools:
        print("  NO LIVE POOLS: nothing was checked for division-label reach")
        vacuous += 1
    for game, plus_flag, pool_id in pools:
        # (False, True) only where match() can report a special hit at all.
        # Derived here rather than imported from check.buildable_labels(), for
        # the reason the header gives about the price table: that function is
        # what decides whether the runtime raise fires, so importing it would
        # let a domain widened by mistake pass this check as well. A domain
        # narrowed by mistake shows up the other way, as a raise below on a
        # healthy pool.
        buildable = {
            check.api_label(game, hits, special)
            for hits in range(mains[game] + 1)
            for special in ((False, True) if game in ("lotto", "powerball") else (False,))
        }
        try:
            published = check.paying_combinations(game, plus_flag, pool_id)
        except RuntimeError as exc:
            # INV-26's runtime half got there first, which is the design. It is
            # reported rather than allowed to abort, so the remaining pools are
            # still swept and the exit code stays the signal. Tagged by what
            # happened rather than by which raise it was: the other one a live
            # pool can hit is "no recent draw", which is also a pool that could
            # not be swept, and the message below names which it was.
            print(f"  RAISED {game}/{plus_flag} pool {pool_id}: {exc}")
            unreachable += 1
            continue
        if not published:
            print(
                f"  NO DIVISIONS {game}/{plus_flag} pool {pool_id}: the division "
                f"table is empty, so reach passes over nothing"
            )
            vacuous += 1
        for label in published:
            if label not in buildable:
                print(
                    f"  UNREACHABLE {game}/{plus_flag} pool {pool_id}: the feed pays "
                    f"{label!r}, which no label this project builds can equal"
                )
                unreachable += 1
    print(
        f"division-label reach: {len(pools)} live pools, {unreachable} unreachable "
        f"divisions, {vacuous} vacuous"
    )

    # INV-26's runtime half (LOTTO-0026 step 2): paying_combinations() must
    # refuse a division table it cannot fully name, rather than returning one
    # with a hole in it. The sweep above only sees the pools the dump reaches,
    # and only when someone runs this; the raise covers whatever pool a scoring
    # run touches, in the run that would otherwise have mis-scored it.
    #
    # Driven with doubles for the same reason the unpriceable-win probes above
    # are: the live feed is healthy, so real data cannot exercise any of it.
    unguarded = 0
    real_draws, real_divs = check.draws, check.divisions
    reach_probes = [
        # The state that actually shipped until 2026-08-03: api_label() built
        # "MATCH 5 + PB" against a feed paying "MATCH 5 + PowerBall", and 53
        # wins read as losses (LOTTO-0027). Read from the feed's side here.
        ("powerball pays a division this project cannot name",
         "powerball", ["MATCH 5 + PB"], True),
        # The converse, which must NOT raise: the direction is one-way, and a
        # feed publishing fewer divisions than api_label() can build is the
        # normal case, not a grammar move. Reversing this raises on every pool.
        ("lotto publishes a subset of the buildable labels",
         "lotto", ["MATCH 6", "MATCH 5 + BONUS", "MATCH 3"], False),
        # The domain bound. The same string is buildable for powerball and not
        # for daily, because match() never reports a special hit for daily.
        ("daily pays a division outside its own domain",
         "daily", ["MATCH 3 + POWERBALL"], True),
    ]
    try:
        for name, game, labels, want_raise in reach_probes:
            check.draws = lambda *a, **k: [{"plusFlag": 0, "wagerIssue": 1}]
            check.divisions = lambda *a, **k: [
                {"matches": lbl, "winLevelName": lbl} for lbl in labels
            ]
            check._struct.clear()  # the answer is memoised per pool
            try:
                check.paying_combinations(game, 0, 100)
                raised = False
            except RuntimeError:
                raised = True
            if raised != want_raise:
                print(f"  {'NO RAISE' if want_raise else 'FALSE RAISE'}: {name}")
                unguarded += 1
    finally:
        check.draws, check.divisions = real_draws, real_divs
        check._struct.clear()

    print(
        f"unnameable-division guard: {len(reach_probes)} probes, "
        f"{unguarded} unguarded"
    )

    # INV-31 (LOTTO-0023): the reach check above asks whether every division
    # the feed publishes TODAY can be named. This asks the same question of the
    # era that ended - a division the archive era paid and the current set does
    # not carry drops every one of its winners at check()'s pay gate, one step
    # before INV-22's money path can refuse.
    #
    # Live half first: no pool may currently carry such a gap. It passes today
    # (measured 2026-08-12: six pools, none), which is exactly why the probes
    # below exist - a check that can only ever print zero proves nothing about
    # whether it can still see.
    stale = 0
    for game, plus_flag, pool_id in pools:
        if gone := check.retired_divisions(game, plus_flag, pool_id):
            print(
                f"  RETIRED DIVISION {game}/{plus_flag} pool {pool_id}: archive "
                f"draws paid {', '.join(repr(g) for g in gone)}, which the "
                f"current set does not name - those wins are scored as losses"
            )
            stale += 1

    # Both arms, because each fails in the opposite direction and only one of
    # them is caught by the live half above.
    #
    # The ambiguous-label arm is not a hypothetical: all three Lotto pools
    # sample a page whose bottom row reads "2" rather than "2 + Bonus", and
    # both spellings are Division 8 (each page states "eight prize divisions"
    # and carries eight rows). Read as a distinct "Match 2" division it would
    # report a gap on every Lotto pool and flag every match-2-without-bonus
    # line in the archive era as a possible win - a loss reading as a win,
    # which is this project's cardinal failure inverted.
    blind = 0
    real_pays = check.paying_combinations
    gap_probes = [
        # A division the current set genuinely cannot name, in a pool whose
        # archive pages do carry it. Must be reported.
        ("a genuinely retired division", "MATCH 3 + BONUS", ["MATCH 3 + BONUS"]),
        # The plain "2" key when the current set carries neither reading of it:
        # no reading places it, so it is a real gap and must NOT be swallowed
        # by the ambiguity rule.
        ("the plain key when neither reading exists", "MATCH 2 + BONUS", ["MATCH 2"]),
    ]
    try:
        for name, drop, want in gap_probes:
            def _pays(g, pf=0, pid=100, _drop=drop):
                table = dict(real_pays(g, pf, pid))
                table.pop(_drop, None)
                return table
            check.paying_combinations = _pays
            check._retired.clear()
            got = check.retired_divisions("lotto", 0, 100)
            if got != want:
                print(f"  MISSED {name}: expected {want}, got {got}")
                blind += 1
        # The converse, and the arm that guards the live result above: with the
        # real division set nothing may be reported, or every run cries wolf.
        check.paying_combinations = real_pays
        check._retired.clear()
        if noise := check.retired_divisions("lotto", 0, 100):
            print(f"  FALSE GAP on a healthy pool: {noise}")
            blind += 1
    finally:
        check.paying_combinations = real_pays
        check._retired.clear()

    print(
        f"retired-division guard: {len(pools)} live pools, {stale} carrying a "
        f"retired division, {len(gap_probes) + 1} probes, {blind} blind"
    )

    return (
        0
        if bad == 0
        and not wrong
        and not double
        and not unpriceable
        and not unreachable
        and not vacuous
        and not unguarded
        and not stale
        and not blind
        else 1
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
