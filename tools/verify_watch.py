#!/usr/bin/env python3
"""LOTTO-0003 INV-32..INV-36: the cable-free SMS path writes what adb would.

`watch_sms.py` is the second writer of `lotto_sms_raw.txt`. The dump has always
had exactly one producer, and the invariants this file checks are the ones that
statement used to make for free:

  INV-32  the two collection paths agree on what belongs in the dump
  INV-33  a record this path writes reads back through the dump's own reader
  INV-34  a message already in the dump is never written a second time
  INV-35  the thread state that makes catch-up possible survives a corrupt file
  INV-36  the watcher child is spawned, observed and reaped like the server

INV-32 is checked against SQLite rather than against a second transcription of
the WHERE clause in Python. The clause below is copied from LOTTO-0001 §4.1, but
the thing most likely to be got wrong is not the words - it is LIKE's semantics,
and specifically that it is case-insensitive across ASCII while Python's `in` is
not. Asking the same engine adb asks is the only way that half is checked at
all; a hand-written Python equivalent would agree with its own mistake, which
is the lesson verify_pools.py's price table already carries.

Runs with no phone, no KDE Connect and no dbus-python. The dump is READ (the
real records are the best possible input for the de-duplication case) and never
written: every write in here goes to a temporary file.
"""

import os
import re
import sqlite3
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import supervise  # noqa: E402
import tickets  # noqa: E402
import watch_sms  # noqa: E402

DUMP = os.path.join(os.path.dirname(__file__), "..", "lotto_sms_raw.txt")

# LOTTO-0001 §4.1's adb clause, verbatim in its own language.
WHERE = (
    "(body LIKE '%lotto%' OR body LIKE '%powerball%' OR body LIKE '%VAS00%') "
    "AND body NOT LIKE '%kWh%' AND body NOT LIKE '%Enter tokens%'"
)

# Synthetic bodies only - never a real message (CLAUDE.md §Privacy). Each is a
# shape the dump actually holds, written from the spec's descriptions, with the
# sentinel reference. The last four are the ones the filter has to get right:
# two utility shapes that must be excluded, a payout that names no game and must
# be included, and a plain bank SMS that must not be.
#
# The prices are R99.00 throughout, and that is not decoration: R10.00 is a
# real ticket price, so a "synthetic" body built with it matched the dump
# verbatim and `tools/verify_privacy.py` refused the push. R99.00 is the amount
# tickets.py's own docstring uses, already proven absent from real data. A
# sample here must be impossible, not merely invented.
BODIES = [
    "Played R99.00 Lotto Plus 2 for 1 draw(s)\nDate 01/01/2020 to 01/01/2020\n"
    "A: 07 11 19 23 31 44\nRef:VAS00000000000",
    "Played R99.00 Powerball\nDate 01 Jan 2020 (for 10 draws)\n"
    "A: 08 14 27 33 41 -07\nRef:VAS00000000000",
    "Played R99.00 LOTTO 5 MAX for 2 draws\nRef:VAS00000000000",
    "Your lotto transaction was unsuccessful.",
    "R100.00 to VAS00000000000 LOTTO from Acc. 1234",
    # Included: names no game anywhere, which is what LOTTO-0030 was about.
    "The winnings of R50.00 for ticket ref: VAS00000000000 will be paid in "
    "your account within 24 hours.",
    # Excluded: prepaid electricity, which shares the VAS reference format.
    "R100.00 purchased for VAS00000000000. U: 52.3kWh. Token: 0000",
    # Excluded, and the reason one exclusion is not enough: the continuation
    # carries no kWh at all.
    "R100.00 for VAS00000000000. Enter tokens on SMS 1 first.",
    # Not lottery, not VAS: no marker, so neither path may take it.
    "Your account balance is R1,234.56 as at 01 Jan.",
    "Your OTP is 000000. Do not share it with anyone.",
]


def filter_matches_adb():
    """INV-32: wanted() accepts exactly what adb's WHERE clause accepts."""
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE sms (i INTEGER, body TEXT)")
    db.executemany("INSERT INTO sms VALUES (?, ?)", list(enumerate(BODIES)))
    sql = {i for (i,) in db.execute(f"SELECT i FROM sms WHERE {WHERE}")}
    py = {i for i, body in enumerate(BODIES) if watch_sms.wanted(body)}

    for i in sorted(sql ^ py):
        who = "adb only" if i in sql else "watcher only"
        print(f"  FILTER DISAGREEMENT on body {i} ({who})")
    # Anti-vacuity, the shape INV-3 and INV-6 carry: two empty sets agree, and
    # a filter that accepted nothing would pass this case in silence.
    if not sql:
        print("  NO ACCEPTED BODIES: the parity check passed over nothing")
    if len(sql) == len(BODIES):
        print("  EVERY BODY ACCEPTED: the exclusions were not exercised")
    return len(sql ^ py) + (not sql) + (len(sql) == len(BODIES))


