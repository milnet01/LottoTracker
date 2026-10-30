#!/usr/bin/env python3
"""LOTTO-0029 INV-40..INV-47: the bank's payout SMSes, reconciled against wins.

    python3 tools/verify_payouts.py            # every case
    python3 tools/verify_payouts.py --list
    python3 tools/verify_payouts.py --break accept_debits   # RED-TEST: must FAIL

This is the only check in the project that compares its output against
something OUTSIDE itself. verify_sources.py compares two results feeds,
verify_coverage.py compares scoring against its own draw selection,
verify_pools.py compares a price against a transcribed table - all of them
verify the code against the code's own inputs. The bank's messages are the
only record of what this user was actually paid.

Three constraints, from LOTTO-0029 §7 and binding on every case:

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
rest patch the OUTPUT of reconcile() or, for INV-69, payment_status() to
produce exactly what the named
defect would produce, which is indistinguishable from the buggy code at the
boundary the case observes. Said plainly rather than implied: only the first
exercises the production code path itself.
"""

import os
import re
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import check  # noqa: E402
import history  # noqa: E402
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


# The five SYNTHETIC cases need one thing from the draw record: a date early
# enough that history.scorable() says yes, and - for daily/1 - a pool with no
# draws at all. Neither needs the live feed, and reaching for it dragged those
# cases onto a third party's production API purely to look up a date. An
# outage then reddened them for a reason that has nothing to do with the code
# under test, on a check that runs on every push. So they seed history's memo
# instead. `categories_partition` is the one case whose subject IS the real
# data; _real_draws() hands it back the live path.
#
# Seeding the MEMO rather than patching all_draws: check.reconcile() reaches
# history.scorable() directly, so a patched name in this module would not be
# seen. User decision 2026-09-02.
_STUB_START = "2020-01-01"
_STUB = {
    ("lotto", 0): [{"date": _STUB_START, "main": [1, 2, 3, 4, 5, 6],
                    "special": 7, "issue": None, "source": "stub"}],
    ("daily", 0): [{"date": _STUB_START, "main": [1, 2, 3, 4, 5],
                    "special": None, "issue": None, "source": "stub"}],
    ("daily", 1): [],          # the pool no source carries - unscorable
}


def _stub_draws():
    """Seed history's memo so the synthetic cases make no network call."""
    history._cache.update(_STUB)


def _real_draws():
    """Drop the stubs so the real-data case sees the real record."""
    for key in _STUB:
        history._cache.pop(key, None)


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
    # daily/1 for unscorability, NOT lotto/1 with an early date - the sibling
    # case below gives the reason and this fixture used to get it wrong. Pinned
    # to a date, unscorability rests on backfill.FIRST_YEAR, which is a knob
    # that has ALREADY been turned once (LOTTO-0006 pushed the archive back to
    # the earliest purchase SMS). The next turn would make this case red with a
    # false accusation against the cardinal rule - the most expensive kind of
    # failure message to misdiagnose. A pool no source carries cannot rot.
    unscorable = [_ticket(SYNTH_B, game="daily", pools=((1, 101),),
                          start=_scorable_start("daily", 0),
                          boards=[("A", [1, 2, 3, 4, 5], None)])]
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
    # The OTHER half of the three-valued rule, and it was missing. `a` is the
    # only fixture in this file that is paid, fully scorable and won nothing -
    # the only place `computed_cents == 0` is produced. Without this assertion
    # you can change check.py's `elif any(scorable(...)): computed = 0` to
    # `computed = None` and every case in this file still passes, because
    # `category` is decided by an ordered if-chain that never reads `computed`.
    # reconcile_report() would then move this reference into the unscorable
    # count and say "nothing could be scored, which is not a zero" about a
    # reference that WAS checked and won nothing - the cardinal rule broken on
    # the money line, in the direction it exists to prevent (INV-43).
    assert a["computed_cents"] == 0, (
        f"a paid, fully scorable reference with no winning line reports "
        f"{a['computed_cents']!r}; 0 means 'checked, won nothing' and None "
        f"means 'not checkable', and the two must not converge")
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
    # LOTTO-0062 s7: printed, never asserted - one forged SMS would otherwise
    # block every push for good. A non-zero count means the page is flagging
    # records; read them there, not here (no message content in a CI log).
    flagged = check.unknown_senders(tk, payouts)
    print(f"  {len(flagged)} records from a sender not seen before")
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
    # The real-dump figure was printed here from a SECOND full scoring pass -
    # two more dump parses, another load_payouts(), and check.check() over all
    # 1,233 entries - for a number the line itself says is not asserted, and
    # which categories_partition (two cases earlier in CASES) has already
    # computed. Measured 2026-09-02: that case is 27.8s of this file's 35.5s.
    # It prints its own full category census, this one included.
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


