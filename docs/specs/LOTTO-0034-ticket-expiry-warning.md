# LOTTO-0034 — Warn the user a ticket is about to run out

**Status:** accepted (2026-08-22); **implemented and verified 2026-08-22** —
all eight cases of `tools/verify_expiry.py` pass and each was observed failing
under its own `--break` (nine breaks for eight cases). The measured figures the
spec predicted came back unchanged from the verifier: INV-49 lotto 170/171,
powerball 171/171, daily 597/597; INV-51 257/260 exact, 3 off by one. INV-51
was amended 2026-08-31 (§4.2) when LOTTO-0006 widened the archive. Gated by
`review-contract` (genre spec):
two loops, three cold lanes each, 20 verified findings all fixed, 1 dismissed
as immaterial. Reached the 2-loop cap for a spec, which is the normal exit —
implementation is the third reviewer. See §12.
**Kind:** feature.
**Source:** ROADMAP LOTTO-0034 — the project's primary job, settled with the
user during discovery on 2026-08-20 and recorded as sign of success 1 in
`README.md` § How you would know it works. The scope decisions in §3 were taken
with the user on 2026-08-22.

**Pairs with:** LOTTO-0013 (the tray and supervisor this hangs off) and
LOTTO-0003 (the watcher that makes a new ticket appear without a cable).

*Layman: the app tells you your ticket is nearly used up, so you can buy the
next one instead of having to remember*

## 1. Goal

After this ships, a user running the tray is told — without going to look —
that a ticket is two draws from its last, and which game to re-buy. The
warning is derived from the ticket alone and the calendar, so it is correct
whether or not results have been downloaded, whether or not the server is
running, and whether or not the machine has been online.

## 2. Problem

The project's primary job is the one thing it does not do. `README.md`
§ How you would know it works lists five signs of success; this is the first
of them and the least built. Tickets are bought ten draws at a time, and
nothing in the app says when one is nearly finished.

What exists today falls short in three separate ways.

1. **Nothing reaches the user unprompted about expiry.** `tray.py` runs one
   `QTimer` at `POLL_MS`, whose `timeout` is connected to `TrayIcon.sync()`;
   `sync()` sets the icon, the tooltip and the menu enablement from
   `Supervisor.is_running()`, then delegates to `check_new_tickets()` — so it
   already ends in a call to a helper that owns a decision. The only unprompted notice the
   tray produces is `supervise.new_ticket_notice()`, which fires when the dump
   grows — the opposite event to the one this item is about.

2. **The model carries a count, never a date.** `serve.py::build_model()`
   emits `draws_covered` and `draws_remaining`, and `page.py::_draws_cell()`
   renders them. `draws_remaining` is `t.ndraws - covered`, where `covered`
   comes from `history.covered()`. There is no date of a final draw anywhere
   in the project, and nothing that can compute one, because `history.py`
   holds only draws that have already happened — `history.all_draws()` merges
   `archive_results.json` with `results.py::api_draws()`, both of which are
   records of the past.

3. **`draws_remaining` cannot answer the question, even though its name
   suggests it can.** It counts draws not yet *scored*, which conflates two
   different things: draws that have not happened, and draws that have
   happened but whose results have not been fetched. A user who has not
   refreshed for a week sees a ticket with more life in it than it has. §4.3
   settles the distinction rather than repairing `draws_remaining`, which is
   out of scope (§9).

## 3. Scope decisions (agreed with the user)

All four were preference rather than deduction, taken with the user on
2026-08-22.

1. **The warning fires once a ticket has two draws or fewer left** — never at
   three, and never on a fixed number of days. On Lotto and PowerBall that is roughly four to seven
   days' notice; on Daily Lotto it is two days, which the user accepted.

2. **It is said once and not repeated.** A ticket that crosses the threshold
   produces exactly one re-buy notice, ever. (§4.7's unrecognised-game notice
   is not a re-buy notice and deliberately recurs.) The user rejected a daily repeat and a
   once-per-startup repeat. The cost is stated honestly in §6: a user whose
   machine is off for the whole window is never told.

3. **The notice names the game and the final draw date.** This is a
   deliberate exception to an existing project rule, and it is recorded here
   because that rule is stated absolutely at its own site.
   `supervise.new_ticket_notice()`'s docstring says *"No ticket data in any
   branch, for refresh_message()'s reason - a desktop notification may be
   logged and synced off the machine."* The user was shown that trade and
   chose usefulness: with two tickets running, a notice that will not name the
   game cannot say what to go and buy. **The exception is bounded by INV-54**
   — the game name, the final draw date and the number of draws left, and no
   other field of the ticket.
   The rule stands unchanged for `new_ticket_notice()` and
   `refresh_message()`, neither of which is touched.

4. **The tray process computes it, not the server.** The warning must work
   with the server stopped, so it may not depend on `serve.py`. Which module
   inside that process does the work is §4.7's, not this decision's. Putting the same figure
   on the page is LOTTO-0032's and LOTTO-0021's territory and is out of scope
   here (§9).

## 4. Design

### 4.1 The draw calendar, and why it is hardcoded

A new module `expiry.py` holds one table and two pure functions. It imports
nothing from the project and touches no file.

```python
# expiry.py
DRAW_DAYS = {          # weekday numbers as datetime.date.weekday() reports them
    "lotto":     {2, 5},          # Wednesday, Saturday
    "powerball": {1, 4},          # Tuesday, Friday
    "daily":     set(range(7)),   # every day
}

def final_draw_date(game, start, ndraws):
    """The date of the ndraws-th draw on or after `start`. Pure."""

def draws_left(game, start, ndraws, today):
    """How many of this ticket's draws have not happened yet, as of `today`."""
```

**A draw falling on `today` counts as NOT yet happened.** So a ticket reads
`draws_left == 1` on its own final draw day and `0` the day after. The other
boundary is `start`, inclusive, because a ticket bought on a draw day is
entered in that day's draw. Leaving either open shifts every date by one.

**Only the `start` boundary is checked, and INV-51 is what checks it.** The
`today` boundary is pinned by nothing: `calendar_matches_real_draws` never
calls `draws_left` and takes no `today` at all. Confirmed 2026-08-31 by
mutation — changing `draws_left`'s `d >= today` to `d > today` leaves **all
eight cases green**, because the one fixture whose draw falls on `TODAY`
interpolates the value into a message and never asserts it. A flip there
silently costs every ticket its final-day warning, which is the day the warning
matters most. §10 records it as uncovered rather than letting this sentence
imply otherwise; a ninth case is filed against LOTTO-0007.

**A game absent from `DRAW_DAYS` raises `KeyError`; neither function returns
`None`.** `check.py::paying_combinations()` raises for the same reason — an
empty answer is indistinguishable from a real one — and LOTTO-0031 is what a
silent `None` costs: a rebranded game name parsed to `None` and the ticket was
never scored. §4.7 says what the caller does with it; INV-56 is what stops it
being swallowed.

