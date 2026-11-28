# CLAUDE.md

## What this is

A personal tool that reads South African National Lottery ticket SMSes (Standard
Bank wording) off an Android phone and builds **one consolidated ledger** of
every ticket: what was chosen, what was drawn, what it won, what it cost.

**Its primary job is telling the user when a ticket is about to run out, so
they buy the next one** — they buy for ten draws at a time (settled with the
user 2026-08-20). Surfacing wins before the 365-day claim deadline is still
true and useful, but not the headline: the bank pays most small wins back
automatically (LOTTO-0011). **The five signs of success are in `README.md`
§ How you would know it works** — read them before adding a feature, and take
which are open from the standing line there.

Pure Python 3.9+ standard library. **`ruff.toml`'s `py39` target holds the
SYNTAX floor; nothing checks library use** — CI runs a much newer Python — so
check a new stdlib call's version by hand. Plus `dbus-python`
(`find_lotto_sms.py`, `watch_sms.py`), PyGObject (`watch_sms.py`'s GLib main
loop) and PySide6 (`tray.py`, and the one `verify_page.py` case that starts it
in a subprocess). No package manager, no virtualenv, no test framework, no
build step — everything runs as `python3 <file>` from the repository root.

## Commands

```bash
python3 backfill.py            # one-off: scrape pre-2026-06-01 results into
                               # archive_results.json + archive_cache/. One fetch
                               # per pool per year, backfill.FIRST_YEAR..today
python3 check.py               # score every ticket, print claimable wins
python3 results.py             # smoke-test the official API (prints 3 recent draws/game)
python3 find_lotto_sms.py      # INSPECT SMSes over KDE Connect: prints, writes
                               # nothing, wider keyword list than the pipeline
python3 watch_sms.py           # the cable-free import (LOTTO-0003): listen over
                               # KDE Connect and APPEND new lottery SMSes to the
                               # dump. --once catches up and exits; tray.py
                               # starts the long-running form
python3 serve.py               # the local page on http://127.0.0.1:4322 (headless-safe)
python3 tray.py                # the tray icon: starts serve.py, opens the page, reaps it
tools/build_appimage.sh        # LOTTO-0015: dist/LottoTracker-<VERSION>-x86_64.AppImage;
                               # its data lives in ~/.local/share/LottoTracker
python3 tools/verify_appimage.py  # the built AppImage end to end: by hand, before a
                               # release, phone unreachable. Not in ./local-CI.sh
tools/build_apk.sh             # LOTTO-0106: dist/LottoTracker-<VERSION>.apk, in podman;
                               # signs with the key in ~/.config/LottoTracker-signing
python3 tools/verify_apk.py    # the built APK: no data file, the exact permissions,
                               # backup off. By hand, before a release
```

**A data path comes from `paths.py`, never from a module's own folder**: the
AppImage's code folder is read-only.

**`./local-CI.sh` is the pre-push gate — run it before every `git push`.** CI
runs the same script (`--ci`). **It gates COMMITTED changes** (the refs being
pushed, or `upstream..HEAD` by hand), and skips most checks when those are
documentation only. **So use `--force` to gate work you have not committed
yet**, or it may test none of your edits. Once per clone, since git does not
track hooks:

```bash
git config core.hooksPath .githooks   # pre-push runs the gate; pre-commit runs
                                      # the privacy check on the STAGED files
```

The two lanes are **not** equal and must not be made so: most verifiers need
`lotto_sms_raw.txt` or the scraped archive, which may never reach a public
runner. A green tick on GitHub is weaker than a green `./local-CI.sh`;
`local-CI.sh`'s header holds the reasoning.

**What each verifier checks, which lane runs it, and how the gate picks what
to run, are in `.claude/rules/verifiers.md`.** It loads when you Read a file
under `tools/`, `local-CI.sh`, `.githooks/` or `.github/` natively; read it
by hand otherwise.

Exit code is the signal, not the printed counts. Counts in the specs are dated
snapshots that grow — **except** the unscorable ratio, which fails above 90%
because that is what a missing `archive_results.json` looks like. The remaining
invariants are one-line `python3 -c` commands in their spec's §5 — INV-1,
INV-2 and INV-5 in `docs/specs/LOTTO-0001-lottery-ticket-tracker.md`, INV-8,
INV-9 and INV-10 in `docs/specs/LOTTO-0009-entered-pools.md`. **INV-10 has no
verifier at all.** Run them from there rather than re-inventing them.

