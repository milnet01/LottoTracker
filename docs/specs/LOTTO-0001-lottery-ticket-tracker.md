# LOTTO-0001 — Track lottery tickets from SMS and score them against real draws

**Status:** accepted (2026-08-01).
**Kind:** implement.
**Source:** ROADMAP LOTTO-0001 (user request, 2026-08-01).

Layman: the PC reads the lottery ticket texts your bank sends, remembers
every ticket, and tells you whether any of them won.

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
   at all (259 of 1233 entries) — 426 predate every available draw record
   (§4.2, §4.4). Of those
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
- **Read SMS via KDE Connect for new tickets, adb for history.** Both were
  set up; neither is a fallback for the other (§4.1).

## 4. Design

### 4.1 Getting messages off the phone

Two paths, because they solve different problems:

| Path | Module | Use | Filtering happens |
|------|--------|-----|-------------------|
| adb over USB | shell `content query` | bulk history | on the phone |
| KDE Connect over Wi-Fi | `find_lotto_sms.py` | **inspection only** | on the PC |

The adb query filters with a SQL `WHERE` clause executed on the device, so
only lottery messages ever cross to the PC:

```bash
adb shell "content query --uri content://sms \
  --projection address:date:body \
  --where \"body LIKE '%lotto%' OR body LIKE '%powerball%'\""
```

KDE Connect cannot filter server-side — `activeConversations()` returns the
newest message of every thread — so `find_lotto_sms.py` matches keywords
locally and calls `requestConversation()` only for threads that hit. Its
keyword list is deliberately narrow for the same reason.

**Only the adb path feeds the pipeline in this spec.** `find_lotto_sms.py`
prints; it writes no file, and `tickets.py::load()` reads only the adb dump
format (`^Row: N address=…, date=…, body=…`, one record per match, from
`lotto_sms_raw.txt` at the repo root). Turning the KDE Connect stream into
that format is LOTTO-0003.

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

The game name maps to a results pool. This table is load-bearing and cannot be
derived from anything else *in the SMS text* — but since LOTTO-0009 it is no
longer the authority on `winPoolId` / `plusFlag`. **The ticket price is**, and
this table is the fallback used when a price resolves to no tier. An
implementer who builds name-authoritative scoring from the table alone
reproduces the bug LOTTO-0009 removed.

**Amended by LOTTO-0009: this table maps an SMS to the one pool its name
states, which is the *top* tier only.** A PLUS game cannot be bought alone, so
a ticket is entered in every tier below its top one as well, and those tiers
are derived from the ticket price rather than from this table — see
`docs/specs/LOTTO-0009-entered-pools.md` §4.2–§4.3. `tickets.py::GAME_MAP` is
still exactly this table, and is still what `parse()` falls back to when a
price matches no tier, but `Ticket.pools` is what scoring iterates and
`Ticket.plus_flag` / `Ticket.pool_id` are now the top tier the **price** paid
for, which differs from the name on 5 of the 558 tickets.

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
  each winning independently. Locked by INV-2.

### 4.3 Two results sources

`history.py::all_draws()` merges them into one shape per draw:

```python
{"date": "YYYY-MM-DD", "main": [int], "special": int|None,
 "issue": int|None, "source": "api"|"archive"}
```

| Source | Covers | Has payouts | Module |
|--------|--------|-------------|--------|
| Sizekhaya JSON API | 2026-06-01 → | yes, per division | `results.py` |
| za.national-lottery.com | 2025-01-01 → | only per-draw pages | `backfill.py` |

Two conventions the merged shape depends on, neither derivable from it:

- **The special ball is last.** The API's `winNumList` places the bonus
  (Lotto) or PowerBall last; the archive instead derives the role from each
  ball's CSS class. `history.py::all_draws()` normalises both to `special`.
  Drawn order does not imply this - it is an observed contract of the feed.
- **Money units differ by source.** The API reports cents; archive payout
  pages report rands. Every amount leaving `check.py::amount()` is rands.

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