**There is a second precondition and a second exception: `ndraws` is at least
1, and below that both functions raise `ValueError`.** Stated 2026-08-31
because it was not, while `expiry_notices()` already caught
`(KeyError, ValueError)` together — so a ticket with a bad `ndraws` produces the
*unrecognised-game* notice, telling the user the draw calendar needs updating
when the real defect is a malformed ticket. An implementer building from the
old text writes `except KeyError` and a bad `ndraws` kills the tray instead.
Both routes are wrong in a way that matters, which is why the contract is named
here rather than left to the caller. **Catching them together is what shipped
and is what this documents; giving the `ValueError` its own wording is a
deferred rough edge (LOTTO-0007), not a licence to widen the catch.**

The table is hardcoded because no feed publishes a draw schedule. That is the
same position `tickets.py::TIER_PRICES` is in, and it carries the same risk —
CLAUDE.md records that table as *"the one hardcoded table in the project and
the one most likely to rot"*. The answer here is the answer there: a verifier
whose job is to make a change loud. INV-49 checks `DRAW_DAYS` against observed
history in both directions, because a one-directional check passes a removed
draw day silently.

The table was measured, not recalled:

```
$ python3 -c "
import json,datetime as dt,collections
a=json.load(open('archive_results.json'))
for p in ('lotto:0','powerball:0','daily:0'):
    w=collections.Counter(dt.date.fromisoformat(d).strftime('%a') for d in a[p])
    print(p, len(a[p]), sorted(w))
"
lotto:0 165 ['Sat', 'Thu', 'Wed']
powerball:0 165 ['Fri', 'Tue']
daily:0 576 ['Fri', 'Mon', 'Sat', 'Sun', 'Thu', 'Tue', 'Wed']
```

The stray `Thu` is one draw in nineteen months, and §4.2 is where it matters.

That census is of the archive alone, because the archive is what the table was
*derived* from. INV-49 checks it against the **merged** record instead, that
being what stays current: measured 2026-08-22 over archive + API, on-calendar
draws run lotto 170/171, powerball 171/171 and daily 597/597, with every
weekday the table lists carrying a draw inside the 90-day window.

### 4.2 The final draw date is fixed at purchase, and is never late

A ticket's last draw is decided the moment it is bought: it is the `ndraws`-th
calendar draw on or after `Ticket.start`. No results data enters the
calculation, which is what lets the warning work with the server stopped and
the machine offline.

Two measurements bound how far that can be trusted.

**Projection against held-out history.** Deriving `DRAW_DAYS` from 2025 draws
alone and using it to predict every 2026 draw in the archive — 333 draws
across the three base pools, `daily:0` 212, `powerball:0` 61, `lotto:0` 60 —
gives the right count in every pool and one wrong date: the Lotto draw due
Wednesday 2026-04-29 ran on Thursday 2026-04-30.

That held-out run, and §4.1's census above it, were both measured against the
archive as it stood on 2026-08-22 — 2025-01-01 onward. LOTTO-0006 widened it to
2022, so **re-running either prints different numbers**, and the count of
irregularities went up rather than the record getting less regular: §4.2's
amendment below enumerates all seven over the full span, of which four are the
same Daily Lotto Christmas cancellation in four consecutive years. The
conclusion the two runs support is unchanged.

**Projection against every ticket that has already finished.** For each entry
whose `history.covered()` is complete, `final_draw_date()` was compared with
the date of the last covered draw. Measured 2026-08-22, before
`tools/verify_expiry.py` existed, with an inline script — `history.covered()`
for the real dates, the `DRAW_DAYS` projection above for the predicted one,
comparing only entries where `len(covered) == ticket.ndraws`:

```
fully-covered entries compared: 260
calendar agrees with real results: 257
disagrees: 3   (all lotto, all +1 day, all spanning 2026-04-30)
```

`tools/verify_expiry.py::calendar_matches_real_draws` (§7) is that comparison
made permanent, so these figures become an output rather than a
transcription. They will move as tickets are added; INV-51 states the floor,
not the snapshot.

So the contract is **never late**, not exact, and INV-51 states it that way
with the measured share.

**Amended 2026-08-31 (LOTTO-0006).** The contract was *within one day*, which
the wider archive falsified with a fact about the world rather than a defect:
there was no Lotto draw on 2024-12-25, and three tickets spanning that gap
project three days early.

**The direction depends on the ticket, not only on the event.** A weekly
pattern disagrees with history whenever the schedule does something the pattern
cannot express, and there are three ways it can:

| Event | Ticket spans the ORIGINAL date | Ticket starts AFTER it |
|---|---|---|
| Draw **cancelled** | **early** — the calendar counted a day nothing ran | exact |
| Draw **moved later** | **early** — same reason | **LATE** |
| Draw **moved earlier**, or an **extra** draw | **LATE** — the record reaches its n-th draw first | exact |

Early is safe: the warning still arrives before the ticket runs out. Late is
not — it names a final draw after the ticket has already ended, too late to
buy.

**The middle row's right-hand cell is the one to know**, and it was missed when
this section was first amended. A draw moved later sits on a day `DRAW_DAYS`
does not list, so the calendar never counts it — but `covered()` filters on
`date >= start` and therefore *does*, for any ticket starting on or after the
moved date and before the next scheduled one. The record then runs a draw
ahead. Worked against the one move in the archive, a Lotto ticket bought
2026-04-30 for 10 draws projects 2026-06-03 against a real last draw of
2026-05-30 — **four days late**.

**INV-51 asserts the sign, and zero entries are late today for a contingent
reason.** Enumerated 2026-08-31 over the whole archive (2022-01-01 to
2026-07-31) there are seven irregularities: five Christmas cancellations —
Daily Lotto on 2022-12-25, 2023-12-25, 2024-12-25 and 2025-12-25, Lotto on
2024-12-25 — and one draw moved later, the Lotto draw due 2026-04-29 running on
2026-04-30, which the enumeration sees as a missing date plus an extra one. **A
later move HAS happened, so the unsafe class is not empty of events — it is
empty of tickets**: no ticket in the dump starts on 2026-04-30. **That is a
measurement about the dump, not a property of the calendar**, and §6 carries it
as a live exposure.

Bounding the absolute deviation made the check fail on a holiday; asserting the
sign makes it fail only where the warning would actually mislead. The 98% exact
floor is unchanged and is still what stops the projection rotting silently.

### 4.3 `draws_left` is not `draws_remaining`, and the two must not be merged

Two quantities that look alike and answer different questions:

| Name | Where | Means | Source |
|------|-------|-------|--------|
| `draws_remaining` | `serve.py::build_model()` | draws not yet **scored** | `history.covered()` — results |
| `draws_left` | `expiry.py` | draws that have not **happened** | `DRAW_DAYS` — the calendar |

They coincide exactly when results are current, and diverge when they are
stale — which is precisely when the warning still has to be right. This is the
project's cardinal rule one layer out: `page.py::_money_cell()` keeps *no
data* and *did not win* apart, and these two are kept apart for the same
reason. **Do not "unify" them.** The warning reads `draws_left` and never
`draws_remaining`, and neither is computed from the other.

