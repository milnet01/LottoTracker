# Chunk 3 — verify_payouts.py + verify_periods.py

Lane return, verbatim (methodology prose dropped; findings unedited).
review-tests run 2026-09-02. Staleness check: injected CLAUDE.md matched disk.

## Findings

**[HIGH] [dim 1] tools/verify_payouts.py:188-192**
> ```
> a = check.reconcile(every, [], [_payout(SENTINEL, 500)])[0]
> ...
> assert a["category"] == "unexplained", (
> ```
This fixture is the file's only reference that is paid, fully scorable, and won
nothing — i.e. the only place where `computed_cents == 0` is produced. Nothing
asserts it. Across all eight cases the only three-valued assertion is
`assert n["computed_cents"] is None` (:170), which pins one direction only.

Consequence: change check.py:415-416's `elif any(scorable(...)): computed = 0`
to `computed = None` and EVERY case in this file still passes, because
`category` is decided by an independent ordered if-chain that never reads
`computed`. Downstream, check.reconcile_report() then moves that reference out
of `scored` into `unscorable` and prints "N references are OUTSIDE that
comparison: nothing could be scored, which is not a zero" about a reference
that WAS checked and won nothing — the cardinal rule broken on the money line,
in the direction it exists to prevent. The docstring claims INV-43 and
reconcile() names three values; only two are held.
Fix: one line — `assert a["computed_cents"] == 0` beside :190, and a BREAKS
entry (zero_becomes_none -> unscored_is_not_unexplained).

**[MEDIUM] [dim 1] tools/verify_periods.py:198**
> `got = serve.period_buckets([t], [], draws("2026-01-05", "2026-03-05"),`
period_buckets() states a rule the file does not exercise: "The key set comes
from the SPEND side; the win side only adds into keys that already exist. A win
whose period carries no spend is dropped rather than conjuring a bucket
(INV-60)" (serve.py:164-167), implemented as `if w["date"][:7] in months:` /
`if w["date"][:4] in years:` (serve.py:193-196).

No case supplies a win dated in a period with no spend. empty_period_is_absent
passes wins=[] at both call sites (:198, :207); periods_by_draw_date's win is
in April, which has spend; periods_over_checkable's stray win is removed
earlier by the resolved_refs filter; periods_reconcile asserts nothing on
won_cents. Replace both guards with setdefault and all four cases stay green.
No BREAKS entry covers it either.

Consequence: a win-conjured bucket renders spend R0.00 against a real win — a
period the ledger never charged for, presented as a period it won in. INV-60 is
held in one half only.
Fix: in empty_period_is_absent, pass a win for SENTINEL dated 2026-07-05 (no
draw, no spend) and assert "2026-07" not in m; register a bucket_from_win_only
break.

**[MEDIUM] [dim 12] tools/verify_periods.py:105**
> `    wins = check.check(all_tickets)`
periods_reconcile is the only case in this file that touches real data, and it
asserts on spend_cents and no_result_cents only (:126-130). Nothing it asserts
is derived from `wins`: the bucket key set comes from the spend side, and
won_cents is never read. Substituting [] for :105 changes no assertion.

That call drags in the expensive network path: check.check() ->
paying_combinations() (check.py:43, an UNCACHED results.draws(game, 50) POST
per (game, plus_flag, pool_id) key) and -> amount() -> divisions()
(check.py:214, one live POST per distinct winning draw). Without it only
history.all_draws is reached. The baseline puts this file at 37.6 s against a
suite median of ~8 s; those POSTs are the only heavy operation, and no
assertion depends on them.
Fix: either drop it and say the win side is INV-58/59's, or make the cost earn
its keep — assert that the summed won_cents over month buckets equals the total
of wins whose ref is resolved.

**[MEDIUM] [dim 12] tools/verify_payouts.py:244-246**
> ```
> real = sum(1 for r in check.reconcile(load(), check.check(load()), load_payouts())
>            if r["category"] == "unpaid")
> print(f"  {real} unpaid references against the real dump (printed, not asserted)")
> ```
Three extra full-dump parses (load() twice, load_payouts() once) and a second
complete check.check() pass over all 1,233 entries, for a value the line itself
says is not asserted. categories_partition (two cases earlier) already computes
recs = check.reconcile(tk, wins, payouts) over exactly this data and already
builds counts from it — counts.get("unpaid", 0) is the same number, already
paid for.

Consequence: the file's real-data work is roughly doubled to print a
diagnostic. Network is not re-paid (history._cache, check._struct,
results._divisions_cache are process-level), but the dump parse and the
entry x board x draw scoring loop are.
Fix: stash counts from categories_partition, or delete the line.