**An entry starting before the earliest known draw for its pool is not
scorable and must be excluded, never truncated.** `history.py::scorable()`
gates this and `covered()` returns empty for such an entry. Both take the pool
as an argument rather than reading it off the ticket, because a ticket can be
checkable in one pool and not another. Without the gate a 2022 ticket silently
takes the first N draws of 2025 - real draws, wrong ones - and every
count-based check still reports it as correct. **963 of 1233 entries** fall in
this window, on 426 of 558 tickets that fall in it wholly. A further 11 entries
are uncheckable for the *other* reason — `daily/1`, which no source publishes
(§4.2) — for 974 uncheckable entries in total. The two reasons are counted
separately and must stay that way: merging them is how "nobody publishes this"
starts reading as "the data does not go back far enough". `check.py` reports
both as uncheckable rather than as losses, at entry granularity
(LOTTO-0009 §4.6).

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
is part of the contract:

| | API (`matches`, uppercased and stripped) | archive payout table (column 2) |
|---|---|---|
| plain | `MATCH 3` | `3` |
| Lotto + bonus | `MATCH 3 + BONUS` | `3 + Bonus` |
| PowerBall + PB | `MATCH 3 + PB` | `3 + PowerBall` |

**Whether a line paid at all is gated by the *current* division set, in both
eras** — `check.py::check()` tests the match label against
`paying_combinations()` before `amount()` is reached. Only the amount is
era-specific. A pre-handover division with no current equivalent is therefore
dropped, not priced at zero. That is a known limit, not an oversight (§11).

Pre-handover draws did not share a single division structure: some list a
bottom tier of `2 + Bonus`, others a plain `2`. When the bonus-qualified
label is absent from a payout table, `check.py::amount()` falls back to the
plain match tier, which is the one that paid.

`tickets.py` parses, and since LOTTO-0009 also derives which pools a ticket was
entered in from its price - `check.py` is still the only scoring path.

## 5. Invariants

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
  *Breaks when:* either source renames a pool, so it contributes no overlap
  and the run passes on the strength of the other five. `daily:1` (Daily Lotto
  Plus) is exempt via `EXPECTED_EMPTY` — no source publishes it, so zero
  overlap is its correct state, not rot. The check fails any
  pool with zero overlap for that reason. The comparison is order-insensitive
  by design — the archive sorts ascending, the API preserves drawn order.

