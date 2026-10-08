# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal tool that reads South African National Lottery ticket SMSes (Standard
Bank wording) off an Android phone and builds **one consolidated ledger** of
every ticket: what was chosen, what was drawn, what it won, what it cost.

**Its primary job is telling the user when a ticket is about to run out, so
they buy the next one** — they buy for ten draws at a time. That was settled
with the user on 2026-08-20 and it corrects the project's own earlier framing,
which led with surfacing wins before the 365-day claim deadline. That framing
was never the user's main need, and the bank pays most small wins back
automatically anyway (LOTTO-0011). **The five signs of success are in
`README.md` § How you would know it works** — read them before adding a
feature, and take which are open from the standing line THERE rather than from
a count here. This sentence carried its own tally until 2026-08-31 and was
wrong for three consecutive items, most recently claiming the primary sign was
the least built after LOTTO-0034 built it.
The claim-deadline material is still true and still useful, but it is not the
headline.

Pure Python 3.9+ standard library. **`ruff.toml`'s `py39` target holds the
SYNTAX floor; nothing checks library use** — CI runs a much newer Python — so
check a new stdlib call's version by hand.
Plus `dbus-python` (`find_lotto_sms.py`, `watch_sms.py`) and PySide6 (`tray.py`,
and the one `verify_page.py` case that starts it in a subprocess). No package
manager, no virtualenv, no test framework, no build step — everything runs as
`python3 <file>` from the repository root.

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
```

**`./local-CI.sh` is the pre-push gate — run it before every `git push`.** It
runs the verifiers below plus `ruff` and a syntax pass — but none of the
`python3 -c` invariant commands at the end of this section, which stay
hand-run. It is what
`.github/workflows/ci.yml` invokes (as `./local-CI.sh --ci`), so the runner and
this machine cannot drift apart — there is no second list of checks to forget.
On a local run, a documentation-only push (every changed file `.md`) still runs
`verify_privacy.py` at full strength — prose is its subject — and skips the
rest; it fails if that check fails. `--force` runs everything. **Under `--ci`
that branch is skipped entirely**, and `ci.yml` carries no `paths-ignore`, so
the whole CI lane runs on a docs push too.

**It classifies the push from the refs being pushed (`$GATE_RANGES`, which
`.githooks/pre-push` passes in), falling back to `upstream..HEAD` on a hand
run. Either way the unit is COMMITTED changes, so it is a push gate and not a
pre-commit check.** Run it by hand with uncommitted code in the tree and it
reads whatever is already committed: if that is documentation, it skips the
rest of the gate having tested none of your edits.
**Use `--force` to gate work you have not committed yet.** The
push hook is unaffected, because by then the work is committed — which is
exactly why the gap is easy to miss.

Make it structural rather than remembered — **once per clone**, because git
does not track hooks and `core.hooksPath` is local config:

```bash
git config core.hooksPath .githooks   # pre-push runs the gate; pre-commit runs
                                      # the privacy check on the STAGED files
```

The two lanes are **not** equal and must not be made so. Most verifiers need
`lotto_sms_raw.txt` or the scraped archive, neither of which may reach a public
runner, and `verify_privacy.py` drops to a weaker pattern-only mode without the
dump — while still exiting 0. So a green tick on GitHub is weaker than a green
`./local-CI.sh`, and the script asserts locally that the privacy check ran at
full strength rather than trusting its exit code. `local-CI.sh`'s header holds
the reasoning.

Verification — there is no test runner; these scripts *are* the test
suite, and each maps to a numbered invariant in the specs. Run from the
repository root, after `backfill.py`, with `lotto_sms_raw.txt` present. The CI
lane is the verifiers that still run honestly on a fresh clone; the rest FAIL
there on missing input, and that failure is what puts a verifier on the local
lane. `verify_page.py` needs neither input, and `verify_hooks.py` builds a
throwaway repository instead; `verify_watch.py` needs no phone
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
python3 tools/verify_hooks.py     # LOTTO-0004: .githooks/pre-commit refuses a
                                  # commit carrying a reference, reading the
                                  # STAGED copy; --break/--list like verify_page
```