### 4.4 Which tickets are warned about

A ticket qualifies when **both** hold, as of today:

- `0 < draws_left(...) <= 2`
- its reference is not already in the state file (§4.5)

The lower bound is what stops a first run against a dump of finished tickets
from firing hundreds of notices. `python3 -c "import sys;sys.path.insert(0,'.');
from tickets import load;print(len(load()))"` reported **561** tickets on 2026-08-22, of
which two were mid-run. An expired ticket is never warned about, however
recently it expired: `draws_left` of zero means the last draw has happened, and
a notice saying two draws remain would then be false. INV-52 holds the bound.

The unit is the **ticket**, not the entry. A Lotto ticket is entered in up to
three pools (`Ticket.pools`, LOTTO-0009 INV-8), all sharing one start date and
one `ndraws`, so all three expire together; warning per entry would say the
same thing three times. `Ticket.ref` is the key, and it is unique per
purchase: measured 2026-08-22 with
`collections.Counter(t.ref for t in tickets.load())`, 561 tickets carry 561
distinct references and none is reused.

### 4.5 Saying it once: the state file

```
$XDG_CONFIG_HOME/lotto-tracker/expiry_warned.json     (else ~/.config/...)

{"warned": [{"ref": "<VAS reference>", "final": "YYYY-MM-DD"}, ...]}
```

It sits beside `settings.json`, whose paths `supervise.config_home()` and
`supervise.settings_path()` already resolve, and a new
`supervise.expiry_state_path()` resolves this one the same way.

**It has exactly one writer — `supervise.expiry_notices()`, which only the
tray process calls — and that is deliberate.**
`settings.json` is read by `supervise.read_settings()` and written only by
`serve.py::write_settings()` behind `_settings_lock`, because `POST /settings`
is a server route (LOTTO-0013 §4.1). Putting warn-state into `settings.json`
would give it a second writer that is not the server, which is the arrangement
that rule exists to prevent. A separate file with one writer keeps both rules
intact.

Read failures follow `read_settings()`'s rule exactly: a missing, unreadable
or malformed file yields the empty set rather than raising. The consequence is
a repeated notice rather than a lost one, which is the right way round for a
file the user may delete.

**The WRITE side is not guarded, and that is stated rather than chosen.**
`_write_warned()` calls `os.makedirs()` and `open(path, "w")` with no `try`, and
`tray.py` calls `expiry_notices()` with none either — so an unwritable config
directory, a read-only home or a full disk puts the exception in the tray's
timer slot and kills the tray, which is the outcome §6 names the read-side
catch to prevent. The asymmetry was unnoticed until 2026-08-31: only one of the
two I/O paths in this function had its contract pinned.

**What to do about it is a decision, not a default, and it has not been taken.**
Swallowing the failure silently converts *say it once* into a repeated notice —
the direction §3.2 records the user rejecting — while letting it propagate
loses the tray. Neither is obviously right, so this documents what ships today
(unguarded, propagates) and files the choice as a deferred rough edge
(LOTTO-0007) rather than inventing a contract inside a review. §6 carries the
failure mode.

The record is written **before** the notice is shown, not after. A crash
between the two then costs a missed notice rather than a repeated one, which
is the **opposite** direction to the read rule above, deliberately. *Say it
once* is a user decision (§3.2), so a duplicate contradicts the contract
directly, while a missed notice is a cost §6 already records. Do not
"harmonise" the two by moving the write after the notice.

**Nothing checks that ordering, and INV-53 is not it.** Inside
`expiry_notices()` both orderings return the same thing to two successive
calls, so `notice_is_said_once` cannot go red on a reorder; its break
(`never_records`) removes the write rather than moving it, and observing the
difference needs the process to die between the two statements. What INV-53
catches is the write being *removed*. The ordering is held by keeping the write
inside `expiry_notices()` and by this paragraph, and §10 records it as
uncovered rather than letting the invariant imply a guard it does not have.

`final` is stored so entries can be pruned (INV-55), and the prune is the only
thing that reads it back. No *warning* decision does — that is `draws_left()`'s,
from the calendar. Said this way since 2026-08-31: it read "nothing reads it
back to make a decision", which the prune contradicts in the same sentence that
describes it.

### 4.6 When the check runs

No new timer. `TrayIcon.sync()` already runs at `POLL_MS`; it gains a
date-guarded call:

```python
today = datetime.date.today()
if today != self.expiry_checked_on:
    self.expiry_checked_on = today
    for body in supervise.expiry_notices(today):
        self.note(body)
```

Recomputing 561 tickets every five seconds would be waste; comparing one date
is not. The guard also handles the two cases a 24-hour timer gets wrong —
midnight rollover while the tray is running, and resume from suspend — because
it keys on the date changing rather than on elapsed time.

`self.expiry_checked_on` starts as `None`, so the first `sync()` after startup
always checks. The tray supplies a date and displays strings; it decides
nothing (§4.7).

### 4.7 What the notice says

The wording lives in `supervise.py`, beside `new_ticket_notice()` and
`refresh_message()`, for the reason those two are there: a wording decision
inside `tray.py` cannot be checked without constructing a `QSystemTrayIcon`,
and this project has no Qt-constructing test. The tray keeps only the call.

```python
def expiry_notice(game_name, final_draw, draws_left):
    """One ticket's re-buy warning, as a string. LOTTO-0034 §4.7, INV-54."""

def expiry_notices(today, tickets=None, state_path=None):
    """Every notice owed right now, and the state write that makes it once.

    Loads the dump itself when `tickets` is None, treating a missing or
    unreadable one as no tickets rather than raising — `read_settings()`'s
    rule, for `read_settings()`'s reason. Applies §4.4's qualifying test,
    reads and prunes the §4.5 state file, records each qualifying reference
    BEFORE its notice is emitted, and returns a list of strings, empty when
    nothing is owed.
    LOTTO-0034 §4.7; INV-52, INV-53, INV-55, INV-56.
    """
```

**`expiry_notices()` owns loading, selection and the state file; `tray.py`
owns none of them.** The tray passes today's date in and passes each returned
string to `note()` — it holds no decision, which is what makes INV-52, INV-53,
INV-55 and INV-56 reachable from a headless script. `tickets` and `state_path`
are injectable so a verifier can supply constructed tickets and a temporary
file, and both default to the real thing.

The dependency edges this adds are `supervise.py` → `expiry` and
`supervise.py` → `tickets`. **Both widened LOTTO-0013 §4.1, whose module table
said `supervise.py  stdlib only` until 2026-08-22** — deliberately, and §11 carries the
amendment that document needs. `expiry.py` still imports nothing but
`datetime` (INV-50), and **`tray.py` gains `datetime` and nothing else** — no
project import and no decision, which is the point the accounting is making.
Corrected 2026-08-31: this said `tray.py` gained no import at all, while §4.6's
own snippet calls `datetime.date.today()` and cannot be written without one.
Confirmed against the commit that shipped this item — `tray.py` had no
`import datetime` before it.

