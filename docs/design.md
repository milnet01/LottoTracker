# LottoTracker — design

**Status:** written 2026-10-15 (LOTTO-0056), from the code as built. Gated the
same day with `review-contract --genre adr`: three loops, the cap; calm.

This says what the whole project is for, which part delivers what, and what
each part may touch. A single feature's contract is its spec (§ 9). A close
call gets a record in [`docs/decisions/`](decisions/).

## 1. What it is for

The user buys South African National Lottery tickets through Standard Bank,
ten draws at a time. The bank confirms each purchase, and each prize it pays,
by SMS. This project reads those messages and keeps one ledger of every
ticket.

**Its primary job is to tell the user when a ticket is about to run out, so
they buy the next one** (`CLAUDE.md` § What this is, settled with the user
2026-08-20). Everything else — what each ticket won, spend against winnings,
the bank's record against the app's — serves the ledger behind that warning.

## 2. How you would know it works

The signs of success are in `README.md` § How you would know it works, with
where each stands. This table places each in the part that delivers it.

| Sign | Delivered by | Contract |
|---|---|---|
| 1. Told when to buy again | the calendar (`expiry.py`), warned by the tray and supervisor | LOTTO-0034 |
| 2. Numbers chosen beside numbers drawn | scoring (`check.py::check()`), shown by the page | LOTTO-0001, LOTTO-0002 |
| 3. What each ticket won, in one place | scoring, shown by the page | LOTTO-0001, LOTTO-0009, LOTTO-0002 |
| 4. Cost against winnings by period | the page's builder (`serve.py::period_buckets()`) | LOTTO-0036 |
| 5. Every disagreement with the bank explained | reconciliation (`check.py::reconcile()`) | LOTTO-0029; payment status in LOTTO-0001 |

## 3. The parts, and their files

| Part | Responsible for | Files |
|---|---|---|
| Collection | Getting SMSes off the phone into the dump. Two writers: adb over USB for history, KDE Connect for new messages | `watch_sms.py`, `tools/import_adb.py`; `find_lotto_sms.py` only prints |
| Reading | Turning dump records into tickets and bank payouts; the dump format's one reader; the sender check | `tickets.py` |
| Results | Drawn numbers and prizes from two sources, merged into one draw record | `results.py`, `backfill.py`, `history.py` |
| Scoring | Matching entries to draws, pricing wins, reporting what cannot be checked, reconciling against the bank | `check.py` |
| Calendar | Each ticket's final draw date, from the draw calendar alone | `expiry.py` |
| Time | Every date, in South African time | `clock.py` |
| Page | Building the model (`serve.py`, all of the I/O) and rendering it (`page.py`, pure); the local HTTP surface | `serve.py`, `page.py` |
| Tray and supervisor | The icon, starting and reaping the server and the watcher, the settings reader, the re-buy warning | `tray.py`, `supervise.py` |
| Verification | The test suite and the pre-push gate | `tools/verify_*.py`, `local-CI.sh`, `.githooks/` |

What each file owns in detail is in `.claude/rules/architecture.md`.

## 4. What each part may touch

Data flows one way: collection → dump → reading → scoring → page. These rules
are what keep that so.

**A file imports only files at its own step or an earlier one:**

1. Time — `clock.py`, which imports nothing of the project.
2. Reading, Results, Calendar, and the renderer `page.py`.
3. Scoring (`check.py`), the supervisor (`supervise.py`) and Collection.
4. The page builder, `serve.py`.
5. The tray, `tray.py`.

Verification sits outside the order. A `tools/verify_*.py` file may import
any step, and nothing outside `tools/` imports from `tools/`.
`tools/import_adb.py` belongs to Collection and imports nothing of the
project.

Within that order:

- **`page.py` imports nothing of the project.** It is a pure function from a
  model dict to HTML, so the whole page renders in a test with no socket and
  no data (LOTTO-0002).
- **`expiry.py` imports nothing of the project and opens no file**, so the
  re-buy warning is right with the server stopped and the machine offline
  (LOTTO-0034 INV-50).
- **`history.py` is the only place the two results sources are merged.** The
  draws a ticket is scored against reach scoring through it alone. Scoring
  reads prize tables, and the recent draw that names the current prize
  divisions, from `results.py` and `backfill.py` directly.
- **`tickets.py::rows()` is the dump's one reader.** `watch_sms.py` depends on
  it to avoid appending a record twice (LOTTO-0003 INV-34).
  `tools/import_adb.py` rewrites the whole dump from adb's output and never
  reads it.
- **`tray.py` is the only file that imports PySide6, and it never imports
  `serve.py`.** What the tray needs from the server's side — the settings
  reader, the notice wording — lives in `supervise.py`, which is Qt-free so a
  headless script can check it (LOTTO-0013). The order already keeps
  `supervise.py` from importing `serve.py`.
