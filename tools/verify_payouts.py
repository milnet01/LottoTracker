#!/usr/bin/env python3
"""LOTTO-0029 INV-40..INV-47: the bank's payout SMSes, reconciled against wins.

    python3 tools/verify_payouts.py            # all eight
    python3 tools/verify_payouts.py --list
    python3 tools/verify_payouts.py --break accept_debits   # RED-TEST: must FAIL

This is the only check in the project that compares its output against
something OUTSIDE itself. verify_sources.py compares two results feeds,
verify_coverage.py compares scoring against its own draw selection,
verify_pools.py compares a price against a transcribed table - all of them
verify the code against the code's own inputs. The bank's messages are the
only record of what this user was actually paid.

Three constraints, from LOTTO-0029 §7 and binding on all eight cases:

  * NO MESSAGE CONTENT, and no amount against a reference. The census is
    counts and totals only. verify_privacy.py compares tracked files against
    the dump, and a verifier echoing a payout line into a CI log puts real
    content where that check cannot see it (LOTTO-0001 INV-4).
  * COUNTS ARE PRINTED, NOT ASSERTED - and that now includes `unexplained`
    and `unscored`, not only `unpaid`. §8 rejects `assert unpaid == 0`
    because a count that is true today is not thereby a contract; the same
    reasoning covers the other two from the other direction. `unexplained` is
    a defect residue this project intends to explain away, and LOTTO-0006
    turned most of the `unscored` references into an oracle on 2026-08-31. An
    assertion that either stays non-empty goes red on exactly that progress,
    in local-CI.sh's local-only lane, blocking a push.
  * BUILD THE POPULATION INDEPENDENTLY. categories_partition takes its
    denominator from load_payouts() and check() directly, never from
    reconcile()'s own output - taking it from the output means dropping a
    reference shrinks both sides and the count passes against precisely the
    defect it exists to catch. The rule verify_pools.py already states about
    never importing the thing under test.

What IS asserted: 0 purchase debits accepted as payouts, 0 references dropped
by the partition, and the synthetic fixtures below. Exit code is the signal.

RED-TESTING. `--break accept_debits` patches the real production regex. The
other seven patch reconcile()'s OUTPUT to produce exactly what the named
defect would produce, which is indistinguishable from the buggy code at the
boundary the case observes. Said plainly rather than implied: only the first
exercises the production code path itself.
"""

import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import check  # noqa: E402
import tickets  # noqa: E402
from history import all_draws  # noqa: E402
from tickets import Ticket, load, load_payouts, parse_payout, rows  # noqa: E402

SENTINEL = "VAS00000000000"

# Fixtures needing a SECOND distinct reference do not get a second VAS-shaped
# one. tools/verify_privacy.py treats EVERY reference-shaped string that is not
# exactly the sentinel as a leak, invented or not - and it only reads TRACKED
# files, so a new file passes every local run until `git add` makes it tracked,
# and then fails at the push. reconcile() takes a reference as an opaque
# string, so these cost nothing.
SYNTH_B, SYNTH_C, SYNTH_D = "SYNTH-B", "SYNTH-C", "SYNTH-D"


# ---------------------------------------------------------------- fixtures

def _ticket(ref, game="lotto", pools=((0, 100),), start="2026-07-01", boards=None):
    """A Ticket with no dependence on the dump.

    `start` decides scorability: on or after the pool's first known draw it is
    scorable, well before it is not (history.scorable). That is the only lever
    these fixtures need, and it uses the real rule rather than a stand-in.
    """
    d = datetime.strptime(start, "%Y-%m-%d")
    return Ticket(game, pools[-1][0], pools[-1][1], d, 1,
                  boards if boards is not None else [("A", [1, 2, 3, 4, 5, 6], None)],
                  ref, 5.0, list(pools), d, True)


def _scorable_start(game="lotto", plus_flag=0):
    rows_ = all_draws(game, plus_flag)
    if not rows_:
        raise SystemExit(f"no draws for {game}/{plus_flag} - run backfill.py first")
    return rows_[0]["date"]


def _win(ref, cents, date="2026-07-02"):
    # The shape check.check() emits; reconcile reads only these four keys.
    return {"ref": ref, "amount": cents / 100, "date": date,
            "game": "lotto", "plus_flag": 0, "pool_id": 100, "line": "A",
            "division": "DIV 5", "matched": "MATCH 3", "source": "api",
            "expired": False, "expires": "2027-07-02"}


def _payout(ref, cents):
    return tickets.Payout(ref, cents, datetime(2026, 7, 3))


# ------------------------------------------------------------------ cases