The display name comes from a second table beside `DRAW_DAYS`:

```python
DISPLAY_NAME = {"lotto": "Lotto", "powerball": "PowerBall",
                "daily": "Daily Lotto"}
```

**Deliberately not `history.POOL_NAMES`.** That table exists to match the
API's `winPoolName` field, is keyed per pool rather than per game, and changes
when the wire format changes — a sentence the user reads must not. Keeping the
display names here also keeps `expiry.py` free of project imports.

**`DISPLAY_NAME` must carry an entry for every key of `DRAW_DAYS`, and the two
tables are edited together.** `expiry_notices()` subscripts it directly, and
that subscript sits *outside* the guard which catches an unknown game: a game
absent from `DRAW_DAYS` is caught and skipped before reaching it, so the only
way to hit a `KeyError` there is to add a game to `DRAW_DAYS` and not to
`DISPLAY_NAME` — and that exception lands in the tray's timer slot, killing the
tray. Stated 2026-08-31 because it was not: an implementer writing
`.get(t.game, t.game)` and one writing `[...]` both conformed, and the second
is what shipped. **Nothing checks the coupling** (§10) — INV-56 covers the
other table only.

One notice per qualifying ticket, of the form:

> Your PowerBall ticket has 2 draws left — last draw Tue 8 Sep. Time to buy
> the next one.

Nothing else from the ticket appears: no reference, no board numbers, no cost,
no prize, no purchase date. INV-54 holds that line, and it is the whole of the
§3.3 exception.

**An unrecognised game gets one notice per call, and names nothing.** Where
`DRAW_DAYS` has no entry for a ticket's game, `expiry_notices()` skips that
ticket and appends **at most one** such notice however many tickets carry that
game — a rebrand makes every new ticket unknown at once (LOTTO-0031), and one
per ticket would be a burst of hundreds. It does **not** name the game: that
string came from an SMS, and §3.3's exception is bounded to the three games
above.

**It is deliberately NOT recorded in the state file, so it recurs every day
until the table is updated.** Two reasons, and the first is mechanical: §4.5's
record needs a `final`, and `final_draw_date()` raises for exactly these
games, so there is nothing to key it on — while a `final: null` entry would
have no prune rule and would breach INV-55. The second is the point of it.
This notice reports a defect rather than nudging a re-buy, §3.2's *say it
once* is a decision about re-buy notices, and going quiet about a game the app
cannot score is LOTTO-0031's failure exactly. INV-53 and INV-56 both say so.

## 5. Invariants

- **INV-49** — `expiry.DRAW_DAYS` agrees with observed draw history in both
  directions: for each game, at least 98% of the draws
  `history.all_draws(game, 0)` returns fall on a weekday the table lists,
  **and** every weekday the table lists carries at least one draw in the 90
  days before the newest draw in that record.
  *Test:* `tools/verify_expiry.py`, case `calendar_matches_history`.
  *Breaks when:* the operator adds, removes or permanently moves a draw day
  and the table is not updated. The first half alone would pass a **removed**
  day forever, which is why there is a second half. **The record is the merged
  one, and the window is measured from its newest draw rather than from
  today** — `archive_results.json` only advances when `backfill.py` is re-run
  by hand (it ended 2026-07-31 when this was written, three weeks back), so a
  case reading the archive alone could never see a change made after the last
  scrape, and its second half would decay to a wholesale failure as the file
  aged.

- **INV-50** — `expiry.final_draw_date()` and `expiry.draws_left()` are pure:
  they open no file, make no network call, and `expiry.py` imports no project
  module. The same arguments give the same answer with `archive_results.json`
  absent and no network.
  *Test:* `tools/verify_expiry.py`, case `expiry_is_pure`.
  *Breaks when:* someone "improves" the projection by consulting known draws,
  which reintroduces the dependency §4.2 exists to remove.
  **The case is stricter than that sentence and deliberately so:** it asserts
  `imported == {"datetime"}` exactly, so *any* new import reddens it, standard
  library included. That is the tightest available form of a
  no-project-imports check — a project module can always be reached through a
  stdlib one — and the strictness is the point rather than an accident. An
  implementer who needs `bisect` here is being asked to justify it, not
  blocked: widen the set in the case and say why, in the same change.

- **INV-51** — For every entry whose `history.covered()` is complete,
  `final_draw_date()` never names a date **later** than the last covered draw,
  and names it exactly for at least 98% of them. Earlier is permitted; it is
  what a cancelled draw produces, and what a later move produces for a ticket
  spanning it (§4.2).
  *Test:* `tools/verify_expiry.py`, case `calendar_matches_real_draws`.
  *Scope: the `start` boundary only. `draws_left`'s `today` boundary is pinned
  by nothing* — §10 records it.
  *Breaks when:* a draw day changes; the ndraws-th-draw rule is off by one at
  the start boundary — an entry bought on a draw day is entered in that day's
  draw, and treating `start` as exclusive shifts every date later, which is
  exactly the direction this forbids; **or the schedule changed**, which is a
  fact about the world rather than a defect and is diagnosed, not patched
  (§4.2, §6). **Check the schedule first, and within it the gap-ticket case**:
  a ticket starting in the gap left by a draw moved later is the only unsafe
  case with a precedent in the archive. A red run against it looks identical to
  an off-by-one, and "fixing" the start boundary would shift all 1,210
  currently-exact entries. The previous form of this invariant was withdrawn
  for exactly that confusion.

- **INV-52** — No notice is ever produced for a ticket whose `draws_left` is
  zero.
  *Test:* `tools/verify_expiry.py`, case `expired_tickets_are_silent`.
  *Breaks when:* the qualifying test is written as `<= 2` without the lower
  bound. Against today's dump that is 561 tickets, nearly all finished.

- **INV-53** — A given `Ticket.ref` produces at most one notice: two calls to
  `expiry_notices()` with the same tickets and the same state file return it
  on the first and not on the second, across restarts.
  *Test:* `tools/verify_expiry.py`, case `notice_is_said_once`.
  *Breaks when:* the state record is keyed on something not unique per
  purchase. **Not** the write being reordered after the notice: §4.5 and §10
  both record that as undetectable here, and every other *Breaks when* in this
  section names something its case actually reddens.
  **Scope: tickets qualifying under §4.4, and `expiry_notices()` rather than
  `sync()`.** The unrecognised-game notice (§4.7) is outside this invariant by
  design — it cannot be keyed, and it is meant to recur. Whether the tray's date guard
  calls it once a day is §4.6's claim and is checked by nothing, needing a
  `QSystemTrayIcon`; §10 records that half as uncovered rather than letting
  this invariant imply coverage it does not have. Same honesty LOTTO-0003
  INV-37 uses.

- **INV-54** — A notice contains the game's display name, the final draw date
  and the number of draws left, and no other field of the ticket: not the
  reference, the board numbers, the cost, the prize or the purchase date. The
  unrecognised-game notice (§4.7) names no game at all.
  *Test:* `tools/verify_expiry.py`, case `notice_names_nothing_else`.
  *Breaks when:* someone interpolates the `Ticket` itself, or adds the amount
  "so the user knows what to spend". This is the bound on §3.3's exception,
  and a desktop notification may be logged and synced off the machine.

