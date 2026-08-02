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
python3 serve.py               # the local page on http://127.0.0.1:4322 (headless-safe)
python3 tray.py                # the tray icon: starts serve.py, opens the page, reaps it
```

Verification — there is no test runner; these five scripts *are* the test
suite, and each maps to a numbered invariant in the specs. Run from the
repository root, after `backfill.py`, with `lotto_sms_raw.txt` present:

```bash
python3 tools/verify_sources.py   # INV-3: the two results sources agree on overlap
python3 tools/verify_coverage.py  # INV-6: each entry scored over exactly its draws
python3 tools/verify_privacy.py   # INV-4: no real SMS content is tracked by git
python3 tools/verify_pools.py     # INV-7/INV-11: prices resolve; partly-checkable
                                  # tickets are never written off whole
python3 tools/verify_page.py      # INV-12..INV-21: the page, its security boundary
                                  # and the tray's spawn-and-reap lifecycle
```

`verify_page.py` carries a `--break <name>` flag that applies one deliberate
defect and asserts the named case goes red. That is not a debugging aid: these
three items are greenfield, so there was no pre-fix code to red-test against,
and the flag is what makes "every case observed failing" reproducible rather
than a one-off hand edit. `--list` shows the thirteen breaks. It caught a real
defect in a *case* rather than in the code — see CHANGELOG.

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
                                                                              │
                                                    ┌─────────────────────────┴──┐
                                                    ▼                            ▼
                                        check.py::__main__            serve.py ──> page.py
                                        (the terminal output)         (the local page)
                                                                          ▲   │
                                                          tray.py ──> supervise.py
                                                          (PySide6)   (spawns serve.py;
                                                                       owns the settings
                                                                       reader both import)
```

- **`tickets.py`** is the only bank-specific file. `parse()` handles two SMS
  eras; `GAME_MAP` translates an SMS game name to the one `(game, plus_flag,
  pool_id)` it names, and `entered_pools()` derives the *full* set of pools
  from the ticket price, which is what scoring actually iterates
  (`Ticket.pools`).
- **`results.py` / `backfill.py`** are two results sources with different
  shapes; **`history.py`** normalises both into one draw record
  `{date, main, special, issue, source}` and is the only place that merges them.
  `issue` (the draw number) exists only for API draws — that asymmetry is why
  `check.py::amount()` has two pricing paths.
- **`check.py`** scores and prices. Prize divisions are read from the live
  source, never hardcoded (INV-5).
- **`serve.py`** is `check.py`'s second consumer and adds no third opinion: a
  wrong number on the page is a bug in its rendering or in LOTTO-0001/0009,
  never a separate calculation. It does **all** the I/O; **`page.py`** is a pure
  function from a model dict to one HTML string, which is what lets the whole
  page be rendered in a test with no socket and no `archive_results.json`.
- **`supervise.py`** owns the server child — its token, its port, its reaping —
  and is Qt-free so that lifecycle is checkable from a headless script.
  It also owns **reading** the two settings (`config_home()`, `autostart_path()`,
  `settings_path()`, `read_settings()`), because `tray.py` needs them and may
  not import `serve`; **`serve.py` imports them from here** and owns only the
  *writing*, behind `POST /settings`'s lock. One reader, three callers — do not
  add a second, however local it looks: two readers that agree today pass every
  check and diverge later (LOTTO-0013 §4.1).
  **`tray.py`** is the only file that imports PySide6.
- **`tools/verify_*.py`** import the modules directly via a `sys.path` insert.

### Load-bearing decisions — do not "simplify" these

- **An entry nothing can score is *uncheckable*, not a loss.** `history.py::scorable()`
  gates it out and `check.py::uncheckable_report()` reports the two reasons
  separately (predates all draw data / pool no source publishes). Silently
  scoring such an entry against the wrong draws is the bug this project was
  built after hitting. **The unit is the entry**: a ticket checkable in one
  pool and not another is *partly* uncheckable, still scored on the rest, and
  must never be counted as wholly excluded (INV-11).
- **A ticket is entered in every tier its price paid for**, base game first,
  because a PLUS game cannot be bought alone (INV-8). The tiers come from the
  price in whole cents, not from the printed name, which states only the top
  tier and since 2026-06-01 states none (INV-9). A price matching no tier is
  reported, never guessed at (INV-7) — `tickets.py::TIER_PRICES` is hardcoded
  because no feed publishes it, so `tools/verify_pools.py` is the only thing
  that makes a price change loud.
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
  carries**, so those 11 *entries* read as uncheckable while the same tickets'
  `daily/0` entries score normally — they are the project's only partly
  uncheckable tickets. Aliasing them onto plain Daily Lotto would score them
  against a different game. `tools/verify_sources.py` exempts it via
  `EXPECTED_EMPTY`.
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
- **Count in entries, not tickets.** `LOTTO-0009` shipped 2026-08-01: all
  1,233 paid entries across 558 tickets are scored, where 558 were before.
  Read `docs/specs/LOTTO-0009-entered-pools.md` before touching `GAME_MAP`,
  `TIER_PRICES`, `Ticket`, or anything that counts tickets — §4.2's price
  table is the one hardcoded table in the project and the one most likely to
  rot.
- **The page must never let "no data" read as "did not win"** — the cardinal
  rule, in its newest form. `page.py::_money_cell()` renders `won_cents: None`
  as "not checkable" and an integer `0` as `R0.00`, and they must not converge;
  `_draws_cell()` does the same for `draws_covered`/`draws_remaining`. An empty
  page is correct only when it carries a notice naming *why* (the dump is
  missing, the first build failed, or `LOTTO_NO_BUILD` is set) — three states,
  one rule. `tools/verify_page.py::uncheckable_not_a_loss` is what catches a
  breach, and its forbidden-strings list includes the empty string.
- Known deferred rough edges are listed under `LOTTO-0007` in `ROADMAP.md`;
  check there before reporting one as new.
