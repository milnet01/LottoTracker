#!/usr/bin/env python3
"""LOTTO-0036 INV-57..INV-60: cost against winnings, per period.

    python3 tools/verify_periods.py                            # all four
    python3 tools/verify_periods.py --list
    python3 tools/verify_periods.py --break attribute_by_purchase  # must FAIL

This item is greenfield, so there was no pre-fix code to red-test against.
`--break` is what makes "every case observed failing" reproducible rather than
a one-off hand edit, exactly as CLAUDE.md records for verify_page.py and
verify_expiry.py.

WHY THIS IS A NEW FILE AND NOT FOUR CASES IN verify_page.py.

Every case in verify_page.py is RENDERER-only: fixture_model() is a
hand-authored dict and render_pure() installs an all_draws double that RAISES,
to prove page.py performs no I/O. Nothing in that file calls
serve.build_model(). All four breaks below live in the BUILDER, so a case
placed there could not be observed failing under its own break and would assert
only what its author typed. (LOTTO-0002 INV-15's prose describes its fixture as
"built by running the real builder"; the shipped case does not, which is filed
against LOTTO-0007.)

serve.py::period_buckets() takes its two data sources as arguments precisely so
this file can drive the real rules over synthetic tickets. INV-57 additionally
reconciles against the real dump, so:

IT GOES IN local-CI.sh's DATA-DEPENDENT LANE, and it has no weak mode. One case
needs real data:

    periods_reconcile   lotto_sms_raw.txt AND the merged draw record

The other three are synthetic and would pass on a bare runner - but a verifier
that silently skipped its one rot-prone case is the degraded-mode trap
verify_privacy.py already carries and local-CI.sh's header warns about, so the
file fails as a whole without its inputs rather than reporting a weaker pass.

PRIVACY. No message content and no ticket reference is printed. The fixtures
use the one sentinel reference and names that are not reference-shaped at all,
per CLAUDE.md.
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import history  # noqa: E402
import serve  # noqa: E402
from tickets import Ticket, load  # noqa: E402

SENTINEL = "VAS00000000000"
UNRESOLVED_REF = "unresolved-ticket"  # deliberately NOT reference-shaped

ACTIVE_CASE = None  # set by main(); a break fires only in its own case


def need(cond, msg):
    if not cond:
        raise AssertionError(msg)


def ticket(ref=SENTINEL, game="lotto", start="2026-03-28", ndraws=10,
           boards=1, resolved=True):
    """A Ticket carrying only what the bucketing reads. No real data anywhere."""
    d = datetime.datetime.strptime(start, "%Y-%m-%d")
    return Ticket(game, 0, 100, d, ndraws, [[i, 1, 2, 3, 4, 5] for i in
                                            range(boards)],
                  ref, 5.0 * boards * ndraws, [(0, 100)], d, resolved)


def increments(_game, _era):
    """500c per board per draw - a round number so the arithmetic is readable."""
    return {0: 500}


def draws(*dates):
    """An entry_draws function returning fixed dates for every entry."""
    return lambda _t, _pf: list(dates)


def buckets_of(result, kind):
    return {b["key"]: b for b in result["buckets"] if b["kind"] == kind}


# --------------------------------------------------------------- the cases


def periods_reconcile():
    """INV-57 - buckets plus the residue equal the compared spend, both kinds.

    Over the REAL dump, because the rule this locks is that no cent is lost or
    double-counted, and a synthetic fixture proves that only of itself. The
    expected figures are recomputed here from tickets.py::TIER_PRICES and
    history.covered() - never by calling serve.py's own tier_increments(),
    which is the code under test.
    """
    from tickets import HANDOVER, TIER_PRICES

    all_tickets = load()
    need(all_tickets, "lotto_sms_raw.txt yielded no tickets")
    import check

    wins = check.check(all_tickets)

    compared = 0
    for t in all_tickets:
        if not t.resolved:
            continue
        era = "sizekhaya" if t.bought >= HANDOVER else "ithuba"
        inc = {pf: i for pf, _c, i in TIER_PRICES[(t.game, era)]}
        for pf, _pool in t.pools:
            if history.scorable(t, pf):
                compared += inc[pf] * len(t.boards) * t.ndraws

    got = serve.period_buckets(
        all_tickets, wins,
        lambda t, pf: ([d["date"] for d in history.covered(t, pf)]
                       if history.scorable(t, pf) else None),
        serve.tier_increments,
    )
    months = sum(b["spend_cents"] for b in got["buckets"] if b["kind"] == "month")
    years = sum(b["spend_cents"] for b in got["buckets"] if b["kind"] == "year")
    res = got["no_result_cents"]
    need(months + res == compared,
         f"months {months} + residue {res} != compared spend {compared}")
    need(years + res == compared,
         f"years {years} + residue {res} != compared spend {compared}")
    need(got["buckets"], "the real dump produced no buckets at all")

    # The WIN side carries an assertion too, so `wins` above - which is what
    # drags this case onto the network and makes it the slowest in the suite -
    # is load-bearing rather than computed and discarded. A conservation
    # identity rather than a re-derivation: the same wins filed by month and by
    # year must total the same, so a win landing in a month bucket but not its
    # year (or the reverse) fails here.
    won_m = sum(b["won_cents"] for b in got["buckets"] if b["kind"] == "month")
    won_y = sum(b["won_cents"] for b in got["buckets"] if b["kind"] == "year")
    need(won_m == won_y,
         f"month buckets carry {won_m}c won and year buckets {won_y}c - the "
         f"same wins filed under two period kinds must total the same")
    return (f"{len(got['buckets'])} buckets, {compared}c reconciled, "
            f"{won_m}c won filed consistently")


def periods_by_draw_date():
    """INV-58 - a cost AND a win belong to the period of the draw.

    The ticket is bought in the last days of March and its draws run into
    April, so a purchase-dated implementation yields ONE bucket where the
    contract requires two. Its win falls in the SECOND month, which is what
    gives the "and a win" half of the invariant an assertion at all.
    """
    t = ticket(start="2026-03-28", ndraws=4)
    dates = ["2026-03-29", "2026-03-31", "2026-04-02", "2026-04-05"]
    win = {"ref": SENTINEL, "date": "2026-04-05", "amount": 20.0}
    got = serve.period_buckets([t], [win], draws(*dates), increments)
    m = buckets_of(got, "month")
    need(set(m) == {"2026-03", "2026-04"},
         f"expected March and April buckets, got {sorted(m)}")
    need(m["2026-03"]["spend_cents"] == 1000,
         f"March spend {m['2026-03']['spend_cents']}, expected 1000 (2 draws)")
    need(m["2026-04"]["spend_cents"] == 1000,
         f"April spend {m['2026-04']['spend_cents']}, expected 1000 (2 draws)")
    # The win half. A builder keying winnings on the purchase date puts this
    # in March, which is the whole point of the case.
    need(m["2026-04"]["won_cents"] == 2000,
         f"April won {m['2026-04']['won_cents']}, expected 2000")
    need(m["2026-03"]["won_cents"] == 0,
         f"March won {m['2026-03']['won_cents']}, expected 0 - the win was in April")
    return "spend 1000/1000 across two months, win in the second"


def periods_over_checkable():
    """INV-59 - both sides drawn over the scorable entries of RESOLVED tickets.

    The fixture carries an unresolved ticket that WINS. The live dump holds no
    such case (unresolved tickets is 0), so without it the win-side clause
    could never fail and would be an unfalsifiable assertion.
    """
    good = ticket(ref=SENTINEL, start="2026-05-01", ndraws=2)
    bad = ticket(ref=UNRESOLVED_REF, start="2026-05-01", ndraws=2,
                 resolved=False)
    wins = [
        {"ref": SENTINEL, "date": "2026-05-02", "amount": 10.0},
        {"ref": UNRESOLVED_REF, "date": "2026-05-02", "amount": 99.0},
    ]
    got = serve.period_buckets([good, bad], wins,
                               draws("2026-05-02", "2026-05-09"), increments)
    m = buckets_of(got, "month")
    need(set(m) == {"2026-05"}, f"expected one May bucket, got {sorted(m)}")
    need(m["2026-05"]["spend_cents"] == 1000,
         f"May spend {m['2026-05']['spend_cents']}, expected 1000 - the "
         "unresolved ticket's cost must not be in it")
    need(m["2026-05"]["won_cents"] == 1000,
         f"May won {m['2026-05']['won_cents']}, expected 1000 - the "
         "unresolved ticket's R99.00 win must not be in it")
    return "unresolved ticket excluded from both sides"


def empty_period_is_absent():
    """INV-60 - a bucket exists only where a scorable, resolved draw fell.

    Two halves, and both are the cardinal rule: a month the draws SKIP gets no
    bucket, and a month reachable only through an UNRESOLVED ticket gets none
    either. Either would render R0.00/R0.00, an R0.00 meaning "excluded".
    """
    t = ticket(start="2026-01-05", ndraws=2)
    # Draws in January and March. February is skipped entirely.
    got = serve.period_buckets([t], [], draws("2026-01-05", "2026-03-05"),
                               increments)
    m = buckets_of(got, "month")
    need("2026-02" not in m,
         "a February bucket exists, but no draw fell in February")
    need(set(m) == {"2026-01", "2026-03"}, f"unexpected buckets {sorted(m)}")

    # THE WIN SIDE of the same rule, and nothing exercised it. period_buckets()
    # says "the key set comes from the SPEND side; a win whose period carries
    # no spend is dropped rather than conjuring a bucket" - and every case here
    # passed wins=[] or a win in a month that already had spend, so replacing
    # both of its `if … in months/years` guards with setdefault left all four
    # green. A conjured bucket renders R0.00 spend against a real win: a period
    # the ledger never charged for, presented as one it won in.
    stray = [{"ref": t.ref, "date": "2026-02-11", "amount": 25.0}]
    got_stray = serve.period_buckets([t], stray,
                                     draws("2026-01-05", "2026-03-05"),
                                     increments)
    m_stray = buckets_of(got_stray, "month")
    need("2026-02" not in m_stray,
         "a win dated in February conjured a February bucket, which carries "
         "no spend - INV-60's win side")
    need(set(m_stray) == {"2026-01", "2026-03"},
         f"the stray win changed the key set: {sorted(m_stray)}")

    only_unresolved = ticket(ref=UNRESOLVED_REF, start="2026-06-01",
                             ndraws=1, resolved=False)
    got2 = serve.period_buckets([t, only_unresolved], [],
                                lambda _t, _pf: ["2026-06-02"] if
                                _t.ref == UNRESOLVED_REF else ["2026-01-05"],
                                increments)
    m2 = buckets_of(got2, "month")
    need("2026-06" not in m2,
         "June has a bucket, but only an unresolved ticket's draw fell in it")
    return "skipped month absent; unresolved-only month absent"


CASES = [
    ("periods_reconcile", "INV-57", periods_reconcile),
    ("periods_by_draw_date", "INV-58", periods_by_draw_date),
    ("periods_over_checkable", "INV-59", periods_over_checkable),
    ("empty_period_is_absent", "INV-60", empty_period_is_absent),
]

# Each break must make exactly the named case fail. Named in the *Test:* clauses.
BREAKS = {
    "fold_residue_into_bucket": "periods_reconcile",
    "attribute_by_purchase": "periods_by_draw_date",
    "period_spend_is_lifetime": "periods_over_checkable",
    "period_won_unfiltered": "periods_over_checkable",
    "zero_bucket_for_empty_period": "empty_period_is_absent",
}


def _apply_break(name):
    """Replace period_buckets with a deliberately wrong one.

    Scoped to the case the break names: a defect injected globally reddens
    whichever other cases happen to share the code path, and then "exactly the
    named case fails" stops being checkable. Two of these did exactly that
    before the guard was added.
    """
    real = serve.period_buckets

    def patched(all_tickets, wins, entry_draws, incs):
        if ACTIVE_CASE != BREAKS[name]:
            return real(all_tickets, wins, entry_draws, incs)

        if name == "attribute_by_purchase":
            # Every draw filed under the ticket's purchase month.
            def by_purchase(t, pf):
                d = entry_draws(t, pf)
                return None if d is None else [
                    t.bought.strftime("%Y-%m-%d")] * len(d)
            return real(all_tickets, wins, by_purchase, incs)

        if name == "period_spend_is_lifetime":
            # Drop the resolved filter on the SPEND side.
            class _All(list):
                pass
            widened = _All(all_tickets)
            for t in widened:
                t.resolved = True
            return real(widened, wins, entry_draws, incs)

        if name == "period_won_unfiltered":
            # Keep the spend filter, drop it on the win side only.
            out = real(all_tickets, wins, entry_draws, incs)
            for b in out["buckets"]:
                extra = 0
                for w in wins:
                    if any(t.ref == w["ref"] and not t.resolved
                           for t in all_tickets):
                        key = w["date"][:7] if b["kind"] == "month" else w["date"][:4]
                        if key == b["key"]:
                            extra += round(w["amount"] * 100)
                b["won_cents"] += extra
            return out

        if name == "fold_residue_into_bucket":
            out = real(all_tickets, wins, entry_draws, incs)
            out["no_result_cents"] = 0  # dropped rather than reported
            return out

        if name == "zero_bucket_for_empty_period":
            out = real(all_tickets, wins, entry_draws, incs)
            months = [b for b in out["buckets"] if b["kind"] == "month"]
            if months:
                keys = sorted(b["key"] for b in months)
                lo, hi = keys[0], keys[-1]
                y, mth = int(lo[:4]), int(lo[5:7])
                have = {b["key"] for b in months}
                while f"{y:04d}-{mth:02d}" <= hi:
                    k = f"{y:04d}-{mth:02d}"
                    if k not in have:
                        out["buckets"].append(
                            {"key": k, "kind": "month", "label": k,
                             "spend_cents": 0, "won_cents": 0})
                    mth += 1
                    if mth == 13:
                        y, mth = y + 1, 1
            return out

        return real(all_tickets, wins, entry_draws, incs)

    serve.period_buckets = patched


def main(argv):
    if "--list" in argv:
        for name, inv, _ in CASES:
            print(f"{inv}  {name}")
        print("\nbreaks:")
        for b, case in sorted(BREAKS.items()):
            print(f"  --break {b:30} -> {case} must FAIL")
        return 0

    broken_name = None
    for i, a in enumerate(argv):
        if a == "--break":
            broken_name = argv[i + 1]
            if broken_name not in BREAKS:
                print(f"unknown break {broken_name!r}; --list shows them")
                return 2
            _apply_break(broken_name)
            print(f"BREAK {broken_name}: {BREAKS[broken_name]} must FAIL\n")

    global ACTIVE_CASE
    failed = []
    for name, inv, fn in CASES:
        ACTIVE_CASE = name
        try:
            detail = fn()
            print(f"  {inv}  {name:24} PASS  {detail}")
        except AssertionError as e:
            failed.append(name)
            print(f"  {inv}  {name:24} FAIL  {e}")

    print()
    if broken_name:
        want = BREAKS[broken_name]
        # EXACTLY the named case - see verify_payouts.py's note. The
        # ACTIVE_CASE guard in _apply_break() is what makes this achievable
        # here; this is the assertion that holds it.
        if failed == [want]:
            print(f"RED-TEST OK: {want} failed under --break {broken_name}")
            return 0
        if want in failed:
            others = [f for f in failed if f != want]
            print(f"RED-TEST TOO COARSE: {broken_name} also reddened {others}")
            return 1
        print(f"RED-TEST FAILED: {want} still passes under --break {broken_name}")
        return 1
    if failed:
        print(f"{len(failed)} of {len(CASES)} FAILED: {', '.join(failed)}")
        return 1
    print(f"all {len(CASES)} cases pass")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