def purchase_is_not_a_payout():
    """INV-40: a purchase debit never parses as a prize payment."""
    bodies = [b for _a, _m, b in rows(open("lotto_sms_raw.txt", errors="replace").read())]
    debits = [b for b in bodies if "paid from Acc" in b]
    if not debits:
        raise AssertionError("no purchase debits in the dump - the fixture is gone")
    accepted = [b for b in debits if parse_payout(b)]
    print(f"  {len(debits)} purchase debits, {len(accepted)} accepted as payouts")
    assert not accepted, (
        f"{len(accepted)} purchase debits parsed as winnings - money SPENT "
        f"counted as money WON")
    # The obvious clause - "no body parses as both a ticket and a payout" - is
    # vacuous here: a debit does not parse as a ticket either, so it would pass
    # against exactly the widening this forbids. Asserted directly instead.
    return f"{len(debits)} debits, none accepted"


def multiple_payouts_sum():
    """INV-41: the unit is the reference; payments to one ref are summed."""
    tk = [_ticket(SENTINEL, start=_scorable_start())]
    recs = check.reconcile(tk, [], [_payout(SENTINEL, 1050), _payout(SENTINEL, 2075)])
    assert len(recs) == 1, f"expected one record per reference, got {len(recs)}"
    assert recs[0]["paid_cents"] == 3125, (
        f"two payments to one reference summed to {recs[0]['paid_cents']}c, "
        f"expected 3125c - keyed by message rather than by reference")
    real = load_payouts()
    multi = len({p.ref for p in real}) < len(real)
    print(f"  {len(real)} payments over {len({p.ref for p in real})} references"
          f"{' (some paid more than once)' if multi else ''}")
    return "3125c from two payments"


def cents_not_floats():
    """INV-42: money is compared in whole cents, never as float rands."""
    # 0.1 + 0.2 == 0.30000000000000004, so this pair is equal in cents and
    # unequal in rands. Comparing in rands categorises it `high`.
    tk = [_ticket(SENTINEL, start=_scorable_start())]
    wins = [_win(SENTINEL, 10), _win(SENTINEL, 20)]
    assert 0.1 + 0.2 != 0.3, "the float fixture no longer exercises the rule"
    recs = check.reconcile(tk, wins, [_payout(SENTINEL, 30)])
    assert recs[0]["category"] == "agree", (
        f"cents-equal payout categorised {recs[0]['category']!r}, expected "
        f"'agree' - compared in rands rather than whole cents")
    return "0.1+0.2 == 0.30 in cents"


def disagreement_keeps_both():
    """INV-43: both figures survive, and the bank's never replaces ours."""
    tk = [_ticket(SENTINEL, start=_scorable_start())]
    wins = [_win(SENTINEL, 500)]
    before = [dict(w) for w in wins]
    recs = check.reconcile(tk, wins, [_payout(SENTINEL, 1200)])
    r = recs[0]
    assert r["category"] == "low", f"expected 'low', got {r['category']!r}"
    # The positive assertion is the one that matters. "every non-agree record
    # carries both fields" cannot falsify this: adopting the bank's figure
    # turns the reference INTO `agree`, so it leaves the quantifier entirely.
    assert r["computed_cents"] == 500, (
        f"computed_cents is {r['computed_cents']}c, expected 500c - the sum of "
        f"its OWN winning lines, not the bank's 1200c")
    assert r["paid_cents"] == 1200, f"paid_cents is {r['paid_cents']}c, expected 1200c"
    assert wins == before, "reconcile() mutated the wins list it was passed"
    # None must stay distinguishable from 0 (the cardinal rule at this layer).
    unscorable = [_ticket(SYNTH_B, pools=((1, 101),), start="2020-01-01")]
    n = check.reconcile(unscorable, [], [_payout(SYNTH_B, 900)])[0]
    assert n["computed_cents"] is None, (
        f"a reference nothing could score reports {n['computed_cents']!r}; None "
        f"means 'not checkable' and 0 means 'checked, won nothing'")
    return "500c vs 1200c, both kept; None is not 0"


