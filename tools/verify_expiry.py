#!/usr/bin/env python3
"""LOTTO-0034 INV-49..INV-56: the re-buy warning, from the calendar alone.

    python3 tools/verify_expiry.py                       # all eight
    python3 tools/verify_expiry.py --list
    python3 tools/verify_expiry.py --break no_lower_bound   # RED-TEST: must FAIL

This item is greenfield, so there was no pre-fix code to red-test against.
`--break` is what makes "every case observed failing" reproducible rather than
a one-off hand edit, exactly as CLAUDE.md records for verify_page.py.

IT GOES IN local-CI.sh's DATA-DEPENDENT LANE, and it has no weak mode. Three of
the eight cases need real data and not the same data:

    calendar_matches_history    the merged draw record, via history.all_draws()
    calendar_matches_real_draws the merged draw record AND lotto_sms_raw.txt
    expired_tickets_are_silent  lotto_sms_raw.txt - the point of the case is the
                                real dump of mostly-finished tickets

A verifier that silently skipped its three most rot-prone cases on a public
runner would be the degraded-mode trap verify_privacy.py already carries and
local-CI.sh's header warns about. These three FAIL without their inputs.

PRIVACY. No message content and no ticket reference is printed, for the reason
verify_payouts.py states: this runs in a lane whose output is read, and a
verifier echoing real content puts it where verify_privacy.py cannot see it.
The two constructed fixtures use the one sentinel reference and a name that is
not reference-shaped at all.

The two cases that touch a state file write to a temporary directory via
$XDG_CONFIG_HOME, never to the user's real config.
"""

import datetime
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import expiry  # noqa: E402
import supervise  # noqa: E402
from history import all_draws, covered  # noqa: E402
from tickets import Ticket, load  # noqa: E402

SENTINEL = "VAS00000000000"
SECOND_REF = "second-ticket"  # deliberately NOT reference-shaped (CLAUDE.md)

GAMES = ("lotto", "powerball", "daily")
TODAY = datetime.date(2026, 8, 22)


def ticket(game="powerball", start=datetime.datetime(2026, 8, 1), ndraws=10,
           ref=SENTINEL):
    """A Ticket carrying only what the warning reads. No real data anywhere."""
    return Ticket(game, 0, 100, start, ndraws, [[1, 2, 3, 4, 5]], ref,
                  60.0, [(0, 100)], start, True)


def _tmp_state():
    return os.path.join(tempfile.mkdtemp(prefix="lotto-expiry-"), "warned.json")


# ------------------------------------------------------------------- the cases


def calendar_matches_history():
    """INV-49: DRAW_DAYS agrees with observed history in BOTH directions.

    The second half is not decoration: checking only that draws land on listed
    days passes a REMOVED draw day forever. And the record is the MERGED one,
    with the window measured from its newest draw rather than from today -
    archive_results.json only advances when backfill.py is re-run by hand, so a
    case reading the archive alone could never see a change made after the last
    scrape and would decay to wholesale failure as the file aged.
    """
    out = []
    for game in GAMES:
        rows = all_draws(game, 0)
        assert rows, f"{game}: no draw record - run backfill.py"
        days = expiry.DRAW_DAYS[game]
        on = sum(1 for r in rows
                 if datetime.date.fromisoformat(r["date"]).weekday() in days)
        share = on / len(rows)
        assert share >= 0.98, f"{game}: only {on}/{len(rows)} draws on a listed day"

        newest = datetime.date.fromisoformat(rows[-1]["date"])
        window = newest - datetime.timedelta(days=90)
        seen = {datetime.date.fromisoformat(r["date"]).weekday() for r in rows
                if datetime.date.fromisoformat(r["date"]) >= window}
        missing = sorted(days - seen)
        assert not missing, (
            f"{game}: table lists weekday(s) {missing} with no draw in the 90 "
            f"days to {newest} - a removed draw day"
        )
        out.append(f"{game} {on}/{len(rows)}")
    return ", ".join(out)


