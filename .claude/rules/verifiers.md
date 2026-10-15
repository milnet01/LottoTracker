---
paths:
  - "tools/**"
  - "local-CI.sh"
  - ".githooks/**"
  - ".github/**"
---

# Verifiers — what each one checks, and which lane runs it

Moved out of `CLAUDE.md` § Commands so it loads only when the verifiers
are being touched. `CLAUDE.md` keeps the rules about running them.

Verification — there is no test runner; these scripts *are* the test
suite, and each maps to a numbered invariant in the specs. Run from the
repository root, after `backfill.py`, with `lotto_sms_raw.txt` present. The CI
lane is the verifiers that still run honestly on a fresh clone; the rest FAIL
there on missing input, and that failure is what puts a verifier on the local
lane. `verify_page.py` needs neither input, `verify_hooks.py` builds a
throwaway repository instead, and `verify_senders.py` a throwaway dump; `verify_watch.py` needs no phone
and no `dbus-python` either, and reads the dump only if it is there;
`verify_privacy.py` drops to its weaker pattern-only mode. So
`verify_sources.py` is on the local lane despite needing no dump — it reads the
archive:

```bash
python3 tools/verify_sources.py   # INV-3: the two results sources agree on overlap
python3 tools/verify_coverage.py  # INV-6: each entry scored over exactly its draws
python3 tools/verify_privacy.py   # INV-4: no real SMS content is tracked by git
python3 tools/verify_pools.py     # INV-7/11/22/26/31: prices resolve; partly-checkable
                                  # tickets are never written off whole
python3 tools/verify_page.py      # the page, its security boundary, the tray's
                                  # spawn-and-reap lifecycle, what it reports after a
                                  # refresh, the port it binds, the managed (no-icon)
                                  # run, the colour themes, and the results transport
                                  # underneath them. Its own CASES table names the
                                  # invariant each case covers — read it there, not
                                  # from a list here, which went stale twice
python3 tools/verify_periods.py   # INV-57..INV-60: cost against winnings per
                                  # period. Money belongs to the period of the
                                  # DRAW, never of the purchase; both sides are
                                  # drawn over the scorable entries of RESOLVED
                                  # tickets; a period nothing scored gets no
                                  # bucket at all. --break/--list like
                                  # verify_page
python3 tools/verify_payouts.py   # INV-40..INV-47: the bank's own payout SMSes,
                                  # reconciled per VAS reference against every
                                  # computed win; --break/--list like verify_page
python3 tools/verify_expiry.py    # INV-49..INV-56, INV-61, INV-64: the re-buy
                                  # warning - the draw calendar against real
                                  # history in BOTH directions, that an EXPIRED
                                  # ticket is never warned about, that a notice
                                  # is said once and names nothing but game,
                                  # date and count, and that dates are SAST
                                  # whatever $TZ says; --break/--list like
                                  # verify_page
python3 tools/verify_watch.py     # INV-32..INV-39: the cable-free SMS path writes
                                  # what adb would, never twice, and its child is
                                  # spawned, observed and reaped; two watchers
                                  # appending at once collide never; and a KDE
                                  # Connect restart is read as one
python3 tools/verify_senders.py   # INV-72..INV-75: a lottery SMS from a sender
                                  # the bank is not known to use is KEPT and
                                  # flagged on the page and in check.py, never
                                  # dropped; --break/--list like verify_page
python3 tools/verify_hooks.py     # LOTTO-0004: .githooks/pre-commit refuses a
                                  # commit carrying a reference, reading the
                                  # STAGED copy; --break/--list like verify_page
```

`verify_page.py` is the one verifier that needs PySide6 installed — its
`tray_headless_when_managed` case imports `tray.py` in a subprocess. It needs no
display.
