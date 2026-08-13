# LOTTO-0003 — Pick up new tickets as the SMS arrives, with no cable

**Status:** accepted (2026-08-13)
**Kind:** feature.
**Source:** ROADMAP LOTTO-0003 (user-request-2026-08-01), reaffirmed
2026-08-13 ("get the app to a point where I don't have to plug in the cable").
**Blocked by:** nothing.
**Blocker for:** nothing, though LOTTO-0028 (refresh on a schedule) becomes
less necessary once the page refreshes when a ticket actually arrives (§4.7).
**Amends:** `docs/specs/LOTTO-0001-lottery-ticket-tracker.md` §4.1, whose
closing sentence — "Only the adb path feeds the pipeline in this spec" — this
document makes false. §12 records the edit.

Sections: [1 Goal](#1-goal) · [2 Problem](#2-problem) ·
[3 Scope decisions](#3-scope-decisions) · [4 Design](#4-design) ·
[5 Invariants](#5-invariants) · [6 Failure modes](#6-failure-modes) ·
[7 Tests](#7-tests) ·
[8 Alternatives considered (and rejected)](#8-alternatives-considered-and-rejected) ·
[9 Out of scope](#9-out-of-scope) · [10 Resource cost](#10-resource-cost) ·
[11 What checks this](#11-what-checks-this) ·
[12 Cross-doc impact](#12-cross-doc-impact) ·
[13 Cold-eyes loop log](#13-cold-eyes-loop-log)

Layman: buy a ticket, and it shows up on the page by itself. No USB cable, no
running a script — the phone sends the message to the PC over Wi-Fi the moment
it arrives, and the page re-scores itself.

## 1. Goal

A lottery SMS that reaches the phone reaches `lotto_sms_raw.txt` without anyone
plugging anything in, and the page it feeds re-scores itself so the ticket is
visible rather than merely stored. The cable stops being required for the
*routine* case — it remains the tool for bulk history (§3).

## 2. Problem

Two problems, and the second is the one that made this urgent.

**The cable is the only road in.** `find_lotto_sms.py` has talked to the phone
over Wi-Fi since the beginning, but it only ever *printed*: LOTTO-0001 §4.1
calls it "inspection only", and `tickets.load()` reads one format, which only
adb writes. So every ticket entered the project by USB, on the days someone
remembered.

**A dump that stands still hides a parser that has stopped working.** On
2026-08-12 the import filter was widened (LOTTO-0030) and the re-pull that
followed exposed LOTTO-0031: a ticket bought on 2026-08-08 naming the rebranded
"LOTTO 5 MAX" had parsed to `None` and was silently never scored. No test could
have caught it, because the defect was invisible until fresh data arrived. A
four-day-old dump is not a stale convenience; it is a period in which the
project cannot tell the difference between "no wins" and "not looking".

## 3. Scope decisions

- **This path owns NEW messages; adb keeps bulk history.** A full history pull
  is 951 records the phone already holds and the dump already has. The two
  paths are complementary, not competing, and §4.2 is what stops them
  disagreeing about what a lottery message is.
- **It runs with the tray, and only with the tray.** The user chose this over
  an always-on service (2026-08-13). One less moving part, and the watcher's
  life matches the life of the thing that displays what it collects.
- **A managed run (`LWSM_MANAGED=1`) does NOT start it.** That path's contract
  is "the server, logged to stdout" (LOTTO-0013 §4.7), and a manager that
  wanted a second process would start it the way it starts `serve.py` —
  directly. Adding an unrequested child to someone else's process tree is the
  same error as handing them a port they did not ask for (§4.5 there).
- **`find_lotto_sms.py` is unchanged and stays inspection-only.** Its keyword
  list is deliberately wider and also matches addresses; the two must not be
  merged (§4.2).
- **No page changes.** The page already renders whatever the dump holds. What
  is new is that it gets asked to look again (§4.7).

## 4. Design

### 4.1 Two ways in, because neither is sufficient alone

**`conversationCreated` cannot carry discovery, and the first implementation of
this item was built on the belief that it could.** Measured on the paired
Galaxy S21, 2026-08-13: a first `requestAllConversationThreads()` after the
KDE Connect daemon started delivered 202 `conversationCreated` signals in 60
seconds, steady at ~3.3/second. Every later call delivered **zero**, while
`activeConversations()` held 2,325 entries the whole time. The signal fires
when the daemon *learns* of a conversation, not when it is asked about one.

That is not a small correction. A discovery built on it works exactly once per
daemon lifetime and then silently finds nothing — and it did: the first live
run of this watcher reported "0 new" against a phone holding 951 matching
messages, and left no thread state behind, which is the only reason it was
caught rather than shipped. A collection path that quietly stops collecting is
this project's cardinal failure with a new coat on.

So the two sources are used for what each actually does:

| Source | What it gives | Used for |
|---|---|---|
| `activeConversations()` | a snapshot: newest message per thread | discovery, and the ordinary new ticket |
| `conversationUpdated` | genuinely new messages, **and** every message delivered in answer to `requestConversation()` (measured: 25 for one thread) | live arrivals and history |
| `conversationCreated` | first-ever sighting of a conversation only | live arrivals in a thread never seen before |

The completion problem LOTTO-0001 §4.1 warns about is real and unchanged — a
partial list is indistinguishable from a complete one, and a six-second wait
once returned 25 threads where the phone has 2,325. It is answered by watching
the snapshot **stop growing** (`QUIET = 8.0` seconds of no change,
`CATCHUP_CAP = 1200.0` as the ceiling) rather than by sleeping on it. A cold
daemon fills the list over about twelve minutes at the rate measured above; a
warm one is complete on the first read, and the whole catch-up then takes 21
seconds. Neither case needs a guessed wait.

**The ordinary new ticket needs no history request at all.** A purchase SMS is
the newest message in its thread, so the snapshot alone carries it.

### 4.2 One filter, because there is one file

Both collection paths append to `lotto_sms_raw.txt`. If they disagree about
what belongs in it, the dump's contents depend on which path happened to
collect a message — the same defect class as LOTTO-0030, where a filter
silently excluded 366 payout SMSes for months.

So `watch_sms.wanted()` is LOTTO-0001 §4.1's adb `WHERE` clause, re-expressed:

| adb (SQL, on the phone) | watcher (Python, on the PC) |
|---|---|
| `body LIKE '%lotto%' OR '%powerball%' OR '%VAS00%'` | `INCLUDE = ("lotto", "powerball", "vas00")` |
| `AND body NOT LIKE '%kWh%'` | `EXCLUDE` carries `"kwh"` |
| `AND body NOT LIKE '%Enter tokens%'` | `EXCLUDE` carries `"enter tokens"` |

Body only, never the address: adb matches `body LIKE`, and SQLite's `LIKE` is
case-insensitive across ASCII, which is why the Python side lower-cases first.
**`find_lotto_sms.py` matches a wider list and also matches addresses. Do not
unify them** — that one prints and this one writes, and widening the printer is
free where widening the pipeline is not.

INV-32 checks the two against **SQLite itself** rather than against a second
Python transcription (§7 says why).

### 4.3 The record, and reading it back before believing it

A record is adb's own line: `Row: N address=A, date=MS, body=B`, newline
terminated, bodies allowed to span lines (561 of the 951 records held on
2026-08-13 do).

Two hazards, both because an SMS body is data from outside:

- **A comma in the address** would swallow the `date=` field, because
  `tickets.rows()` reads the address as everything up to the first comma. The
  address is stripped of commas and newlines.
- **A body containing a line matching `^Row: N address=`** would split one
  record into two, the second carrying a date nobody sent. Such a line is
  prefixed with a space. No message has ever contained one (measured across all
  951 records, 2026-08-13); the guard costs one substitution and prevents a
  wrong ticket rather than a crash.

`append_new()` then **reads each record back through `tickets.rows()` before
accepting it**, so what is de-duplicated is exactly what will later be scored,
and a record the reader cannot see is dropped at the door rather than written
and ignored forever.

`tickets.rows()` is new, and is the dump format's one reader:
`tickets.load()` now calls it too. Two readers of one format agree today and
drift later, and a drifted reader would duplicate every record it failed to
recognise.

### 4.4 De-duplication on (date, body)

The catch-up pass (§4.5) re-offers history the dump already holds on **every**
run, so de-duplication is the normal path, not an edge case. The key is the
pair `(date_ms, body)`, measured unique across all 951 records on 2026-08-13.
It is not the ticket reference: a payout and its purchase share a reference,
and 122 distinct references cover 149 sampled payout messages.

### 4.5 Catching up on what arrived while the PC was off

Live signals cover everything that happens while the watcher runs. The snapshot
covers each thread's newest message, which is the whole story for a thread that
received one lottery SMS while it did not. Two cases are left over: a thread
that received **two**, and a thread whose latest message is now an ordinary
bank notice sitting on top of a ticket — invisible to the snapshot, because
`activeConversations()` reports only the newest (LOTTO-0001 §4.1's caveat,
which this design does not repeal).

Both are closed by asking: `requestConversation(thread, 0, 200)`, whose answer
arrives as `conversationUpdated` signals. **Which threads get asked is the part
that needs a bound.** 543 of the phone's 2,325 threads match the filter — the
bank sends from many shortcodes — so asking all of them for 200 messages each
would move a hundred thousand messages on every start.

`pull_targets()` asks only for threads that have **moved**: whose newest
message is newer than the newest date the dump already holds, and which either
match the filter now or are remembered as having matched before. If nothing
moved, nothing is asked, which is the normal case. Measured on the live run of
2026-08-13: 2,325 threads, **one** asked for history.

The remembered set lives in `sms_threads.json` beside the dump — 543 thread ids
after the first full run, and no message content. It is gitignored anyway: it
is a by-product of one phone and means nothing on another.

**A corrupt or missing file reads as the empty set, and the cost is not merely
a slower run — say what it is.** With no remembered set, `pull_targets()` keeps
only the threads that match *now*, so the one case the set exists for — a
ticket sitting under a newer non-matching message — is not asked for and cannot
be seen by the snapshot either. **Nor does it heal**: `consume()` re-adds a
thread only on a message that matches, which that thread by definition no
longer has. Those tickets are then reachable only over the cable, until another
lottery SMS arrives in the same thread and re-adds it.

The file is still never a reason to *stop*: reading it must not raise, which is
the rule `supervise.read_settings()` follows. But "it degrades quietly" was the
wrong description, and a degradation this specific is a candidate for a visible
warning rather than a silent fallback — recorded here, not built, because it
was found by review after the code shipped.

### 4.6 A second child, reaped like the first

`supervise.SmsWatch` owns `watch_sms.py` with the same spawn-and-reap contract
`Supervisor` has for `serve.py`, in the same Qt-free module so the lifecycle
stays checkable from a headless script — but with no token and no port, because
this child talks to the phone and never to us. `cwd=HERE` for the reason
`Supervisor.start()` gives: the dump and the thread state are resolved relative
to the working directory, and an autostarted session's cwd is not the
repository.

The command is injectable (`SmsWatch(command=...)`) for one reason, stated at
its site: INV-36's case must drive spawn-and-reap **without running the real
watcher**, which would talk to the phone and append to the real dump. A
verifier with a side effect on live data is not one.

`tray.py` starts it after the tray exists, stops it in `quit()` and on
`aboutToQuit` — the logout path, which is the commonest way an orphan is made.

### 4.7 What the user sees

Two things, and the first is not optional.

**A watcher that cannot run says so.** `died_early()` waits up to three seconds
for the child to fall over on its own imports (dbus-python absent, KDE Connect
not running), off the GUI thread, and the tray raises a notification naming the
cost: new tickets will not arrive on their own, import over the cable meanwhile.
Silence here is this project's cardinal failure arriving by a new road — *no
new tickets collected* looks exactly like *no new tickets won*.

**A ticket that arrives is scored.** The tray's existing five-second timer
compares the dump's size against what it was; `watch_sms.py` only ever appends,
so a bigger file is new records and nothing else. On growth the tray notifies
and triggers the refresh it already has. A shrunk file is an adb re-pull
rewriting the dump — it re-baselines silently rather than announcing an arrival
that did not happen. **When the server is stopped**, the notification says to
use *Refresh results now* instead of claiming a refresh is running.

**The check runs inside `sync()`, after its `if self.busy: return`**, so an
arrival during a long refresh is not announced as it lands: it is noticed on
the first tick after that action finishes, and announced then. That is the
behaviour, and it is acceptable — five seconds late on a message the user has
not looked for yet. The `self.busy` half of `check_new_tickets()`'s own guard
is therefore unreachable through the only caller it has; it is kept as a guard
against a second caller, not as a path that runs today. An earlier draft of
this section claimed a busy run produced the *Refresh results now* wording,
which it cannot.

## 5. Invariants

- **INV-32** — `watch_sms.wanted()` accepts exactly the bodies LOTTO-0001
  §4.1's adb `WHERE` clause accepts, case-insensitivity included. Neither path
  may write to the dump what the other would have refused.
- **INV-33** — Every record `watch_sms.format_row()` writes reads back through
  `tickets.rows()` as exactly one record, with its date intact and its body
  unchanged but for the deliberate header guard.
- **INV-34** — A message the dump already carries is never appended a second
  time, keyed on `(date_ms, body)`; a message it does not carry, and that reads
  back through `tickets.rows()`, always is; a body the filter excludes never
  is. The read-back clause is not a hedge — §4.3 drops an unparseable record at
  the door on purpose, and an invariant demanding it be written would undo
  that.
- **INV-35** — The thread state that makes catch-up possible round-trips, and
  reads as the empty set when missing or corrupt rather than raising. History
  is asked for exactly the threads that have moved since the dump's newest
  record — never for every matching thread, and never for none of them when a
  known thread's newest message has stopped matching.
- **INV-36** — The watcher child is spawned, observed and reaped like the
  server; and a watcher that cannot start is reported in words that name what
  is lost, never silently.
- **INV-37** — A dump that grew is announced, and re-scored **when the server
  is running**; when it is not, the notice names *Refresh results now* instead
  of claiming a refresh that is not happening. A dump that shrank is not
  announced. The page must never gain a ticket the user is not told about, nor
  be told about one it did not gain.

## 6. Failure modes

| What goes wrong | What happens | Why that is the right answer |
|---|---|---|
| `dbus-python` or KDE Connect absent | watcher exits non-zero naming the cable; tray notifies | the alternative is a page that quietly stops growing |
| phone off, asleep or off the network | no signals; nothing written; catch-up on the next start | the dump is append-only, so a gap closes itself later |
| KDE Connect restarts | signals stop arriving; watcher stays alive on a dead bus | accepted — see §9; the tray's growth check will simply see nothing |
| two watchers running | usually the second writes nothing — but see below | **not guaranteed**, and nothing prevents it |
| an SMS body carrying a record header | prefixed with a space, one record | §4.3 |
| the dump is deleted | catch-up rewrites what the phone still holds | not a recovery plan; adb remains the recovery plan |

**The two-watchers row is a warning, not a guarantee, and the earlier draft had
it backwards.** `append_new()` reads the dump into a `seen` set and then
appends, with no lock, so two watchers that both read before either writes will
both append the same message — and their row indices collide too, since each
takes `max(existing) + 1`. The de-duplication key is checked against the file's
*contents at read time*, which is exactly why it cannot serialise two writers.
The case is reachable: `SmsWatch.start()` guards only against its own second
spawn, and `python3 watch_sms.py` is documented as a hand invocation. **Run
one.** A single-instance guard (a lockfile or an abstract socket) is the fix if
this ever bites; it is not built, and this row is what stops the omission being
read as a decision that it is safe.

## 7. Tests

`tools/verify_watch.py`, seven cases, exit code is the signal. It needs no phone,
no KDE Connect and no `dbus-python`, which is why it runs in `local-CI.sh`'s
**CI lane** rather than the local-only one. It reads the real dump and writes
only to temporary files.

**INV-32 is checked against SQLite, not against a second transcription.** The
clause is copied from LOTTO-0001 §4.1 into `WHERE`, but the half most likely to
be got wrong is not the words — it is `LIKE`'s case-insensitivity against
Python's case-sensitive `in`. Asking the engine adb asks is the only way that
half is checked at all; a hand-written Python equivalent would agree with its
own mistake, which is the lesson `tools/verify_pools.py`'s price table carries.

Every case was **observed failing** on 2026-08-13, by deliberate defect:
dropping the `vas00` clause (the LOTTO-0030 gap) reddened `filter_matches_adb`;
removing the header guard reddened `round_trip`; removing de-duplication
reddened `no_duplicates` on three counts; a `read_threads` that forgets
reddened `thread_state`; an unbounded catch-up and a catch-up blind to
remembered threads each reddened `catch_up_targets`; a `stop()` that does not
reap reddened `watcher_lifecycle`; and softening the failure message so it no
longer names the cable reddened `absent_dbus_is_named`.

The filter case carries the anti-vacuity floor INV-3 and INV-6 use: two empty
sets agree, so a filter accepting nothing — or everything — fails rather than
passes.

**None of these seven caught the defect §4.1 describes**, and that is worth
recording rather than glossing. Every one of them passed against a watcher
whose discovery could not discover anything, because the defect was not in the
filter, the format, the de-duplication or the lifecycle — it was in a belief
about what a D-Bus signal means, and the only thing that could contradict it
was the phone. What caught it was running the thing and disbelieving a
convenient answer: "0 new" against a phone holding 951 matching messages, and
an empty state file that should have held hundreds.

**Live proof, 2026-08-13.** A `--once` run against the paired phone over Wi-Fi,
with the cable unplugged: 2,325 threads read in 21 seconds, one thread asked
for history, **two new payout SMSes written** (07:03 and 07:04 that morning,
both arriving after the last cable pull on 2026-08-12). The 951 records already
in the dump were left byte-identical, and the `(date, body)` key remained
unique across all 953.

## 8. Alternatives considered (and rejected)

- **Poll `activeConversations()` on a timer, as the only mechanism.** Rejected,
  though the snapshot is read once at start (§4.1): a timer alone means a new
  ticket waits for the next tick, and every reading is possibly partial with
  nothing saying so. The signals are what make an arrival immediate, and the
  stop-growing test is what makes the one snapshot trustworthy.
- **Signals as the only mechanism.** This is what was built first, and §4.1 is
  the record of why it fails: `conversationCreated` fires once per conversation
  per daemon lifetime, so discovery finds nothing on every run but the first.
- **Run adb on a schedule instead.** Still needs the cable. It is the thing
  being removed.
- **An always-on systemd user service.** Offered and declined 2026-08-13: more
  setup, and it collects when nothing is displaying what it collected.
- **De-duplicate on the ticket reference.** Wrong unit — a purchase and its
  payouts share one (§4.4).
- **Let the watcher POST a refresh to the server.** It would need the token,
  which `Supervisor` owns and deliberately does not share. The tray already
  watches the file and already has a refresh; a size comparison is cheaper than
  a second authenticated client.
- **Widen `find_lotto_sms.py` and have it write.** It matches addresses and a
  wider keyword list on purpose. Making the inspection tool the pipeline would
  import that width into the dump (§4.2).

## 9. Out of scope

- **Reconnecting to a KDE Connect that restarted.** The watcher holds a D-Bus
  proxy from start-up; if the daemon goes away, signals stop and nothing says
  so. Quitting and reopening the tray fixes it. Filed as a rough edge rather
  than solved, because the failure is visible the moment a ticket is bought and
  the page does not move.
- **Windows.** `dbus-python` and KDE Connect are Linux-only; LOTTO-0015 §
  already names the fetcher as the entry point that cannot cross.
- **Payout reconciliation.** LOTTO-0029 / LOTTO-0010 own it. The decision taken
  2026-08-13 — a disagreement between a payout SMS and the computed score is
  flagged loudly rather than resolved in the SMS's favour — is recorded there,
  not built here.

## 10. Resource cost

One extra Python process, idle in a GLib main loop. Startup reads the phone's
conversation list once — 21 seconds against a warm KDE Connect daemon, up to
about twelve minutes against a cold one that must fill it first (§4.1) — plus
one 200-message history request per thread that has moved, usually zero or one
(§4.5). Steady state is one D-Bus signal per incoming message and one 210 KB
file read per accepted message. The tray's growth check is two integers every
five seconds on a timer that already existed.

**The dominant startup cost is not the D-Bus traffic, it is the dump.**
`snapshot()` calls `consume()` per entry and `consume()` calls `append_new()`,
which re-reads and re-parses the whole file every time — so a catch-up is one
210 KB read and parse **per filter-matching snapshot entry**, 543 of them on
this phone, on every start rather than only the first. That is roughly 114 MB
of reads inside the measured 21 seconds, which is why it was not noticed. It is
affordable and it is not defended: batching the snapshot into a single
`append_new()` call would make it one read, and the only reason it is written
per message is that the same function serves the signal path, where one message
is all there is.

## 11. What checks this

| Invariant | Checked by |
|---|---|
| INV-32 | `tools/verify_watch.py::filter_matches_adb` (against SQLite) |
| INV-33 | `tools/verify_watch.py::round_trip` |
| INV-34 | `tools/verify_watch.py::no_duplicates` (against real dump records) |
| INV-35 | `tools/verify_watch.py::thread_state`, `::catch_up_targets` |
| INV-36 | `tools/verify_watch.py::watcher_lifecycle`, `::absent_dbus_is_named` — **watcher half only**, see below |
| INV-37 | not checked by a case — see below |

**Two gaps, both for the same reason, and neither is a decision.**

**INV-36's tray half is unchecked.** `absent_dbus_is_named` checks that
`watch_sms.py`'s own exit message names the cable; the notification §4.7
promises — `tray.main()`'s `watcher_checked` — is checked by nothing. The row
above lists both cases against INV-36 and that is honest about the *watcher*
half only.

**INV-37 is stated and not checked**, and that is a gap rather than a decision.

Both gaps are the same shape: every unchecked half lives in `tray.py` and needs
a QSystemTrayIcon, and the one tray case that exists
(`tools/verify_page.py::tray_headless_when_managed`) runs the managed path
precisely because it constructs no Qt object. Closing either would mean the
first Qt-constructing case in the project. What is exercised instead is
reality: the growth path runs on every real ticket, and the watcher-failure
message was observed by running the watcher with `dbus` made unimportable.
Recorded here so neither is mistaken for covered.

## 12. Cross-doc impact

- **`docs/specs/LOTTO-0001-lottery-ticket-tracker.md` §4.1** — its closing
  paragraph said only adb feeds the pipeline and named this item as what would
  change that. Amended in the same commit to point here. The table above it now
  has a second writing path; the `find_lotto_sms.py` row stays "inspection
  only", which is still true.
- **`CLAUDE.md`** — the commands list gains `watch_sms.py`, the verifier list
  gains `tools/verify_watch.py`, and the architecture diagram gains the second
  arrow into `lotto_sms_raw.txt`.
- **`ROADMAP.md`** — LOTTO-0003 flips to shipped.
- **`CHANGELOG.md`** — one entry under Added.
- **`README.md`** — not amended; it describes what to run, and the answer for a
  user is still `tray.py`.

## 13. Cold-eyes loop log

| Loop | Date | Reviewer | Findings | Outcome |
|------|------|----------|----------|---------|
| 1 | 2026-08-13 | 2 cold lanes + `check-doc-facts` (by hand) | **Q1 5 · Q2 2 · Q3 0 · Q4 0** (verified 7 / dismissed 0), plus 1 mechanical | All fixed. Both lanes read the code and neither accepted the document's account of it. Q1: the state-file fallback claimed its only cost was slowness, where losing it makes a ticket under a newer non-matching message unreachable and the set does not self-heal; the two-watchers row claimed the second writer is harmless *because* de-duplication is against the file rather than a lock, which is the reason it is **not** harmless; §4.7 promised a notification the code cannot emit, its `busy` branch being unreachable through `sync()`; §10 omitted the dominant startup cost (one full dump read per matching snapshot entry, ~543 on this phone); §11 presented INV-36 as covered when only its watcher half is. Q2: INV-37 made re-scoring unconditional where the code guards on the server running, and INV-34's "always is" contradicted §4.3's drop-at-the-door. Mechanical: one path cited without its `tools/` prefix. Collateral: the same false state-file claim in `watch_sms.py`'s comment, and a ROADMAP line counting one gap where there are two. Two code changes were surfaced rather than applied — a single-instance guard, and batching the snapshot into one `append_new()`. |
