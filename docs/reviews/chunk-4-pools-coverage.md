# Chunk 4 — verify_pools.py + verify_coverage.py

Lane return, verbatim (methodology prose dropped; findings unedited).
review-tests run 2026-09-02.

CLAUDE.md staleness check (lane's own): injected copy matched the file on disk
on every sentence probed, including CLAUDE.md:19 and :294-296. No correction.

## Findings

**[HIGH] [dim 1] tools/verify_coverage.py:81 (runs to :89)**
> `if rows and rows[0]["date"] != after[0]["date"]:`
> `span = [d for d in known if rows[0]["date"] <= d["date"] <= rows[-1]["date"]]`

Every one of the five properties compares only the `date` key of a draw record.
Nothing in the file ever reads `main`, `special`, `issue` or `source`, and no
row is compared for identity with the row in `known` it is supposed to be.
Within a game the pools are drawn in one event and therefore share dates —
`history.POOL_NAMES` maps ("lotto",0/1/2) to LOTTO, LOTTO PLUS 1 and LOTTO 5
MAX out of one feed keyed on the same `drawTime`, and the archive keys them
`lotto:0/1/2` by the same date string. So a `covered()` that dropped its
`plus_flag` argument, or a caller passing `ticket.plus_flag` (the top tier)
instead of the entry's pool, returns the *wrong pool's* records on the *right
dates*: start date matches, first-covered matches `after[0]`,
`len(span) == len(rows)`, the count rule holds, and verify_coverage prints
"0 with wrong draw coverage". Every Plus entry would then be scored against the
base game's numbers. That is exactly INV-6's failure, and the file's own
docstring claims these are "asserted against the draw records directly, never
against the shape of what covered() returned" — which is only half true.
Fix: compare the records, not the dates — `rows == after[:t.ndraws]` (dict
equality carries main/special/issue/source), which subsumes properties 2, 3
and 4 and still allows a short window at the end of the draw list.

ORCHESTRATOR CONFIRMATION 2026-09-02: grep over verify_coverage.py returns only
`["date"]` comparisons at :61, :68, :74, :81, :85, :90. No other record key is
read anywhere in the file. Finding confirmed by inspection.

**[HIGH] [dim 4] tools/verify_pools.py:120 (runs to :149)**
> `name, bought = facts.get(t.ref, (None, None))`
> `if bought is not None and bought != t.bought:`

The ERA cross-check — the one thing asserting that the parser reads the era off
the SMS timestamp rather than falling back to the first draw date — is guarded
by `bought is not None`, and `bought` comes from `dump_facts()`. `dump_facts()`
is a **second, independent reader of the dump format**: its own
`re.split(r"^Row: \d+ address=", ...)` at :87 and its own copy of tickets.py's
head regex at :91-93, while tickets.py:273 declares `rows()` "The dump format's
ONE reader" precisely because "two readers of one format agree today and drift
later". If a bank wording change or a dump-format change makes that regex miss
— the very event the era check exists for — `facts` comes back empty or
partial, every comparison is skipped, `disagree` stays at zero, and the summary
prints "0 name/price disagreements" and exits 0. A run that checked nothing is
byte-identical to a healthy one. The file already applies the correct pattern
twice, 130 lines later (:274-282, and the NO DIVISIONS branch at :309).
Fix: floor it the same way — if `len(facts) < len(tickets)`, print the
shortfall and count it into `bad`.

ORCHESTRATOR MEASUREMENT 2026-09-02: dump_facts() returns 561 entries against
561 tickets; 0 tickets would have the ERA check skipped. The check IS firing
today. The finding is the absent floor, not a live blind spot.

**[MEDIUM] [dim 4] tools/verify_pools.py:186 (runs to :203)**
> `partly = [t for t in tickets if any(reaches(t, pf) ...) and not all(...)]`
> `wrong = [t for t in partly if t in counts["wholly"]]`

The entire INV-11 half of this file is `wrong` and `double`, and `wrong` cannot
be non-empty unless `partly` is non-empty. The known population of partly-
uncheckable tickets is the 11 Daily Lotto Plus tickets, which exist only
because `GAME_MAP` maps "daily lotto plus" to a pool no source carries. A
GAME_MAP/parse() regression that drops those tickets — LOTTO-0031's exact
shape — empties `partly`, and the run prints "0 partly-uncheckable tickets, 0
reported as wholly uncheckable" and exits 0. Failure mode 2 in this file's own
docstring then has no detector, killed by the same event that most needs one.
`double` is weaker still: check.uncheckable_report builds `partly` and `wholly`
as complementary comprehensions over one list (check.py:311-312), so their
intersection is empty by construction and that line cannot fire against the
current implementation.
Fix: floor `partly` exactly as `pools` is floored at :281.

ORCHESTRATOR MEASUREMENT 2026-09-02: verify_pools.py prints "11 partly-
uncheckable tickets, 0 reported as wholly uncheckable, 0 double-counted". The
population is non-empty and the check IS firing today.

**[MEDIUM] [dim 9 + dim 5] tools/verify_coverage.py:54 and tools/verify_pools.py:109, :298**
> `known = all_draws(t.game, plus_flag)` -> results.py:18
> `API = "https://www.nationallottery.co.za/api"`

Yes, both of these tests can fail for reasons that have nothing to do with the
code under test, and almost nothing bounds it. Every `all_draws()` and every
`paying_combinations()` call POSTs to a third party's live production endpoint;
verify_pools additionally reaches `backfill.payouts()`, which scrapes
za.national-lottery.com payout pages. Both files sit in local-CI.sh's local
lane, which .githooks/pre-push runs, so a lottery-site outage, a rate limit, a
TLS hiccup or a feed schema change blocks every push. `results._post` retries
3x behind a 20s timeout, so a dead endpoint costs up to ~63s per call and then
aborts the verifier with an unhandled exception; verify_coverage alone makes
six such calls. What IS bounded: the payout-page scrape is disk-cached under
archive_cache/, and results.divisions is memoised. What is not bounded at all:
the draw feed, refetched every run, with no recorded fixture, no offline mode
and no "ran against cached data" signal. Blast radius on the third party is
read-only query load with no credentials, which is why this is MEDIUM.
Fix: persist the feed to a gitignored cache the way archive_cache/ already
works, have the verifiers print which mode they ran in, and have local-CI.sh
assert "fetched live" — the identical pattern it already applies to
verify_privacy at :196-201.

**[LOW] [dim 12] tools/verify_coverage.py:54**
> `known = all_draws(t.game, plus_flag)`

Measured 11.2s standalone, essentially all of it network. history.all_draws
memoises per (game, plus_flag), but results.draws has no cache (contrast
results.py:101 _divisions_cache), so the six pools issue six 400-draw POSTs of
which only three are distinct requests — lotto/0, lotto/1 and lotto/2 each POST
the identical draws("lotto", 400) body. Roughly half the runtime of a 13-check
pre-push gate is a duplicated fetch.
Fix: memoise results.draws on (game, count) as divisions already is. LOW
because the fix is in the code under test, not the test.

**[LOW] [dim 4] tools/verify_coverage.py:96 (with :43 and :107)**
> `if entries and unscorable / len(entries) > 0.90:`

On a dump that exists but yields nothing — truncated, or recreated empty by a
failed watch_sms.py append — `expected` is 0 and `len(tickets)` is 0, so PARSE
GAP does not fire; `entries` is empty, so the 90% floor is guarded off; the
script prints "0 tickets, 0 entries, 0 unscorable, 0 with wrong draw coverage"
and returns 0. INV-6 reports green having verified nothing. (A *missing* dump
is safe — tickets.load() raises loudly.) Mitigated at suite level only:
verify_pools' "NO LIVE POOLS" floor at :281 turns the same run red, so
./local-CI.sh still fails — but the per-file signal is wrong and CLAUDE.md
documents running these individually.
Fix: `if not tickets: bad += 1`.

## Pre-pass verdicts
- None supplied for this chunk; nothing to confirm.

## The four chunk-specific questions

(a) Would verify_pools go red if the operator changed a price? YES — a
genuinely independent check, not a table checked against itself.
verify_pools.CUMULATIVE (:50-57) is transcribed in running-total form (lotto
500/750/1000) while tickets.TIER_PRICES (:76-84) holds per-tier increments
(500/+250/+250), and expected_pools() (:60-71) re-derives the answer rather
than calling entered_pools(). A board-price change reaches the dump as a ticket
whose unit matches neither table -> UNRESOLVED -> exit 1; a wrong edit to
TIER_PRICES alone makes t.pools != want -> POOLS -> exit 1; a ticket reaching
the right pools by the name-only fallback is caught by UNFLAGGED at :141-145.
Caveat, not a finding: the two transcriptions share the derivation, so a change
in HOW the bank prices would be seen as UNRESOLVED rather than diagnosed.

(b) Are the doubles faithful? Checked every double against the fields its
consumer actually reads. `class _T: game = "lotto"` (:219-220) — check.amount()
reads only ticket.game. The archive/api draw dicts (:222-223) carry
date/issue/source; amount() reads draw["date"] and draw["issue"] and nothing
else. The divisions double {"matches","winAmount"} matches amount():214-217
exactly; the payouts double {"6": 1.0} matches the table[exact]/table[plain]
shape at :224-230. The check.draws double at :358-360 now carries winPoolName,
plusFlag and wagerIssue, and paying_combinations reads winPoolName and
wagerIssue — so the incompleteness is repaired and the double is now a superset
of what is read. NO DOUBLE IN THIS FILE IS THINNER THAN THE OBJECT IT STANDS
IN FOR.

(c) See the first HIGH. Yes: the assertion can pass while an entry was scored
over the wrong draws, because "wrong" here can mean the right dates from the
wrong pool, and only dates are compared.

(d) See the MEDIUM dim 9/5 finding.

## Dimensions scanned
- 1: 1 finding. The `double` list at verify_pools:194 is additionally
  non-firable against the current uncheckable_report implementation — folded
  into the dim 4 finding rather than double-counted.
- 4: 3 findings. Neither file has a CASES registry; both run inline in main().
  Skippable-while-green checks named: the ERA + name/price census
  (verify_pools:120-149), the INV-11 wrong/double pair (:186-198), and the
  whole of verify_coverage on an empty-but-present dump. Everything else in
  verify_pools is self-flooring.
- 5: 1 finding (shared with dim 9). No sleep, no threads, no hash-order or
  timing assertions; the flakiness is entirely the un-mocked feed.
- 6: clean. verify_pools rebinds check.payouts, check.divisions, check.draws
  and check.paying_combinations and clears check._struct/_retired, and every
  block restores the originals in a finally (:247-248, :374-376, :443-445).
  Loop-variable capture uses default args (_g=game at :358, _drop=drop at
  :426), so no late-binding leak. Only cost: the finally at :376 discards the
  real division tables, forcing the retired-division sweep at :394 to refetch.
- 7: clean. No now(), no RNG, no uuid; HANDOVER is a fixed datetime.
- 8: N/A — no skip, xfail or disable markers.
- 9: 1 finding — the target is a third party's live production site, not a
  sandbox, and there is no gate on its availability.
- 11: clean — no empty or TODO bodies.
- 12: 1 finding (verify_coverage at 11.2s measured).
- 14: clean. The three `except RuntimeError` blocks are the assertion rather
  than a suppression: :239 and :369 record the raise as the expected outcome
  and are each paired with a converse probe (:243-245, :346-347); :302-308
  reports the raise into `unreachable` and continues, naming which raise.

## Noted, not mine
- results.py:19-24 sends a spoofed Chrome User-Agent with Origin/Referer to a
  third party. Code under test; a review-code/policy question.
- results.py:93 draws() is un-memoised while divisions() at :101 is; that
  asymmetry is what makes verify_coverage 11.2s.
- check.py:194-235 amount() reads only ticket.game off its first argument,
  which makes verify_pools' one-attribute _T double legitimate rather than
  sloppy. Recorded so a later reader does not "fix" the double.

## Possibly wider
- The date-only coverage comparison probably recurs in verify_periods.py. If it
  compares buckets by date rather than by record, the same wrong-pool
  substitution would pass there too. Hypothesis; not read.
- dump_facts() being a second reader of the dump format suggests other
  verifiers may have their own third and fourth readers, against tickets.py:273's
  explicit one-reader rule. verify_privacy.py and verify_payouts.py are likely.
- The live-feed dependency is shared by every verifier reaching
  history.all_draws — verify_sources, verify_periods, verify_payouts and
  verify_expiry as well, so the push-gate exposure is suite-wide.

## Open questions (settled by the orchestrator — see the two measurement notes
above; both checks are firing today, so both findings are missing floors rather
than live blind spots).