def expiry_is_pure():
    """INV-50: expiry.py imports no project module, opens no file, no network.

    Two halves, because either alone is weak. The source scan catches an import
    added at module scope; the call with open() disabled catches one made
    lazily inside a function - which is how "let me just consult the known
    draws" actually gets written.
    """
    here = os.path.join(os.path.dirname(__file__), "..")
    imported = set()
    for line in open(os.path.join(here, "expiry.py")):
        line = line.strip()
        if line.startswith("import "):
            imported.add(line.split()[1].split(".")[0])
        elif line.startswith("from ") and " import " in line:
            imported.add(line.split()[1].split(".")[0])
    assert imported == {"datetime"}, f"expiry.py imports {sorted(imported)}"

    args = ("lotto", datetime.date(2026, 8, 1), 10)
    want = expiry.final_draw_date(*args)

    import builtins
    real_open = builtins.open

    def no_open(*a, **k):
        raise AssertionError(f"expiry opened {a[0]!r}")

    builtins.open = no_open
    try:
        got = expiry.final_draw_date(*args)
        left = expiry.draws_left(*args, TODAY)
    finally:
        builtins.open = real_open
    assert got == want, f"{got} != {want} with open() disabled"
    return f"imports only datetime; {want} and {left} draws left with no I/O"


def calendar_matches_real_draws():
    """INV-51: within one day of the real last draw, exact for >= 98%.

    Compared against every entry whose history.covered() is COMPLETE, which is
    the only population where the real final draw is known. A one-day deviation
    is immaterial to a warning that fires several days ahead; the floor is what
    stops the projection rotting silently.
    """
    exact = off_by_one = worse = 0
    for t in load():
        for plus_flag, _pool_id in t.pools:
            rows = covered(t, plus_flag)
            if len(rows) != t.ndraws:
                continue
            real = datetime.date.fromisoformat(rows[-1]["date"])
            try:
                got = expiry.final_draw_date(t.game, t.start, t.ndraws)
            except KeyError:
                continue
            delta = abs((got - real).days)
            if delta == 0:
                exact += 1
            elif delta == 1:
                off_by_one += 1
            else:
                worse += 1
    total = exact + off_by_one + worse
    assert total, "no fully-covered entry to compare - run backfill.py"
    assert not worse, f"{worse} of {total} entries off by more than one day"
    assert exact / total >= 0.98, f"only {exact}/{total} exact"
    return f"{exact}/{total} exact, {off_by_one} off by one"


def expired_tickets_are_silent():
    """INV-52: no notice, ever, for a ticket whose draws_left is zero.

    Run against the REAL dump, because that is where the failure lives: 561
    tickets, nearly all finished, and a qualifying test written as `<= 2`
    without the lower bound fires hundreds of notices on its first run.
    """
    real = load()
    assert real, "no tickets - lotto_sms_raw.txt is missing"
    eligible = [t for t in real
                if 0 < expiry.draws_left(t.game, t.start, t.ndraws, TODAY)
                <= supervise.WARN_AT]
    notices = supervise.expiry_notices(TODAY, real, _tmp_state())
    assert len(notices) == len(eligible), (
        f"{len(notices)} notices for {len(eligible)} live tickets out of "
        f"{len(real)} - expired tickets are being warned about"
    )

    dead = ticket(start=datetime.datetime(2020, 1, 1), ndraws=10)
    assert expiry.draws_left(dead.game, dead.start, dead.ndraws, TODAY) == 0
    assert supervise.expiry_notices(TODAY, [dead], _tmp_state()) == []
    return f"{len(notices)} of {len(real)} tickets warned about"


def notice_is_said_once():
    """INV-53: one notice per reference, across calls and across restarts."""
    state = _tmp_state()
    live = [ticket(start=datetime.datetime(2026, 8, 21), ndraws=2)]
    assert expiry.draws_left(live[0].game, live[0].start, 2, TODAY) == 1

    first = supervise.expiry_notices(TODAY, live, state)
    assert len(first) == 1, f"first call gave {len(first)} notices"
    second = supervise.expiry_notices(TODAY, live, state)
    assert second == [], f"second call repeated it: {len(second)}"
    # A restart reads the same file from scratch; nothing is held in memory.
    third = supervise.expiry_notices(TODAY + datetime.timedelta(days=1), live, state)
    assert third == [], "a later day repeated it"
    return "said once, silent on the second and third call"


