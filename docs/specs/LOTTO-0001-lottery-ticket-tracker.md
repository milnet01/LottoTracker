# LOTTO-0001 — Track lottery tickets from SMS and score them against real draws

**Status:** accepted (2026-08-01).
**Kind:** implement.
**Source:** ROADMAP LOTTO-0001 (user request, 2026-08-01).

Layman: the PC reads the lottery ticket texts your bank sends, remembers
every ticket, and tells you whether any of them won.

[1. Goal](#1-goal) · [2. Problem](#2-problem) ·
[3. Scope decisions](#3-scope-decisions-agreed-with-the-user) ·
[4. Design](#4-design) — [4.1 Getting messages off the phone](#41-getting-messages-off-the-phone),
[4.2 Parsing two SMS eras](#42-parsing-two-sms-eras),
[4.3 Two results sources](#43-two-results-sources),
[4.4 Scoring](#44-scoring) · [5. Invariants](#5-invariants) ·
[6. Failure modes](#6-failure-modes) · [7. Tests](#7-tests) ·
[8. Alternatives](#8-alternatives-considered-and-rejected) ·
[9. Out of scope](#9-out-of-scope) · [10. Resource cost](#10-resource-cost) ·
[11. What checks this](#11-what-checks-this) ·
[12. Cross-doc impact](#12-cross-doc-impact) ·
[13. Cold-eyes loop log](#13-cold-eyes-loop-log)

## 1. Goal

Every lottery ticket Standard Bank has confirmed by SMS is parsed, stored and
scored against the real draw results it covers, so unclaimed winnings surface
before the 365-day claim deadline instead of being discovered by accident.

## 2. Problem

Tickets arrive only as SMS on a Galaxy S21 and are never checked. Three
things make manual checking impractical, and each shapes the design:

1. **Volume.** 558 ticket purchases since 2022-11-09, covering 745 played
   lines once Multiplay boards are expanded. Most tickets run for 10 draws,
   so a single ticket is 10 separate checks per line **per pool it was entered
   in** — a Lotto Plus 2 ticket is 30. Only 132 tickets are checkable
   at all (259 of 1233 entries) — the rest predate the earliest known draw of
   **every** pool they were entered in, which is a per-pool gate and not one
   global cutoff date (§4.4, §9). Of those
   132, 11 are checkable in one pool and not another, because no source
   publishes `daily/1`; LOTTO-0009 scores those on the pools that remain and
   counts in **entries** rather than tickets, since one ticket is entered in
   every tier its price paid for.
   `python3 -c "from tickets import load; ts=load(); print(len(ts), sum(len(t.boards) for t in ts))"` → `558 745`
2. **The SMS format changed.** Sizekhaya replaced Ithuba as licence holder on
   2026-06-01, and the bank's message wording changed with it. Both eras are
   still live in the inbox and must both parse.
3. **No single results source spans the ticket history.** The official feed
   begins at the handover; everything earlier needs a second source.

## 3. Scope decisions (agreed with the user)

- **Free sources only.** The user's instruction was explicit: if the project
  costs money, cancel it. `resultsza.co.za` offers an API at R149/month
  minimum; it is rejected on that ground alone (§8).
- **A local web page** is the eventual UI, chosen by the user over a desktop
  app or CLI — but it is LOTTO-0002. This spec delivers terminal output.
- **Backfill the pre-handover gap** from a third party rather than leaving
  those tickets unchecked — user's decision, 2026-08-01.
- **Read SMS via KDE Connect for *inspecting* new tickets, adb for history.**
  Both were set up; neither is a fallback for the other (§4.1). Only the adb
  path feeds this spec's pipeline — turning the KDE Connect stream into ingest
  is LOTTO-0003 (§9).

## 4. Design

### 4.1 Getting messages off the phone

Three paths, because they solve different problems:

| Path | Module | Use | Filtering happens |
|------|--------|-----|-------------------|
| adb over USB | shell `content query` | bulk history | on the phone |
| KDE Connect over Wi-Fi | `find_lotto_sms.py` | **inspection only** | on the PC |
| KDE Connect over Wi-Fi | `watch_sms.py` | **new messages, unattended** | on the PC |

The third path was added 2026-08-13 (LOTTO-0003) and is specced in
`docs/specs/LOTTO-0003-live-sms-watch.md`. It writes the same dump in the same
format, which is why its filter is this section's `WHERE` clause re-expressed
rather than a second opinion about what a lottery message is — LOTTO-0003
INV-32 checks the two against SQLite. `find_lotto_sms.py` stays inspection
only, and its wider keyword list stays wider.

The adb query filters with a SQL `WHERE` clause executed on the device, so
the inbox at large never crosses to the PC (see the limits below the query):

```bash
adb shell "content query --uri content://sms \
  --projection address:date:body \
  --where \"(body LIKE '%lotto%' OR body LIKE '%powerball%' \
             OR body LIKE '%VAS00%') \
            AND body NOT LIKE '%kWh%' \
            AND body NOT LIKE '%Enter tokens%'\""
```

**The `VAS00` clause is the one that is not obvious, and it was missing until
2026-08-12 (LOTTO-0030).** Filtering on game names alone silently excludes
the payout SMS, whose wording — "The winnings of R*amount* for ticket ref:
VAS00000000000 will be paid in your account…" — names no game anywhere; note
also that `lotto` is not a substring of `lottery`. Every shape the old filter
*did* catch happens to name a game (`Played R… Lotto Plus 2`, `… to VAS…
LOTTO`, `Your lotto transaction was unsuccessful`), which is why the gap held
for so long and why the dump could report "no payout messages exist" when the
phone held 366 of them. The `VAS00` reference is the one term common to every
shape, and it is also `Ticket.ref`, the join key scoring uses — which is what
makes a payout reconcilable at all (LOTTO-0010 / LOTTO-0029).

**The two `NOT LIKE` clauses are the price of that width, and the honest
statement of this filter is narrower than "only lottery messages".** `VAS` is
Standard Bank's *value-added services* platform, not a lottery namespace:
prepaid electricity is bought through it and its messages carry an identically
formatted reference (`VAS` + 11 digits, prefix `00` — measured across all 993
records on 2026-08-13, every shape alike, so the reference cannot discriminate).
Electricity arrives as two SMSes, a `U: <n>kWh` purchase and a token
continuation reading "Enter tokens on SMS 1"; the second carries no `kWh`,
which is why one exclusion is not enough. What remains after both is a handful
of VAS messages that name neither a game nor a utility — `R… purchased for
VAS…`, `R… deposited into Acc. … from VAS…` — and these are deliberately KEPT:
they may be lottery refunds, and if they are not, `tickets.py::parse()` returns
`None` and they are inert. **So the guarantee this section can actually make is
"no message without a lottery-or-VAS marker crosses, and no known utility
message crosses" — not "only lottery messages cross".** Anything relying on the
stronger reading is relying on something that was never true.

KDE Connect cannot filter server-side — `activeConversations()` returns the
newest message of every thread — so `find_lotto_sms.py` matches keywords
locally and calls `requestConversation()` only for threads that hit. Its
keyword list stays narrow for the same reason, and carries `vas00` for the
reason above: one `matches()` drives both thread discovery and the
within-thread filter, so widening the list is what lets an inspection run see
a payout without dumping the rest of the inbox.

**A caveat this path cannot design away:** matching runs against the *newest*
message per thread, so a lottery thread whose latest message is an ordinary
bank SMS is invisible to discovery. Adding `vas00` widens *what counts as a
lottery message*, not *how far back the match looks*, so the limitation stands.
Measured 2026-08-12 across the phone's 2,324 threads: the eight-keyword list
matched 386, the nine-keyword list matches 560, and 149 of the additions are
payouts. This path is inspection only and nothing in the pipeline depends on
it, so the residue is accepted rather than engineered around.

**Reading a count off this API is itself a trap, and it cost a wrong
measurement on the day this section was written.** `requestAllConversationThreads()`
populates `activeConversations()` ASYNCHRONOUSLY with no completion signal, so
an early read returns a partial list that is indistinguishable from a complete
one — a 6-second wait returned 25 threads where the phone has 2,324, which
produced two confident and false conclusions (that discovery matched nothing,
and that `requestConversation()` had stopped delivering). Sample at two
different waits and compare before believing any figure taken from here.

**`find_lotto_sms.py` still prints and writes no file.** `tickets.py::load()`
reads one format (`^Row: N address=…, date=…, body=…`, one record per match,
from `lotto_sms_raw.txt` at the repo root), and until 2026-08-13 only adb wrote
it — this paragraph used to say so, and to name LOTTO-0003 as what would change
it. **LOTTO-0003 shipped**: `watch_sms.py` now writes that format from the KDE
Connect stream, so the dump has two producers and one reader
(`tickets.py::rows()`, which `load()` calls). The caveat about matching against
each thread's newest message survives unchanged and is why that path also asks
for the history of threads that have moved (LOTTO-0003 §4.5).

### 4.2 Parsing two SMS eras

`tickets.py::parse()` accepts both. The distinguishing feature is the date
line, not the header:

```
old   Standard Bank: Played R99.00 Lotto Plus 2 for 1 draw(s)
      Date 01/01/2020 to 01/01/2020
      A: 07 11 19 23 31 44

new   Standard Bank: Played R99.00 Powerball
      Date 01 Jan 2020 (for 10 draws)
      A: 08 14 27 33 41 -07
```

The game name maps to a results pool, and that mapping cannot be derived from
anything else *in the SMS text* — which is why the table below is load-bearing.
**Amended by LOTTO-0009: it maps an SMS to the one pool its name states, which
is the *top* tier only, and it is no longer the authority on `winPoolId` /
`plusFlag`. The ticket price is.** A PLUS game cannot be bought alone, so a
ticket is entered in every tier below its top one as well, and those tiers come
from the price — see `docs/specs/LOTTO-0009-entered-pools.md` §4.2–§4.3.
`tickets.py::GAME_MAP` is still exactly this table, and is still the fallback
`parse()` uses when a price matches no tier, but `Ticket.pools` is what scoring
iterates and `Ticket.plus_flag` / `Ticket.pool_id` are now the top tier the
**price** paid for, which differs from the name on 5 of the 558 tickets
(2026-08-01). An implementer who builds name-authoritative scoring from the
table alone reproduces the bug LOTTO-0009 removed.

| SMS game name | game | plusFlag | winPoolId |
|---|---|---|---|
| `Lotto`, `Lotto game` | lotto | 0 | 100 |
| `Lotto Plus 1` | lotto | 1 | 101 |
| `Lotto Plus 2` | lotto | 2 | 102 |
| `Powerball` | powerball | 0 | 100 |
| `Powerball Plus` | powerball | 1 | 101 |
| `Daily Lotto` | daily | 0 | 100 |
| `Daily Lotto Plus` | daily | 1 | 101 — **no source carries this pool** |

`Daily Lotto Plus` appears on 11 tickets and has no pool in either results
source. It resolves to an always-empty pool so those **entries** report as
uncheckable; aliasing it onto plain Daily Lotto would score them against a
different game. Since LOTTO-0009 the tickets themselves are not uncheckable —
their `daily/0` entry is scored, and they are reported as *partly*
uncheckable. API `gameId`s are LOTTO 11101, POWERBALL 11201,
DAILY_LOTTO 11001 — observed constants, taken from the site's own bundle.

Two traps, both of which produce plausible-looking wrong answers:

- **The PowerBall number.** New-format messages prefix it with `-`; old-format
  ones do not, leaving it indistinguishable from a main number by shape. It is
  always the final number on the line, in both eras. Locked by INV-1.
- **Multiplay.** A Lotto board with seven numbers is not one line with an
  extra pick; it is seven separate paid lines, one per 6-number combination,
  each winning independently. Locked by INV-2. **After expansion
  `Ticket.boards` holds one entry per scored *line*, not per lettered board**
  — which is why §2 counts 745 lines out of it and §4.4's per-board loop is a
  per-line loop. The two words name the same object everywhere below.

### 4.3 Two results sources

`history.py::all_draws()` merges them into one shape per draw:

```python
{"date": "YYYY-MM-DD", "main": [int], "special": int|None,
 "issue": int|None, "source": "api"|"archive"}
```

| Source | Covers | Has payouts | Module |
|--------|--------|-------------|--------|
| Sizekhaya JSON API | 2026-06-01 → | yes, per division | `results.py` |
| za.national-lottery.com | `backfill.FIRST_YEAR`-01-01 → | only per-draw pages | `backfill.py` |

Three conventions this project depends on, none of them derivable from the
shape above:

- **The special ball is last.** The API's `winNumList` places the bonus
  (Lotto) or PowerBall last; the archive instead derives the role from each
  ball's CSS class. `history.py::all_draws()` normalises both to `special`.
  Drawn order does not imply this — it is an observed contract of the feed.
- **The API pages newest-first.** `results.py::draws()` asks for
  `pageNum: 1` and returns the list verbatim, and
  `check.py::paying_combinations()` takes `rows[0]` as *the pool's most recent
  draw* with no sort anywhere between them. Same class of assumption as the
  special ball — observed, not promised — and it is what makes the paying set,
  and therefore the `division` name on every win in both eras, current rather
  than arbitrary. A feed that started paging oldest-first would build the gate
  from a 2026-06 draw and stay silent about it.
- **Money units differ by source.** The API reports cents; archive payout
  pages report rands. Every amount leaving `check.py::amount()` is rands.

**The API names its pools in prose, and the mapping is load-bearing in exactly
the way §4.2's SMS table is.** One `issueWinPoolInfoPageQuery` response carries
every pool of a game, so `all_draws()` selects one by comparing
`r["winPoolName"]` against `history.py::POOL_NAMES` case-insensitively. Those
strings are not derivable from `(game, plus_flag)` — two of them are the June
2026 rebrand names (§4.4), not the names the SMS or this document uses:

| game, plusFlag | API `winPoolName` |
|---|---|
| lotto, 0 | `LOTTO` |
| lotto, 1 | `LOTTO PLUS 1` |
| lotto, 2 | `LOTTO 5 MAX` — **not** "Lotto Plus 2" |
| powerball, 0 | `PowerBall` |
| powerball, 1 | `PowerBall XTRA` — **not** "PowerBall Plus" |
| daily, 0 | `DAILY LOTTO` |
| daily, 1 | `DAILY LOTTO PLUS` — no source publishes it (§4.2) |

An implementer who guesses these gets **zero API draws for `lotto/2` and
`powerball/1`** with no error — the pool simply never matches, which is the
cardinal failure one layer below scoring. The seven rows are also what INV-26's
ceiling of six live pools counts.

The API is unauthenticated and needs no key. Endpoints were found by reading
the site's own JavaScript bundle; they are what its results page calls.

Where both cover a draw the API wins, though in practice they agree — see
INV-3.

### 4.4 Scoring

`check.py::check()` walks every ticket × **pool it was entered in** × board ×
covered draw (the pool level added by LOTTO-0009 §4.5). A ticket covers the
first N draws on or after its start date, taken from real draw data rather
than a computed calendar, so a cancelled or moved draw cannot shift the
window (INV-6).

`check()` returns one dict per winning line, oldest first. That shape is a
contract, not an internal detail: `serve.py` reads it key by key into the page
model, and **drops `amount` as it adds `amount_cents`** rather than spreading
the dict through — LOTTO-0002 §4.1 specifies that deletion and calls it
load-bearing against a 100× money error. A renamed key therefore breaks the
page rather than this module.

```python
{"ref": str, "game": str, "plus_flag": int, "pool_id": int,
 "line": str,               # the board line: "A", or "A1".."A7" on Multiplay
 "date": "YYYY-MM-DD",
 "division": str,           # a winLevelName - but always the API's, see below
 "matched": str,            # site_label() grammar - "3 + Bonus", never "MATCH 3"
 "amount": float,           # RANDS, not cents (§4.3)
 "source": "api" | "archive",
 "expired": bool, "expires": "YYYY-MM-DD"}
```

**`division` does not come from the win's own draw, and on an archive-era win
it does not come from the win's own era.** `check()` sets it from
`paying_combinations()`, which reads the pool's *newest API draw* (§4.3), so an
archive win carries a 2026 division name. That is the majority case, not a
corner: 69 of the 86 wins measured before LOTTO-0027 were archive-era. `source`
is the field that says where the money came from; `division` says only which
*current* division the line's match qualifies for. A second, narrower
disagreement rides on `amount()`'s archive plain-tier fallback, described at
the end of this section — `division` and `matched`
can both name the bonus tier while `amount` was read from the plain row.
`page.py` renders `division` and `matched` side by side (LOTTO-0002 §4.1), so
the pair must not be read as one statement about one row.

**An entry starting before the earliest known draw for its pool is not
scorable and must be excluded, never truncated.** `history.py::scorable()`
gates this and `covered()` returns empty for such an entry. Both take the pool
as an argument rather than reading it off the ticket, because a ticket can be
checkable in one pool and not another. Without the gate a ticket older than the
record silently takes the first N draws the record *does* hold — real draws,
wrong ones — and every count-based check still reports it as correct.
**Since LOTTO-0006 (2026-08-31) that window is empty**: the archive reaches back
to the year of the earliest purchase SMS, so no entry predates its pool's data.
Every uncheckable entry today is uncheckable for the *other* reason — `daily/1`,
which no source publishes (§4.2). **The gate is not thereby spent**, and neither
is the split: the window reopens the moment an older ticket is imported, which
is precisely the failure this exists to make safe. The two reasons are counted
separately and must stay that way: merging them is how "nobody publishes this"
starts reading as "the data does not go back far enough" — and with one of them
now usually zero, a merged count would read as a clean bill of health. `check.py` reports
both as uncheckable rather than as losses, at entry granularity
(LOTTO-0009 §4.6).

**One set, three words, and they are the same set:** an entry is *uncheckable*
(the report's word, `check.py`) exactly when `history.py::scorable()` is false
for it, which `tools/verify_coverage.py` prints as *unscorable*. Nothing means
one and not the others.

Prize expiry uses `check.py::CLAIM_DAYS = 365`, the SA claim deadline. A win
older than that is counted in the lifetime total but not listed individually,
and never in the claimable total.

Prize divisions are never hardcoded. For API draws they come from
`getIssueDrawResultDetail`; for archive draws from that draw's payout page.
`check.py::paying_combinations()` reads the paying set from a live draw
**per pool**, not per game - Lotto 5 Max and PowerBall XTRA do not share the
base pool's divisions, and one lookup applied to all of them drops wins whose
division exists only in the pool they were won in.

Both lookups join on an exact string this project constructs, so the grammar
is part of the contract — and the two sources do not share one grammar:

| | API (`matches`, uppercased and stripped) | archive payout table (column 2) |
|---|---|---|
| plain | `MATCH 3` | `3` |
| Lotto + bonus | `MATCH 3 + BONUS` | `3 + Bonus` |
| PowerBall + PB | `MATCH 3 + POWERBALL` | `3 + PowerBall` |
| PowerBall, no mains | `MATCH POWERBALL` | `0 + PowerBall` |

**Transcribed from the live feed on 2026-08-03, not inferred**, after this
table's previous API column was found wrong on both PowerBall rows: the feed
spells the PowerBall out where this document recorded an abbreviation, and its
PowerBall-only division carries no digit and no `+` at all, where the
archive's is `0 + PowerBall`. `check.py::api_label()` built both wrong forms,
so `check()`'s pay gate (`if label not in pays: continue`) dropped **53
PowerBall wins as losses** — the cardinal rule
broken by shipped code, and the failure LOTTO-0026 was filed against arriving
before its guard did (LOTTO-0027, 2026-08-03).

The rule that catches it is **directional** — every division the source
publishes must be *reachable* by a label this project can build, and the
converse must not be asserted. **INV-26 owns that rule**, including its
direction, its domain and why the converse is false; it is stated in full
there.
`check.py::paying_combinations()` raises on an unreachable division at run time,
and `tools/verify_pools.py` checks the same direction ahead of a run over every
pool the dump reaches; INV-26 states both halves in full.

**Whether a line paid at all is gated by the *current* division set, in both
eras** — `check.py::check()` tests the match label against
`paying_combinations()` before `amount()` is reached. Only the amount is
era-specific. A pre-handover division with no current equivalent is therefore
dropped, not priced at zero. **A drop is silent, and it is the one place this
document leaves the cardinal rule in its "omission" form with no planned
repair**: a genuine
win in a retired division leaves no row, no count and no diagnostic, and is
indistinguishable from a losing line. It is not unreportable by construction —
the draw's *own* division set would separate the two cases — so read §11's
`nothing` here as work not yet done rather than as a limit of the sources.
Tracked by LOTTO-0023.

Pre-handover draws did not share a single division structure: some list a
bottom tier of `2 + Bonus`, others a plain `2`. When the bonus-qualified
label is absent from a payout table, `check.py::amount()` falls back to the
plain match tier, which is the one that paid.
**The fallback is not confined to that bottom tier**, and reading it as the
narrow repair it was written for understates its reach: the code tries
`str(hits)` for *any* `hits` and on both games that carry a special ball, so a
payout page missing its
`3 + PowerBall` row prices that win at the plain `3` amount instead of raising
under INV-22. That is a real price for a real division rather than a zero, so
it does not breach the cardinal rule — but it is a *different* division's
price, and nothing distinguishes the intended bottom-tier case from the rest
from inside.

`tickets.py` parses, and since LOTTO-0009 also derives which pools a ticket was
entered in from its price - `check.py` is still the only scoring path.

## 5. Invariants

Invariant ids are **project-wide, not per document**, which is why this section
runs INV-1 to INV-6 and then jumps. The ids in between are owned as follows,
and the ranges are not contiguous per document — INV-15 to INV-18 were moved
out of LOTTO-0014, and INV-19 to INV-20 out of it as well; each *moved*
invariant left a tombstone in LOTTO-0014 naming its new owner:

| Range | Owner |
|-------|-------|
| INV-7 – INV-11 | `docs/specs/LOTTO-0009-entered-pools.md` |
| INV-12 – INV-14, INV-21 | `docs/specs/LOTTO-0014-http-surface-and-security.md` |
| INV-15 – INV-18, INV-24 | `docs/specs/LOTTO-0002-local-web-page.md` |
| INV-19 – INV-20, INV-23, INV-25 | `docs/specs/LOTTO-0013-tray-and-supervisor.md` |

This document owns INV-1 to INV-6; INV-22, which LOTTO-0007(a) added on
2026-08-02 after the specs above had taken their ranges; and INV-26, added by
LOTTO-0026 on 2026-08-03. A new invariant here takes the next free number in
the project, not the next free number in this file.

- **INV-1** — For PowerBall tickets the final number on a board line is the
  PowerBall, never a main number, in both SMS eras.
  *Test:* `python3 -c "from tickets import parse; t=parse('Standard Bank: Played R99.00 Powerball Plus for 1 draw(s)\nDate 01/01/2020 to 01/01/2020\nA: 06 12 25 38 47 05\nRef:VAS00000000000.'); print(t.boards)"` → `[('A', [6, 12, 25, 38, 47], 5)]`
  *Test (new era):* `python3 -c "from tickets import parse; t=parse('Standard Bank: Played R99.00 Powerball\nDate 01 Jan 2020 (for 10 draws)\nA: 08 14 27 33 41 -07\nRef:VAS00000000000.'); print(t.boards)"` → `[('A', [8, 14, 27, 33, 41], 7)]`
  *Breaks when:* a parser change treats the six numbers as all-main, making
  every PowerBall ticket score one match too many and never match the PB.

- **INV-2** — A Lotto board carrying more than six numbers expands to one
  line per 6-number combination, each scored independently.
  *Test:* `python3 -c "from tickets import parse; t=parse('Standard Bank: Played R99.00 Lotto game\nDate 01 Jan 2020 (for 10 draws)\nA: 03 09 16 24 37 42 50\nRef:VAS00000000000.'); print(len(t.boards))"` → `7`
  *Breaks when:* the seven picks are scored as a single line, undercounting
  winnings — measured at R107.50 against a correct R392.20 on one ticket.

- **INV-3** — Where the two sources cover the same draw they report the same
  numbers, so merging them cannot introduce a contradiction.
  *Test:* `python3 tools/verify_sources.py` → `148 overlapping draws, 148 agree, 0 disagree`
  *Breaks when:* either source renames a pool, so it contributes no overlap —
  **caught by a per-pool zero-overlap floor, which is part of the check and not
  an optional extra**: every pool must contribute at least one overlapping
  draw, and the run exits non-zero if any does not. Without that floor a
  renamed pool contributes nothing and the run still passes on the strength of
  the other five, which is the regression the floor exists to catch. `daily:1`
  (Daily Lotto Plus) is exempt via `EXPECTED_EMPTY` — no source publishes it,
  so zero overlap is its correct state, not rot. The comparison is
  order-insensitive by design — the archive sorts ascending, the API preserves
  drawn order.

- **INV-4** — No file containing real SMS content is ever tracked by git.
  *Test:* `python3 tools/verify_privacy.py` → `33 tracked files, 0 leak(s) [content+pattern]` (2026-08-03; the file count grows, the leak count must not)
  *Breaks when:* a dump is committed under a name `.gitignore` does not
  match, or real message content is pasted into prose as an "example". Two
  leaks got past weaker forms of this check, one per review loop, and the
  test is shaped by both: a filename check only restates `.gitignore` and
  passes on `messages_backup.txt`; a `Ref:VAS…` check misses pasted program
  output, which drops the prefix; and a reference-only check misses a
  verbatim message whose reference was scrubbed but whose numbers, date and
  amount identify the ticket anyway. `tools/verify_privacy.py` therefore
  compares tracked files against the dump itself, not against a guessed
  pattern, and falls back to pattern-only on a clone with no dump. Sample
  references must be the sentinel `VAS00000000000`. Red-tested 2026-08-01 by
  pasting a real board line into `README.md`: 1 leak, exit 1.

- **INV-5** — Which match combinations pay is read from the results source at
  runtime, never hardcoded in this project.
  *Test:* `grep -nE '"MATCH [0-9]' *.py | wc -l` → `0`
  **The glob is the production modules only.** Widening it to `tools/` returns
  hits against entirely correct code, where the obvious repair deletes one of
  INV-22's four probes. **No count is given here on purpose** — most of those
  hits are *prose*, comments in `verify_pools.py` quoting the labels LOTTO-0027
  got wrong, so the number moves whenever someone edits a comment and any
  figure written down rots by the next commit. (It has already rotted once, on
  the commit that fixed those very comments.) That the hits are mostly prose is
  the durable point, and on its own it is enough to make the wider glob
  useless: no rename-catching grep can tell a quoted label from a built one.
  The two real literals are not the same kind either. `verify_pools.py`'s is a
  genuine test double,
  standing in for the very feed this invariant says the project must read at
  runtime; `verify_page.py`'s sits in a page-model fixture's `matched` field,
  which production fills from `site_label()` in the *site* grammar (`3 + Bonus`),
  so an API-grammar label there is unrepresentative of any real model rather
  than a hardcoded division.
  *Breaks when:* someone inlines an SA prize table; the game's divisions
  changed at the 2026-06-01 handover and would silently rot again. Catches a
  hardcoded division *label* only — it cannot see a hardcoded prize amount,
  which nothing checks (§11).

- **INV-6** — An entry is scored against the first N drawn results on or
  after its ticket's start date, where N is the draw count in its SMS.
  *Test:* `python3 tools/verify_coverage.py` → `558 tickets, 1233 entries, 974 unscorable (excluded), 0 with wrong draw coverage` (repo root, after `backfill.py`)
  **The unit is the entry, not the ticket** (LOTTO-0009 §4.5): `covered()`
  takes the pool, and each of a ticket's entries is checked separately, since
  one can reach back far enough to be scorable while another does not. The
  figures above were measured against the shipped implementation on
  2026-08-01, not predicted.
  *Breaks when:* an entry predating all draw data is truncated onto later
  draws instead of excluded, or the window is computed from a weekday
  calendar so a skipped draw shifts every later match. The check asserts
  start-alignment and contiguity against the draw records directly; asserting
  `len(covered(t, pf)) == t.ndraws` is a tautology over the function's own
  slice and passed while 426 tickets were mis-scored. The check must **not**
  import `history.scorable()` — the predicate under test — or it agrees with
  the bug; it recomputes the comparison itself. Red-tested 2026-08-01 by
  regressing `scorable()` to `bool(rows)`: 426 wrong, exit 1. It also fails
  if over 90% of **entries** are unscorable, which is what a missing
  `archive_results.json` looks like.

- **INV-22** — A win whose prize cannot be looked up **raises**; it is never
  priced at R0.00. Added 2026-08-02 by LOTTO-0007(a).
  *Test:* `python3 tools/verify_pools.py` (repo root, after `backfill.py`) →
  `unpriceable-win guard: 4 blind-lookup probes, 0 mispriced`
  The trailing count spans **five** checks, not the four the line names: the
  converse below shares the counter, so a guard that broke it also reports here.
  **`check.py::amount()` has no "did not win" answer to give**, and that is the
  whole basis of this invariant. `check()` calls it only after the combination
  matched a paying division (`if label not in pays: continue`), so every call
  prices a line already known to have won. An empty or unrecognised division
  table therefore means *the source could not be read*, and returning `0.0` for
  it puts a figure on the page and in the terminal that is indistinguishable
  from a real losing line — the project's cardinal failure on the money path
  itself. `paying_combinations()` already raises for exactly this reason; this
  extends the same rule to the pricing step, on both the API and archive
  branches.
  **A division the source *does* carry and states as zero still returns
  `0.0`**, because that is an answer rather than a gap. The invariant
  distinguishes the two, and the guard asserts both directions.
  *Breaks when:* the archive payout page changes markup so `payouts()` parses
  to `{}`, or renames the division column it keys on; the API returns an empty
  or partial division table for one draw; or a future edit "simplifies" either
  branch back to a `.get(..., 0.0)` default. **An API-side rename of the
  `MATCH n` grammar is not one of them** — `paying_combinations()` reads its
  keys from the same feed, so `check()`'s gate drops every line before
  `amount()` is reached. That case belongs to **INV-26**, and §11's
  label-grammar row attributes it there rather than here; it read **nothing**
  until INV-26 was added on 2026-08-03. Only the archive branch's labels are
  ungated, because they
  are matched against a scraped payout table rather than against the gate's
  API-derived set. The one API case that *does* reach here is a grammar that
  differs between draws: the gate is built from the pool's newest draw and
  `amount()` looks up the draw being priced, so a rename applied to recent
  draws only lets a label pass the gate and then miss — which is the partial
  table above, and raising is the intended answer.
  Measured 2026-08-02 before the change: 86 wins, 69 of them archive-era, **0
  priced at R0.00**, and all 67 distinct archive draws parsed — so real data
  cannot exercise this and the guard is driven by doubles. Figures after the
  change are identical (86 wins, R2,651.60, 62 claimable lines), which is the
  point: it is a latent-defect guard, not a repricing. **All three figures are
  pre-LOTTO-0027**, which on 2026-08-03 restored 53 PowerBall wins the pay gate
  had been dropping (§4.4); they are this guard's before/after pair, not
  current totals. Red-tested the same day
  by reverting the archive branch to `return 0.0` → 2 probes mispriced, exit 1.

- **INV-26** — Every division the pool's newest draw publishes is
  **reachable**: some `(hits, special)` pair in the domain below makes
  `check.py::api_label()` return exactly that label. A published division no
  label can equal means the feed's grammar moved. Added 2026-08-03 by
  LOTTO-0026; the number is the next free one project-wide, not the next free
  one in this file (§5's opening paragraph).
  **The unit is the newest draw, not the pool's history**, in both halves of
  the invariant: `paying_combinations()` reads `rows[0]` and nothing else, so
  the reachable set and the set being checked are the same one table. A
  division retired before that draw is outside this invariant entirely — it is
  §4.4's silent-drop case, and INV-31 below is what covers it.
  *Test:* `python3 tools/verify_pools.py` (repo root, after `backfill.py`) →
  `division-label reach: 6 live pools, 0 unreachable divisions, 0 vacuous`
  (2026-08-03) for the sweep, and
  `unnameable-division guard: 3 probes, 0 unguarded` (2026-08-04) for the
  raise. Six is also the **ceiling**: `history.py::POOL_NAMES` holds
  seven pools and `daily/1` can never pass `reaches()`, so unlike every other
  count in this document the pool count cannot grow — it can only fall, and
  falling is what the floor below exists to catch.
  **The floor is part of the check, as it is for INV-3 and INV-6.** The pool
  set is derived from the tickets that `reaches()` rather than listed, so a
  partial archive silently shrinks what gets checked, and a pool whose division
  table parsed to empty passes vacuously — every division in an empty set is
  reachable. The check therefore fails on zero live pools and on any live pool
  whose division set is empty. Without that, §7's demotion of the `6 live
  pools` count to a non-asserted figure would leave nothing asserting the check
  ran at all.
  **The invariant is asserted twice, and the two halves are not
  interchangeable.** `check.py::paying_combinations()` inspects the division
  table it has just built and raises on any label outside
  `check.py::buildable_labels()`, so a grammar move is caught inside the run
  that would otherwise have mis-scored it, for whatever pool that run touches
  and whether or not anyone ran a verifier first. `tools/verify_pools.py`
  sweeps ahead of a run instead, which names the pool and the offending label
  rather than aborting — but only over the pools the dump reaches, and only
  when someone runs it. Shipped 2026-08-04 as LOTTO-0026 step 2.
  **The raise aborts the run**, like the no-recent-draw
  raise beside it and for the same reason: nothing catches `RuntimeError`, a
  grammar that moved for one pool has almost certainly moved for its siblings,
  and a run that pressed on would report a partial win list indistinguishable
  from a complete one.
  **The domain is bounded, and the bound is part of the contract** — an
  unbounded sweep weakens the guard silently while too narrow a one raises on
  healthy pools. `hits` runs `0` to the pool's main-ball count (Lotto 6,
  PowerBall 5, Daily Lotto 5) and `special` is tried both ways only for Lotto
  and PowerBall: `check.py::match()` returns `special=False` unconditionally
  for Daily Lotto, so `api_label("daily", n, True)` is unreachable in
  production and must not be counted as buildable.
  **The direction is the invariant, and reversing it breaks correct code.**
  Every *feed* division must be buildable here; the converse is false, because
  for Daily Lotto `api_label()` builds `MATCH 0` and `MATCH 1` while its
  published divisions start at two matches. An implementer asserting set
  equality would raise on every pool on day one.
  **Conformance to the `MATCH n` shape is not a substitute**, which is the
  lesson this invariant is built on rather than a hypothetical. The rule first
  proposed for it was *raise when no label conforms to the grammar*, and that
  rule sits quiet through the failure that actually happened: on 2026-08-03
  `api_label()` was found building `MATCH 5 + PB` against a feed publishing
  `MATCH 5 + POWERBALL`, dropping 53 PowerBall wins as losses (LOTTO-0027,
  §4.4), while the plain `MATCH 3` labels went on conforming. A partial rename
  is the likely rename; a wholesale one is the easy case.
  **Scope is the pay gate, not the price.** The gate is API-derived in both
  eras (§4.4), so this covers every line either era scores. A *site*-grammar
  drift shows up one step later instead, as a win the archive branch cannot
  price — which raises under INV-22, and is why that invariant's *Breaks when*
  keeps the API-side rename out of its own list.
  *Breaks when:* the operator renames a division, or adds one whose label this
  project cannot construct — both silent before this invariant, and both
  costing money in the only direction that matters, since an unreachable
  division is one whose winners are all reported as losers. It also breaks if
  a future edit "simplifies" the raise into skipping the unrecognised label,
  which is the same silent drop wearing a filter.

- **INV-31** — Every division a pool's **archive era** paid is either named by
  the current division set or **reported**. INV-26 asks that question of the
  newest draw; a division retired at the June 2026 handover falls outside it,
  and `check.py::check()`'s pay gate drops every one of its winners before
  `amount()` is reached — the cardinal rule in its omission form, one step
  earlier than INV-22's money path. Added 2026-08-12 by LOTTO-0023; the number
  is the next free one project-wide, not the next free one in this file (§5's
  opening paragraph).
  **The unit is the pool, and the sample is one page — not one per draw.** What
  moves at a handover is a pool's division *structure*, so the last archive
  draw before the break samples the era that ended: six pages, one per live
  pool, cached thereafter. Asking per line instead would scrape a payout page
  per (pool, draw) scored, because every *losing* line reaches the same branch
  and the question therefore cannot be narrowed to near-misses — several
  hundred fetches to settle a structural question that six answer. That
  costing, measured 2026-08-12, is why this is built as a structural comparison
  and not as the per-line count LOTTO-0023's bullet first proposed.
  **A bare `<n>` key on an archive payout page is ambiguous, and the resolution
  is evidence rather than a default.** Lotto archive pages spell Division 8 as
  `2 + Bonus` on some draws and a bare `2` on others; both shapes state *"eight
  prize divisions"* in prose and carry exactly eight rows, so the two spellings
  are one division (measured 2026-08-12 across 26 cached Lotto pages —
  `check.py::amount()` already leans on the same equivalence from the other
  direction). A bare key whose bonus-qualified sibling is absent from that page
  is therefore read as whichever tier the current set does carry, and only a
  key that **no** reading can place is reported. This is load-bearing, not
  cosmetic: all three Lotto pools sample a bare-`2` page, so read the other way
  the check reports a retired division on every one of them and flags every
  match-2-without-bonus line in the archive era as a possible win — a loss
  reading as a win, which is this project's cardinal failure inverted.
  **Reported, not scored.** The report names the pool and the label; it prices
  nothing and moves no total. Every archive draw predates 2026-06-01, so any
  such prize is already past its 365-day claim window (§4.4) and a rand figure
  would be unactionable. Counting the lines a real gap swallows is the
  follow-up this makes possible, and is worth building once there is something
  to count.
  *Test:* `python3 tools/verify_pools.py` (repo root, after `backfill.py`) →
  `retired-division guard: 6 live pools, 0 carrying a retired division, 3
  probes, 0 blind` (2026-08-12). Zero is the entire live population today,
  which is precisely why the three probes are part of the check rather than a
  supplement to it: a detector that has gone blind and a set of healthy pools
  print the same zero. Both directions were observed red before the case was
  believed — a detector stubbed to return nothing misses both gap probes, and
  the ambiguity rule deleted reports a false gap on all three Lotto pools.
  *Breaks when:* the operator retires a division, or a payout page's label
  grammar drifts so a tier no longer resolves. It also breaks if the ambiguity
  rule above is deleted — which reports three false gaps — or inverted so that
  an unplaceable key is swallowed, which is the original silent drop wearing a
  tidier filter.

## 6. Failure modes

- **The API changes shape or path.** `results.py::_post()` raises on any
  non-zero `code`, so scoring stops rather than reporting zero wins. The
  endpoints were reverse-engineered and carry no compatibility promise.
- **The network is unreachable, or the endpoint times out.** The most likely
  runtime failure and the one the bullet above does *not* cover: `urlopen`
  raises `URLError` / `socket.timeout` before any response `code` exists to
  check (`results.py` at 20 s, `backfill.py` at 30 s). Nothing catches it, so
  the run aborts with a traceback and reports nothing — which is the correct
  side to fail on, since the alternative is a partial win list that reads as
  complete.
- **An input file is absent**, and the three answers deliberately differ.
  `tools/verify_sources.py` exits cleanly naming the fix
  (`archive_results.json missing - run \`python3 backfill.py\` first`);
  `tools/verify_privacy.py` degrades to pattern-only and still exits 0, which
  is why `local-CI.sh` asserts separately that it ran at full strength; and
  everything reaching `tickets.py::load()` — `check.py`, `verify_coverage.py`,
  `verify_pools.py` — raises on the missing dump rather than scoring zero
  tickets. A clean exit reporting "0 wins" from an absent dump is the cardinal
  failure, so raising is intended, not an oversight.
- **The archive site changes markup.** `backfill.py::parse_page()` returns
  an empty dict, which surfaces as a game with 0 draws. This has already
  happened once: the site renamed Lotto Plus 2 to Lotto 5 Max and the
  hardcoded slug silently matched nothing.
- **An unrecognised SMS format.** `parse()` returns `None` and the message is
  skipped. This failed silently once — 552 of 558 tickets were dropped by a
  pattern that did not allow `draw(s)` — which is why INV-6's test asserts
  the parsed count, not merely that parsing succeeded. That assertion means
  every `Played R` message in the dump must parse: a purchase for a game
  outside `GAME_MAP` fails the check rather than being quietly skipped, which
  is the intended behaviour.
- **An entry predates all draw data for its pool.** Excluded by
  `history.py::scorable(ticket, plus_flag)` and reported by `check.py` as
  uncheckable. It is never scored against later draws, and never counted as a
  loss. The *ticket* is excluded only when every one of its entries is; one
  checkable pool is enough for it to be scored and reported as partly
  uncheckable (LOTTO-0009 §4.6).
- **An entry's window runs past the last known draw.** Scored over the draws
  that exist so far. `tools/verify_coverage.py` distinguishes this from a real
  gap, including the case where a ticket is newer than every known draw and no
  draws are available at all; `check.py` itself does not report the shortfall.
- **A ticket's price matches no board price on record**, or its message
  carried no parsable board line at all — `tickets.py::entered_pools()` returns
  unresolved for `paid_lines == 0` too, and such a ticket parses, counts and is
  scorable while contributing zero lines. `entered_pools()`
  returns unresolved, `pools` falls back to the single pool the game name
  states, and `check.py` prints the count — loudly, because that fallback is
  the project's pre-LOTTO-0009 behaviour and is invisible otherwise. It is the
  one path on which a tier the ticket never paid for could be scored.
  LOTTO-0009 INV-7 asserts the count is zero.
- **No division matches a win's label.** The line is **dropped**, not listed
  at zero: `check.py::check()` gates on `paying_combinations()` before
  `amount()` runs. A label that passed that gate and is then absent from the
  draw's own division table means the source could not be read, not that the
  prize was zero, so `amount()` **raises** (INV-22). Its only `0.0` return is
  a division the source itself states as zero. Nothing detects a
  systematically wrong label either way (§11).
- **A pool has no recent draw record.** `paying_combinations()` raises rather
  than returning an empty set, because an empty set would score every line in
  the pool as a loss with no diagnostic.
- **The source publishes a division this project cannot name.** The intended
  answer is the same raise, for the same reason one step finer: the division
  set is not empty but is missing the label a winner would join on, so the hole
  scores exactly the lines that fall in it as losses and leaves the rest
  looking healthy (INV-26). A rename reaching only *some* labels is the shape
  to expect — it is the one that happened (§4.4, LOTTO-0027) — so the test is
  whether every published division is reachable, not whether the set as a whole
  still looks like the grammar. `paying_combinations()` raises on it (INV-26
  owns the detail), which covers every pool a run scores including one no
  ticket in the dump reaches, and `tools/verify_pools.py` catches the same
  thing before the fact over the pools the dump does reach.

## 7. Tests

**Every count in this document is a dated measurement, and most of them grow
over time** —
§5's expected outputs are as of 2026-08-01, INV-22's of 2026-08-02, and INV-4's
of 2026-08-03. INV-26's are dated in two parts: its sweep line is of
2026-08-03 and its probe line of **2026-08-04**, when the runtime half
shipped. The figures in §2 and §4.2 are of 2026-08-01, and
§10's of 2026-08-01 with the caveat it carries. §4.4 is dated in two parts: its
86-wins and 69-archive figures are INV-22's measurement of **2026-08-02**,
taken before LOTTO-0027, and only its 53-dropped-PowerBall-wins figure is
LOTTO-0027's of 2026-08-03. Overlap grows
with every draw, ticket totals with every SMS. What each invariant actually
asserts is the zero-term and the exit code (`0 disagree`, `0 with wrong draw
coverage`, exit 0); a changed count is not a failure — **except the unscorable
count**, which has a 90% floor precisely because "almost everything is
unscorable" is what missing data looks like, and **except INV-26's pool
count**, which is the one count here that cannot grow: it is bounded at six,
is not asserted as a number, and must not reach zero (its own floor, stated
with the invariant). Every script exits non-zero on a real
breach, so prefer `&& echo PASS` over string-matching the line.

**Run them from the repository root, after `python3 backfill.py`** — but that
is a consequence of which handle each script reaches through, not a convention
they share, and the differences matter to anyone writing a fifth. Stated as a
table because three consecutive review loops found this wrong in prose:

| script | tickets | archive | dump, direct | run from |
|---|---|---|---|---|
| `verify_sources.py` | — | `ARCHIVE`, cwd | — | repo root |
| `verify_coverage.py` | `load()`, cwd | `ARCHIVE`, cwd | `DUMP`, `__file__` | repo root |
| `verify_pools.py` | `load()`, cwd | `ARCHIVE`, cwd | `DUMP`, `__file__` | repo root |
| `verify_privacy.py` | — | — | `DUMP`, `ROOT` | **anywhere** |

Two readings follow from it, and both have been got wrong. **`verify_sources.py`
never opens the dump at all** — it needs only the archive, so "with the SMS dump
present" is not a precondition of running it. **`verify_privacy.py` is the one
script that runs from any directory and needs no `backfill.py`**: it imports
nothing from this project, and resolves both its `DUMP` and its file list from
`ROOT` (its own `__file__`) and `git -C ROOT ls-files`.

The hazard is the middle two rows, which reach the same file by *both* routes.
`DUMP` is never how they load tickets — those come from `load()`'s cwd-relative
default, while `DUMP` serves a second, direct read: the `Played R` parse count
and the per-reference facts. So run `verify_coverage.py` from a directory
holding a *different* `lotto_sms_raw.txt` and it counts the **repository**
dump's purchases (via `DUMP`) against the **foreign** dump's parsed tickets (via
`load()`), printing a PARSE GAP that is an artefact of the two handles rather
than a parser defect. Resolve both ends the same way or neither.

`tools/verify_sources.py`, `tools/verify_coverage.py` and
`tools/verify_privacy.py` are this spec's executable checks, joined by
`tools/verify_pools.py`, which carries this spec's INV-22 and INV-26 as well as
LOTTO-0009's invariants; INV-1, INV-2 and INV-5 are the one-line commands
recorded in §5. There is no test framework in this project and adding one is
out of scope (§9) — these run under plain `python3`.

Red-tested against a state that should fail: INV-2's one-liner against the
pre-Multiplay scorer; INV-6's script against the parser that dropped
`draw(s)`, against the coverage bug that mis-scored 426 tickets, and against
a `scorable()` regressed to `bool(rows)`; INV-4's script against a real board
line pasted into `README.md`; INV-3's per-pool floor against an un-exempted
empty pool; INV-22's probes against the archive branch reverted to
`return 0.0` (2 mispriced, exit 1); INV-26's reach case against the `+ PB`
labels that preceded LOTTO-0027, which is the state that shipped rather than a
contrived one (12 unreachable divisions across the two PowerBall pools,
exit 1); and INV-26's anti-vacuity floor on both branches (2026-08-03) —
`reaches()` forced false gives `0 live pools, 0 unreachable divisions,
1 vacuous`, exit 1, and an emptied division table gives six pools each
reporting NO DIVISIONS, exit 1, where before the floor both states printed
`0 unreachable` and passed; and INV-26's runtime raise on both of its own
failure directions (2026-08-04) — with the guard disabled, two probes report
`NO RAISE`, exit 1, and with its direction reversed to set equality the subset
probe reports `FALSE RAISE` while three of the six live pools report six
unreachable divisions between them, exit 1, which is the "raises on every pool
on day one" the invariant's direction paragraph warns of, observed rather than
argued. Three further assertions have no red test:
INV-1, INV-5, and INV-3's agreement half — the sources have agreed on every
run.

## 8. Alternatives considered (and rejected)

- **ResultsZA API** — R149/month for 300 calls. Rejected: the user requires
  zero cost. A weekly check of the three games costs roughly 30 result
  lookups a month, comfortably inside the free official feed and not worth
  R1,788/year.
- **Microsoft Phone Link** for SMS — Windows only, no Linux client.
- **Scraping the official results page** rather than its JSON API — the site
  is a JavaScript app, so the page HTML contains no results.
- **Computing draw dates from a weekday calendar** instead of reading actual
  draws — simpler, but wrong the first time a draw is moved or cancelled.

## 9. Out of scope

- The web page UI — tracked by LOTTO-0002.
- The known deferred rough edges — tracked by LOTTO-0007.
- Automatic ingestion of new tickets as they arrive — tracked by LOTTO-0003.
- A test framework; **this spec's** verify scripts are deliberately
  dependency-free (LOTTO-0002's `tools/verify_page.py` needs PySide6). (No
  count here on purpose — it has rotted twice as scripts were added.)
- Tickets predating all draw data (the count is §4.4's, which owns the gate).
  The gate is per pool — each pool's own earliest known draw — not a global
  date. The floor was always a configured default rather than a source limit,
  and LOTTO-0006 lowered it on 2026-08-31 to `backfill.FIRST_YEAR`, the year of
  the earliest purchase SMS, which emptied this category. It stays out of scope
  here because the *gate* is what this section is about: such a ticket is
  excluded by `history.py::scorable()` and reported as uncheckable, not silently
  dropped, and that is what protects the next dump that reaches back further
  than the archive does.

## 10. Resource cost

**Python 3.8+** — the walrus operator is the highest feature used; developed
on 3.13. No `match`/`case` statement appears in any module
(`grep -rn "^\s*match .*:" *.py` → nothing). No third-party packages — standard library only. The KDE
Connect path additionally needs the distribution's `python3-dbus`, which is
not a Python dependency this project declares or installs.

**Wall clock:** `backfill.py` sleeps 1 s between uncached fetches as a
courtesy to a free third-party source, so a cold backfill is ~12 s of delay
plus 1 s per uncached payout page, on top of the HTTP timeouts above. A warm
run sleeps not at all.

**Disk:** `archive_cache/` holds 12 archive pages (6 pools × 2 years) plus
one payout page per draw a winning ticket touches — 3.7 MB measured
2026-08-01 (`du -sh archive_cache`). Gitignored and regenerable, as is
`archive_results.json`.

**Network, per `check.py` run:** `results.py::draws()` is **not** memoised, so
`issueWinPoolInfoPageQuery` is called once per pool by `history.all_draws()`
and once per pool by `check.paying_combinations()` — **7 + 6 = 13 requests**
regardless of how many entries score, given at least one scorable entry per
pool; with a partial archive the 6 falls with the pools that have none. **All thirteen are lazy and interleaved**,
issued from inside the same loop in `check.py::check()`: `all_draws()` fires
through `scorable()` as each pool's first *entry* is reached and the paying-set
query as its first *scorable* entry is, so the two sequences interleave rather
than one preceding the other. Both are memoised, which is what holds the total
at thirteen. Seven for `all_draws()`, one per pool; six for the
paying sets, because the always-empty `daily/1` is never asked for one (no
entry in it is scorable). **`paying_combinations()` is itself memoised** in
`check.py::_struct`, keyed `(game, plus_flag, pool_id)` — without that it would
fire once per *scorable entry*, 259 of them, against a free public endpoint.
Establishing each paying set costs one `getIssueDrawResultDetail`, and then one
more per distinct `(game, issue, pool, plusFlag)` a win
lands on. `divisions()` **is** memoised, so a 7-line Multiplay ticket over 10
draws costs at most 10 detail requests, not 70. Archive payout pages are
cached to disk; only a first run fetches them. **27 requests measured** for a
whole run on 2026-08-01 with the archive cache warm (13 + 14); LOTTO-0009 §10
carries the breakdown and the before/after. **That measurement predates
LOTTO-0027 and has not been retaken.** Only the 13 is structural; the other 14
is one lookup per distinct `(game, issue, pool, plusFlag)` a *win* lands on,
and LOTTO-0027 restored 53 PowerBall wins that had been scored as losses, so
the figure is a lower bound until it is re-measured.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | §5 command, `tickets.py::parse()` |
| INV-2 | §5 command, `tickets.py::parse()` |
| INV-3 | `tools/verify_sources.py` |
| INV-4 | `tools/verify_privacy.py`, run by `local-CI.sh` and so by `.githooks/pre-push` — **partly advanced by LOTTO-0025**, which made it a pre-*push* gate; still **not a pre-commit hook**, so a commit can carry a leak that only the push refuses. Tracked by LOTTO-0004 |
| INV-5 | §5 grep, production modules only — labels only; **nothing** catches a hardcoded prize *amount*, and nothing checks the `tools/` literals the glob deliberately excludes. It also cannot see a feed-side **rename**, and no widening fixes that: `api_label()` builds three of its four forms with f-strings and the fourth as the plain literal `"MATCH POWERBALL"`, so a pattern broad enough to see them fires on correct code — and since LOTTO-0027 the widened glob also matches the comments quoting the old labels. INV-26 is what catches a rename, and closes LOTTO-0007(c) in place of a wider glob |
| INV-6 | `tools/verify_coverage.py` |
| §4.3 special-ball-is-last | `tools/verify_sources.py` — catches a change on either source alone; blind only if both change the same way together |
| §4.4 expiry / `CLAIM_DAYS` | **nothing** — no test covers the 365-day boundary, and nothing tracks the gap |
| INV-31 §4.4 current-era pay gate | `check.py::retired_divisions()`, swept per live pool by `tools/verify_pools.py` with three probes driving both failure directions. Was **nothing** until 2026-08-12 (LOTTO-0023). What remains unchecked is narrower: the sample is one archive page per pool, so a division retired *within* the archive era rather than at the handover is seen only if the sampled draw carries it |
| INV-26 §4.4 label grammar reachable | `check.py::paying_combinations()`, which raises on a division no label `api_label()` builds can equal, and `tools/verify_pools.py`, which sweeps the same rule ahead of a run plus three probes driving the raise itself. The sweep reads only the pools the dump reaches; the raise covers whatever pool a run scores, so a pool nobody holds a ticket in is checked from the moment one is. That division of labour is the design |
| INV-22 unpriceable win raises | `tools/verify_pools.py` — four blind-lookup probes (empty and unrecognised division tables, both branches), plus the converse that a source-stated R0.00 still prices as 0.0 |
| archive payout scrape | `tools/verify_pools.py` (INV-22) — an unscrapable payout page now raises instead of pricing an archive win at R0.00. What remains unchecked is narrower: a page that parses into a **wrong** table, which is well-formed and not detectably wrong from inside |
| `backfill.py` date parsing | **nothing** — an abbreviated month in a href raises `KeyError`, not an empty result |
| Multiplay on non-Lotto games | `tools/verify_pools.py` (LOTTO-0009 INV-7) — the PowerBall branch is tested first, so a >6-number PowerBall board still becomes one line, but the price paid for more, so it resolves to no tier and exits non-zero. The wrong line *count* itself is still unchecked |
| §4.2 pools derived from price, not from the game name | `tools/verify_pools.py` (LOTTO-0009 INV-7, INV-8) |

## 12. Cross-doc impact

README.md (usage), ROADMAP.md (LOTTO-0002 onward), CHANGELOG.md, and:

- `docs/specs/LOTTO-0009-entered-pools.md`, which amends this document in §2,
  §4.2, §4.4, INV-6, §7, §10 and §11 — it changed the unit of work from the
  ticket to the entry.
- `docs/specs/LOTTO-0002-local-web-page.md`, which consumes §4.4's win dict by
  name and specifies the `amount` → `amount_cents` substitution made on the way
  into the page model. A key renamed here breaks that document's §4.1.
- `docs/specs/LOTTO-0014-http-surface-and-security.md` and
  `docs/specs/LOTTO-0013-tray-and-supervisor.md`, which own two of the four
  rows in §5's ownership table and are otherwise independent of this document —
  listed so the map has somewhere to point.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 9 | 2026-08-03 | 2 | 0 | 3 | 7 | 8 | **Converged by cap at three loops (7–9), and stopping is the finding.** 18 distinct findings, **all 18 verified, all 18 fixed, 0 dismissed, 0 deferred** — but the split inverted from loop 8: **10 draft defects to 8 collateral**, and one of the draft defects is *structural*, which is the signal this document is past the size a cold read can cover. HIGH, both lanes: **§7's `DUMP` sentence was wrong in both directions** — it said the three non-privacy scripts each carry a `__file__`-relative `DUMP`, where `verify_sources.py` has none and never opens the dump at all, while `verify_privacy.py`, the "genuine exception" loop 8 had just carved out, does carry one. That paragraph has now produced a finding in **three consecutive loops** (loop 7: a false exception; loop 8: the hazard written backwards; loop 9: the wrong scripts), so it is no longer prose — it is a four-row table of which handle each script reaches through, with the two readings that keep being got wrong stated beneath it. Prose that fails three cold reads is a shape problem, not a wording problem. HIGH, lane B alone and **the structural one**: **§4.3 never gave the `POOL_NAMES` table**. `all_draws()` selects a pool by comparing the API's `winPoolName` against it, and two of the seven strings are June-2026 rebrand names — `LOTTO 5 MAX`, not "Lotto Plus 2"; `PowerBall XTRA`, not "PowerBall Plus" — so an implementer rebuilding `history.py` from this spec gets **zero API draws for `lotto/2` and `powerball/1` with no error**, the cardinal failure one layer below scoring. §4.2 calls its analogous SMS table load-bearing for exactly this reason; §4.3 had no equivalent, and INV-26's ceiling-of-six argument had been leaning on a table the document never defined. Now stated. **That it surfaced only at loop 3 is the evidence for splitting**: two prior cold reads did not reach it. Also fixed, §6 having grown two absent failure modes: **the network being unreachable** — the most likely runtime failure, and the existing bullet does not cover it, since `urlopen` raises before any response `code` exists to check — and **an input file being absent**, where the three answers deliberately differ (`verify_sources.py` exits cleanly naming the fix, `verify_privacy.py` degrades to pattern-only and still exits 0, everything reaching `load()` raises) and none of the three was written down. §6's unresolved-price bullet named only an operator price change where `entered_pools()` also returns unresolved for `paid_lines == 0`, a ticket that parses, counts, is scorable and contributes zero lines. §3's KDE Connect bullet read as in-scope ingestion against §4.1's "inspection only" and §9's LOTTO-0003. §10 pinned requests and disk but no wall clock, omitting `backfill.py`'s 1 s courtesy delay per uncached fetch. Loop 7's own "step 2, not yet built" marker had landed in four places, three of which would rot the day step 2 ships — reduced to pointers, with INV-26 keeping the full statement; loop 8's "it is stated once, there" was self-falsifying two sentences after stating it; `426 of 558` was written three times and is now §4.4's alone; INV-22's 86/69/R2,651.60 carried no pre-LOTTO-0027 qualifier where §4.4's copy does; §2 cited §4.2 for a gate §4.2 does not describe; §10's `7 + 6 = 13` is contingent on one scorable entry per pool; and two forward references in §4.4 now name their targets. `./local-CI.sh --force` 9 checks PASS. **The run stops here rather than looping**: `--max-loops` is 3, and the structural draft defect at loop 3 is its own trigger. Nothing is deferred — every finding is fixed — but these fixes have had **no cold read**, and the document is now **831 lines**. Splitting it is the recommendation carried to the user, not a decision taken here. |
| 8 | 2026-08-03 | 2 | 0 | 3 | 4 | 6 | **The loop that read its own previous loop's edits.** 14 distinct findings, **13 verified, 13 fixed, 1 dismissed on evidence** — and the number that matters is the origin split: **10 of the 13 were collateral from loop 7's own fixes, only 3 were draft defects.** That is the signature of an under-running blast-radius sweep rather than a bad document, so this loop answered it by sweeping wholesale and by **deleting duplication instead of reconciling it**, which is the only fix that stops a finding recurring. Both lanes independently found the same three. **§7's PARSE-GAP hazard was written backwards** — loop 7 said `verify_coverage.py` counts a foreign dump's purchases against the repository dump's parsed tickets, where `DUMP` is `__file__`-relative and `load()` is cwd-relative, so it is the exact opposite: repository purchases against foreign tickets. It is the one paragraph a maintainer reads while diagnosing a real PARSE GAP, and it pointed at the wrong dump. **§7 also asserted "There is no exception" two lines after naming the exception**: `tools/verify_privacy.py` imports nothing from this project, never calls `load()`, never touches the archive, and resolves everything from its own `__file__` and `git ls-files` — it runs from any directory and needs no `backfill.py`. Loop 7 had over-corrected a false claim into its mirror image. Third: **INV-5's "five hits, three of them prose" was already stale when it was written** — the commit that fixed the comments it was counting added two more matching lines, so the figure rotted on the same commit that created it. Fixed by **removing the count entirely** rather than re-measuring: the hits are mostly comment prose, the number moves whenever anyone edits a comment, and "mostly prose" is both the durable point and, on its own, the whole argument for keeping the glob narrow. HIGH, lane B alone and a genuine draft defect: **INV-22's *Breaks when* still said §11's label-grammar row "reads **nothing**" for an API-side rename**, which INV-26 made false on 2026-08-03 — a reader following that pointer is told nothing catches a rename, and the risk is a second guard built beside the one that exists. The duplication fix: §4.4 and INV-26 both carried the directional rule and its Daily Lotto justification at near-equal length, and the LOTTO-0027 story appeared three times; §4.4 now states the rule in one sentence and points at INV-26, which owns direction, domain and converse. Also fixed: §7 dated §4.4's win totals to LOTTO-0027 when its 86/69 pair is INV-22's 2026-08-02 measurement and only the 53-win figure is 2026-08-03; §7's dating sweep omitted §10 entirely, whose `du` figure carried no date and whose **27-request measurement predates LOTTO-0027** — the 14 non-structural requests are one per distinct draw a *win* lands on, and 53 restored wins make it a lower bound until re-measured, now said so in place; §11's INV-5 row said `api_label()` builds "two of its three forms" with f-strings where it has four returns (three f-strings, one literal); §12 claimed those two docs own "four of the invariant ranges" where §5's table gives them two rows; INV-26's `6 live pools` was described as growing with the dump when six is the **ceiling** (`POOL_NAMES` holds seven and `daily/1` can never pass `reaches()`), so it is the one count here that can only fall — which is what the floor exists to catch, and §7's blanket "every count grows" was corrected to match; §4.4's plain-tier fallback said "both games" in a three-game project; and §9's "the verify scripts are dependency-free" was scoped to this spec's, LOTTO-0002's `verify_page.py` needing PySide6. **Dismissed on evidence:** a lane reported ASCII hyphens used as dashes at two lines that carry no such thing; the document's single ` - ` sits inside the win-dict code fence, matching its neighbour on the next line. **Not converged** — loop 9 follows cold, and is the `--max-loops` cap. |
| 7 | 2026-08-03 | 2 | 1 | 3 | 6 | 8 | **Run on the LOTTO-0026 step-1 amendment (INV-26) and the LOTTO-0027 corrections, before step 2 touches `paying_combinations()`.** 19 distinct findings after merging the lanes, **all 19 verified true, all 19 fixed, 0 dismissed** — the first loop in this document's history with nothing to drop, which is itself a signal: the amendment described unbuilt behaviour, and unbuilt behaviour cannot contradict the code it is checked against, so the reviewers found wording rather than argument. CRITICAL, found independently by both lanes: **INV-26 stated `paying_combinations()`'s raise in the present tense across §5, §6 and §11 when it is LOTTO-0026's own step 2 and is not built**, and INV-26's *Test* named a probe that does not exist — so a reader closes step 2 unbuilt and believes a pool nobody holds a ticket in is guarded. Resolved by marking the runtime half pending in all four places rather than by landing step 2 first: three of this loop's own findings (the `(hits, special)` domain, whether the raise aborts the run or fails one pool, and whether "publishes for a pool" means the pool's history or its newest draw) are exactly the contract holes step 2 must build against, so implementing first would have built from the gaps the gate had just found. The pending markers come off with step 2. HIGH: §4.4 described `amount()`'s archive plain-tier fallback as the bottom-tier case it was written for, where the code tries `str(hits)` for any `hits` and both games, so a payout page missing its `3 + PowerBall` row prices at the plain `3` amount instead of raising under INV-22 — a real price for the wrong division, which is not the cardinal-rule breach but is indistinguishable from inside. HIGH, both lanes: **`division` is documented as the win's own `winLevelName` and is always the API's newest draw's**, in both eras, so an archive-era win carries a 2026 division name — the majority case (69 of the 86 wins measured before LOTTO-0027), and on the plain-tier fallback `division` and `matched` can name the bonus tier while `amount` came from the plain row, three fields disagreeing on the money path with nothing saying so. The structural gap: **§5's invariant-ownership map was wrong about four ranges** — it sent INV-12 to INV-21 wholesale to LOTTO-0002, where LOTTO-0014 owns INV-12–14 and INV-21 and LOTTO-0013 owns INV-19–20, and `LOTTO-0014-http-surface-and-security.md` appeared nowhere in this document, §12 included. Now a table, with §12 extended to name every document the map points at. Two findings were fixed in **code** rather than prose, both in `tools/verify_pools.py`: INV-26's reach check had **no anti-vacuity floor** where INV-3 and INV-6 both carry one — its pool set is derived from the tickets that `reaches()`, so a partial archive silently shrinks what is checked, and every division in an *empty* division set is trivially reachable, so a feed returning no divisions would have printed `0 unreachable` and passed; it now fails on zero live pools and on any pool with an empty table, red-tested on both branches. And the comment justifying the check's direction carried §4.4's wrong counter-example verbatim — `MATCH 6` for Daily Lotto, which the domain caps at five and therefore never builds; the real buildable-but-unpublished daily labels are `MATCH 0` and `MATCH 1`. Also fixed: §7 claimed `verify_coverage.py` resolves its inputs relative to its own file, where its *tickets* come from `load()`'s cwd default like every other script and three scripts share the `__file__`-relative `DUMP` handle — the mixture prints a spurious PARSE GAP when cwd holds a different dump; §7 misdated INV-4 to 2026-08-02 against INV-4's own 2026-08-03 and carried no vintage for INV-26; §10 said the seven `all_draws()` calls precede scoring when both they and the paying-set queries are lazy inside the same loop (the 7 + 6 = 13 total was right); §4.4 said `serve.py` *spreads* the win dict where LOTTO-0002 §4.1 specifies it drops `amount` for `amount_cents` and calls that deletion load-bearing against a 100× money error; §4.4's `"line"` was "the board letter" where Multiplay lines are `A1`…`A7`; INV-5's "two such literals live under `tools/`" is five hits since LOTTO-0027, three of them comments quoting the old labels — a third kind the paragraph's taxonomy did not cover, and on its own enough to make the wider glob useless; §11's INV-5 row rested on "`api_label()` builds its labels with f-strings" when one is now the plain literal `"MATCH POWERBALL"` (the row's conclusion survives, and it is the sentence LOTTO-0007(c) was closed on); §11's INV-4 row still read "not yet a pre-commit hook" without noting LOTTO-0025 made it a pre-*push* one; and INV-22's `rows[0]` reasoning assumed the feed pages newest-first, the same class of observed-not-promised assumption §4.3 already records for the special ball, now recorded beside it as a third convention. `./local-CI.sh` 9 checks PASS after the code changes. **Not converged** — a cold loop 8 follows, un-briefed, per the re-brief rule. |
| 6 | 2026-08-02 | 2 | 0 | 1 | 5 | 6 | **Accepted at two loops.** Loop 5's fixes held: neither lane re-raised §6, INV-5 or INV-22's triggers, which is the proof the cold re-read exists to give. All 12 verified findings fixed, 0 dismissed, 1 surfaced to the user as code-side, 1 filed as LOTTO-0023. Nine were draft defects, two were collateral from loop 5's own fixes — §7's dating sentence named INV-22 as the sole 2026-08-02 exception when loop 5 had just dated INV-4 the same day, and INV-5's new exemption paragraph called both `tools/` literals feed doubles when `verify_page.py`'s sits in a page-model `matched` field that production fills from `site_label()` in the *site* grammar. HIGH: INV-3's *Breaks when* contradicted itself inside one bullet — *"either source renames a pool, so it contributes no overlap and the run passes on the strength of the other five"*, then three lines later *"The check fails any pool with zero overlap"*. The first half is the pre-floor rationale lifted from `verify_sources.py`'s own comment, so an implementer building the script from the invariant alone omits the per-pool floor, which is the regression it exists to catch. The structural gap: **§4.4 never stated what `check()` returns**, though `serve.py` spreads that twelve-key dict into the page model and LOTTO-0002 §4.1 consumes it by name — no document carried the shape, so an implementer would have invented the key names. Now fenced in §4.4 beside §4.3's draw record, which is also where the `matched` grammar and the rands-not-cents rule become findable. Also fixed: §4.2 stated the same three facts in two consecutive paragraphs (deduped); §7 claimed every script resolves its inputs relative to the working directory, where `verify_coverage.py` resolves the dump relative to its own file; §10's *"before anything is scored"* was wrong about ordering, since the six paying-set queries are lazy; *unscorable* / *uncheckable* / *not scorable* named one set in three words with nothing saying so; §9 pointed at a loop-log entry a cold reader must not open; and a section index was added after three of four lanes across both loops asked for one. **Filed rather than fixed:** §4.4's pre-handover-division drop is silent — the cardinal rule in its omission form, one step earlier than the money path INV-22 closed — and it is separable with the draw's own division set, so it is LOTTO-0023 rather than a limit. `spec_lint` still reports INV-7–INV-21 as id gaps; that is mechanical noise here, since those ids never lived in this file and a tombstone would assert a move that never happened. |
| 5 | 2026-08-02 | 2 | 1 | 2 | 3 | 5 | **The gate LOTTO-0022 recorded as owed for INV-22** — the invariant shipped, checked and red-tested on 2026-08-02, but no independent reader had seen the contract describing it. All 11 verified findings fixed, 2 dismissed on evidence, 0 deferred. Both lanes independently found the same CRITICAL and the same HIGH-graded second item. CRITICAL: §6's *"No division matches a win's label"* bullet still said *"`amount()`'s 0.00 return is reachable only for a label that passed the gate but is missing from that draw's payout table"* — the pre-INV-22 behaviour, stated in the section an implementer reads for the unhappy path, so the doc licensed the `.get(..., 0.0)` default INV-22's own *Breaks when* forbids. The amendment had added the invariant and left its contradiction standing five sections away. Second: **INV-5's recorded test was red against correct code** — `grep -nE '"MATCH [0-9]' *.py tools/*.py` returns `2`, not `0`, and one of the two hits is INV-22's own API probe double added the same day, so the obvious repair deletes a guard on the cardinal money rule; the glob is now production-only with the exclusion stated. HIGH: INV-22's *Breaks when* claimed a feed-side `MATCH n` rename as a trigger, which cannot fire — `paying_combinations()` reads its keys from the same feed, so `check()`'s gate drops every line before `amount()` is reached, and §4.4, §6 and §11 all already said so; only the archive branch's labels are ungated. Also fixed: nothing in the doc explained that invariant ids are project-wide, so §5 jumped INV-6 → INV-22 and the next invariant added here would have collided with LOTTO-0009's INV-7; §7 still credited `verify_pools.py` to LOTTO-0009 alone and its red-test roster omitted INV-22's while claiming only INV-3 lacked one; §9's script count had rotted a second time (now carries no count); §2 read as one global cutoff date where the gate is per pool; and `Ticket.boards` holds lines rather than lettered boards, which §2 and §4.4 counted both ways. Dismissed on evidence: a lane asked for a section index (no sibling spec carries one, and `doc_integrity` would then police a TOC across a corpus that has none); both lanes queried §10's undecomposed `(13 + 14)`, which LOTTO-0009 §10's measured table does carry, exactly as §10 says. |
| 4 | 2026-08-01 | 2 | 0 | 3 | 6 | 8 | **Retrofit pass, after LOTTO-0009 changed the unit of work from the ticket to the entry.** All 17 verified findings fixed, 1 dismissed, 0 deferred. Both lanes independently found the same two HIGH items. First: §4.2 still said an implementer *"cannot derive `winPoolId` or `plusFlag` from anything else"* — false since `tickets.py::entered_pools()` derives both from the price, and the sentence sat directly above its own amendment, so a top-down reader was told the table was authoritative before being told it was not. Second: §4.4's *"(974 of 1233 entries)"* merged the two uncheckable reasons this project exists to keep apart — 963 entries predate their pool's data, and the other 11 are `daily/1`, which nobody publishes. Third HIGH: §11 still credited **nothing** with catching a >6-number PowerBall board when LOTTO-0009 INV-7 now exits non-zero on one, so two live contracts asserted opposite things about the same known defect. Also fixed: §10's 13-request budget was unreachable from what the document stated, because `paying_combinations()`'s memoisation was never mentioned and `check()` calls it once per scorable **entry** — an implementer building to the text would have fired 259 requests at a free public endpoint; §6's failure modes still excluded whole tickets; §6 had no failure mode at all for the shipped unresolved-price path; §9 said "the two verify scripts" where §7 names four; and INV-4's expected tracked-file count was two files stale. Dismissed on evidence: a lane read §11's `KeyError` claim against `backfill.py::payouts()`, which raises `IndexError` — the row is about `parse_page()`'s `MONTHS[...]` lookup, which does raise `KeyError`. |
| 1 | 2026-08-01 | 2 | 2 | 4 | 5 | 7 | All verified findings fixed. Both lanes independently found the same CRITICAL: 426 tickets predating all draw data were scored against Jan-2025 draws, invisible to INV-6 because its test was a tautology over `covered()`'s own slice. Fixed in code (`history.py::scorable()`), in the checks (INV-4 and INV-6 rewritten to be non-circular) and in the spec. Corrected the lifetime total R1,727.10 → R960.40; claimable R800.20 unaffected. |
| 2 | 2026-08-01 | 2 | 2 | 4 | 4 | 6 | All verified findings fixed. Both lanes independently found a real ticket reference (redacted; from the user's own messages) tracked in `README.md` — INV-4 reported 0 because its pattern was anchored on `Ref:`, which pasted program output drops. Scrubbed, pattern broadened, git history rewritten before any push. Also: §6 claimed an unmatched division is "listed at zero" when `check()` drops it before `amount()` runs; `paying_combinations()` returned `{}` for a pool with no recent draw, scoring the whole pool as losses silently (now raises); `verify_coverage.py` raised IndexError for a ticket newer than every known draw; §10 named an endpoint that does not exist and undercounted requests ~4×; §3 and §9 disagreed on whether the web UI is in scope. |
| 3 | 2026-08-01 | 2 | 3 | 4 | 2 | 5 | Converged by cap. Fixed: §4.2's four example SMSes were verbatim real messages (numbers, dates, amounts — only the reference had been scrubbed), now synthetic and verified absent from the dump; `Daily Lotto Plus` was aliased onto plain Daily Lotto's pool, scoring 11 tickets against another game (now an empty pool, reported uncheckable — claimable corrected R800.20 → R700.10); INV-6's check still imported `history.scorable()`, the predicate under test, so a regressed `scorable()` would have passed — now recomputed independently and red-tested, plus a 90% floor for missing data; added the game-name and division-label tables an implementer cannot derive; KDE Connect documented as inspection-only. Five verified findings deferred to LOTTO-0007. |
