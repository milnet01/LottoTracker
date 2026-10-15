#!/usr/bin/env python3
"""LOTTO-0062 INV-72..INV-75: who sent a lottery SMS, and that it is shown.

    python3 tools/verify_senders.py            # every case
    python3 tools/verify_senders.py --list
    python3 tools/verify_senders.py --break drop_unknown   # RED-TEST: must FAIL

CI lane: it reads no dump. unknown_is_kept builds a throwaway one holding the
sentinel reference only, so nothing here can carry real message content
(LOTTO-0001 INV-4). The sender rule's constants are the bank's own sender
name and a numeric prefix, not anything identifying the user.

The breaks patch the production functions themselves, never their output, and
each fires only inside the case it names - the ACTIVE_CASE rule
verify_payouts.py states - so "exactly the named case fails" stays checkable.
This item is greenfield: there is no pre-fix code to red-test against, so the
breaks are what make every case observed red.
"""

import os
import shutil
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import check  # noqa: E402
import page  # noqa: E402
import tickets  # noqa: E402

SENTINEL = "VAS00000000000"
STRANGER = "SOMEONEELSE"
# Normalised, so accept_rule_is_exact reads the rule and not INV-72's
# normalisation: a fixture carrying its "+" would also redden that case under
# normalise_case_only.
LEGACY = tickets.LEGACY_PREFIX + "0" * (tickets.LEGACY_DIGITS - len(tickets.LEGACY_PREFIX))
BEFORE = datetime(2025, 2, 28)
AT_CUTOFF = datetime(2025, 3, 1)

PURCHASE = ("Standard Bank: Played R30.00 Lotto Plus 2 for 3 draw(s)\n"
            "Date 01/01/2020 to 01/01/2020\nA: 07 11 19 23 31 44\n"
            f"Ref:{SENTINEL}.")
PAYOUT = f"You received winnings of R50.00 for ticket ref: {SENTINEL}"


def spellings_collapse():
    got = {tickets.normalise_sender(a) for a in ("StdBank ", "STDBANK\n", "stdbank")}
    assert got == {"STDBANK"}, f"three spellings did not collapse: {sorted(got)!r}"
    digits = tickets.normalise_sender("+" + LEGACY)
    assert digits == LEGACY, f"'+' not removed: {digits!r}"
    return "three spellings -> STDBANK; '+' removed"


def accept_rule_is_exact():
    # Each fixture isolates one condition (LOTTO-0062 INV-73).
    cases = [
        ("known name", "STDBANK", BEFORE, True),
        ("another name", STRANGER, BEFORE, False),
        ("empty address", "", BEFORE, False),
        ("legacy before cutoff", LEGACY, BEFORE, True),
        ("legacy at cutoff", LEGACY, AT_CUTOFF, False),
        ("fifteen digits", LEGACY[:-1], BEFORE, False),
        ("other prefix", "1" + LEGACY[1:], BEFORE, False),
        ("prefix plus a letter", LEGACY[:-1] + "X", BEFORE, False),
    ]
    wrong = [label for label, addr, when, want in cases
             if tickets.sender_known(addr, when) is not want]
    assert not wrong, f"sender_known() wrong for: {wrong}"
    return f"{len(cases)} fixtures, one condition each"


def _row(n, address, when, body):
    ms = int((when.timestamp()) * 1000)
    return f"Row: {n} address={address}, date={ms}, body={body}\n"


def unknown_is_kept():
    d = tempfile.mkdtemp(prefix="verify_senders-")
    try:
        path = os.path.join(d, "dump.txt")
        when = datetime(2026, 7, 1, 12)
        with open(path, "w") as fh:
            fh.write(_row(0, STRANGER, when, PURCHASE))
            fh.write(_row(1, STRANGER, when, PAYOUT))
        tk, paid = tickets.load(path), tickets.load_payouts(path)
    finally:
        shutil.rmtree(d)
    assert len(tk) == 1, f"{len(tk)} tickets loaded from one unknown-sender purchase"
    assert len(paid) == 1, f"{len(paid)} payouts loaded from one unknown-sender payout"
    flags = [tk[0].sender_known, paid[0].sender_known]
    assert flags == [False, False], f"sender_known not False on both: {flags}"
    assert tk[0].sender == STRANGER, f"sender not normalised onto the ticket: {tk[0].sender!r}"
    return "one ticket and one payout kept, both flagged"