def notice_names_nothing_else():
    """INV-54: the game, the date and the count - and no other ticket field.

    The bound on §3.3's exception to the no-ticket-data rule. A desktop
    notification may be logged and synced off the machine, so "so the user
    knows what to spend" is exactly the addition this case exists to refuse.
    """
    t = ticket(start=datetime.datetime(2026, 8, 21), ndraws=2)
    body = supervise.expiry_notices(TODAY, [t], _tmp_state())[0]
    for want in ("PowerBall", "1 draw left", "Tue 25 Aug"):
        assert want in body, f"notice omits {want!r}"
    forbidden = {
        "reference": SENTINEL, "board numbers": "1, 2, 3",
        "cost": "60", "purchase date": "2026-08-21", "plural draws": "draws",
    }
    for what, needle in forbidden.items():
        assert needle not in body, f"notice leaks the {what} ({needle!r})"

    # The unrecognised-game notice names no game at all.
    unknown = supervise.expiry_notices(
        TODAY, [ticket(game="scratchcard")], _tmp_state())
    assert len(unknown) == 1
    for name in expiry.DISPLAY_NAME.values():
        assert name not in unknown[0], f"unknown-game notice names {name}"
    assert "scratchcard" not in unknown[0], "unknown-game notice names the game"
    return "game, date and count only"


def state_file_is_pruned():
    """INV-55: records more than 90 days past their final draw are dropped."""
    state = _tmp_state()
    stale = (TODAY - datetime.timedelta(days=200)).isoformat()
    fresh = (TODAY - datetime.timedelta(days=10)).isoformat()
    os.makedirs(os.path.dirname(state), exist_ok=True)
    with open(state, "w") as fh:
        json.dump({"warned": [{"ref": SENTINEL, "final": stale},
                              {"ref": SECOND_REF, "final": fresh}]}, fh)

    live = [ticket(ref="third-ticket", start=datetime.datetime(2026, 8, 21),
                   ndraws=2)]
    supervise.expiry_notices(TODAY, live, state)
    kept = {r["ref"] for r in json.load(open(state))["warned"]}
    assert SENTINEL not in kept, "a record 200 days past its final draw survived"
    assert SECOND_REF in kept, "a record 10 days past its final draw was dropped"
    assert "third-ticket" in kept, "the ticket just warned about was not recorded"
    return f"{len(kept)} records kept, the 200-day one dropped"


def unknown_game_is_loud():
    """INV-56: a game the table does not know raises, and says so ONCE.

    LOTTO-0031's failure class from the other end: there a rebranded game name
    parsed to None and the ticket was silently never scored. A rebrand makes
    every new ticket unknown at once, so one notice per ticket would be a burst
    of hundreds - and it is deliberately not recorded, so it recurs until the
    table is updated.
    """
    try:
        expiry.final_draw_date("scratchcard", TODAY, 10)
    except KeyError:
        pass
    else:
        raise AssertionError("final_draw_date returned for an unknown game")

    many = [ticket(game="scratchcard", ref=f"unknown-{i}") for i in range(5)]
    state = _tmp_state()
    first = supervise.expiry_notices(TODAY, many, state)
    assert len(first) == 1, f"5 unknown tickets gave {len(first)} notices"
    second = supervise.expiry_notices(TODAY, many, state)
    assert second == first, "the unrecognised-game notice went quiet on repeat"

    # A known ticket beside them is still warned about normally.
    mixed = many + [ticket(start=datetime.datetime(2026, 8, 21), ndraws=2)]
    assert len(supervise.expiry_notices(TODAY, mixed, _tmp_state())) == 2
    return "one notice for 5 unknown tickets, and it recurs"