- **`dbus` is imported only by the collection part** — at the top of
  `find_lotto_sms.py`, and inside the `watch_sms.py` functions that reach the
  phone — so every other file, `tray.py` included, imports without
  `dbus-python`.

The import edges as built can be listed with:

```bash
mods="$(ls *.py | sed 's/\.py$//' | paste -sd'|')"
for f in *.py; do printf '%s: ' "$f"; grep -E '^\s*(import|from) ' "$f" \
  | grep -oE '(import|from) [a-z_]+' | awk '{print $2}' | sort -u \
  | grep -xE "$mods" | paste -sd' '; echo; done
```

## 5. What every part does the same way

- **Not checkable is never a loss.** An entry nothing can score is reported
  with its reason, never counted as a zero win. Missing data raises or is
  named; it never becomes an empty result that reads as "nothing won"
  (`CLAUDE.md` § Working conventions, the cardinal rule).
- **Money is compared and summed in whole cents.** `check.py::amount()`
  returns float rands, so each figure is converted to cents before it is added
  or compared (LOTTO-0029 INV-42).
- **Every date is South African time, read through `clock.py`.** No part but `clock.py` calls
  `date.today()`, `datetime.now()` or `fromtimestamp()` directly; an SMS
  timestamp goes through `clock.from_ms()` (LOTTO-0066; LOTTO-0034 INV-64).
- **Each state file has one writer, except the dump.** The dump has two
  writers, the two collectors, and one reader, `tickets.py::rows()`. `settings.json`: `serve.py`, behind `POST /settings`.
  `expiry_warned.json`: `supervise.py::expiry_notices()`.
- **Third-party text is made safe where it leaves.** `terminal_safe()` for the
  terminal, `page.py::_e()` for HTML.
- **A desktop notification carries no ticket data**, with one bounded
  exception for the re-buy notice (`CLAUDE.md` § Privacy).

## 6. The stack, and what it rules out

Python 3.9 or later and its standard library, plus `dbus-python` and
PyGObject (`gi`, for the watcher's GLib main loop) for collection, and PySide6
for the tray. No package manager, no virtualenv, no
build step: every file runs as `python3 <file>` from the repository root.

That rules out any third-party library outside those three, any service the
user would have to sign up for, and any network call beyond the two results
sources LOTTO-0001 names: the operator's API and a third-party archive. The page listens on `127.0.0.1` only.

## 7. Trust boundaries

- **The user's messages.** The dump (`lotto_sms_raw.txt`) and `archive_cache/` are real personal
  data and never tracked by git; nothing real is pasted into code or docs
  (`CLAUDE.md` § Privacy, LOTTO-0001 INV-4).
- **Who sent an SMS.** A sender ID is not authenticated. A record from a
  sender the bank is not known to use is kept and flagged, never trusted
  silently and never dropped (LOTTO-0062).
- **The local page's HTTP surface.** It binds `127.0.0.1`, checks the `Host`
  header on every request, and needs the per-run token and a matching origin
  for every change (LOTTO-0014).
- **The bank's own record never replaces a computed figure.** A disagreement
  is flagged, never resolved in the SMS's favour (LOTTO-0029 INV-43).

## 8. Deliberately out of scope

- **Countries other than South Africa**, until 1.0.0 is out — the user,
  2026-10-15 (LOTTO-0080).
- **Banks other than Standard Bank**, until contributors send redacted
  samples (LOTTO-0079).
- **Buying tickets, or claiming prizes.** The app reads and reports; it acts
  on nothing.

## 9. The specs

| Spec | What it governs |
|---|---|
| [LOTTO-0001](specs/LOTTO-0001-lottery-ticket-tracker.md) | Reading tickets, the results sources, scoring and payment status |
| [LOTTO-0002](specs/LOTTO-0002-local-web-page.md) | The local page: its model and its sections |
| [LOTTO-0003](specs/LOTTO-0003-live-sms-watch.md) | The cable-free SMS watcher |
| [LOTTO-0009](specs/LOTTO-0009-entered-pools.md) | Every pool a ticket's price paid for |
| [LOTTO-0013](specs/LOTTO-0013-tray-and-supervisor.md) | The tray and the server supervisor |
| [LOTTO-0014](specs/LOTTO-0014-http-surface-and-security.md) | The page's HTTP surface and security boundary |
| [LOTTO-0019](specs/LOTTO-0019-build-reporting.md) | Reporting what a build is doing |
| [LOTTO-0029](specs/LOTTO-0029-payout-reconciliation.md) | The bank's payouts against computed wins |
| [LOTTO-0034](specs/LOTTO-0034-ticket-expiry-warning.md) | The re-buy warning |
| [LOTTO-0036](specs/LOTTO-0036-period-totals.md) | Cost against winnings by period |
| [LOTTO-0062](specs/LOTTO-0062-sender-pinning.md) | Flagging an SMS from an unknown sender |

Review record: [`reviews/design-loop-log.md`](reviews/design-loop-log.md).
