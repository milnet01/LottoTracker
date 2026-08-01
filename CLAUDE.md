# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal tool that reads South African National Lottery ticket SMSes (Standard
Bank wording) off an Android phone, scores every ticket against real draw
results, and reports what is still claimable. Pure Python 3.8+ standard library
plus `dbus-python` (only for `find_lotto_sms.py`). No package manager, no
virtualenv, no test framework, no build step — everything runs as `python3 <file>`
from the repository root.

## Commands

```bash
python3 backfill.py            # one-off: scrape pre-2026-06-01 results into
                               # archive_results.json + archive_cache/ (12 fetches)
python3 check.py               # score every ticket, print claimable wins
python3 results.py             # smoke-test the official API (prints 3 recent draws/game)
python3 find_lotto_sms.py      # pull new lottery SMSes over KDE Connect (D-Bus)
```

Verification — there is no test runner; these three scripts *are* the test
suite, and each maps to a numbered invariant in the specs. Run from the
repository root, after `backfill.py`, with `lotto_sms_raw.txt` present:

```bash
python3 tools/verify_sources.py   # INV-3: the two results sources agree on overlap
python3 tools/verify_coverage.py  # INV-6: each ticket scored over exactly its draws
python3 tools/verify_privacy.py   # INV-4: no real SMS content is tracked by git
```

Exit code is the signal, not the printed counts (`&& echo PASS`). Counts in the
specs are dated snapshots that grow — **except** the unscorable ratio, which
fails above 90% because that is what a missing `archive_results.json` looks
like. The remaining invariants (INV-1, INV-2, INV-5) are one-line `python3 -c`
commands recorded in §5 of `docs/specs/LOTTO-0001-lottery-ticket-tracker.md`;
run them from there rather than re-inventing them.

## Architecture

Data flows in one direction, and the two halves are independent:

```
phone ──adb/KDE Connect──> lotto_sms_raw.txt ──tickets.py::parse()──> [Ticket]
                                                                          │
results.py    (official API, 2026-06-01 on, has payouts) ──┐              │
backfill.py   (scraped archive, 2025-01-01 on, no payouts) ┴─ history.py ─┴─> check.py
```

- **`tickets.py`** is the only bank-specific file. `parse()` handles two SMS
  eras and `GAME_MAP` translates an SMS game name to `(game, plus_flag, pool_id)`.
- **`results.py` / `backfill.py`** are two results sources with different
  shapes; **`history.py`** normalises both into one draw record
  `{date, main, special, issue, source}` and is the only place that merges them.
  `issue` (the draw number) exists only for API draws — that asymmetry is why
  `check.py::amount()` has two pricing paths.
- **`check.py`** scores and prices. Prize divisions are read from the live
  source, never hardcoded (INV-5).
- **`tools/verify_*.py`** import the modules directly via a `sys.path` insert.

### Load-bearing decisions — do not "simplify" these

- **A ticket nothing can score is *uncheckable*, not a loss.** `history.py::scorable()`
  gates it out and `check.py` reports the two reasons separately (predates all
  draw data / pool no source publishes). Silently scoring such a ticket against
  the wrong draws is the bug this project was built after hitting.
- **The PowerBall is the final number on a board line in both eras**, marked
  with `-` only in the new format. Treating it as a main number scores every
  PowerBall ticket one match high and never matches the PB (INV-1).
- **A Lotto board with >6 numbers is Multiplay** and expands to one line per
  6-number combination, each winning independently (INV-2). Currently
  Lotto-only — see LOTTO-0007(d).
- **`paying_combinations()` raises** rather than returning `{}` when a pool has
  no recent draw. An empty set would score the whole pool as losses with no
  diagnostic.
- **`daily/1` (Daily Lotto Plus) is deliberately mapped to a pool no source
  carries**, so those 11 tickets read as uncheckable. Aliasing them onto plain
  Daily Lotto would score them against a different game. `tools/verify_sources.py`
  exempts it via `EXPECTED_EMPTY`.
- **Source-agreement comparison is set-based**: the archive sorts numbers
  ascending, the API preserves drawn order.
- **Site slugs renamed at the June 2026 rebrand** (Lotto Plus 2 → Lotto 5 Max,
  PowerBall Plus → XTRA) and the archive rewrote its *old* links to match, so
  `PAYOUT_SLUG` uses current names for historic draws.

## Privacy — this repo is intended to be public

`lotto_sms_raw.txt` and `archive_cache/` are real personal data and are
gitignored. The non-obvious part: **never paste real message content into code,
docs or commit messages**, even with the reference scrubbed — numbers, date and
amount identify a ticket on their own. Two leaks got past weaker checks, one per
review loop. Sample references must be the sentinel `VAS00000000000`. Run
`python3 tools/verify_privacy.py` before any commit that touches prose or
examples; it compares tracked files against the dump itself, not a guessed
pattern.

## Working conventions

- Roadmap items are `LOTTO-000N` in `ROADMAP.md`; commits are
  `LOTTO-000N: <description>`. `CHANGELOG.md` follows Keep a Changelog and
  each entry cites its id.
- Specs live in `docs/specs/LOTTO-000N-<topic>.md` and carry numbered
  invariants (INV-n), failure modes, and a cold-eyes loop log. Code comments
  reference those invariants — when changing behaviour, update the spec's
  invariant and its §11 "what checks this" row in the same change.
- **`LOTTO-0009` (score every pool a ticket was entered in) is specced,
  accepted and unimplemented, and blocks `LOTTO-0002`.** Today a PLUS ticket is
  scored against one pool only, so 558 of 1,233 paid entries (45%) are checked —
  reported totals are known-low. Read
  `docs/specs/LOTTO-0009-entered-pools.md` before touching `GAME_MAP`,
  `Ticket`, or anything that counts tickets.
- Known deferred rough edges are listed under `LOTTO-0007` in `ROADMAP.md`;
  check there before reporting one as new.