def round_trip():
    """INV-33: what this path writes is what the dump's reader reads back."""
    bad = 0
    cases = [
        ("plain", "Std Bank", 1767936736696, BODIES[0]),
        ("multi-line body", "Std Bank", 1767936736697, BODIES[1]),
        # An address with a comma would swallow the date field whole.
        ("comma in address", "Bank, Std", 1767936736698, BODIES[2]),
        # An SMS body is outside data. A body carrying a record header must not
        # become a second record with a date nobody sent.
        ("header inside the body", "Std Bank", 1767936736699,
         "Played R99.00 Lotto for 1 draw(s)\nRow: 9 address=x, date=1, body=y"),
    ]
    for name, address, date_ms, body in cases:
        row = watch_sms.format_row(0, address, date_ms, body)
        got = tickets.rows(row)
        if len(got) != 1:
            print(f"  ROUND TRIP {name}: read back as {len(got)} records, not 1")
            bad += 1
            continue
        _address, got_date, got_body = got[0]
        if got_date != date_ms:
            print(f"  ROUND TRIP {name}: date {got_date} != {date_ms}")
            bad += 1
        # The body survives except for the deliberate header guard, which is
        # asserted by the record count above.
        if "Row: " not in body and got_body != body.strip():
            print(f"  ROUND TRIP {name}: body changed in the round trip")
            bad += 1
    return bad


def no_duplicates():
    """INV-34: a message the dump already carries is never appended again.

    Driven against the REAL dump's own records, copied to a temporary file. The
    catch-up pass re-offers history the dump already holds on every single run,
    so this is the normal path - and real records are the only input that can
    catch a de-duplication key that is wrong about real data.
    """
    bad = 0
    if os.path.exists(DUMP):
        real = tickets.rows(open(DUMP, errors="replace").read())[-40:]
    else:
        # Weaker input, not an absent check: the synthetic rows below still
        # exercise every branch. Said out loud rather than passed over, and NOT
        # counted as a failure - this file is in the CI lane precisely because
        # it needs no personal data, and a public runner has no dump to hold it
        # to. The local lane's three data-dependent verifiers are what fail
        # loudly when the dump is missing on this machine.
        print("  (no dump present: de-duplication ran on synthetic rows only)")
        real = []

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "dump.txt")
        # A fresh dump, built from the same writer under test.
        seed = [(a, d, b) for a, d, b in real] or [("Std Bank", 1767936736696, BODIES[0])]
        first = watch_sms.append_new(seed, path)
        if first != len(seed):
            print(f"  SEED: wrote {first} of {len(seed)} records into an empty dump")
            bad += 1
        again = watch_sms.append_new(seed, path)
        if again:
            print(f"  DUPLICATES: re-offering the same {len(seed)} records wrote {again}")
            bad += 1

        # A genuinely new message still gets through - the converse, without
        # which "wrote nothing" would pass this case for the wrong reason.
        fresh = [("Std Bank", 1767936736999, BODIES[5])]
        if watch_sms.append_new(fresh, path) != 1:
            print("  DEAF: a message the dump does not hold was not written")
            bad += 1
        # And an excluded shape never reaches the file at all.
        if watch_sms.append_new([("Std Bank", 1767936737000, BODIES[6])], path):
            print("  LEAK: an electricity SMS was written to the dump")
            bad += 1

        # Every record in the finished file still parses as one record.
        rows = tickets.rows(open(path, errors="replace").read())
        if len(rows) != len(seed) + 1:
            print(f"  SHAPE: file holds {len(rows)} records, expected {len(seed) + 1}")
            bad += 1
        indices = [int(m.group(1)) for m in
                   re.finditer(r"^Row: (\d+) address=", open(path).read(), re.M)]
        if indices != sorted(set(indices)):
            print(f"  INDICES: row numbers are not unique and ascending: {indices[:5]}…")
            bad += 1
    return bad


def thread_state():
    """INV-35: the catch-up state survives absence and corruption."""
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "threads.json")
        if watch_sms.read_threads(path) != set():
            print("  THREADS: a missing state file did not read as empty")
            bad += 1
        watch_sms.write_threads({2424, 17, 2424}, path)
        if watch_sms.read_threads(path) != {17, 2424}:
            print("  THREADS: ids did not survive a write/read round trip")
            bad += 1
        open(path, "w").write("{not json")
        if watch_sms.read_threads(path) != set():
            print("  THREADS: a corrupt state file did not read as empty")
            bad += 1
    return bad