def payment_follows_record():
    """LOTTO-0001 INV-69: each win's payment state, from its reference's record.

    Hand-built wins and records, one reference per category plus one with no
    record, so every row of LOTTO-0001 s4.4's table is reached. References
    here are opaque names, not VAS-shaped (see SYNTH_B above).
    """
    want = {"agree": "paid", "low": "paid", "high": "partly paid",
            "unpaid": "unpaid", "no_ticket": "unknown",
            "unexplained": "unknown", "unscored": "unknown"}
    wins = [{"ref": f"SYNTH-{c}", "line": 1} for c in want] + [{"ref": "SYNTH-none", "line": 1}]
    records = [{"ref": f"SYNTH-{c}", "paid_cents": 700, "computed_cents": 900,
                "category": c, "first_win": "2026-07-01"} for c in want]
    before = [dict(w) for w in wins]
    got = {d["ref"]: d for d in check.payment_status(wins, records)}
    assert wins == before, "payment_status() modified its input"
    wrong = {c: got[f"SYNTH-{c}"]["payment"] for c in want
             if got[f"SYNTH-{c}"]["payment"] != want[c]}
    assert not wrong, f"wrong payment state per category: {wrong}"
    none = got["SYNTH-none"]
    assert (none["payment"], none["ref_paid_cents"], none["ref_computed_cents"]) \
        == ("unknown", None, None), f"a reference with no record read {none}"
    high = got["SYNTH-high"]
    assert (high["ref_paid_cents"], high["ref_computed_cents"]) == (700, 900), \
        "the reference's two figures were not carried"
    empty = {d["payment"] for d in check.payment_status(wins, [])}
    assert empty == {"unknown"}, f"with no payout data, wins read {sorted(empty)}"
    return f"{len(want)} categories and a missing record mapped; no data reads unknown"


def claim_deadline_boundary():
    """LOTTO-0058: the 365-day claim deadline, a day either side and on it.

    `expires` is the last day a claim is accepted, so a win reads unexpired on
    that day - late in the day included, since check() passes clock.now() -
    and expired from the next. Both sides are asserted: a one-sided test goes
    green against a defect arriving from the other direction (INV-61's
    reasoning in verify_expiry.py).
    """
    drawn = datetime(2025, 3, 10)
    last = drawn + timedelta(days=check.CLAIM_DAYS)
    cases = [
        ("day before the deadline", last - timedelta(days=1), False),
        ("the deadline, late in the day", last.replace(hour=23, minute=59), False),
        ("the day after", last + timedelta(days=1), True),
    ]
    for label, today, want in cases:
        expired, expires = check.claim_deadline(drawn, today)
        assert expires == last.date().isoformat(), f"expires {expires}, want {last.date()}"
        assert expired is want, f"{label}: expired={expired}, want {want}"
    return f"expires {last.date()}; unexpired on it, expired the day after"