- **INV-4** — No file containing real SMS content is ever tracked by git.
  *Test:* `python3 tools/verify_privacy.py` → `17 tracked files, 0 leak(s) [content+pattern]`
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
  *Test:* `grep -nE '"MATCH [0-9]' *.py tools/*.py | wc -l` → `0`
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
  *Test:* `python3 tools/verify_pools.py` → `unpriceable-win guard: 4
  blind-lookup probes, 0 mispriced` (repo root, after `backfill.py`)
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
  to `{}`; a feed-side rename of the `MATCH n` grammar makes every label miss
  (the live form of §11's label-grammar row); or a future edit "simplifies"
  either branch back to a `.get(..., 0.0)` default.
  Measured 2026-08-02 before the change: 86 wins, 69 of them archive-era, **0
  priced at R0.00**, and all 67 distinct archive draws parsed — so real data
  cannot exercise this and the guard is driven by doubles. Figures after the
  change are identical (86 wins, R2,651.60, 62 claimable lines), which is the
  point: it is a latent-defect guard, not a repricing. Red-tested the same day
  by reverting the archive branch to `return 0.0` → 2 probes mispriced, exit 1.

## 6. Failure modes

- **The API changes shape or path.** `results.py::_post()` raises on any
  non-zero `code`, so scoring stops rather than reporting zero wins. The
  endpoints were reverse-engineered and carry no compatibility promise.
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
- **A ticket's price matches no board price on record.** `entered_pools()`
  returns unresolved, `pools` falls back to the single pool the game name
  states, and `check.py` prints the count — loudly, because that fallback is
  the project's pre-LOTTO-0009 behaviour and is invisible otherwise. It is the
  one path on which a tier the ticket never paid for could be scored.
  LOTTO-0009 INV-7 asserts the count is zero.
- **No division matches a win's label.** The line is **dropped**, not listed
  at zero: `check.py::check()` gates on `paying_combinations()` before
  `amount()` runs. `amount()`'s 0.00 return is reachable only for a label
  that passed the gate but is missing from that draw's payout table. Nothing
  detects a systematically wrong label either way (§11).
- **A pool has no recent draw record.** `paying_combinations()` raises rather
  than returning an empty set, because an empty set would score every line in
  the pool as a loss with no diagnostic.

## 7. Tests

**The counts in §5's expected outputs are as of 2026-08-01 and grow over
time** — overlap grows with every draw, ticket totals with every SMS. What
each invariant actually asserts is the zero-term and the exit code
(`0 disagree`, `0 with wrong draw coverage`, exit 0); a changed count is not
a failure — **except the unscorable count**, which has a 90% floor precisely
because "almost everything is unscorable" is what missing data looks like. Every script exits non-zero on a real breach, so prefer
`&& echo PASS` over string-matching the line.

Every script must be run **from the repository root, after
`python3 backfill.py`**, with the SMS dump present; they resolve their inputs
relative to the working directory.

`tools/verify_sources.py`, `tools/verify_coverage.py` and
`tools/verify_privacy.py` are this spec's executable checks, joined by
`tools/verify_pools.py` for LOTTO-0009's invariants; the remaining invariants
here are one-line commands recorded in
§5. There is no test framework in this project and adding one is out of scope
(§9) — these run under plain `python3`.

Red-tested against a state that should fail: INV-2's one-liner against the
pre-Multiplay scorer; INV-6's script against the parser that dropped
`draw(s)`, against the coverage bug that mis-scored 426 tickets, and against
a `scorable()` regressed to `bool(rows)`; INV-4's script against a real board
line pasted into `README.md`; INV-3's per-pool floor against an un-exempted
empty pool. Only INV-3's agreement assertion has no red test — the sources
have agreed on every run.

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
- The verified-but-unfixed tail from cold-eyes loop 3 — tracked by LOTTO-0007.
- Automatic ingestion of new tickets as they arrive — tracked by LOTTO-0003.
- A test framework; the four verify scripts are deliberately dependency-free.
- Tickets predating all draw data — 426 of 558. The gate is per pool (each
  pool's own earliest known draw, 2025-01-01 for the earliest), not a global
  date. The limit is a configured default, not a source limit —
  `backfill.build(years=(2025, 2026))` — and all are long past the 365-day
  claim deadline. They are excluded by `history.py::scorable()` and reported
  as uncheckable, not silently dropped. Extending coverage is LOTTO-0006.

## 10. Resource cost

**Python 3.8+** — the walrus operator is the highest feature used; developed
on 3.13. No `match`/`case` statement appears in any module
(`grep -rn "^\s*match .*:" *.py` → nothing). No third-party packages — standard library only. The KDE
Connect path additionally needs the distribution's `python3-dbus`, which is
not a Python dependency this project declares or installs.

**Disk:** `archive_cache/` holds 12 archive pages (6 pools × 2 years) plus
one payout page per draw a winning ticket touches — 3.7 MB measured
(`du -sh archive_cache`). Gitignored and regenerable, as is
`archive_results.json`.

**Network, per `check.py` run:** `results.py::draws()` is **not** memoised, so
`issueWinPoolInfoPageQuery` is called once per pool by `history.all_draws()`
and once per pool by `check.paying_combinations()` — **7 + 6 = 13 requests**
before anything is scored. Seven for `all_draws()`, one per pool; six for the
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
carries the breakdown and the before/after.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | §5 command, `tickets.py::parse()` |
| INV-2 | §5 command, `tickets.py::parse()` |
| INV-3 | `tools/verify_sources.py` |
| INV-4 | `tools/verify_privacy.py`; **not yet a pre-commit hook** — tracked by LOTTO-0004 |
| INV-5 | §5 grep — labels only; **nothing** catches a hardcoded prize *amount* |
| INV-6 | `tools/verify_coverage.py` |
| §4.3 special-ball-is-last | `tools/verify_sources.py` — catches a change on either source alone; blind only if both change the same way together |
| §4.4 expiry / `CLAIM_DAYS` | **nothing** — no test covers the 365-day boundary, and nothing tracks the gap |
| §4.4 current-era pay gate | **nothing** — a pre-handover-only division is dropped silently |
| §4.4 label grammar | **nothing** — a feed-side rename of `MATCH n` drops every win with no error |
| INV-22 unpriceable win raises | `tools/verify_pools.py` — four blind-lookup probes (empty and unrecognised division tables, both branches), plus the converse that a source-stated R0.00 still prices as 0.0 |
| archive payout scrape | `tools/verify_pools.py` (INV-22) — an unscrapable payout page now raises instead of pricing an archive win at R0.00. What remains unchecked is narrower: a page that parses into a **wrong** table, which is well-formed and not detectably wrong from inside |
| `backfill.py` date parsing | **nothing** — an abbreviated month in a href raises `KeyError`, not an empty result |
| Multiplay on non-Lotto games | `tools/verify_pools.py` (LOTTO-0009 INV-7) — the PowerBall branch is tested first, so a >6-number PowerBall board still becomes one line, but the price paid for more, so it resolves to no tier and exits non-zero. The wrong line *count* itself is still unchecked |
| §4.2 pools derived from price, not from the game name | `tools/verify_pools.py` (LOTTO-0009 INV-7, INV-8) |

## 12. Cross-doc impact

README.md (usage), ROADMAP.md (LOTTO-0002 onward), CHANGELOG.md, and
`docs/specs/LOTTO-0009-entered-pools.md`, which amends this document in §2,
§4.2, §4.4, INV-6, §7, §10 and §11 — it changed the unit of work from the
ticket to the entry.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 4 | 2026-08-01 | 2 | 0 | 3 | 6 | 8 | **Retrofit pass, after LOTTO-0009 changed the unit of work from the ticket to the entry.** All 17 verified findings fixed, 1 dismissed, 0 deferred. Both lanes independently found the same two HIGH items. First: §4.2 still said an implementer *"cannot derive `winPoolId` or `plusFlag` from anything else"* — false since `tickets.py::entered_pools()` derives both from the price, and the sentence sat directly above its own amendment, so a top-down reader was told the table was authoritative before being told it was not. Second: §4.4's *"(974 of 1233 entries)"* merged the two uncheckable reasons this project exists to keep apart — 963 entries predate their pool's data, and the other 11 are `daily/1`, which nobody publishes. Third HIGH: §11 still credited **nothing** with catching a >6-number PowerBall board when LOTTO-0009 INV-7 now exits non-zero on one, so two live contracts asserted opposite things about the same known defect. Also fixed: §10's 13-request budget was unreachable from what the document stated, because `paying_combinations()`'s memoisation was never mentioned and `check()` calls it once per scorable **entry** — an implementer building to the text would have fired 259 requests at a free public endpoint; §6's failure modes still excluded whole tickets; §6 had no failure mode at all for the shipped unresolved-price path; §9 said "the two verify scripts" where §7 names four; and INV-4's expected tracked-file count was two files stale. Dismissed on evidence: a lane read §11's `KeyError` claim against `backfill.py::payouts()`, which raises `IndexError` — the row is about `parse_page()`'s `MONTHS[...]` lookup, which does raise `KeyError`. |
| 1 | 2026-08-01 | 2 | 2 | 4 | 5 | 7 | All verified findings fixed. Both lanes independently found the same CRITICAL: 426 tickets predating all draw data were scored against Jan-2025 draws, invisible to INV-6 because its test was a tautology over `covered()`'s own slice. Fixed in code (`history.py::scorable()`), in the checks (INV-4 and INV-6 rewritten to be non-circular) and in the spec. Corrected the lifetime total R1,727.10 → R960.40; claimable R800.20 unaffected. |
| 2 | 2026-08-01 | 2 | 2 | 4 | 4 | 6 | All verified findings fixed. Both lanes independently found a real ticket reference (redacted; from the user's own messages) tracked in `README.md` — INV-4 reported 0 because its pattern was anchored on `Ref:`, which pasted program output drops. Scrubbed, pattern broadened, git history rewritten before any push. Also: §6 claimed an unmatched division is "listed at zero" when `check()` drops it before `amount()` runs; `paying_combinations()` returned `{}` for a pool with no recent draw, scoring the whole pool as losses silently (now raises); `verify_coverage.py` raised IndexError for a ticket newer than every known draw; §10 named an endpoint that does not exist and undercounted requests ~4×; §3 and §9 disagreed on whether the web UI is in scope. |
| 3 | 2026-08-01 | 2 | 3 | 4 | 2 | 5 | Converged by cap. Fixed: §4.2's four example SMSes were verbatim real messages (numbers, dates, amounts — only the reference had been scrubbed), now synthetic and verified absent from the dump; `Daily Lotto Plus` was aliased onto plain Daily Lotto's pool, scoring 11 tickets against another game (now an empty pool, reported uncheckable — claimable corrected R800.20 → R700.10); INV-6's check still imported `history.scorable()`, the predicate under test, so a regressed `scorable()` would have passed — now recomputed independently and red-tested, plus a 90% floor for missing data; added the game-name and division-label tables an implementer cannot derive; KDE Connect documented as inspection-only. Five verified findings deferred to LOTTO-0007. |