- **INV-55** — `expiry_warned.json` cannot grow without bound: on every write,
  entries whose `final` is more than 90 days before today are dropped.
  *Test:* `tools/verify_expiry.py`, case `state_file_is_pruned`.
  *Breaks when:* pruning is skipped, or is keyed on the write date rather than
  on the ticket's own final draw.

- **INV-56** — A ticket whose game is absent from `DRAW_DAYS` is never
  silently dropped: `expiry.final_draw_date()` raises rather than returning
  `None`, and `expiry_notices()` returns **exactly one** notice reporting an
  unrecognised game — however many tickets carry it — naming no game, and
  returns it again on the next call rather than recording it as said.
  *Test:* `tools/verify_expiry.py`, case `unknown_game_is_loud`.
  *Breaks when:* a rebrand introduces a game name the table has no entry for
  and the call is wrapped in a bare `except`; or the notice is emitted per
  ticket, which after a rebrand is a burst of hundreds. This is LOTTO-0031's failure
  class, where a rebranded name parsed to `None` and the ticket was silently
  never scored.

## 6. Failure modes

- **The dump is missing or unreadable.** `tickets.load()` **raises**
  `FileNotFoundError` — it opens the path directly rather than guarding it —
  so `expiry_notices()` catches it and returns no notices. Correct: the app
  cannot know about a ticket it has never seen. Letting it propagate would put
  the exception in the tray's timer slot, which is why the catch is named here
  rather than left to the implementer.

- **A draw day changes and nobody notices.** Every projected date drifts, and
  the warning fires early or late by however much the schedule moved. INV-49
  is the guard, and it only fires when someone runs the verifier — so this is
  a *loud on check, silent in production* failure. It is the same exposure
  `TIER_PRICES` carries and is accepted on the same grounds.

- **A cancelled or later-moved draw**, as on 2024-12-25 and 2026-04-30. The
  calendar has counted a draw that did not happen, so the warning lands
  early — by three days in the worst case measured. Immaterial at two draws'
  notice, and on the safe side; recorded because INV-51's sign rule and its
  98% floor are what permit it rather than an oversight.

- **The state file cannot be WRITTEN.** A read-only home, an unwritable
  `$XDG_CONFIG_HOME`, a full disk. `_write_warned()` is unguarded, so the
  exception propagates through `expiry_notices()` into the tray's timer slot
  and the tray dies — the same outcome the read-side catch exists to prevent,
  from the path nobody pinned. §4.5 records that the remedy is a decision
  rather than a default, and it is filed against LOTTO-0007.

- **A ticket bought in the gap left by a draw moved LATER** — and this is the
  live one, because such a move has already happened. The moved draw sits on a
  day `DRAW_DAYS` does not list, so the calendar misses it while `covered()`
  counts it, and the record runs a draw ahead: the notice names a date after
  the ticket has already ended and the user is told too late to buy. Measured
  four days against the 2026-04-29 → 2026-04-30 move (§4.2). **No ticket in the
  dump falls in that gap, which is why INV-51 reads zero late** — a fact about
  the dump, not about the calendar. A draw moved EARLIER or added on an
  unlisted day does the same thing; neither has occurred.

  INV-51 is the only thing that would surface any of them, and only when the
  verifier is run. **A red INV-51 is a diagnosis before it is a defect**: check
  the record for a schedule change first, and this gap-ticket case before the
  other two, since it is the only one with a precedent.

- **The machine is off for the whole window.** The ticket crosses two draws
  remaining, then reaches zero, all while the tray is not running. No notice is
  ever shown, because §4.4 refuses to warn about an expired ticket and §3.2
  refuses to repeat. This is the accepted cost of *say it once*, and it is the
  one case where the user is not told at all.

- **The state file is deleted or corrupt.** Every currently-qualifying ticket
  is warned about again — at most a handful, since only live tickets qualify.
  Chosen over the alternative, where an unreadable file silences a real
  warning.

- **A ticket names a game `DRAW_DAYS` does not know.** The ticket is skipped
  and one notice reports an unrecognised game, naming none. Loud rather than
  silent, and the notice is what sends someone to update the table. INV-56.

- **The managed run never warns at all.** Under `LWSM_MANAGED=1`, `tray.py`
  takes `run_headless()`, which starts the server and waits; it never
  constructs a `QSystemTrayIcon`, so `sync()` never runs and no notice is
  possible. That follows from LOTTO-0013 §4.7 (INV-25) rather than from
  anything here, and it is not worked around: a run with no icon has nowhere
  to put a notification. Stated so nobody reads silence there as a defect.

- **The clock is wrong.** A machine whose date is far in the past shows no
  warning; far in the future, tickets read as expired and are silent. Both are
  silence rather than a false alarm, which is the safer direction.

- **Two tickets qualify on the same day.** Two notices, one per ticket, both
  naming their own game. Not merged: merging would need a wording that names
  neither game clearly, which is what §3.3 was decided against.

## 7. Tests

One new verifier, `tools/verify_expiry.py`, following the shape of
`tools/verify_page.py` and `tools/verify_payouts.py` — named cases, exit code
as the signal, and a `--break <name>` flag applying one deliberate defect so
every case is observed red. `--list` shows the breaks. This item is
greenfield, so there is no pre-fix code to red-test against; the flag is what
makes "every case observed failing" reproducible, exactly as CLAUDE.md records
for `verify_page.py`.

| Case | Locks |
|------|-------|
| `calendar_matches_history` | INV-49 |
| `expiry_is_pure` | INV-50 |
| `calendar_matches_real_draws` | INV-51 |
| `expired_tickets_are_silent` | INV-52 |
| `notice_is_said_once` | INV-53 |
| `notice_names_nothing_else` | INV-54 |
| `state_file_is_pruned` | INV-55 |
| `unknown_game_is_loud` | INV-56 |

**It goes in the data-dependent lane of `local-CI.sh`, not the CI lane.**
`archive_results.json` is gitignored (`.gitignore` lists it under
*Regenerable*) and `lotto_sms_raw.txt` never leaves this machine. Three of the
eight cases need real data, and not the same data:

| Case | Needs |
|------|-------|
| `calendar_matches_history` | the merged draw record, via `history.all_draws()` |
| `calendar_matches_real_draws` | the merged draw record **and** `lotto_sms_raw.txt` |
| `expired_tickets_are_silent` | `lotto_sms_raw.txt` — the point of the case is the real dump of mostly-finished tickets |

The other five are built on constructed `Ticket` objects and a temporary state
file, so they need neither input. A verifier that silently skipped its three
most rot-prone cases on a public runner would be the degraded-mode trap
`verify_privacy.py` already carries and `local-CI.sh`'s header warns about;
this one does not get a weak mode.