def plain_two_row_pays():
    """LOTTO-0001 INV-79: a plain "2" row pays two mains, with or without bonus.

    Every direction a wrong rule could take, because the failure this project
    fears most is a loss reading as a win: the row must be plain, the draw must
    be on or after the change, and an API-era draw is never read this way.
    """
    plain, bonus = {"3": 20.0, "2": 7.77}, {"3": 20.0, "2 + Bonus": 30.0}
    pages = {"2025-09-17": plain, "2025-09-20": bonus, "2025-09-24": plain,
             "2025-09-27": bonus}
    rows_ = [{"date": d, "main": [1, 2, 3, 4, 5, 6], "special": 7, "issue": None,
              "source": "archive"} for d in sorted(pages)]
    rows_.append({"date": "2026-06-03", "main": [1, 2, 3, 4, 5, 6], "special": 7,
                  "issue": 1, "source": "api"})
    history._cache[("lotto", 0)] = rows_

    two, two_bonus = [1, 2, 40, 41, 42, 43], [1, 2, 7, 41, 42, 43]
    one = [1, 40, 41, 42, 43, 44]
    # (name, draw, board, how many wins, what each pays)
    want = [
        ("two mains, plain row", "2025-09-24", two, 1, 7.77),
        ("two mains and the bonus, plain row", "2025-09-24", two_bonus, 1, 7.77),
        ("one main, plain row", "2025-09-24", one, 0, None),
        ("two mains, plain row before the change", "2025-09-17", two, 0, None),
        ("two mains, Bonus row before the change", "2025-09-20", two, 0, None),
        ("two mains, Bonus row after the change", "2025-09-27", two, 0, None),
        ("two mains, API-era draw", "2026-06-03", two, 0, None),
    ]
    real_pays, real_payouts = check.paying_combinations, check.payouts
    check.paying_combinations = lambda *a: {"MATCH 3": "DIV 7", "MATCH 2 + BONUS": "DIV 8"}
    check.payouts = lambda game, plus_flag, date: pages[date]
    try:
        for name, date, board, count, price in want:
            t = _ticket(SENTINEL, start=date, boards=[("A", board, None)])
            try:
                wins = check.check([t])
            except RuntimeError as e:
                raise AssertionError(f"{name}: {e}") from e
            assert len(wins) == count, f"{name}: {len(wins)} wins, want {count}"
            for w in wins:
                assert w["amount"] == price, f"{name}: priced {w['amount']}, want {price}"
                assert w["division"] == "DIV 8", f"{name}: division {w['division']}"
    finally:
        check.paying_combinations, check.payouts = real_pays, real_payouts
    return f"{len(want)} match, page and era combinations"


