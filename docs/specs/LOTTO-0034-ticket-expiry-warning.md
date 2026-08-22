# LOTTO-0034 — Warn the user a ticket is about to run out

**Status:** spec draft (2026-08-22).
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
   `Supervisor.is_running()`, and nothing else. The only unprompted notice the
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

1. **The warning fires when two draws remain**, not one, not three, and not a
   fixed number of days. On Lotto and PowerBall that is roughly four to seven
   days' notice; on Daily Lotto it is two days, which the user accepted.

2. **It is said once and not repeated.** A ticket that crosses the threshold
   produces exactly one notice, ever. The user rejected a daily repeat and a
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
   — the game name and the final draw date, and no other field of the ticket.
   The rule stands unchanged for `new_ticket_notice()` and
   `refresh_message()`, neither of which is touched.

4. **The tray computes it, not the page.** The warning must work with the
   server stopped, so it may not depend on `serve.py`. Putting the same figure
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

### 4.2 The final draw date is fixed at purchase, and is accurate to a day

A ticket's last draw is decided the moment it is bought: it is the `ndraws`-th
calendar draw on or after `Ticket.start`. No results data enters the
calculation, which is what lets the warning work with the server stopped and
the machine offline.

Two measurements bound how far that can be trusted.

**Projection against held-out history.** Deriving `DRAW_DAYS` from 2025 draws
alone and using it to predict every 2026 draw in the archive — 333 draws
across the three base pools, `daily:0` 212, `powerball:0` 61, `lotto:0` 60 —
gives the right count in every pool and one wrong date: the Lotto draw due
Wednesday 2026-04-29 ran on Thursday 2026-04-30. The one other irregularity in
the file is a missing Daily Lotto draw on 2025-12-25.

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

So the contract is **within one day**, not exact, and INV-51 states it that
way with the measured share. A deviation of one day is immaterial to a warning
that fires two draws — several days — ahead, and §6 records what a larger
deviation would do.

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
same thing three times. `Ticket.ref` is the key.

### 4.5 Saying it once: the state file

```
$XDG_CONFIG_HOME/lotto-tracker/expiry_warned.json     (else ~/.config/...)

{"warned": [{"ref": "<VAS reference>", "final": "YYYY-MM-DD"}, ...]}
```

It sits beside `settings.json`, whose paths `supervise.config_home()` and
`supervise.settings_path()` already resolve, and a new
`supervise.expiry_state_path()` resolves this one the same way.

**It has exactly one writer — the tray — and that is deliberate.**
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

The record is written **before** the notice is shown, not after. A crash
between the two then costs a missed notice rather than a repeated one — the
same direction of failure the read rule takes, chosen for consistency rather
than because one is obviously better.

`final` is stored so entries can be pruned (INV-55); nothing reads it back to
make a decision.

### 4.6 When the check runs

No new timer. `TrayIcon.sync()` already runs at `POLL_MS`; it gains a
date-guarded call:

```python
today = datetime.date.today()
if today != self.expiry_checked_on:
    self.expiry_checked_on = today
    for body in supervise.expiry_notices(...):
        self.note(body)
```

Recomputing 561 tickets every five seconds would be waste; comparing one date
is not. The guard also handles the two cases a 24-hour timer gets wrong —
midnight rollover while the tray is running, and resume from suspend — because
it keys on the date changing rather than on elapsed time.

`self.expiry_checked_on` starts as `None`, so the first `sync()` after startup
always checks.

### 4.7 What the notice says

The wording lives in `supervise.py`, beside `new_ticket_notice()` and
`refresh_message()`, for the reason those two are there: a wording decision
inside `tray.py` cannot be checked without constructing a `QSystemTrayIcon`,
and this project has no Qt-constructing test. The tray keeps only the call.

```python
def expiry_notice(game, final_draw, draws_left):
    """One ticket's re-buy warning. LOTTO-0034 §4.7, INV-53, INV-54."""
```

One notice per qualifying ticket, of the form:

> Your PowerBall ticket has 2 draws left — last draw Tue 8 Sep. Time to buy
> the next one.

The game name is the display name, not the internal key. Nothing else from the
ticket appears: no reference, no board numbers, no cost, no prize, no purchase
date. INV-54 is what holds that line, and it is the whole of the §3.3
exception.

## 5. Invariants

- **INV-49** — `expiry.DRAW_DAYS` agrees with observed draw history in both
  directions: for each game, at least 98% of the draws recorded in
  `archive_results.json` fall on a weekday the table lists, **and** every
  weekday the table lists carries at least one draw in the most recent 90 days
  of that file.
  *Test:* `tools/verify_expiry.py`, case `calendar_matches_history`.
  *Breaks when:* the operator adds, removes or permanently moves a draw day
  and the table is not updated. The first half alone would pass a **removed**
  day forever, which is why there is a second half.

- **INV-50** — `expiry.final_draw_date()` and `expiry.draws_left()` are pure:
  they open no file, make no network call, and `expiry.py` imports no project
  module. The same arguments give the same answer with `archive_results.json`
  absent and no network.
  *Test:* `tools/verify_expiry.py`, case `expiry_is_pure`.
  *Breaks when:* someone "improves" the projection by consulting known draws,
  which reintroduces the dependency §4.2 exists to remove.

