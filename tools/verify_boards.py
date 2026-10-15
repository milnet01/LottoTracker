#!/usr/bin/env python3
"""LOTTO-0007 (d): a board too big for one line is never scored as one.

    python3 tools/verify_boards.py            # every case
    python3 tools/verify_boards.py --list
    python3 tools/verify_boards.py --break oversized_misfiled   # RED-TEST: must FAIL

Locks LOTTO-0001 INV-67 (parse, gate, report), LOTTO-0002 INV-68 (the entry's
reason and the banner) and LOTTO-0009 INV-7's oversized half (price_counts()).
One line holds six numbers on PowerBall, the PowerBall counted, and five on
Daily Lotto; a Lotto board over six is Multiplay and is never oversized.

CI lane: it reads neither the dump nor the archive. Its fixtures are
synthetic, carry only the sentinel reference, and its draw record is a seeded
history._cache - check.py imports all_draws by name, so patching
history.all_draws would not reach it. One draw per pool on the fixtures' start
date, so a normal ticket is scorable and only the size rule can make an entry
unscorable: that is what makes each case test the rule it names.

The dump holds no oversized board (measured 2026-10-15), so nothing on the
local lane exercises this rule; these fixtures are the only cover it has.

The breaks patch production functions, never their output, and each fires
only inside the case it names (verify_payouts.py's ACTIVE_CASE rule). This
item is greenfield, so the breaks are what make every case observed red.
"""

import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import check  # noqa: E402
import history  # noqa: E402
import page  # noqa: E402
import serve  # noqa: E402
import tickets  # noqa: E402
import verify_pools  # noqa: E402

SENTINEL = "VAS00000000000"
START = "2020-01-01"
BOUGHT = datetime(2020, 1, 1)   # the Ithuba era: R5.00 a PowerBall line

# One draw per pool on the fixtures' start date, every pool the fixtures enter.
_ROW = {"date": START, "main": [1, 2, 3, 4, 5, 6], "special": 7,
        "issue": None, "source": "stub"}
_STUB = {(g, pf): [dict(_ROW)] for g, pfs in
         (("lotto", (0, 1, 2)), ("powerball", (0, 1)), ("daily", (0, 1)))
         for pf in pfs}

# The pinned wording (LOTTO-0002 s4.5): the reason, and the banner's bit.
REASON = "board A: more numbers than one line of this game holds"
BANNER = "on a ticket whose board holds more numbers than one line of its game"


def _sms(price, name, board):
    return (f"Standard Bank: Played R{price} {name} for 1 draw(s)\n"
            f"Date 01/01/2020 to 01/01/2020\nA: {board}\nRef:{SENTINEL}.")


def _parse(price, name, board):
    t = tickets.parse(_sms(price, name, board), BOUGHT)
    assert t is not None, f"fixture did not parse: {name} {board}"
    return t


PB_SEVEN = ("5.00", "Powerball", "01 02 03 04 05 06 07")      # 6 mains + PB
PB_SIX = ("5.00", "Powerball", "01 02 03 04 05 06")           # 5 mains + PB
DAILY_SIX = ("3.00", "Daily Lotto", "01 02 03 04 05 06")
LOTTO_SEVEN = ("35.00", "Lotto", "01 02 03 04 05 06 07")      # Multiplay, 7 lines


def oversized_not_scored():
    for fx, want in ((PB_SEVEN, ["A"]), (DAILY_SIX, ["A"]),
                     (PB_SIX, []), (LOTTO_SEVEN, [])):
        t = _parse(*fx)
        assert t.oversized == want, f"{fx[1]} {fx[2]!r}: oversized {t.oversized}, want {want}"
        flags = {pf: history.scorable(t, pf) for pf, _ in t.pools}
        if want:
            assert not any(flags.values()), f"{fx[1]} {fx[2]!r} scorable: {flags}"
        else:
            assert all(flags.values()), f"{fx[1]} {fx[2]!r} not scorable: {flags}"
    return "7-number PowerBall and 6-number Daily unscorable; 6-number PowerBall and Multiplay scorable"


def odd_board_counted_first():
    over = [_parse(*PB_SEVEN), _parse(*DAILY_SIX)]
    lines, counts = check.uncheckable_report(over)
    n = counts["entries"]
    got = (counts["odd_board"], counts["too_old"], counts["no_pool"])
    assert got == (n, 0, 0), f"odd_board/too_old/no_pool {got}, want ({n}, 0, 0)"
    assert any("more numbers than one line of its game" in ln for ln in lines), \
        f"report does not name the reason: {lines!r}"
    return f"all {n} entries odd_board, none too_old or no_pool"


