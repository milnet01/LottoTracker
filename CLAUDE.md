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
feature; three of the five are open, and the primary one is the least built.
The claim-deadline material is still true and still useful, but it is not the
headline.

Pure Python 3.8+ standard library
plus `dbus-python` (`find_lotto_sms.py`, `watch_sms.py`) and PySide6 (`tray.py`,
and the one `verify_page.py` case that starts it in a subprocess). No package
manager, no virtualenv, no test framework, no build step — everything runs as
`python3 <file>` from the repository root.

## Commands

```bash
python3 backfill.py            # one-off: scrape pre-2026-06-01 results into
                               # archive_results.json + archive_cache/ (12 fetches)
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
runs everything below plus `ruff` and a syntax pass, and it is what
`.github/workflows/ci.yml` invokes (as `./local-CI.sh --ci`), so the runner and
this machine cannot drift apart — there is no second list of checks to forget.
A documentation-only push (every changed file `.md`) skips the gate
automatically; `--force` overrides.

Make it structural rather than remembered — **once per clone**, because git
does not track hooks and `core.hooksPath` is local config:

```bash
git config core.hooksPath .githooks   # .githooks/pre-push then runs the gate
```

The two lanes are **not** equal and must not be made so. Four verifiers need
`lotto_sms_raw.txt` and the scraped archive, neither of which may reach a public
runner, and `verify_privacy.py` drops to a weaker pattern-only mode without the
dump — while still exiting 0. So a green tick on GitHub is weaker than a green
`./local-CI.sh`, and the script asserts locally that the privacy check ran at
full strength rather than trusting its exit code. `local-CI.sh`'s header holds
the reasoning.

Verification — there is no test runner; these seven scripts *are* the test
suite, and each maps to a numbered invariant in the specs. Run from the
repository root, after `backfill.py`, with `lotto_sms_raw.txt` present
(three need no dump and are therefore the CI lane: `verify_watch.py`, which
needs no phone and no `dbus-python` either, `verify_page.py`, and
`verify_privacy.py` in its weaker pattern-only mode):

```bash
python3 tools/verify_sources.py   # INV-3: the two results sources agree on overlap
python3 tools/verify_coverage.py  # INV-6: each entry scored over exactly its draws
python3 tools/verify_privacy.py   # INV-4: no real SMS content is tracked by git
python3 tools/verify_pools.py     # INV-7/11/22/26/31: prices resolve; partly-checkable
                                  # tickets are never written off whole
python3 tools/verify_page.py      # INV-12..INV-21, INV-23..INV-25 and INV-27..INV-30:
                                  # the page, its security boundary, the tray's
                                  # spawn-and-reap lifecycle, what it reports after a
                                  # refresh, the port it binds, the managed (no-icon)
                                  # run, and the results transport underneath them
python3 tools/verify_payouts.py   # INV-40..INV-47: the bank's own payout SMSes,
                                  # reconciled per VAS reference against every
                                  # computed win; --break/--list like verify_page
python3 tools/verify_watch.py     # INV-32..INV-39: the cable-free SMS path writes
                                  # what adb would, never twice, and its child is
                                  # spawned, observed and reaped; two watchers
                                  # appending at once collide never; and a KDE
                                  # Connect restart is read as one
```

`verify_page.py` is the one verifier that needs PySide6 installed — its
`tray_headless_when_managed` case imports `tray.py` in a subprocess. It needs no
display.

`verify_page.py` carries a `--break <name>` flag that applies one deliberate
defect and asserts the named case goes red. That is not a debugging aid: these
three items are greenfield, so there was no pre-fix code to red-test against,
and the flag is what makes "every case observed failing" reproducible rather
than a one-off hand edit. `--list` shows the thirty-one breaks. It caught a real
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

results.py    (official API, 2026-06-01 on, has payouts) ──┐
backfill.py   (scraped archive, 2025-01-01 on, no payouts) ┴─ history.py ──┐
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
                                                                       import)
```

- **`watch_sms.py`** is the cable-free collector (LOTTO-0003). It reads the
  phone's conversation list at start — polling it until it stops growing, which
  is the completion signal D-Bus does not give — then lives on `conversationUpdated`
  signals. **`conversationCreated` fires only the first time the KDE Connect
  daemon learns of a conversation** — measured 202 signals on a first run and
  **zero** on every later one against the same 2,325 conversations — so nothing
  may build discovery on it; that mistake shipped a watcher that reported "0
  new" against a phone holding 951 matching messages. Its filter is
  LOTTO-0001 §4.1's adb `WHERE` clause re-expressed, and `verify_watch.py`
  checks the two against SQLite. `find_lotto_sms.py` is a different tool with a
  deliberately wider list: it prints, this writes. Do not merge them.
  **A KDE Connect restart breaks it in HALF, and the half that survives is the
  one you would expect to lose** — measured 2026-08-15, the second D-Bus
  assumption this project got wrong by recall rather than by measuring. The
  held proxy dies (`ServiceUnknown`, because dbus-python pins a well-known name
  to the unique connection it resolved at `get_object()` time), while the
  signal match rule survives untouched (it carries an interface and a member
  and no sender). So the watcher does not go deaf — it goes **mute**, and since
  steady state makes no call to the phone, the loss is invisible until a
  catch-up that never ran is noticed. **And nothing brings the daemon back:**
  the watcher must reach for it, because the bus name is D-Bus *activatable* and
  the act of reaching starts it. `RETRY_EVERY` is 60s, not 2s, so it cannot
  resurrect a daemon the user stopped on purpose. LOTTO-0003 §4.8.