- **INV-51** — For every entry whose `history.covered()` is complete,
  `final_draw_date()` names the same date as the last covered draw to within
  one day, and exactly for at least 98% of them.
  *Test:* `tools/verify_expiry.py`, case `calendar_matches_real_draws`.
  *Breaks when:* a draw day changes, or the ndraws-th-draw rule is off by one
  at the start boundary — an entry bought on a draw day is entered in that
  day's draw, and treating `start` as exclusive would shift every date.

- **INV-52** — No notice is ever produced for a ticket whose `draws_left` is
  zero.
  *Test:* `tools/verify_expiry.py`, case `expired_tickets_are_silent`.
  *Breaks when:* the qualifying test is written as `<= 2` without the lower
  bound. Against today's dump that is 561 tickets, nearly all finished.

- **INV-53** — A given `Ticket.ref` produces at most one notice, across
  restarts and across any number of `sync()` calls.
  *Test:* `tools/verify_expiry.py`, case `notice_is_said_once`.
  *Breaks when:* the state record is keyed on something not unique per
  purchase, or is written after the notice and the process dies between them.

- **INV-54** — A notice contains the game's display name and the final draw
  date and no other field of the ticket: not the reference, the board numbers,
  the cost, the prize or the purchase date.
  *Test:* `tools/verify_expiry.py`, case `notice_names_nothing_else`.
  *Breaks when:* someone interpolates the `Ticket` itself, or adds the amount
  "so the user knows what to spend". This is the bound on §3.3's exception,
  and a desktop notification may be logged and synced off the machine.

- **INV-55** — `expiry_warned.json` cannot grow without bound: on every write,
  entries whose `final` is more than 90 days before today are dropped.
  *Test:* `tools/verify_expiry.py`, case `state_file_is_pruned`.
  *Breaks when:* pruning is skipped, or is keyed on the write date rather than
  on the ticket's own final draw.

## 6. Failure modes

- **The dump is missing or unreadable.** `tickets.load()` has nothing to
  return, no ticket qualifies, and no notice is shown. Correct: the app cannot
  know about a ticket it has never seen. The tray's existing empty-dump
  behaviour is unchanged.

- **A draw day changes and nobody notices.** Every projected date drifts, and
  the warning fires early or late by however much the schedule moved. INV-49
  is the guard, and it only fires when someone runs the verifier — so this is
  a *loud on check, silent in production* failure. It is the same exposure
  `TIER_PRICES` carries and is accepted on the same grounds.

- **A one-off moved draw**, as on 2026-04-30. One ticket's warning lands a day
  early or late. Immaterial at two draws' notice; recorded because INV-51's
  98% floor is what permits it rather than an oversight.

- **The machine is off for the whole window.** The ticket crosses two draws
  remaining, then reaches zero, all while the tray is not running. No notice is
  ever shown, because §4.4 refuses to warn about an expired ticket and §3.2
  refuses to repeat. This is the accepted cost of *say it once*, and it is the
  one case where the user is not told at all.

- **The state file is deleted or corrupt.** Every currently-qualifying ticket
  is warned about again — at most a handful, since only live tickets qualify.
  Chosen over the alternative, where an unreadable file silences a real
  warning.

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

**It goes in the data-dependent lane of `local-CI.sh`, not the CI lane.**
`archive_results.json` is gitignored (`.gitignore` lists it under *Regenerable*)
and INV-49 and INV-51 both read it. A verifier that silently skips its two
most rot-prone cases on a public runner is the degraded-mode trap
`verify_privacy.py` already carries and `local-CI.sh`'s header warns about;
this one does not get a weak mode. The four cases that need no data still run
locally alongside the rest.

`notice_is_said_once` and `state_file_is_pruned` write to a temporary
directory via `$XDG_CONFIG_HOME`, never to the user's real config.

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
- Backfilling draws earlier than 2025-01-01 — LOTTO-0006.
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
| §4.6's date guard actually firing in the tray | **nothing** — it lives in `tray.py::sync()`, which needs a `QSystemTrayIcon`; the project has no Qt-constructing test. The wording and the selection are checkable because §4.7 and §4.4 put them outside the tray; the call site is not. Same exposure LOTTO-0003 INV-37 records. |
| A draw day changing in the real world | **nothing in production** — INV-49 catches it only when the verifier is run. Accepted, as for `TIER_PRICES`. |

## 11. Cross-doc impact

- **`CLAUDE.md`** — the architecture section gains `expiry.py`, and the
  `supervise.py` paragraph gains `expiry_notice()` alongside
  `new_ticket_notice()`. The privacy paragraph gains §3.3's bounded exception,
  so a later reader does not read the notice rule as absolute and "fix" it.
- **`README.md`** — sign of success 1 moves from open to built.
- **`CHANGELOG.md`** — one entry citing LOTTO-0034.
- **`docs/specs/LOTTO-0003-live-sms-watch.md` §4.7** — states the
  no-ticket-data rule for `new_ticket_notice()`. Unchanged in force, but gains
  a cross-reference so the two rules are not read as one.
- **`local-CI.sh`** — its header states which verifiers are data-dependent and
  why; `verify_expiry.py` joins the data-dependent group named there.

## 12. Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|

## 13. Resource cost

No new dependency; `expiry.py` uses `datetime` only. `DRAW_DAYS` is three
sets. `expiry_warned.json` holds one record per warned ticket, pruned at 90
days past the final draw (INV-55); at the observed rate of roughly one ticket
per ten days that is a bounded few dozen records. The per-day recomputation
walks the parsed ticket list once — 561 tickets today — and does date
arithmetic only; the five-second `sync()` path does one date comparison.