**Every case that calls `expiry_notices()` passes a temporary `state_path`,
and there are five of them** — `expired_tickets_are_silent`,
`notice_is_said_once`, `notice_names_nothing_else`, `state_file_is_pruned` and
`unknown_game_is_loud`. **The isolation is the injected argument §4.7 provides,
not an environment variable**: `_tmp_state()` returns a path under
`tempfile.mkdtemp()`, and the verifier never sets `$XDG_CONFIG_HOME`.

Corrected 2026-08-31, having been wrong in both halves — two cases named where
five touch the file, and an environment variable the verifier does not use.
The same sentence had been copied into the verifier's own module docstring, so
the spec and the code agreed with each other and both disagreed with the code.
**It is the most expensive error this document has carried.** An implementer
isolating only the two named cases leaves the other three defaulting to the
real `expiry_warned.json`, and `expired_tickets_are_silent` runs against the
REAL dump — so one run of the test suite records every live ticket as already
warned, and §3.2's *say it once* then means the user is never told. The suite
would silently destroy the feature it exists to check, before every push.

## 8. Alternatives considered (and rejected)

- **Compute expiry from `history.covered()`.** Rejected: it makes the warning
  depend on results being fetched, so a user who has not refreshed is told
  their ticket has more life in it than it has — the failure in §2.3. It would
  also make LOTTO-0028 a real dependency, which measurement showed it is not.

- **A daily repeat until a new ticket appears.** Offered and rejected by the
  user on 2026-08-22. Would have removed the machine-off-all-window failure in
  §6 at the cost of nagging.

- **A fixed number of days rather than draws.** Offered and rejected. Would
  have given Daily Lotto a fairer warning than two days, but the user counts
  in draws because that is what is bought.

- **Put it on the page instead of in a notification.** Rejected in the roadmap
  item before this spec: the stated requirement is to find out *without going
  to look*. The page half is LOTTO-0032/LOTTO-0021.

- **A second `QTimer` at 24 hours.** Rejected for the date guard in §4.6,
  which is fewer moving parts and handles suspend/resume and midnight rollover
  that an elapsed-time timer gets wrong.

- **Store warn-state in `settings.json`.** Rejected: it would give that file a
  second writer that is not the server, against LOTTO-0013 §4.1.

- **Say nothing specific in the notice**, keeping
  `new_ticket_notice()`'s no-ticket-data rule intact. Offered to the user with
  the privacy cost of the alternative stated; rejected, because with two
  tickets running it cannot say what to buy. See §3.3.

## 9. Out of scope

- Showing the final draw date on the page — LOTTO-0032 and LOTTO-0021.
- Repairing `draws_remaining`'s conflation of *not drawn* with *not fetched*
  (§2.3) — filed against LOTTO-0007 as a deferred rough edge.
- Refreshing results on a schedule — LOTTO-0028. Measurement showed it is not
  a dependency of this item.
- Backfilling draws further back — LOTTO-0006, shipped 2026-08-31. It leaves
  the **production path** untouched: the warning is computed from the calendar
  alone and `expiry.py` reads no results (INV-50), so no notice changes because
  the archive moved. **It does not leave the CHECKS untouched, and this bullet
  said so until 2026-08-31.** INV-49 reads `history.all_draws()` and INV-51's
  population is every entry whose `history.covered()` is complete, so widening
  or narrowing the results record changes what both measure — INV-51's grew
  from 260 entries to 1,223 — and it is what forced §4.2's amendment. **Any
  later change to the results record re-arms `tools/verify_expiry.py`**, and
  INV-51's margin over its 98% floor is about a dozen entries.
- Predicting future draws for any purpose other than a ticket's own expiry.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-49 | `tools/verify_expiry.py::calendar_matches_history` |
| INV-50 | `tools/verify_expiry.py::expiry_is_pure` |
| INV-51 | `tools/verify_expiry.py::calendar_matches_real_draws` |
| INV-52 | `tools/verify_expiry.py::expired_tickets_are_silent` |
| INV-53 | `tools/verify_expiry.py::notice_is_said_once` |
| INV-54 | `tools/verify_expiry.py::notice_names_nothing_else` |
| INV-55 | `tools/verify_expiry.py::state_file_is_pruned` |
| INV-56 | `tools/verify_expiry.py::unknown_game_is_loud` |
| §4.6's date guard firing once a day — INV-53's `sync()` half | **nothing** — it lives in `tray.py::sync()`, which needs a `QSystemTrayIcon`; the project has no Qt-constructing test. The wording, the selection and the state file are all checkable because §4.7 puts them in `supervise.py`; the call site is not. Same exposure LOTTO-0003 INV-37 records. |
| A draw day changing in the real world | **nothing in production** — INV-49 catches it only when the verifier is run. Accepted, as for `TIER_PRICES`. |
| `draws_left`'s `today` boundary (§4.1) | **nothing** — INV-51 pins the `start` boundary only. Verified by mutation 2026-08-31: `d >= today` → `d > today` leaves all eight cases green, and the ticket loses its final-day warning. A ninth case is filed against LOTTO-0007. |
| §4.5's write-before-notice ORDERING | **nothing** — inside `expiry_notices()` both orderings look identical to two successive calls, so INV-53 catches the write being removed and not its being moved. Observing it needs the process to die between the two statements. Held by the paragraph in §4.5. |
| A state-file WRITE failure (§4.5) | **nothing** — `_write_warned()` is unguarded and `tray.py` adds no `try`, so it reaches the timer slot. Contract unresolved; filed against LOTTO-0007. |
| `DISPLAY_NAME` covering every `DRAW_DAYS` key (§4.7) | **nothing** — INV-56 covers a game missing from `DRAW_DAYS`, which is the opposite direction. A game added to one table and not the other raises in the timer slot. |

## 11. Cross-doc impact

- **`CLAUDE.md`** — the architecture section gains `expiry.py`, and the
  `supervise.py` paragraph gains `expiry_notice()` and `expiry_notices()`
  alongside `new_ticket_notice()`. The privacy paragraph gains §3.3's bounded exception,
  so a later reader does not read the notice rule as absolute and "fix" it.
  Its § Verification list is the passage that carries a count — it read "these
  seven scripts *are* the test suite" when this item landed and went to eight,
  with the data-dependent group going from four to five and the CI lane
  unchanged at three. It has moved again since; read the line, do not quote
  this one.
- **`docs/specs/LOTTO-0013-tray-and-supervisor.md` §4.1** — its module table
  said `supervise.py  stdlib only`, widened here to stdlib plus `expiry` and
  `tickets`. That edit was required, not optional: an implementer holding §4.1
  as written refuses the import and moves `expiry_notices()` somewhere else,
  which moves where four invariants are exercised. **Landed 2026-08-22**, and
  that document records the old wording itself.
- **`CLAUDE.md` § What this is** — its standing summary said *"three of the
  five are open, and the primary one is the least built"*. Sign 1 IS the primary
  one and this item is what built it, so both halves stop being true here. Added
  2026-08-31: this bullet was missing, and the sentence was still false on disk
  three items later — the file every session loads was telling each new reader
  that the project's primary job was its least-built feature, in the same breath
  as instructing them to read the signs before adding a feature.