def unscored_is_not_unexplained():
    """INV-44: a paid reference with an unscorable entry is reported apart."""
    ok = _scorable_start()
    every = [_ticket(SENTINEL, pools=((0, 100),), start=ok)]
    # daily/1 is Daily Lotto Plus, which NO source carries - the project's only
    # genuinely unscorable pool (LOTTO-0009). lotto/1 does NOT work here: it
    # has draws, so both entries would be scorable and `unexplained` would be
    # the correct answer, which is what this fixture got wrong first time.
    mixed = [_ticket(SYNTH_C, game="daily",
                     pools=((0, 100), (1, 101)),
                     start=_scorable_start("daily", 0),
                     boards=[("A", [1, 2, 3, 4, 5], None)])]
    a = check.reconcile(every, [], [_payout(SENTINEL, 500)])[0]
    b = check.reconcile(mixed, [], [_payout(SYNTH_C, 500)])[0]
    assert a["category"] == "unexplained", (
        f"a paid reference whose every entry is scorable, with no winning line, "
        f"landed in {a['category']!r} rather than 'unexplained'")
    assert b["category"] == "unscored", (
        f"a paid reference carrying an unscorable entry landed in "
        f"{b['category']!r} rather than 'unscored'")
    # A disjointness assertion would be the WRONG clause: merging empties
    # `unexplained`, and the empty set is disjoint from everything, so the
    # obvious test passes against precisely the merge this forbids.
    return "all-scorable -> unexplained; mixed -> unscored"