def disagreements_are_named():
    """LOTTO-0029 INV-80: every `low` and `high` carries a reason, read from data.

    Each reason has a case, and each has a near miss that must read "unnamed":
    a classifier that names everything is the failure sign of success 5 fears,
    because it empties the pile by hiding what is in it.
    """
    def win(cents, date, game="lotto", source="archive"):
        return dict(_win(SENTINEL, cents, date), game=game, source=source)

    def pay(cents, day):
        return tickets.Payout(SENTINEL, cents, datetime.strptime(day, "%Y-%m-%d"))

    whole = _ticket(SENTINEL, start=_STUB_START)
    plus = _ticket(SENTINEL, "daily", ((0, 100), (1, 101)), start=_STUB_START,
                   boards=[("A", [1, 2, 3, 4, 5], None)])
    newest = "2026-08-15"
    a, b = "2026-07-01", "2026-07-08"
    late = "2026-08-20"
    cases = [
        ("a Plus entry", "low", 251, plus, [win(500, a, "daily")],
         [pay(500, a), pay(251, a)], "unscorable_entry"),
        ("one message twice", "low", 333, whole, [win(500, a)],
         [pay(500, a), pay(333, b), pay(333, b)], "repeated_message"),
        ("twice, but on two days", "low", 666, whole, [win(500, a)],
         [pay(500, a), pay(333, a), pay(333, b)], "unnamed"),
        ("a small unknown excess", "low", 100, whole, [win(500, a)],
         [pay(600, a)], "unnamed"),
        ("a feed price", "high", -19, whole, [win(500, a, "daily", "api")],
         [pay(481, a)], "feed_price"),
        ("a win after the dump", "high", -1111, whole, [win(500, a), win(1111, late)],
         [pay(500, a)], "after_last_message"),
        ("one draw unpaid", "high", -1234, whole, [win(500, a), win(1234, b)],
         [pay(500, a)], "no_message_for_draw"),
        ("a part of one draw", "high", -80, whole, [win(500, a), win(1234, b)],
         [pay(500, a), pay(1154, b)], "unnamed"),
    ]
    for name, category, gap, t, wins, paid, want in cases:
        got = check.disagreement_reason(category, gap, [t], wins, paid, newest)
        assert got == want, f"{name}: {got}, want {want}"

    # And through reconcile() itself, with the figures left alone (INV-43).
    t = _ticket(SENTINEL, start=_STUB_START)
    recs = check.reconcile([t], [_win(SENTINEL, 500)], [_payout(SENTINEL, 481)])
    assert recs[0]["reason"] == "unnamed", f"reason {recs[0]['reason']}"
    assert (recs[0]["paid_cents"], recs[0]["computed_cents"]) == (481, 500), recs[0]
    recs = check.reconcile([t], [_win(SENTINEL, 500)], [_payout(SENTINEL, 500)])
    assert recs[0]["reason"] is None, f"agree carries a reason: {recs[0]['reason']}"
    return f"{len(cases)} reasons and near misses; reconcile() moves no figure"


CASES = [
    ("purchase_is_not_a_payout", "INV-40", purchase_is_not_a_payout),
    ("multiple_payouts_sum", "INV-41", multiple_payouts_sum),
    ("cents_not_floats", "INV-42", cents_not_floats),
    ("disagreement_keeps_both", "INV-43", disagreement_keeps_both),
    ("unscored_is_not_unexplained", "INV-44", unscored_is_not_unexplained),
    ("categories_partition", "INV-45", categories_partition),
    ("unpaid_carries_draw_date", "INV-46", unpaid_carries_draw_date),
    ("no_payouts_is_not_agreement", "INV-47", no_payouts_is_not_agreement),
    ("payment_follows_record", "INV-69", payment_follows_record),
    ("claim_deadline_boundary", "LOTTO-0058", claim_deadline_boundary),
    ("plain_two_row_pays", "INV-79", plain_two_row_pays),
    ("disagreements_are_named", "INV-80", disagreements_are_named),
]

ACTIVE_CASE = None  # set by main(); a break fires only in its own case

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
    "short_paid_reads_paid": "payment_follows_record",
    "no_records_reads_paid": "payment_follows_record",
    "other_category_reads_paid": "payment_follows_record",
    "deadline_day_expired": "claim_deadline_boundary",
    "deadline_never_expires": "claim_deadline_boundary",
    "plain_two_never_pays": "plain_two_row_pays",
    "plain_two_ignores_page": "plain_two_row_pays",
    "plain_two_ignores_date": "plain_two_row_pays",
    "reason_never_unnamed": "disagreements_are_named",
    "reason_moves_figure": "disagreements_are_named",
}