`verify_page.py` is the one verifier that needs PySide6 installed — its
`tray_headless_when_managed` case imports `tray.py` in a subprocess. It needs no
display.

`verify_page.py` carries a `--break <name>` flag that applies one deliberate
defect and asserts the named case goes red. That is not a debugging aid: these
three items are greenfield, so there was no pre-fix code to red-test against,
and the flag is what makes "every case observed failing" reproducible rather
than a one-off hand edit. `--list` shows the breaks. It caught a real
defect in a *case* rather than in the code — see CHANGELOG.

Exit code is the signal, not the printed counts (`&& echo PASS`). Counts in the
specs are dated snapshots that grow — **except** the unscorable ratio, which
fails above 90% because that is what a missing `archive_results.json` looks
like. The remaining invariants are one-line `python3 -c` commands recorded in
their own spec's §5 — INV-1, INV-2 and INV-5 in
`docs/specs/LOTTO-0001-lottery-ticket-tracker.md`, and INV-8, INV-9 and INV-10
in `docs/specs/LOTTO-0009-entered-pools.md`. **INV-10 has no verifier at all**,
so that command is the only thing checking it;
run them from there rather than re-inventing them.

## Architecture

Data flows in one direction, and the two halves are independent:

```
phone ──adb over USB─────────┐                        ┌─ parse() ──────────> [Ticket]
       (bulk history)        ├─> lotto_sms_raw.txt ───┤   (a purchase)
phone ──watch_sms.py─────────┘   (two writers,        └─ parse_payout() ──> [Payout]
       (KDE Connect, new           ONE reader)            (a prize the bank paid)
        messages, no cable)

results.py    (official API, 2026-06-01 on, has issue)  ──┐
backfill.py   (scraped archive, FIRST_YEAR on, no issue) ┴─ history.py ──┐
                                                                           │
                      [Ticket] + history.py ─────────────────────────────> check.py::check()
                                                                                  │
                      [Payout] ──────────> check.py::reconcile() <────────────────┤
                      (the bank's record against ours: LOTTO-0029. Flags a        │
                       disagreement, never resolves it in the SMS's favour.)      │
                                                                                  │
                                        ┌─────────────────────────────────────────┤
                                        ▼                                         ▼
                            check.py::__main__                        serve.py ──> page.py
                            (the terminal output)                     (the local page)
                                                                          ▲   │
                                                          tray.py ──> supervise.py
                                                          (PySide6)   (spawns serve.py AND
                                                                       watch_sms.py; owns the
                                                                       settings reader both
                                                                       import, and the re-buy
                                                                       warning)
                                                                          │
                                                                          ▼
                                                                      expiry.py
                                                            (the draw calendar. Imports
                                                             NOTHING of the project's.)
```

**What each file owns is in `.claude/rules/architecture.md`.** It loads
when you Read a `.py` file natively. An Ants-verb read does not load it,
so read it by hand before changing code you have only seen through a verb.

### Load-bearing decisions — do not "simplify" these

The rules not to undo are in `.claude/rules/architecture.md`, under the
same heading. Read them before changing any `.py` file.

## Privacy — this repo is intended to be public

`lotto_sms_raw.txt` and `archive_cache/` are real personal data and are
gitignored. The non-obvious part: **never paste real message content into code,
docs or commit messages**, even with the reference scrubbed — numbers, date and
amount identify a ticket on their own. Two leaks got past weaker checks, one per
review loop. Sample references must be the sentinel `VAS00000000000` — **the one sentinel,
not a family of them.** Every reference-shaped string that is not exactly that
is a leak, invented or not, and a test fixture needing a second distinct
reference uses a name that is not reference-shaped at all (`tools/verify_payouts.py`
does this).