def categories_partition():
    """INV-45: every reference lands in exactly one category, none dropped."""
    tk = load()
    payouts = load_payouts()
    wins = check.check(tk)
    # The denominator, built INDEPENDENTLY of reconcile() - see the header.
    refs = {t.ref for t in tk if t.ref != "?"}
    paid = {p.ref for p in payouts}
    won = {w["ref"] for w in wins if w["ref"] != "?"}
    union = paid | (won & refs) | (won - refs)
    union -= {"?"}
    recs = check.reconcile(tk, wins, payouts)
    seen = [r["ref"] for r in recs]
    counts = {}
    for r in recs:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    print("  " + "  ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print(f"  {len(recs)} records over a union of {len(union)} references")
    assert len(seen) == len(set(seen)), "a reference appears in more than one record"
    assert set(seen) == union, (
        f"{len(union - set(seen))} references dropped and "
        f"{len(set(seen) - union)} invented")
    assert sum(counts.values()) == len(union), (
        f"category counts sum to {sum(counts.values())}, union is {len(union)}")
    return f"{len(union)} references, no overlap, none dropped"


def unpaid_carries_draw_date():
    """INV-46: an unpaid record names its earliest winning line's date."""
    # SYNTHETIC on purpose. The category is empty against the real dump today,
    # so a case run over real data alone passes without executing the rule.
    tk = [_ticket(SENTINEL, start=_scorable_start()),
          _ticket(SYNTH_D, start=_scorable_start())]
    wins = [_win(SENTINEL, 800, date="2026-07-09"),
            _win(SENTINEL, 200, date="2026-07-02")]
    recs = check.reconcile(tk, wins, [_payout(SYNTH_D, 100)])
    unpaid = [r for r in recs if r["category"] == "unpaid"]
    assert len(unpaid) == 1, f"expected one unpaid record, got {len(unpaid)}"
    assert unpaid[0]["first_win"] == "2026-07-02", (
        f"first_win is {unpaid[0]['first_win']!r}, expected the EARLIEST "
        f"winning line '2026-07-02' - without it a reader cannot tell a "
        f"three-day-old win awaiting payment from a prize never paid")
    real = sum(1 for r in check.reconcile(load(), check.check(load()), load_payouts())
               if r["category"] == "unpaid")
    print(f"  {real} unpaid references against the real dump (printed, not asserted)")
    return "earliest winning date carried"


def no_payouts_is_not_agreement():
    """INV-47: a dump with no parsable payout reports absence, not agreement."""
    tk = [_ticket(SENTINEL, start=_scorable_start())]
    wins = [_win(SENTINEL, 500)]
    recs = check.reconcile(tk, wins, [])
    assert recs == [], (
        f"reconcile() returned {len(recs)} records with no payout parsed - every "
        f"scored reference satisfies 'unpaid', so the page would render prizes "
        f"the bank never paid")
    lines, counts = check.reconcile_report(recs)
    assert lines, "no payout data reported as silence"
    text = " ".join(lines).lower()
    assert "no payout data" in text, f"absence not named: {lines!r}"
    # Forbid the CENSUS, not the word "agree" - the report's own sentence says
    # "This is NOT agreement", and a substring check on "agree" fires on it.
    # An assertion loose enough to match text the CORRECT output contains is
    # the same defect pointing the other way.
    census = re.search(r"\d+\s+(" + "|".join(check.CATEGORY_NOTE) + r")\b", text)
    assert not census, f"a category census was printed with no payout data: {census.group(0)!r}"
    assert not counts, f"a category census was emitted with no payout data: {counts}"
    return "absence named, no census"


CASES = [
    ("purchase_is_not_a_payout", "INV-40", purchase_is_not_a_payout),
    ("multiple_payouts_sum", "INV-41", multiple_payouts_sum),
    ("cents_not_floats", "INV-42", cents_not_floats),
    ("disagreement_keeps_both", "INV-43", disagreement_keeps_both),
    ("unscored_is_not_unexplained", "INV-44", unscored_is_not_unexplained),
    ("categories_partition", "INV-45", categories_partition),
    ("unpaid_carries_draw_date", "INV-46", unpaid_carries_draw_date),
    ("no_payouts_is_not_agreement", "INV-47", no_payouts_is_not_agreement),
]

# Each break must make exactly the named case fail. Named in the *Test:* clauses.
BREAKS = {
    "accept_debits": "purchase_is_not_a_payout",
    "payout_per_message": "multiple_payouts_sum",
    "compare_in_rands": "cents_not_floats",
    "adopt_bank_figure": "disagreement_keeps_both",
    "merge_unscored": "unscored_is_not_unexplained",
    "drop_no_ticket": "categories_partition",
    "no_first_win": "unpaid_carries_draw_date",
    "census_without_payouts": "no_payouts_is_not_agreement",
}


def _apply_break(name):
    """Apply one deliberate defect. See the header on what each patches."""
    if name == "accept_debits":
        # The real production regex, widened toward "paid" as the docstring
        # warns against. This is the only break on the production path.
        tickets.PAYOUT = re.compile(r"R([\d,]+\.?\d*).*?(VAS\d+)", re.I | re.S)
        return
    real = check.reconcile

    def broken(tk, wins, payouts):
        if name == "census_without_payouts" and not payouts:
            # The INV-47 guard removed: fall through and categorise anyway.
            return [{"ref": w["ref"], "paid_cents": None,
                     "computed_cents": round(w["amount"] * 100),
                     "category": "unpaid", "first_win": w["date"]} for w in wins]
        recs = real(tk, wins, payouts)
        for r in recs:
            if name == "payout_per_message" and r["paid_cents"]:
                per = [p.cents for p in payouts if p.ref == r["ref"]]
                r["paid_cents"] = per[0] if per else None      # keyed by message
            elif name == "compare_in_rands" and r["paid_cents"] is not None \
                    and r["computed_cents"] is not None:
                # Accumulate the win AMOUNTS as floats, which is the real
                # defect. Converting the already-rounded cents back to rands
                # is not: 30/100 is exactly 0.3, so the float error this rule
                # exists to catch has already been rounded away and the break
                # confirms the rule instead of refuting it.
                c = sum(w["amount"] for w in wins if w["ref"] == r["ref"])
                p = r["paid_cents"] / 100
                r["category"] = "agree" if p == c else "low" if c < p else "high"
            elif name == "adopt_bank_figure" and r["category"] in ("low", "high"):
                r["computed_cents"] = r["paid_cents"]
                r["category"] = "agree"
            elif name == "merge_unscored" and r["category"] == "unexplained":
                r["category"] = "unscored"
            elif name == "no_first_win":
                r["first_win"] = None
        if name == "drop_no_ticket":
            recs = [r for r in recs if r["category"] != "no_ticket"]
        return recs

    check.reconcile = broken


def main(argv):
    if "--list" in argv:
        for name, inv, _ in CASES:
            print(f"{inv}  {name}")
        print("\nbreaks:")
        for b, case in sorted(BREAKS.items()):
            print(f"  --break {b:24} -> {case} must FAIL")
        return 0

    broken = None
    for i, a in enumerate(argv):
        if a == "--break":
            broken = argv[i + 1]
            if broken not in BREAKS:
                print(f"unknown break {broken!r}; --list shows them")
                return 2
            _apply_break(broken)
            print(f"BREAK {broken}: {BREAKS[broken]} must FAIL\n")

    failed = []
    for name, inv, fn in CASES:
        try:
            detail = fn()
            print(f"  {inv}  {name:30} PASS  {detail}")
        except AssertionError as e:
            failed.append(name)
            print(f"  {inv}  {name:30} FAIL  {e}")

    print()
    if broken:
        want = BREAKS[broken]
        if want in failed:
            print(f"RED-TEST OK: {want} failed under --break {broken}")
            return 0
        print(f"RED-TEST FAILED: {want} still passes under --break {broken}")
        return 1
    if failed:
        print(f"{len(failed)} of {len(CASES)} FAILED: {', '.join(failed)}")
        return 1
    print(f"all {len(CASES)} cases pass")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