- **`tickets.py`** holds the bank's *parsing*, and reads **two** message kinds.
  It is not the only bank-specific file: `watch_sms.py::INCLUDE` and
  LOTTO-0001 §4.1's adb `WHERE` clause hold the bank's *admission filter*, and
  `INCLUDE` carries the reference prefix `vas00`. **A bank wording change
  touches both**, and INV-32 asserts the two filters agree — fixing the parser
  alone leaves a message the parser handles correctly and never receives, which
  is exactly how LOTTO-0030 excluded 366 payouts. `rows()` is the dump
  format's one reader, and both writers depend on that staying true — a second
  reader that drifts would duplicate every record it failed to recognise.
  `parse_payout()` reads the bank's statement of a prize it paid; it and
  `parse()` are disjoint by construction and **must stay so**. A purchase debit
  reads "R… paid from Acc. … to VAS… LOTTO" — money *leaving* the account, and
  it names a game. A payout names none, which is the one word that kept every
  payout out of the dump until LOTTO-0030 widened the import filter. Widening
  `PAYOUT` toward "paid" counts the 14 debits as winnings, so lifetime "paid"
  grows by what the user *spent* (LOTTO-0029 INV-40).
  `parse()` handles two SMS eras; `GAME_MAP` translates an SMS game name to the one `(game, plus_flag,
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
- **The port is `$PORT`, else `$LOTTO_PORT`, else 4322** — the same precedence in
  `serve.py::resolve_port()` and `supervise.py::_port_or_default()`, so there is
  one knob whichever way the page is started. `$PORT` is the name an external
  process manager already sets, which is why it wins. Unset and empty mean "no
  preference" and fall through.
  **On a bad value the two deliberately diverge, and must not be "unified"** —
  each says so at its own site. `serve.py` is machine-facing and **exits**
  naming the variable and the value: a manager that asked for port 80 and got
  4322 has been lied to. The tray is human-facing and **falls back to 4322 with
  a notification**, because a tray that exits just vanishes, and a typo in a
  shell profile must never be indistinguishable from the app being broken. That
  is safe only because a manager range-checks before it sets and launches
  `serve.py` directly, so the fallback can never mislead one (LOTTO-0013 §4.5).
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
  It also owns `new_ticket_notice()`, for the same reason `refresh_message()`
  lives here: **a wording decision inside `tray.py` cannot be checked without
  constructing a `QSystemTrayIcon`**, and the project has no Qt-constructing
  test. Every branch must name a menu item that state leaves *enabled* — the
  one that did not sent the user to a greyed-out *Refresh results now*
  (LOTTO-0003 §4.7).
  **`tray.py`** is the only file that imports PySide6, and the only file that
  reads `LWSM_MANAGED` — `=1` means a process manager started it, so it runs
  with no icon and, above all, no path that stops the server (INV-25). It is a
  presentation hint with no security value; nothing else may hang off it.
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
- **The bank's payout SMS never replaces a computed figure.** `check.py::reconcile()`
  joins the bank's own record to tickets on the `VAS` reference and reports both
  figures side by side; a disagreement is flagged, never resolved in the SMS's
  favour (user decision 2026-08-13, LOTTO-0029 INV-43). Adopting it would price
  the archive era for free — and erase the 15 references where the app computes
  LOW, which are the evidence that something in pricing is wrong. Three things
  not to "simplify": the unit is the **reference**, not the payment (77 of 225
  are paid more than once); money is compared in **whole cents**, never float
  rands; and the seven categories are decided in a fixed **order**, because as
  an unordered set they overlap — a reference with no purchase SMS has no
  entries, so "every entry is scorable" is vacuously true of it and it would
  match `unexplained` as well as `no_ticket`.
- **`computed_cents` is three-valued and the three must not converge** — the
  cardinal rule again, one layer below the page. `None` is *not checkable*
  (nothing could be scored), `0` is *checked, total prize zero*, and a positive
  integer is the summed prize. So `computed_cents` never answers "did it win?";
  `first_win` does. A reference that is only **partly** scorable carries an
  integer, never `None`, or LOTTO-0009 INV-11 is breached from the other side.
- **A dump with no parsable payout reports that, and emits no category census.**
  If the bank changes its wording, `parse_payout()` matches nothing and every
  scored reference would otherwise satisfy `unpaid` — announcing prizes nobody
  was ever paid. The guard is in `reconcile()` itself, not only in the report,
  so the page cannot render the fictions either (INV-47). Same class as
  LOTTO-0031, where a rebranded game name parsed to `None` and a ticket was
  silently never scored.
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
review loop. Sample references must be the sentinel `VAS00000000000` — **the one sentinel,
not a family of them.** Every reference-shaped string that is not exactly that
is a leak, invented or not, and a test fixture needing a second distinct
reference uses a name that is not reference-shaped at all (`tools/verify_payouts.py`
does this). Run
`python3 tools/verify_privacy.py` before any commit that touches prose or
examples; it compares tracked files against the dump itself, not a guessed
pattern.
**It only reads TRACKED files, and that is the trap.** A NEW file passes every
local run — including a full `./local-CI.sh` — right up until `git add` makes
it tracked, and then fails at the push. LOTTO-0029's verifier did exactly this:
clean on every run while it was untracked, three leaks the moment it was
staged. `git add -A` first, then run the check, if the change adds a file.

## Working conventions

- Roadmap items are `LOTTO-000N` in `ROADMAP.md`; commits are
  `LOTTO-000N: <description>`.
  **The roadmap DB is the source of truth, and `ROADMAP.md` is its rendered
  output — migrated 2026-08-20 (`roadmap_migrate`, `ants-v1`, 33 items).**
  So writes go through `roadmap_log` and reads through `roadmap_query`; the
  file is no longer hand-edited, and a hand edit is reverted by the next write
  rather than merged. Query one item by id instead of reading the file — at
  1,600 lines that is the whole point of the change. This reverses the previous
  convention, which had writes going in by hand precisely *because* the verb
  re-renders the whole file; that re-render is now the mechanism enforcing one
  roadmap standard across projects, not a defect to route around.
  **The store is machine-local — `~/.local/share/ants-terminal/roadmap.sqlite`,
  outside the repo and in no `.gitignore` — so the tracked `ROADMAP.md` is the
  only thing that crosses machines.** Two consequences, both easy to get wrong.
  **Re-run `roadmap_migrate` when that file changes underneath the store from
  GIT** — a clone, a pull, a checkout, a revert — and always before the next
  `roadmap_log` write. A write after an un-migrated pull reverts what you
  pulled, and the large diff the next paragraph tells you to expect is exactly
  what hides it. **Never re-migrate to pick up a local hand edit.** The store
  cannot tell one from a pull, so migrating would launder into it precisely
  what the rule above forbids; discard a hand edit by writing over it. And **commit
  the re-rendered `ROADMAP.md` with the work it records**: the render is the
  only copy that leaves this machine, an uncommitted one is a lost item, and
  nothing catches it — a `.md`-only change skips the gate. A session with no
  Ants MCP cannot write at all, and leaves the file alone rather than
  hand-editing.
  **Two things that follow, and neither is optional.** Any write re-renders all
  1,600 lines, so a status flip that changes nothing still produces a large
  diff. Review it by checking that every REMOVED line's text still appears
  somewhere in the new file, **comparing with markup and trailing full stops
  stripped from both sides** — the renderer rewrites both deliberately (below),
  so a raw comparison flags dozens of correct lines and teaches you to wave the
  check through, which is the one habit it exists to prevent. A census of ids,
  statuses and word count is not a substitute: dropping a full stop moves none
  of those three. And **a `Layman:` line must be ONE sentence**: the renderer
  keeps only the first and discards the rest permanently — and **write it with
  no trailing full stop**, because a bold `**Layman:**` line can lose one on any
  render (4 of the 7 in this file did). That one is a standing authoring rule,
  not a one-off: it applies to every `Layman:` line written from now on, and to
  no other line. The id-dialect
  normalisation *is* one-off — the two dialects this file had accumulated
  collapse into one on the first render and never again. Ids, statuses, nested
  sub-bullets and their
  indentation all survive (measured 2026-08-20 in an isolated copy, filed as
  Ants MCP feedback).
  `CHANGELOG.md` follows Keep a Changelog and each entry cites its id.
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
- Known deferred rough edges hang off `LOTTO-0007` as a lettered list in its
  body; `roadmap_query` it by id before reporting one as new — an id fetch
  returns the body, so the whole list comes back. **Add one with
  `roadmap_log op:"annotate"` against `LOTTO-0007`, never by editing the file**
  — that appends into the item's body, and a hand edit is reverted by the next
  write.