**A desktop notification carries no ticket data, in any branch — every
notification path, including one added later.** The reason is not the pasting
rule above: a notification may be logged and synced off the machine. It holds
absolutely for `new_ticket_notice()` and `refresh_message()`.
**One bounded exception, bounded on purpose (LOTTO-0034 §3.3):** the re-buy
notice names the game, the final draw date and the number of draws left, and
INV-54 is what holds that line. The user was shown the trade and chose
usefulness — with two tickets running, a notice that will not name the game
cannot say what to go and buy. It is the exception, not the pattern: a new
notification takes the rule, not the exception. Run
`python3 tools/verify_privacy.py --require-content` before any commit that
touches prose or examples — **without that flag a missing dump exits 0** and
the content half never ran. It runs two halves: tracked files compared against the dump's own
text, and identifying patterns, which are what catch an INVENTED reference the
dump never held. Without the dump only the pattern half runs.
**It only reads TRACKED files, and that is the trap.** A NEW file passes every
local run — including a full `./local-CI.sh` — right up until `git add` makes
it tracked, and then fails at the push. LOTTO-0029's verifier did exactly this:
clean on every run while it was untracked, three leaks the moment it was
staged. `git add -A` first, then run the check, if the change adds a file.

## Working conventions

- Roadmap items are `LOTTO-000N` in `ROADMAP.md`; commits are
  `LOTTO-000N: <description>`.
  **The roadmap store is the source of truth, and `ROADMAP.md` is its
  rendered output.** Write through `roadmap_log`, read through
  `roadmap_query`, and never hand-edit the file. Before any `roadmap_log`
  write, any `roadmap_migrate`, or any commit touching `ROADMAP.md`, read
  `docs/roadmap-workflow.md`: when to re-migrate, how to review the
  re-rendered diff, and the one-sentence `Layman:` rule.
  `CHANGELOG.md` follows Keep a Changelog and each entry cites its id.
- Specs live in `docs/specs/LOTTO-000N-<topic>.md` and carry numbered
  invariants (INV-n), failure modes, and a cold-eyes loop log. Code comments
  reference those invariants — when changing behaviour, update the spec's
  invariant and its "what checks this" row in the same change.
- **Count in entries, not tickets.** `LOTTO-0009` shipped 2026-08-01: every
  paid entry is scored, where before a ticket counted once however many pools
  its price had paid for.
  Read `docs/specs/LOTTO-0009-entered-pools.md` before touching `GAME_MAP`,
  `TIER_PRICES`, `Ticket`, or anything that counts tickets — §4.2's price
  table is hardcoded, like `DRAW_DAYS`, and is the one most likely to rot.
- **The page must never let "no data" read as "did not win"** — the cardinal
  rule, in its newest form. `page.py::_money_cell()` renders `won_cents: None`
  as "not checkable" and an integer `0` as `R0.00`, and they must not converge;
  `_draws_cell()` does the same for `draws_covered`/`draws_remaining`.
  **`page.py::_periods_section()` needs neither, and that is the point**: a
  period bucket exists only where a draw was actually scored, so its cells are
  always integers and `R0.00` there always means *checked, won nothing*. The
  three-valued question is settled at the source rather than at the cell — do
  not "fix" it by adding a `None` branch, and do not emit a bucket for a period
  nothing scored, which would put the two states back together. An empty
  page is correct only when it carries a notice naming *why* (the dump is
  missing, the first build failed, or `LOTTO_NO_BUILD` is set) — three states,
  one rule — **and never a ticket table, a zero total or an empty wins list
  beneath that notice**, all three of which read as "you have won nothing".
  `LOTTO-0002` §6 owns the prohibition; the notice is necessary, not
  sufficient. `tools/verify_page.py::uncheckable_not_a_loss` is what catches a
  breach, and its forbidden-strings list includes the empty string.
- Known deferred rough edges hang off `LOTTO-0007` as a lettered list in its
  body; `roadmap_query` it by id before reporting one as new — an id fetch
  returns the body, so the whole list comes back. **Add one with
  `roadmap_log op:"annotate"` against `LOTTO-0007`, never by editing the file**
  — that appends into the item's body, and a hand edit is reverted by the next
  write.