## Architecture

**The data-flow diagram, what each file owns, and the load-bearing decisions
not to "simplify" are in `.claude/rules/architecture.md`.** It loads when you
Read a `.py` file natively. An Ants-verb read does not load it, so read it by
hand before changing code you have only seen through a verb.

## Privacy — this repo is intended to be public

`lotto_sms_raw.txt` and `archive_cache/` are real personal data and are
gitignored. **Never paste real message content into code, docs or commit
messages**, even with the reference scrubbed — numbers, date and amount
identify a ticket on their own. Sample references must be the sentinel
`VAS00000000000` — **the one sentinel, not a family of them.** Every
reference-shaped string that is not exactly that is a leak, invented or not; a
fixture needing a second reference uses a name that is not reference-shaped
(`tools/verify_payouts.py` does this).

**A notification carries no ticket data, in any branch — every notification
path, including one added later**, because a notification may be logged and
synced off the machine. It holds absolutely for `new_ticket_notice()` and
`refresh_message()`. **One bounded exception (LOTTO-0034 §3.3):** the desktop
re-buy notice names the game, the final draw date and the number of draws
left, held by INV-54; the user chose that usefulness. A new notification
takes the rule, not the exception.

Run `python3 tools/verify_privacy.py --require-content` before any commit that
touches prose or examples — **without that flag a missing dump exits 0** and
the content half never ran. **It only reads TRACKED files**: a new file passes
every local run until `git add` makes it tracked, then fails at the push. If
the change adds a file, `git add` it first, then run the check.

## Working conventions

- Roadmap items are `LOTTO-000N`; commits are `LOTTO-000N: <description>`.
  **The roadmap store is the source of truth; `ROADMAP.md` is its rendered
  output.** Write through `roadmap_log`, read through `roadmap_query`, never
  hand-edit the file. Before any `roadmap_log` write, any `roadmap_migrate`,
  or any commit touching `ROADMAP.md`, read `docs/roadmap-workflow.md`.
  `CHANGELOG.md` follows Keep a Changelog and each entry cites its id.
- Specs live in `docs/specs/LOTTO-000N-<topic>.md` and carry numbered
  invariants (INV-n). Code comments cite them — when changing behaviour,
  update the spec's invariant and its "what checks this" row in the same
  change.
- **Keep the app light: as little RAM, CPU and GPU as it can use** (the user,
  2026-11-18). No polling loop where an event will do, no animation or script
  running on an idle page; prefer what the browser and standard library
  provide over a new dependency. Nothing checks this, so measure a change that
  could cost memory or time before calling it done.
- **Count in entries, not tickets** (LOTTO-0009): every paid entry is scored.
  Read `docs/specs/LOTTO-0009-entered-pools.md` before touching `GAME_MAP`,
  `TIER_PRICES`, `Ticket`, or anything that counts tickets — §4.2's price
  table is hardcoded, like `DRAW_DAYS`, and is the one most likely to rot.
- **The page must never let "no data" read as "did not win"** — the cardinal
  rule. `page.py::_money_cell()` renders `won_cents: None` as "not checkable"
  and an integer `0` as `R0.00`, and they must not converge; `_draws_cell()`
  does the same for `draws_covered`/`draws_remaining`.
  **`page.py::_periods_section()` needs neither**: a period bucket exists only
  where a draw was scored, so `R0.00` there always means *checked, won
  nothing*. Do not add a `None` branch there, and do not emit a bucket for a
  period nothing scored. An empty page is correct only with a notice naming
  *why* (the dump is missing, the first build failed, or `LOTTO_NO_BUILD` is
  set) — **and never a ticket table, a zero total or an empty wins list
  beneath it**. `LOTTO-0002` §6 owns the prohibition;
  `tools/verify_page.py::uncheckable_not_a_loss` catches a breach.
- **Every `review-code` sweep leaves a record file in `docs/reviews/`** —
  what each lane found, verified and dismissed (the user, 2026-09-28).
- Known deferred rough edges are a lettered list in `LOTTO-0007`'s body;
  `roadmap_query` it by id before reporting one as new. **Add one with
  `roadmap_log op:"annotate"` against `LOTTO-0007`**, never by editing the
  file.