def catch_up_targets():
    """INV-35: history is asked for exactly the threads that moved.

    The bound is the point. 543 of the phone's 2,325 threads match the filter
    (measured 2026-08-13), so a catch-up that asked all of them for 200
    messages would move a hundred thousand messages on every start. It must ask
    for the ones that moved and no others - and it must not answer "none" by
    being blind to the two shapes that need asking.
    """
    bad = 0
    water = 1_000
    # (date_ms, thread, matched)
    snapshot = [
        (2_000, 11, True),    # moved and lottery-shaped: ask
        (2_000, 12, False),   # moved, not lottery-shaped, but known: ask
        (2_000, 13, False),   # moved, not lottery-shaped, never seen: skip
        (900, 14, True),      # lottery-shaped but has not moved: skip
        (1_000, 15, True),    # exactly at the high-water mark: skip
    ]
    got = watch_sms.pull_targets(snapshot, {12, 14}, water)
    if got != {11, 12}:
        print(f"  TARGETS: asked for {sorted(got)}, expected [11, 12]")
        bad += 1
    if watch_sms.pull_targets([], {12}, water):
        print("  TARGETS: an empty snapshot still asked for history")
        bad += 1
    # A dump that holds nothing has no high-water mark, so everything lottery
    # shaped is fair game - the first-ever run must not be bounded to nothing.
    if watch_sms.pull_targets(snapshot, set(), 0) != {11, 14, 15}:
        print("  TARGETS: an empty dump did not open the catch-up up")
        bad += 1
    return bad


def watcher_lifecycle():
    """INV-36: the watcher child is spawned, observed and reaped.

    With an injected command, never the real `watch_sms.py`: that one talks to
    the phone and appends to the live dump, and a verifier must not do either.
    """
    bad = 0
    alive = supervise.SmsWatch([sys.executable, "-c", "import time; time.sleep(60)"])
    alive.start()
    if not alive.is_running():
        print("  LIFECYCLE: start() left nothing running")
        bad += 1
    if alive.died_early(timeout=1.0):
        print("  LIFECYCLE: a healthy child was reported as having died early")
        bad += 1
    child = alive.child
    alive.stop()
    if alive.is_running() or child.poll() is None:
        print("  LIFECYCLE: stop() did not reap the child")
        bad += 1

    dead = supervise.SmsWatch([sys.executable, "-c", "raise SystemExit(1)"])
    dead.start()
    if not dead.died_early(timeout=5.0):
        print("  LIFECYCLE: a child that exited at once was not reported")
        bad += 1
    dead.stop()

    if supervise.SmsWatch().command[-1] != os.path.join(supervise.HERE, "watch_sms.py"):
        print("  LIFECYCLE: the default command is not watch_sms.py")
        bad += 1
    return bad


def absent_dbus_is_named():
    """INV-36's other half: a watcher that cannot run says what it costs.

    Silence here is the project's cardinal failure arriving by a new road - no
    new tickets collected looks exactly like no new tickets won.
    """
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "dbus.py"), "w").write(
            "raise ImportError('no dbus in this environment')"
        )
        env = {**os.environ, "PYTHONPATH": tmp}
        done = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__), "..",
                                          "watch_sms.py"), "--once"],
            capture_output=True, text=True, env=env, timeout=60,
        )
    said = (done.stdout + done.stderr).lower()
    if done.returncode == 0:
        print("  ABSENT DBUS: the watcher exited 0 with no way to collect anything")
        return 1
    if "cable" not in said:
        print(f"  ABSENT DBUS: the failure does not name the cost: {said.strip()[:120]}")
        return 1
    return 0


CASES = (
    ("filter_matches_adb", filter_matches_adb),
    ("round_trip", round_trip),
    ("no_duplicates", no_duplicates),
    ("thread_state", thread_state),
    ("catch_up_targets", catch_up_targets),
    ("watcher_lifecycle", watcher_lifecycle),
    ("absent_dbus_is_named", absent_dbus_is_named),
)


def main(argv=()):
    if "--list" in argv:
        for name, fn in CASES:
            print(f"{name}: {(fn.__doc__ or '').splitlines()[0]}")
        return 0
    failed = 0
    for name, fn in CASES:
        bad = fn()
        print(f"{name}: {'FAIL' if bad else 'ok'}" + (f" ({bad})" if bad else ""))
        failed += bad
    print(f"{len(CASES)} cases, {failed} failure(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