ORCHESTRATOR MEASUREMENT 2026-09-02 — per-case time and live POSTs for
verify_payouts (the lane's own suggested probe, run):
  multiple_payouts_sum          0.3s  +1 POST
  cents_not_floats              0.0s  +0
  disagreement_keeps_both       0.1s  +1
  unscored_is_not_unexplained   3.3s  +2
  categories_partition         27.8s  +30
  unpaid_carries_draw_date      0.2s  +0
  no_payouts_is_not_agreement   0.0s  +0
categories_partition is 27.8 s of the file's 35.5 s, and the :244-246 block
runs inside it. The cost claim is confirmed; the network half is capped at 30
POSTs by the process-level caches, exactly as the lane predicted.

**[MEDIUM] [dim 9] tools/verify_payouts.py:85 and tools/verify_periods.py:105/119**
> `    rows_ = all_draws(game, plus_flag)`
Plainly: YES, both files can fail for reasons that have nothing to do with the
code under test. history.all_draws -> results.draws -> results._post issues
HTTPS POSTs to https://www.nationallottery.co.za/api (results.py:18,
timeout=20, ATTEMPTS=3 with 1 s/2 s backoff). There is no mock, no fixture
recording, no on-disk cache for the API path, and no env gate. An outage, a
rate-limit, a TLS handshake failure past three attempts, or a schema change
reddens both — and since .githooks/pre-push runs local-CI.sh, that blocks a
push.

The asymmetry is worth naming: verify_periods proved synthetic cases can be
network-free — periods_by_draw_date, periods_over_checkable and
empty_period_is_absent inject draws() and increments() and touch nothing
external. verify_payouts' five equivalent synthetic cases are dragged onto the
network only because _scorable_start() calls all_draws to obtain a date, and
check.reconcile reads history.scorable directly.
Fix (test-side, no production change): seed history._cache[(game, pf)] with a
one-row stub for the synthetic cases and restore the real cache before
categories_partition runs. If the network dependence is accepted deliberately,
say so in the module docstring the way verify_periods:28-36 does — today it is
undeclared.

**[MEDIUM] [dim 4] tools/verify_payouts.py:284 and tools/verify_periods.py:224**
> `# Each break must make exactly the named case fail. Named in the *Test:* clauses.`
local-CI.sh contains no `--break` anywhere. So the eight breaks here and the
five in verify_periods are declared contracts with no execution point — a
registry the runner never reads.

Consequence: this project is greenfield on these items and both docstrings say
--break is the ONLY evidence the cases can be observed failing
(verify_periods:8-11). If a refactor made --break merge_unscored stop reddening
unscored_is_not_unexplained, nothing would ever notice; the evidence is a
one-off historical claim, not a standing one.
Fix: add a --breaks mode that loops every entry in BREAKS in a subprocess and
asserts each reddens its target, and give it one row in local-CI.sh's
data-dependent lane.

**[MEDIUM] [dim 1] tools/verify_payouts.py:168**
> `    unscorable = [_ticket(SYNTH_B, pools=((1, 101),), start="2020-01-01")]`
The fixture for the file's only three-valued assertion (computed_cents is None,
:170). lotto/1 is LOTTO PLUS 1 — a pool every source carries — so
unscorability rests entirely on 2020-01-01 being earlier than the archive's
first known lotto/1 draw. Nothing pins that: backfill.FIRST_YEAR is a knob, and
history.scorable's own docstring records that "LOTTO-0006 pushed the archive
back to the earliest purchase SMS" — the archive has already been extended
backwards once.

Consequence: re-running backfill.py with an earlier FIRST_YEAR makes
scorable(t, 1) true, computed becomes 0, and the case goes red with "a
reference nothing could score reports 0" — a false accusation against the
cardinal rule, the most expensive kind of failure message to misdiagnose. The
same file already knows the durable technique and says so at :182-184: "lotto/1
does NOT work here: it has draws", using daily/1 instead.
Fix: build the unscorable fixture from daily/1, so unscorability does not
depend on a date.

**[LOW] [dim 1] tools/verify_payouts.py:371-374**
> ```
> if want in failed:
>     print(f"RED-TEST OK: {want} failed under --break {broken}")
> ```
The runner returns 0 when the target is AMONG the failures, however many others
also failed — and unlike verify_periods, verify_payouts._apply_break patches
check.reconcile globally with no ACTIVE_CASE guard, while all eight cases call
it. verify_periods:236-240 records that this exact failure was measured here:
"a defect injected globally reddens whichever other cases happen to share the
code path ... Two of these did exactly that before the guard was added."