def oversized_not_unresolved():
    tk = [_parse("35.00", "Powerball", PB_SEVEN[2]),   # matches no tier
          _parse(*PB_SEVEN),                          # resolves by coincidence
          _parse(*PB_SIX)]                            # an ordinary ticket
    got = verify_pools.price_counts(tk)
    assert got == (0, 2), f"price_counts {got}, want (0, 2)"
    return "(unresolved 0, oversized 2)"


def odd_board_is_named():
    t = _parse(*PB_SEVEN)
    early = [{"date": "2019-01-01"}]     # carried pool, reaches back: no other reason
    for rows, why in ((early, "carried pool"), ([], "uncarried pool")):
        got = serve.entry_reason(t, rows)
        assert got == REASON, f"{why}: entry_reason {got!r}, want {REASON!r}"
    u = {"entries": 3, "uncheckable": 2, "odd_board": 2, "too_old": 0,
         "no_pool": 0, "wholly": 1, "partly": 0}
    html = page._uncheckable_banner(u)
    assert f"2 are {BANNER}" in html, f"banner lacks the reason and its count: {html!r}"
    assert "nothing exists" not in html, "banner still says nothing exists to score them"
    return "reason pinned in both pools; banner names it with its count"


CASES = [
    ("oversized_not_scored", "INV-67", oversized_not_scored),
    ("odd_board_counted_first", "INV-67", odd_board_counted_first),
    ("oversized_not_unresolved", "INV-7", oversized_not_unresolved),
    ("odd_board_is_named", "INV-68", odd_board_is_named),
]

ACTIVE_CASE = None  # set by main(); a break fires only in its own case

BREAKS = {
    "oversized_scored_as_line": "oversized_not_scored",
    "oversized_misfiled": "odd_board_counted_first",
    "oversized_counted_unresolved": "oversized_not_unresolved",
    "odd_board_unnamed": "odd_board_is_named",
    "odd_board_not_in_banner": "odd_board_is_named",
    "pool_before_board": "odd_board_is_named",
}


def _apply_break(name):
    """Patch one production function, live only while its own case runs."""
    def scoped(real, broken):
        return lambda *a: (broken if ACTIVE_CASE == BREAKS[name] else real)(*a)

    if name == "oversized_scored_as_line":
        real = tickets.parse

        def broken_parse(body, bought=None):   # parse() stops recording the label
            t = real(body, bought)
            if t is not None:
                t.oversized = []
            return t
        tickets.parse = scoped(real, broken_parse)
    elif name == "oversized_misfiled":
        real = check.uncheckable_report

        def broken_report(tk):               # the odd_board split dropped
            lines, counts = real(tk)
            counts["too_old"] += counts["odd_board"]
            counts["odd_board"] = 0
            return [ln for ln in lines if "one line of its game" not in ln], counts
        check.uncheckable_report = scoped(real, broken_report)
    elif name == "oversized_counted_unresolved":
        verify_pools.oversized = scoped(verify_pools.oversized, lambda t: False)
    elif name in ("odd_board_unnamed", "pool_before_board"):
        real = serve.entry_reason

        def broken_reason(ticket, rows):
            if name == "pool_before_board" and not rows:
                return "no results source carries this pool"
            if name == "odd_board_unnamed" and getattr(ticket, "oversized", None):
                if not rows:
                    return "no results source carries this pool"
                return None if ticket.start.strftime("%Y-%m-%d") >= rows[0]["date"] \
                    else "predates all draw data for this pool"
            return real(ticket, rows)
        serve.entry_reason = scoped(real, broken_reason)
    elif name == "odd_board_not_in_banner":
        real = page._uncheckable_banner
        page._uncheckable_banner = scoped(real, lambda u: real({**u, "odd_board": 0}))


def main(argv):
    if "--list" in argv:
        for name, inv, _ in CASES:
            print(f"{inv}  {name}")
        print("\nbreaks:")
        for b, case in sorted(BREAKS.items()):
            print(f"  --break {b:30} -> {case} must FAIL")
        return 0

    broken = None
    for i, a in enumerate(argv):
        if a == "--break":
            broken = argv[i + 1] if i + 1 < len(argv) else None
            if broken not in BREAKS:
                print(f"unknown break {broken!r}; --list shows them")
                return 2
            _apply_break(broken)
            print(f"BREAK {broken}: {BREAKS[broken]} must FAIL\n")

    history._cache.update(_STUB)
    global ACTIVE_CASE
    failed = []
    for name, inv, fn in CASES:
        ACTIVE_CASE = name
        try:
            detail = fn()
            print(f"  {inv}  {name:26} PASS  {detail}")
        except AssertionError as e:
            failed.append(name)
            print(f"  {inv}  {name:26} FAIL  {e}")

    print()
    if broken:
        want = BREAKS[broken]
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