def _apply_break(name):
    """Apply one deliberate defect. See the header on what each patches."""
    if name == "accept_debits":
        # The real production regex, widened toward "paid" as the docstring
        # warns against. This is the only break on the production path.
        tickets.PAYOUT = re.compile(r"R([\d,]+\.?\d*).*?(VAS\d+)", re.I | re.S)
        return
    if name in ("short_paid_reads_paid", "no_records_reads_paid",
                "other_category_reads_paid"):
        real_ps = check.payment_status

        def broken_ps(wins, records):
            out = real_ps(wins, records)
            if ACTIVE_CASE != BREAKS[name]:
                return out
            cat = {r["ref"]: r["category"] for r in records}
            for d in out:
                c = cat.get(d["ref"])
                if name == "short_paid_reads_paid" and c == "high":
                    d["payment"] = "paid"
                elif name == "no_records_reads_paid" and not records:
                    d["payment"] = "paid"
                elif name == "other_category_reads_paid" and c is not None \
                        and c not in ("agree", "low", "high", "unpaid"):
                    d["payment"] = "paid"
            return out

        check.payment_status = broken_ps
        return
    if name in ("deadline_day_expired", "deadline_never_expires"):
        real_cd = check.claim_deadline

        def broken_cd(drawn, today):
            expired, expires = real_cd(drawn, today)
            if ACTIVE_CASE != BREAKS[name]:
                return expired, expires
            if name == "deadline_day_expired":     # `>=`: the last day lost
                return (today - drawn).days >= check.CLAIM_DAYS, expires
            return False, expires                  # the far side never fires

        check.claim_deadline = broken_cd
        return
    if name == "reason_never_unnamed":
        real_why = check.disagreement_reason

        def broken_why(*a):
            got = real_why(*a)
            return "feed_price" if got == "unnamed" else got

        check.disagreement_reason = broken_why
        return
    if name.startswith("plain_two_"):
        real_two = check.plain_two_pays

        def broken_two(game, plus_flag, d, hits, special):
            # Scoped like the others, and here it matters more: applied to the
            # real-data case, ignoring the date scrapes every old payout page.
            if ACTIVE_CASE != BREAKS[name]:
                return real_two(game, plus_flag, d, hits, special)
            if name == "plain_two_never_pays":
                return False
            two = hits == 2 and not special and d["issue"] is None
            if name == "plain_two_ignores_page":
                return two and d["date"] >= check.PLAIN_TWO_FROM
            table = check.payouts(game, plus_flag, d["date"])       # ignores_date
            return two and "2" in table and "2 + Bonus" not in table

        check.plain_two_pays = broken_two
        return
    real = check.reconcile

    def broken(tk, wins, payouts):
        # Scoped to the case the break names, the way verify_periods.py does
        # it. Injected globally, a defect reddens whichever OTHER cases happen
        # to share the code path, and "exactly the named case fails" stops
        # being checkable. Measured 2026-09-02: compare_in_rands rewrote every
        # record's category, so it also reddened unscored_is_not_unexplained,
        # and the red test could no longer prove cents_not_floats observes the
        # float defect rather than something else.
        if ACTIVE_CASE != BREAKS[name]:
            return real(tk, wins, payouts)
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
            elif name == "reason_moves_figure" and r["reason"]:
                r["computed_cents"] = r["paid_cents"]
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

    global ACTIVE_CASE
    failed = []
    for name, inv, fn in CASES:
        ACTIVE_CASE = name
        # Only the real-data case reaches the live feed. Every other case here
        # is synthetic and was touching it purely to look up a start date.
        _real_draws() if name == "categories_partition" else _stub_draws()
        try:
            detail = fn()
            print(f"  {inv}  {name:30} PASS  {detail}")
        except AssertionError as e:
            failed.append(name)
            print(f"  {inv}  {name:30} FAIL  {e}")

    print()
    if broken:
        want = BREAKS[broken]
        # EXACTLY the named case, not merely among the failures. A break that
        # reddens three cases no longer proves this one observes THAT defect,
        # and the docstring's "one deliberate defect" was held by nothing.
        if failed == [want]:
            print(f"RED-TEST OK: {want} failed under --break {broken}")
            return 0
        if want in failed:
            others = [f for f in failed if f != want]
            print(f"RED-TEST TOO COARSE: {broken} also reddened {others}")
            return 1
        print(f"RED-TEST FAILED: {want} still passes under --break {broken}")
        return 1
    if failed:
        print(f"{len(failed)} of {len(CASES)} FAILED: {', '.join(failed)}")
        return 1
    print(f"all {len(CASES)} cases pass")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