CASES = [
    ("calendar_matches_history", "INV-49", calendar_matches_history),
    ("expiry_is_pure", "INV-50", expiry_is_pure),
    ("calendar_matches_real_draws", "INV-51", calendar_matches_real_draws),
    ("expired_tickets_are_silent", "INV-52", expired_tickets_are_silent),
    ("notice_is_said_once", "INV-53", notice_is_said_once),
    ("notice_names_nothing_else", "INV-54", notice_names_nothing_else),
    ("state_file_is_pruned", "INV-55", state_file_is_pruned),
    ("unknown_game_is_loud", "INV-56", unknown_game_is_loud),
]

BREAKS = {
    "unlisted_draw_day": "calendar_matches_history",
    "impure_expiry": "expiry_is_pure",
    "exclusive_start": "calendar_matches_real_draws",
    "no_lower_bound": "expired_tickets_are_silent",
    "never_records": "notice_is_said_once",
    "notice_names_ref": "notice_names_nothing_else",
    "no_prune": "state_file_is_pruned",
    "swallow_unknown_game": "unknown_game_is_loud",
    "notice_per_unknown_ticket": "unknown_game_is_loud",
}


def _apply_break(name):
    """Apply one deliberate defect. Seven of the nine patch production code.

    Said plainly rather than implied, as verify_payouts.py does: only
    `notice_per_unknown_ticket` patches expiry_notices()' OUTPUT rather than
    the code path, because emitting one notice per ticket is a shape of the
    loop rather than a value any single function returns.
    """
    if name == "unlisted_draw_day":
        expiry.DRAW_DAYS["lotto"] = {2, 5, 0}          # a Monday Lotto draw
    elif name == "impure_expiry":
        real = expiry.draw_dates

        def peeking(*a, **k):
            open(os.path.join(os.path.dirname(__file__), "..", "expiry.py")).close()
            return real(*a, **k)
        expiry.draw_dates = peeking
        expiry.final_draw_date = lambda g, s, n: peeking(g, s, n)[-1]
    elif name == "exclusive_start":
        real = expiry.draw_dates
        # `start` read as exclusive - the off-by-one §4.1 pins the boundary
        # against, which shifts every projected date.
        expiry.final_draw_date = lambda g, s, n: real(
            g, expiry._as_date(s) + datetime.timedelta(days=1), n)[-1]
    elif name == "no_lower_bound":
        supervise._qualifies = lambda left, ref, warned: (
            left <= supervise.WARN_AT and ref not in warned)
    elif name == "never_records":
        supervise._write_warned = lambda path, records: None
    elif name == "notice_names_ref":
        real = supervise.expiry_notice
        supervise.expiry_notice = lambda g, f, n: real(g, f, n) + f" ({SENTINEL})"
    elif name == "no_prune":
        supervise.PRUNE_DAYS = 100000
    elif name == "swallow_unknown_game":
        real = expiry.draws_left
        # A bare except, written as a default: the ticket is dropped in silence.
        expiry.draws_left = lambda g, s, n, t: (
            real(g, s, n, t) if g in expiry.DRAW_DAYS else 0)
    elif name == "notice_per_unknown_ticket":
        real = supervise.expiry_notices

        def per_ticket(today, tickets=None, state_path=None):
            out = real(today, tickets, state_path)
            if supervise.UNKNOWN_GAME_NOTICE in out:
                extra = sum(1 for t in (tickets or [])
                            if t.game not in expiry.DRAW_DAYS) - 1
                out += [supervise.UNKNOWN_GAME_NOTICE] * max(0, extra)
            return out
        supervise.expiry_notices = per_ticket


def main(argv):
    if "--list" in argv:
        for name, inv, _ in CASES:
            print(f"{inv}  {name}")
        print("\nbreaks:")
        for b, case in sorted(BREAKS.items()):
            print(f"  --break {b:26} -> {case} must FAIL")
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
            print(f"  {inv}  {name:28} PASS  {detail}")
        except AssertionError as e:
            failed.append(name)
            print(f"  {inv}  {name:28} FAIL  {e}")

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
