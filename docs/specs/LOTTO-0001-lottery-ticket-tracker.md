# LOTTO-0001 — Track lottery tickets from SMS and score them against real draws

**Status:** spec draft (2026-08-01).
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
   lines once Multiplay entries are expanded. Most tickets run for 10 draws,
   so a single ticket is 10 separate checks per line. Only 132 are checkable
   at all — the other 426 predate every available draw record (§4.4).
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
| KDE Connect over Wi-Fi | `find_lotto_sms.py` | new tickets, live | on the PC |

The adb query filters with a SQL `WHERE` clause executed on the device, so
only lottery messages ever cross to the PC:

```bash
adb shell "content query --uri content://sms \
  --projection address:date:body \
  --where \"body LIKE '%lotto%' OR body LIKE '%powerball%'\""
```

KDE Connect cannot filter server-side — `activeConversations()` returns the
newest message of every thread — so `find_lotto_sms.py` matches keywords
locally and calls `requestConversation()` only for threads that hit.

### 4.2 Parsing two SMS eras

`tickets.py::parse()` accepts both. The distinguishing feature is the date
line, not the header:

```
old   Standard Bank: Played R10.00 Lotto Plus 2 for 1 draw(s)
      Date 09/11/2022 to 09/11/2022
      A: 02 03 26 36 45 52

new   Standard Bank: Played R300.00 Powerball
      Date 12 Jun 2026 (for 10 draws)
      A: 02 18 22 32 48 -03
```

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

`check.py::check()` walks every ticket × board × covered draw. A ticket
covers the first N draws on or after its start date, taken from real draw
data rather than a computed calendar, so a cancelled or moved draw cannot
shift the window (INV-6).

**A ticket starting before the earliest known draw for its pool is not
scorable and must be excluded, never truncated.** `history.py::scorable()`
gates this and `covered()` returns empty for such a ticket. Without the gate
a 2022 ticket silently takes the first N draws of 2025 - real draws, wrong
ones - and every count-based check still reports it as correct. 426 of 558
tickets fall in this window; `check.py` reports them as uncheckable rather
than as losses.

Prize expiry uses `check.py::CLAIM_DAYS = 365`, the SA claim deadline. A win
older than that is counted in the lifetime total but not listed individually,
and never in the claimable total.

Prize divisions are never hardcoded. For API draws they come from
`getIssueDrawResultDetail`; for archive draws from that draw's payout page.
`check.py::paying_combinations()` reads the paying set from a live draw
**per pool**, not per game - Lotto 5 Max and PowerBall XTRA do not share the
base pool's divisions, and one lookup applied to all of them drops wins whose
division exists only in the pool they were won in.

**Whether a line paid at all is gated by the *current* division set, in both
eras** — `check.py::check()` tests the match label against
`paying_combinations()` before `amount()` is reached. Only the amount is
era-specific. A pre-handover division with no current equivalent is therefore
dropped, not priced at zero. That is a known limit, not an oversight (§11).

Pre-handover draws did not share a single division structure: some list a
bottom tier of `2 + Bonus`, others a plain `2`. When the bonus-qualified
label is absent from a payout table, `check.py::amount()` falls back to the
plain match tier, which is the one that paid.

`tickets.py` parses and nothing else - `check.py` is the only scoring path.

## 5. Invariants

- **INV-1** — For PowerBall tickets the final number on a board line is the
  PowerBall, never a main number, in both SMS eras.
  *Test:* `python3 -c "from tickets import parse; t=parse('Standard Bank: Played R7.50 Powerball Plus for 1 draw(s)\nDate 11/11/2022 to 11/11/2022\nA: 01 13 30 31 49 09\nRef:VAS1.'); print(t.boards)"` → `[('A', [1, 13, 30, 31, 49], 9)]`
  *Test (new era):* `python3 -c "from tickets import parse; t=parse('Standard Bank: Played R300.00 Powerball\nDate 12 Jun 2026 (for 10 draws)\nA: 02 18 22 32 48 -03\nRef:VAS3.'); print(t.boards)"` → `[('A', [2, 18, 22, 32, 48], 3)]`
  *Breaks when:* a parser change treats the six numbers as all-main, making
  every PowerBall ticket score one match too many and never match the PB.

- **INV-2** — A Lotto board carrying more than six numbers expands to one
  line per 6-number combination, each scored independently.
  *Test:* `python3 -c "from tickets import parse; t=parse('Standard Bank: Played R700.00 Lotto game\nDate 08 Jul 2026 (for 10 draws)\nA: 21 23 26 29 35 45 47\nRef:VAS2.'); print(len(t.boards))"` → `7`
  *Breaks when:* the seven picks are scored as a single line, undercounting
  winnings — measured at R107.50 against a correct R392.20 on one ticket.

- **INV-3** — Where the two sources cover the same draw they report the same
  numbers, so merging them cannot introduce a contradiction.
  *Test:* `python3 tools/verify_sources.py` → `148 overlapping draws, 148 agree, 0 disagree`
  *Breaks when:* either source renames a pool, so it contributes no overlap
  and the run passes on the strength of the other five. The check fails any
  pool with zero overlap for that reason. The comparison is order-insensitive
  by design — the archive sorts ascending, the API preserves drawn order.