def _flagged(record, known, sender=STRANGER):
    record.sender, record.sender_known = sender, known
    return record


def unknown_is_shown():
    t_bad = _flagged(tickets.parse(PURCHASE, datetime(2026, 7, 2)), False)
    t_ok = _flagged(tickets.parse(PURCHASE, datetime(2026, 7, 3)), True, "STDBANK")
    t_fixture = tickets.parse(PURCHASE, datetime(2026, 7, 4))   # sender_known None
    p_bad = _flagged(tickets.Payout(SENTINEL, 5000, datetime(2026, 7, 1)), False)

    listed = check.unknown_senders([t_bad, t_ok, t_fixture], [p_bad])
    kinds = [(f["kind"], f["received"]) for f in listed]
    assert kinds == [("payout", "2026-07-01"), ("purchase", "2026-07-02")], \
        f"wrong records or order: {kinds}"

    html = page._senders_section({"unknown_senders": listed})
    for want in ("From a sender not seen before", "2026-07-01", "payout",
                 SENTINEL, STRANGER):
        assert want in html, f"page section lacks {want!r}"
    lines = "\n".join(check.unknown_senders_report(listed))
    assert SENTINEL in lines and STRANGER in lines, "terminal lines lack ref or sender"

    assert check.unknown_senders([t_ok, t_fixture], []) == [], "a known or unchecked record listed"
    assert page._senders_section({"unknown_senders": []}) == "", "heading over an empty list"
    assert page._senders_section({}) == "", "absent key rendered something"
    assert check.unknown_senders_report([]) == [], "empty list printed lines"
    return "listed oldest first; page and terminal name each; empty renders nothing"


CASES = [
    ("spellings_collapse", "INV-72", spellings_collapse),
    ("accept_rule_is_exact", "INV-73", accept_rule_is_exact),
    ("unknown_is_kept", "INV-74", unknown_is_kept),
    ("unknown_is_shown", "INV-75", unknown_is_shown),
]

ACTIVE_CASE = None  # set by main(); a break fires only in its own case

BREAKS = {
    "normalise_case_only": "spellings_collapse",
    "legacy_any_date": "accept_rule_is_exact",
    "prefix_only": "accept_rule_is_exact",
    "drop_unknown": "unknown_is_kept",
    "section_silent": "unknown_is_shown",
}


def _apply_break(name):
    """Patch one production function, live only while its own case runs."""
    def scoped(real, broken):
        return lambda *a: (broken if ACTIVE_CASE == BREAKS[name] else real)(*a)

    if name == "normalise_case_only":
        tickets.normalise_sender = scoped(tickets.normalise_sender,
                                          lambda a: str(a).upper())
    elif name in ("legacy_any_date", "prefix_only"):
        def broken(address, received):
            n = tickets.normalise_sender(address)
            if n in tickets.KNOWN_SENDERS:
                return True
            ok = n.isdigit() and n.startswith(tickets.LEGACY_PREFIX)
            if name == "legacy_any_date":        # the date condition dropped
                return ok and len(n) == tickets.LEGACY_DIGITS
            return ok and received < tickets.LEGACY_UNTIL   # length dropped
        tickets.sender_known = scoped(tickets.sender_known, broken)
    elif name == "drop_unknown":
        real_t, real_p = tickets.load, tickets.load_payouts
        tickets.load = scoped(real_t, lambda p: [t for t in real_t(p) if t.sender_known])
        tickets.load_payouts = scoped(real_p, lambda p: [x for x in real_p(p) if x.sender_known])
    elif name == "section_silent":
        page._senders_section = scoped(page._senders_section, lambda m: "")


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
            broken = argv[i + 1] if i + 1 < len(argv) else None
            if broken not in BREAKS:
                print(f"unknown break {broken!r}; --list shows them")
                return 2
            _apply_break(broken)
            print(f"BREAK {broken}: {BREAKS[broken]} must FAIL\n")

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