- **`README.md`** — sign of success 1 moves from *partly done* to built. (The
  same standing line still calls sign 2 open, which LOTTO-0035 shipped on
  2026-08-20; that correction is not this item's to make.)
- **`CHANGELOG.md`** — one entry citing LOTTO-0034.
- **`docs/specs/LOTTO-0003-live-sms-watch.md` §4.7** — states the
  no-ticket-data rule for `new_ticket_notice()`. Unchanged in force, but gains
  a cross-reference so the two rules are not read as one.
- **`local-CI.sh`** — its header states which verifiers are data-dependent and
  why; `verify_expiry.py` joins the data-dependent group named there.

## 12. Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-08-22 | 3, cold — genre pinned `spec` | 1 | 4 | 3 | 2 | **Ten verified, ten fixed; none dismissed.** **All three lanes independently found the same defect**, the run's strongest signal: §4.6's tray hook called `supervise.expiry_notices(...)` — arguments elided — and nothing in the document specified it, while §4.5 called the tray the state file's writer and §10 claimed selection sat outside the tray. Three surfaces bound to a function that did not exist, and the two INV cases locking it would have been built against whatever an implementer guessed. Fixed by giving `expiry_notices()` a signature, an owner and its dependency edges. **The most consequential single finding was INV-49's**, raised by two lanes and an open question from the third: the invariant was scoped to `archive_results.json`, which `backfill.py` only advances when re-run by hand and which ended 2026-07-31 — so the half added specifically to catch a *removed* draw day could never fire on a change made after the last scrape, and would have decayed to wholesale failure as the file aged. Rescoped to the merged record with the window measured from its newest draw, then executed: lotto 170/171, powerball 171/171, daily 597/597, every listed weekday covered. **Two contradictions were the document arguing with itself**: INV-54 excluded the draw count its own specimen notice carries, and §4.5 claimed writing-before-notice took "the same direction of failure" as the read rule when it takes the opposite — an implementer harmonising the two would have written the record after the notice, which INV-53 calls a breach. **Two open questions were promoted to findings by the orchestrator** after measuring: no game→display-name map exists in either direction (`GAME_MAP` runs SMS-name→key, `history.POOL_NAMES` is keyed per pool and tracks the wire format), so §4.7's "the display name" invented a surface INV-54 binds to; and §11 said README moves sign 1 "from open", where README says *partly done*. **One gap nobody had covered**: `DRAW_DAYS` has three keys and nothing said what happens to a fourth game — LOTTO-0031's exact failure class — now INV-56. One open question resolved clean and is not counted: `Ticket.ref` is unique per purchase (561 tickets, 561 distinct references, none reused). Invariants went 7 to 8, cases 7 to 8. |
| 2 | 2026-08-22 | 3, cold — identical brief, packet rebuilt from disk | 2 | 5 | 3 | 0 | **Ten verified, ten fixed; one dismissed as immaterial. Cap reached (2 for a spec); the run ships.** **Four of the ten landed on text loop 1 wrote** — a 40% share, so this is a middling cap rather than a calm or a violent one: loop 1's largest addition, the unrecognised-game contract, was itself underspecified and generated three of them. **All three lanes independently found two defects.** First, §4.7 declared `supervise.py` → `expiry` while LOTTO-0013 §4.1's module table says `supervise.py  stdlib only`, and §11 did not list LOTTO-0013 at all — an implementer holding that document refuses the import and relocates four invariants' code. Second, the unrecognised-game notice could never be recorded as said: §4.5's record needs a `final` and `final_draw_date()` raises for exactly those games, so it would either repeat forever against §3.2 or need a `final: null` entry INV-55 has no prune rule for. Now: one notice per call, deliberately unrecorded and recurring, with INV-53 and §3.2 scoped to re-buy notices. **Two false claims about the code survived loop 1 and were caught by running them.** §6 said `tickets.load()` "has nothing to return" on a missing dump — it raises `FileNotFoundError`, which would have landed in the tray's timer slot. And §13 asserted a purchase rate of one ticket per ten days; measured, it is one per 2.44 days over 1368 days, with 12 inside the trailing 90. **Three gaps nobody had covered:** `draws_left`'s `today` boundary was unpinned while the `start` boundary was pinned two sections away; the managed run (`LWSM_MANAGED=1`) never builds a tray icon so it never warns, which is now stated rather than left as apparent silence; and §11 omitted the one CLAUDE.md passage carrying a count ("these seven scripts"). Loading moved into `expiry_notices()`, so `tray.py` gains no import and holds no decision. One dismissed as true-but-immaterial: §2.1 said `sync()` sets icon, tooltip and menu "and nothing else" while it also calls `check_new_tickets()` — corrected in passing, but it changed nothing anyone would build. |
| 3 | 2026-08-31 | 3, cold — genre pinned `spec`; new run, trigger LOTTO-0006 | 5 | 1 | 3 | 1 | **Ten verified, ten fixed; two dismissed. First loop of a NEW run** (the 2026-08-22 run reached its cap at loop 2). Trigger: LOTTO-0006 widened the scraped archive from 2025 to 2022, which falsified INV-51's *within one day* bound with a public holiday rather than a defect, and the user chose to assert the SIGN instead. **All three lanes independently found the same two defects, and both were in the amendment written that morning** — the strongest signal of the run and an argument for gating a contract change however confident its author is. First, the justification *"a disagreement can only ever be the calendar counting a draw that did not happen"* is unsound: a draw moved EARLIER, or an extra draw on an unlisted day, makes the record reach the ticket's last draw first and projects LATE — the unsafe direction, and the one INV-51 now asserts against unconditionally. The claim is replaced by the four events and their two directions, with the safe-only result restated as a MEASUREMENT (enumerated over the whole archive: six cancellations and one later move, zero earlier moves) rather than an impossibility, and §6 carries the residual late case as a live exposure. Second, §9 said LOTTO-0006 *"changes nothing here: this item reads the calendar, never the results"* while the header and §4.2 two hundred lines apart said it forced this very amendment — true of the production path, false of the checks, since INV-49 reads `all_draws()` and INV-51's population grew from 260 entries to 1,223. A maintainer widening the archive again would have re-run nothing. **All three also found the evidence base stale**: §4.2's *"the one other irregularity in the file"* is false (there are seven), and §4.1's embedded census still printed its pre-backfill output. Both are now dated to the archive they measured. **Two lanes found §11 omitted the one `CLAUDE.md` passage this item falsified** — *"the primary one is the least built"*, of the sign this item BUILT, still false on disk three items later in the file every session loads. Fixed at its home and rot-proofed by pointing at the README instead of restating a tally that had been wrong three times running. **Three Q3 gaps, each a coupling the code already binds to and the contract never stated:** `DISPLAY_NAME` must cover every `DRAW_DAYS` key, and the subscript sits OUTSIDE the guard that catches an unknown game, so a one-table edit kills the tray; `ndraws < 1` raises `ValueError` and `expiry_notices()` routes it to the *unrecognised-game* notice, diagnosing a malformed ticket as a rebrand; and the state file's WRITE path has no failure contract at all while the READ path's is pinned, so an unwritable home reaches the tray's timer slot. The last two are documented as-shipped and filed against LOTTO-0007 (p) and (q) rather than resolved inside a docs gate — the remedy is a decision, not a default. **One Q4**: §4.5 named INV-53 as the guard on write-before-notice ordering, which INV-53 cannot observe — both orderings look identical to two successive calls, and its break removes the write rather than moving it. §10 now records it uncovered, with two more rows beside it. **The run's own lesson is a fix-one-copy failure caught by 4b**: the unsound *early-only* argument had been written into `expiry.py`, `tools/verify_expiry.py`, `CHANGELOG.md` and the `ROADMAP.md` note as well as the spec, all within the hour. Five copies, one sweep. Two dismissed as true-but-immaterial: `TrayIcon.sync()` names a class that does not exist (it is `LottoTray`), which a reader resolves in one grep; and the status header's *"3 off by one"* snapshot, which §4.2 already tells the reader is a floor and not a snapshot. Four lane open questions resolved clean and counted nowhere: `all_draws()` does return sorted rows, INV-54's forbidden clauses are reachable, and the 13 early entries decompose EXACTLY into the two documented causes (9 lotto + 1 daily from 2024-12-25, 3 lotto from the 2026-04-30 move), which also verifies §6's three-day worst case. `check-doc-facts` equivalents run via `doc_integrity` / `spec_lint` / `doc_citations`: clean before and after, except that `spec_lint`'s three test-surface checks did NOT run (no `tests/features/` directory — ANTS-4393), so those clauses were read by hand. |
| 4 | 2026-08-31 | 3, cold — identical brief, packet rebuilt from disk and given a `tray.py` window | 5 | 1 | 0 | 0 | **Six verified, six fixed; three dismissed. Cap reached (2 for a spec); the run files its tail — which is empty — and exits.** **A MIDDLING cap: 3 of the 6 landed on text loop 3 wrote**, so the run is neither calm nor oscillating, and the three that did not are old defects two cold reads had already walked past. **All three lanes independently found the same defect, and it is the most expensive this document has carried.** §7 said *"`notice_is_said_once` and `state_file_is_pruned` write to a temporary directory via `$XDG_CONFIG_HOME`"* — wrong in both halves. FIVE cases call `expiry_notices()` and each passes an injected `tempfile.mkdtemp()` path; `$XDG_CONFIG_HOME` appears nowhere in the verifier. An implementer isolating only the two named cases leaves the other three defaulting to the user's REAL `expiry_warned.json`, and `expired_tickets_are_silent` runs against the REAL dump — so one run of the suite records every live ticket as already warned and *say it once* means the user is never told again. The suite would destroy the feature it checks, before every push. §7 also contradicted itself six lines earlier, saying "the other five". The identical sentence sat in the verifier's own docstring, so spec and code agreed with each other and both disagreed with the code. **One lane falsified loop 3's own taxonomy by construction, and the counter-example was reproduced before it was believed.** Loop 3 wrote that a cancelled *or later-moved* draw "can only ever" land EARLY. It cannot: the moved draw sits on an unlisted day, so the calendar misses it while `covered()` counts it (`date >= start`) — for any ticket starting IN THE GAP the move leaves, the record runs a draw ahead. Executed: a Lotto ticket bought 2026-04-30 for 10 draws projects 2026-06-03 against a real last draw of 2026-05-30, **four days LATE**, the direction INV-51 forbids. §4.2 now carries a three-by-two table instead of a two-way split, and §6's acceptance no longer rests on "neither has ever happened" — a later move HAS happened; the unsafe class is empty of TICKETS, not of events, and only because no ticket starts in that one gap. INV-51's diagnosis order named causes with no precedent and now names this one first. Filed as LOTTO-0007 (s). **One lane proved a coverage hole by mutation and the orchestrator re-ran it: `draws_left`'s `today` boundary is pinned by nothing**, while §4.1 credited INV-51 with pinning it. Changing `d >= today` to `d > today` leaves ALL EIGHT cases green — the one fixture whose draw falls on `TODAY` interpolates the value and never asserts it — so a flip silently costs every ticket its final-day warning and the suite still reports PASS. §4.1 and §10 now record it; a ninth case is filed as LOTTO-0007 (r). **Two lanes found §4.7's *"`tray.py` gains no new import at all"*** false — it imports `datetime`, used only by §4.6's own date guard. One lane could not prove it without git and said so; confirmed against the shipping commit. Also fixed: INV-53's *Breaks when* claimed a cause §4.5 and §10 both call undetectable — loop 3's own collateral, since loop 3 wrote those two passages; and §4.2's enumeration described the moved draw's origin date as a sixth cancellation, double-counting one event (five are Christmas). **Collateral fixed outside the subject, at its home:** `local-CI.sh` said *"the five data-dependent verifiers"* against its own header's six of nine. Two lanes noticed §4.5's *"nothing reads it back to make a decision"* is contradicted by the prune in the same sentence, neither filed it, and it is fixed. Three dismissed as true-but-immaterial: §11's parenthetical that the README "still calls sign 2 open"; the status header's pre-LOTTO-0006 snapshots; and INV-49's first half being arithmetically vacuous for `daily`, whose `DRAW_DAYS` is all seven weekdays — recorded because a reader may take that figure as validation, but no line changes. Lane open questions resolved clean: `expiry.py` has three functions against §4.1's "two" (§4.7 places the second table unambiguously, nothing built differs), and INV-54's forbidden clauses are all reachable. **Routing at the cap: the tail is empty and the document goes to no further gate as it stands.** The 2026-08-31 run took 16 fixes over two loops, and the early/late claim alone has now been wrong twice. What settles it is not a third cold read but the two filed items — (r)'s missing case and (s)'s measured bound — which exercise the contract against real code. `doc_integrity` / `spec_lint` / `doc_citations` clean; `spec_lint`'s test-surface checks did not run (ANTS-4393). |

## 13. Resource cost

No new dependency; `expiry.py` uses `datetime` only. `DRAW_DAYS` is three
sets. `expiry_warned.json` holds one record per warned ticket, pruned at 90
days past the final draw (INV-55). Measured 2026-08-22: 561 tickets span
2022-11-09 to 2026-08-08, one per 2.44 days, and **12** fall inside the
trailing 90 days — so the pruned file settles at roughly a dozen records.

The per-day step **re-parses the dump**: `expiry_notices()` calls
`tickets.load()`, which reads and parses `lotto_sms_raw.txt` rather than
reusing a cached list — deliberately, because a cached list would never see
what `watch_sms.py` appended, which is the arrival path LOTTO-0003 exists for.
It runs inline on the GUI thread, once a day, and that is affordable because
it was measured rather than assumed: `tickets.load()` over the live dump takes
**0.018 s**, import included. The five-second `sync()` path does one date
comparison and nothing else.