- **INV-4** — No file containing real SMS content is ever tracked by git.
  *Test:* `git grep -nE '\bVAS[0-9]{6,}' -- . | grep -cv VAS00000000000` → `0`
  *Breaks when:* a dump is committed under a name `.gitignore` does not
  match, **or a real reference is pasted into prose**. The pattern must not
  be anchored on `Ref:` — that prefix belongs to the dump format, and pasted
  program output drops it. An earlier `Ref:VAS…` form reported 0 while
  `README.md` carried a real reference from the user's own messages
  (found 2026-08-01, loop 2). Sample references in tracked docs must be
  obviously fake (`VAS00000000000`). The repo is public, so a breach
  publishes the user's messages. A filename-based check is strictly weaker:
  it only restates `.gitignore` and passes on `messages_backup.txt`.

- **INV-5** — Which match combinations pay is read from the results source at
  runtime, never hardcoded in this project.
  *Test:* `grep -nE '"MATCH [0-9]' *.py tools/*.py | wc -l` → `0`
  *Breaks when:* someone inlines an SA prize table; the game's divisions
  changed at the 2026-06-01 handover and would silently rot again. Catches a
  hardcoded division *label* only — it cannot see a hardcoded prize amount,
  which nothing checks (§11).

- **INV-6** — A ticket is scored against the first N drawn results on or
  after its start date, where N is the draw count in its SMS.
  *Test:* `python3 tools/verify_coverage.py` → `558 tickets, 426 unscorable (excluded), 0 with wrong draw coverage`
  *Breaks when:* a ticket predating all draw data is truncated onto later
  draws instead of excluded, or the window is computed from a weekday
  calendar so a skipped draw shifts every later match. The check asserts
  start-alignment and contiguity against the draw records directly; asserting
  `len(covered(t)) == t.ndraws` is a tautology over the function's own slice
  and passed while 426 tickets were mis-scored.

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
- **A ticket predates all draw data.** Excluded by `history.py::scorable()`
  and reported by `check.py` as uncheckable. It is never scored against later
  draws, and never counted as a loss.
- **A ticket's window runs past the last known draw.** Scored over the draws
  that exist so far. `tools/verify_coverage.py` distinguishes this from a real
  gap, including the case where a ticket is newer than every known draw and no
  draws are available at all; `check.py` itself does not report the shortfall.
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
a failure. Both scripts exit non-zero on a real breach, so prefer
`&& echo PASS` over string-matching the line.

`tools/verify_sources.py` and `tools/verify_coverage.py` are the two
executable checks; the remaining invariants are one-line commands recorded in
§5. There is no test framework in this project and adding one is out of scope
(§9) — these run under plain `python3`.

Red-tested against the pre-fix state: INV-2's one-liner against the
pre-Multiplay scorer, INV-6's script against both the parser that dropped
`draw(s)` and the coverage bug that mis-scored 426 tickets, and INV-4's
command against a dump committed as `messages_backup.txt`. INV-3's script has
no pre-fix red test — the sources have agreed on every run.

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
- Automatic ingestion of new tickets as they arrive — tracked by LOTTO-0003.
- A test framework; the two verify scripts are deliberately dependency-free.
- Tickets predating all draw data — 426 of 558. The gate is per pool (each
  pool's own earliest known draw, 2025-01-01 for the earliest), not a global
  date. Neither source reaches them and all are long past the 365-day
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
and again per pool by `check.paying_combinations()` — about 12 requests before
anything is scored. Then one `getIssueDrawResultDetail` per pool to establish
its paying set, plus one per distinct `(game, issue, pool, plusFlag)` a win
lands on. `divisions()` **is** memoised, so a 7-line Multiplay ticket over 10
draws costs at most 10 detail requests, not 70. Archive payout pages are
cached to disk; only a first run fetches them.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | §5 command, `tickets.py::parse()` |
| INV-2 | §5 command, `tickets.py::parse()` |
| INV-3 | `tools/verify_sources.py` |
| INV-4 | §5 command; **no automated hook** — tracked by LOTTO-0004 |
| INV-5 | §5 grep — labels only; **nothing** catches a hardcoded prize *amount* |
| INV-6 | `tools/verify_coverage.py` |
| §4.3 special-ball-is-last | `tools/verify_sources.py` — catches a change on either source alone; blind only if both change the same way together |
| §4.4 expiry / `CLAIM_DAYS` | **nothing** — no test covers the 365-day boundary, and nothing tracks the gap |
| §4.4 current-era pay gate | **nothing** — a pre-handover-only division is dropped silently |

## 12. Cross-doc impact

README.md (usage), ROADMAP.md (LOTTO-0002 onward), CHANGELOG.md.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 1 | 2026-08-01 | 2 | 2 | 4 | 5 | 7 | All verified findings fixed. Both lanes independently found the same CRITICAL: 426 tickets predating all draw data were scored against Jan-2025 draws, invisible to INV-6 because its test was a tautology over `covered()`'s own slice. Fixed in code (`history.py::scorable()`), in the checks (INV-4 and INV-6 rewritten to be non-circular) and in the spec. Corrected the lifetime total R1,727.10 → R960.40; claimable R800.20 unaffected. |
| 2 | 2026-08-01 | 2 | 2 | 4 | 4 | 6 | All verified findings fixed. Both lanes independently found a real ticket reference (redacted; from the user's own messages) tracked in `README.md` — INV-4 reported 0 because its pattern was anchored on `Ref:`, which pasted program output drops. Scrubbed, pattern broadened, git history rewritten before any push. Also: §6 claimed an unmatched division is "listed at zero" when `check()` drops it before `amount()` runs; `paying_combinations()` returned `{}` for a pool with no recent draw, scoring the whole pool as losses silently (now raises); `verify_coverage.py` raised IndexError for a ticket newer than every known draw; §10 named an endpoint that does not exist and undercounted requests ~4×; §3 and §9 disagreed on whether the web UI is in scope. |