Consequence: a break that reddens three cases reports RED-TEST OK, so it no
longer proves that case observes that defect. Traced all eight breaks by hand
and none currently collides — but nothing detects it if one starts to.
Fix: `if failed == [want]` in both files' main().

## Dimensions scanned
- 1: 4 findings. On chunk question (b) — does each assertion exclude the defect
  its comment names, or is it one of the vacuous forms LOTTO-0029 warns about?
  EVERY CASE HERE PASSES THAT TEST, and three explicitly reject the vacuous
  form and say why (:116-118, :159-161, :196-198). This file is unusually
  disciplined on (b); its gap is (a). One redundancy, not a defect:
  `assert len(seen) == len(set(seen))` (:220) cannot fail while reconcile
  iterates sorted(set(paid) | set(won)), and `sum(counts.values()) ==
  len(union)` (:224) follows from the two assertions above it.
- 4: clean on registration, 1 finding on the break registry. verify_periods'
  five non-CASES defs are all genuine helpers, all called from inside the four
  cases. verify_payouts' non-CASES defs are likewise all reached.
- 5: 0 findings. No sleep, no threads, no timing assertions, no hash-order or
  filesystem-order comparisons. One unclosed handle at :107 (open() with no
  with) — one descriptor in a short-lived single-process run, no nameable
  consequence.
- 7: clean. No RNG, no uuid, no clock in any assertion. check.check() takes
  today=None -> datetime.now(), but that reaches only the expired/expires keys,
  which neither reconcile() nor period_buckets() reads. All fixture dates are
  literals. The real-data assertions are relational, so new draws arriving
  mid-run cannot flip them.
- 12: 2 findings.
- 6: clean. history._cache, check._struct and results._divisions_cache are
  shared across cases but are read-only caches of the same external data;
  ACTIVE_CASE and the monkeypatched serve.period_buckets/check.reconcile are
  never restored, but main() runs once per process.
  _apply_break("period_spend_is_lifetime") mutates t.resolved = True on
  caller-owned Ticket objects and never undoes it (verify_periods:261-262), but
  the ACTIVE_CASE guard confines it to periods_over_checkable, whose tickets
  are locally constructed — no leak with a consequence.
- 8: clean, and better than clean. No skip/xfail/disable markers.
  verify_periods:33-36 explicitly REFUSES a degraded skip for its one
  data-dependent case, on the grounds that a verifier silently skipping its
  rot-prone case is a trap — the correct call.
- 9: 1 finding.
- 11: clean. No pass/{}/TODO bodies; every case names a live symbol and reaches
  a real assertion.
- 14: clean. main()'s except AssertionError is the runner's reporting path, not
  a suppression around an assertion — every other exception propagates and
  aborts loudly. No verify=False, no bare except: pass, no warning filter, and
  no case mocks the layer it claims to exercise. verify_payouts:39-43 states
  outright that seven of eight breaks patch reconcile()'s OUTPUT rather than
  the production path — that is disclosure, not suppression.

## Noted, not mine
- history.all_draws caches on (game, plus_flag) but calls results.draws(game,
  400), which is NOT memoised (results.py:93-98, unlike divisions() at
  101-116). So one process fetches the same 400-record lotto payload three
  times, powerball twice and daily twice — seven POSTs where three would do.
  Source-side; review-code's.
- verify_payouts:212's `union = paid | (won & refs) | (won - refs)` reduces to
  `paid | won`. Harmless, and the independence the header claims is real.

## Possibly wider
- Five verifiers carry a BREAKS registry. The two break-machinery findings —
  never executed by the gate, and `want in failed` accepting collateral — very
  likely apply to all five. Did not open the other three.
- verify_payouts' pattern of a synthetic fixture reaching the live API only to
  satisfy history.scorable() probably recurs in verify_pools, verify_coverage
  and verify_sources.

## Open questions
- Per-case timing and network attribution: SETTLED by the orchestrator, see the
  measurement note above.
- Two breaks may be data-dependent red-tests: --break fold_residue_into_bucket
  only reddens periods_reconcile if the real dump's no_result_cents is
  non-zero, and --break drop_no_ticket only reddens categories_partition if the
  dump contains at least one no_ticket reference. NOT settled. (Orchestrator
  note: the real dump currently reports no_ticket = 1, so the second is armed
  today; no_result_cents was not separately measured.)
