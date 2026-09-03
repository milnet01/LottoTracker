# Chunk 5 — verify_expiry.py + verify_sources.py

Lane return, verbatim (methodology prose dropped; findings unedited).
review-tests run 2026-09-02. Staleness check: injected CLAUDE.md matched disk
(distinguishing sentence re-read at lines 19-21, identical).
One-hop reads: expiry.py, supervise.py:145-410, tickets.Ticket, history
(all_draws/covered/scorable/POOL_NAMES), results.draws/_post.

## Findings

**[HIGH] [dim 1] tools/verify_expiry.py:256 (runs to 261)**
> ```
> forbidden = {
>     "reference": SENTINEL, "board numbers": "1, 2, 3",
>     "cost": "60", "purchase date": "2026-08-21", "plural draws": "draws",
> }
> ```
The case is named notice_names_nothing_else and INV-54 is "the game, the final
draw date and the number of draws left, and NOTHING else". The assertion is a
BLOCKLIST of five literal strings, not a whitelist, so it verifies "and not
these five renderings" rather than the claim it is named for. The most likely
leak escapes it: supervise.expiry_notice() already formats a date by hand via
_DAY_NAMES/_MONTH_NAMES (supervise.py:186-192), so a purchase date added the
way that function formats dates renders "Fri 21 Aug" — which does not contain
"2026-08-21" and passes. Same for board numbers rendered without commas
("1 2 3 4 5" does not contain "1, 2, 3").

Consequence: the one test holding the bound on LOTTO-0034 s3.3's deliberate
privacy exception, in a repo intended to be public, goes green on a widened
notice.
Fix: assert the notice EQUALS the expected sentence — expiry_notice() is a pure
function of three values, so the exact string is constructible; keep the
blocklist as a second line of defence.

**[MEDIUM] [dim 1] tools/verify_expiry.py:96**
> `assert share >= 0.98, f"{game}: only {on}/{len(rows)} draws on a listed day"`
INV-49's two directions are not measured over the same window. The removed-day
direction is correctly scoped to 90 days from the record's newest draw
(:98-106); the added-day direction divides by len(rows) — the ENTIRE merged
record, which for lotto is every archived draw back to backfill.FIRST_YEAR. A
genuinely added weekly draw day contributes ~1 row per week against a
denominator in the high hundreds, so it needs roughly 0.02*N weeks — months —
to cross the 2% floor, while every projected final_draw_date is wrong from day
one. For daily, DRAW_DAYS["daily"] = set(range(7)) makes this half
unconditionally true, so it asserts nothing at all. No --break exercises this
direction: unlisted_draw_day adds {0}, which trips the 90-day half.
Fix: compute share over the same 90-day window as seen, keeping the
whole-record ratio only as reported detail.

ORCHESTRATOR MEASUREMENT 2026-09-02: the live denominators are
lotto 485/486, powerball 487/487, daily 1701/1701. The dilution argument is
confirmed — one added weekly lotto draw day needs ~10 rows against 486 to cross
2%, i.e. about two and a half months. And daily at 1701/1701 with all seven
days listed confirms that half asserts nothing.

**[MEDIUM] [dim 4 . dim 5] tools/verify_expiry.py:460**
> `        except AssertionError as e:`
main()'s case loop catches AssertionError only. Every other exception
propagates out of main() and aborts the run. The first case in CASES is
calendar_matches_history, which reaches the live API through history.all_draws
-> results.draws -> _post (raises URLError/SSLError/HTTPError after 3
attempts). Consequence: a transport blip on that first call means the eight
later cases — SEVEN of which are pure and need no network — never execute, and
the operator gets one traceback instead of "8 PASS + 1 network failure".
expiry.DRAW_DAYS[game] at :92 raises KeyError on a missing game and does the
same. No false green (exit is still non-zero), but the run stops reporting.
Fix: catch Exception per case, record it as a FAIL with the exception text, and
continue.

**[MEDIUM] [dim 6] tools/verify_expiry.py:71 (used at 8 call sites)**
> `    return os.path.join(tempfile.mkdtemp(prefix="lotto-expiry-"), "warned.json")`
Nothing removes these. A green run leaves 8 /tmp/lotto-expiry-* directories
behind, and the pre-push gate runs on every push. The one created at :217 is
passed real = load(), so supervise._write_warned() writes the REAL dump's VAS
references into it (records.append({"ref": t.ref, ...}), supervise.py:357).
Mode is 0600 under a 0700 dir, so this is accumulation rather than exposure —
but it puts real ticket references outside the repo where verify_privacy.py,
which compares TRACKED files against the dump, structurally cannot see them,
and the module's own docstring (:25-29) claims care on exactly this point.
Fix: one mkdtemp per run, subdirectories under it, and shutil.rmtree in main()'s
finally.

**[MEDIUM] [dim 7] tools/verify_sources.py:26 and :33**
> `    archive = json.load(open(ARCHIVE))`
> `        for r in draws(game, 400):`
The two sides age at different rates. archive_results.json is frozen until
someone re-runs backfill.py by hand; the API side is the most recent 400
records, which slides forward with wall-clock time. Once the sliding window's
oldest record passes the archive's newest draw, `date not in rows` is true for
every row, overlap == before for every pool, and the run prints "NO OVERLAP
<pool> - renamed pool, or archive missing this game" and exits 1. Order of
magnitude: 400 records / pools-per-game / draws-per-week is ~13 months for
daily, ~15 for lotto. So the gate eventually goes red as a function of ELAPSED
TIME SINCE THE LAST BACKFILL, and the message names the wrong cause. The
sibling file in this chunk solves precisely this — calendar_matches_history
measures its window from rows[-1]["date"] "rather than from today", and its
docstring says why (verify_expiry.py:83-86).
Fix: anchor the API fetch to the archive's newest date (or fetch until the
windows overlap), and distinguish "no overlap — archive is stale, re-run
backfill.py" from "no overlap — pool vanished".

**[LOW] [dim 1] tools/verify_sources.py:20 (used at :52)**
> `EXPECTED_EMPTY = {("daily", 1)}`
The exemption is bounded in what it suppresses — it only skips the zero-overlap
floor, and a pool with overlap is still compared, so a disagreement cannot be
hidden by it. But it is ONE-DIRECTIONAL: nothing asserts that an exempted pool
is genuinely absent from both sources. So an entry added here is never
falsified, and a pool silenced because it broke stays silenced for good. That
is the same shape this project forbids for its other hardcoded table
(DRAW_DAYS, checked "in BOTH directions ... because a check that only asks 'do
the draws land on listed days' passes a REMOVED day forever", expiry.py:44-45).
Fix: fail when a pool in EXPECTED_EMPTY DOES contribute overlap.

**[LOW] [dim 1] tools/verify_expiry.py:218**
> `    assert len(notices) == len(eligible), (`
Counts only. A selector that picked a different set of the same size passes.
The identity comparison is available: build the expected notice strings from
eligible via supervise.expiry_notice(...) and compare as multisets. (The refs
deliberately cannot appear in a notice, per INV-54, which is presumably why
length was chosen — the reconstruction route sidesteps that.) The case is not
vacuous regardless: the constructed `dead` ticket at :223-225 is unconditional
and is what catches --break no_lower_bound.
Fix: compare the sorted expected-notice list, not the length.

ORCHESTRATOR MEASUREMENT 2026-09-02 — THIS ESCALATES. At the frozen
TODAY = 2026-08-22, the number of real tickets with 0 < draws_left <= 2 is
ZERO. So `len(notices) == len(eligible)` is currently `0 == 0`: the selection
rule — which tickets get a re-buy warning, the project's PRIMARY job — has no
live assertion from the real dump at all. The `dead` ticket check the lane
names does still fire, so the CASE is not vacuous; this specific assertion is.

**[LOW] [dim 5 . dim 9] tools/verify_sources.py:33**
> `        for r in draws(game, 400):`
Inside the per-pool loop, so results.draws — which is NOT memoised, unlike
results.divisions — is called once per entry in POOL_NAMES: 7 live POSTs to a
third party's production endpoint for 3 distinct queries, 4 of them exact
duplicates at pageSize 400. That is 7 independent chances for a transport
failure to abort the run, and the project's own code calls out this cost —
divisions() is memoised because 70 identical POSTs "to a free public endpoint"
was unacceptable (results.py:110-113). The network dependency itself is
intrinsic to INV-3 and is not the finding.
Fix: hoist draws(game, 400) to one fetch per game outside the pool loop.

**[LOW] [dim 5] tools/verify_sources.py:39**
> `            nums = [int(n) for n in r["winNumList"]]`
No guard, where the other consumer of the same field has one and explains it:
history.all_draws uses r.get("winNumList") or [], catches TypeError/ValueError,
and skips empty lists because "a draw the feed lists before it happens carries
no numbers ... int() raising here takes out every consumer of this module at
once" (history.py:66-75). Here an empty list makes nums[-1] raise IndexError
and a None makes the comprehension raise TypeError, uncaught, out of main().
Narrow in practice — `if date not in rows: continue` runs first — but the
failure is a traceback rather than a DISAGREE line.
Fix: mirror history.py's guard and continue with a printed SKIPPED line.

**[LOW] [dim 1] tools/verify_expiry.py:465 (runs to 471)**
> `        if want in failed:`
> `            print(f"RED-TEST OK: {want} failed under --break {broken}")`
The red test asserts only that the NAMED case is among the failures; a break
that also takes out unrelated cases still returns 0. Not hypothetical here:
--break unlisted_draw_day mutates the shared expiry.DRAW_DAYS["lotto"] dict in
place (:386), which every later case reads — adding Monday shifts
final_draw_date earlier for Lotto, so calendar_matches_real_draws' exactness
ratio drops and that case goes red too, while the run still prints RED-TEST OK.
Consequence: the docstring's claim that --break "applies ONE deliberate defect"
(:7, :377) is not held by anything, so a future break that is too coarse is
indistinguishable from a precise one — and coarseness is what makes a red test
stop proving the case is sensitive to its OWN defect.
Fix: in break mode assert failed == [BREAKS[broken]], not membership.

## Chunk-specific questions (a)-(d)

(a) Determinism / injected `today` — CLEAN, and unusually well done.
TODAY = datetime.date(2026, 8, 22) is a module constant (:61). Nothing in
either file calls datetime.date.today(), datetime.now(), time.time(), random or
uuid. All eight supervise.expiry_notices(...) calls pass TODAY (or TODAY +/-
timedelta) explicitly — :217, 225, 235, 238, 240, 253, 265, 285, 311, 313, 318
— and all also inject state_path, so the default expiry_state_path() (the
user's real ~/.config file) is never reached. draws_left_today_boundary derives
both boundaries from final_draw_date(game, TODAY, 1) rather than from any
literal date, so it is timezone-free as well as clock-free. The one
time-dependence found is in the other file — verify_sources.py:26/33.

(b) INV-49 both directions — both present, but only one is scoped. Direction
"draws land on listed days" is :93-96; direction "every listed day still draws"
is :98-106, correctly windowed to 90 days from rows[-1]. So the documentation's
claim is not false. What is wrong is the denominator on the first direction
(MEDIUM above): diluted across the whole archive, and vacuous for daily. The
REMOVED-day case the documentation worries about is the one properly guarded;
the ADDED-day case is the weak half.

(c) INV-54 — presence is checked AND absence is checked, but the absence check
is enumerated, not total. See the HIGH. Better than a presence-only test (the
SENTINEL reference, the comma-joined board numbers and the bare cost are all
excluded, and --break notice_names_ref is caught), but it would pass on a
notice carrying the purchase date in the same house date format the function
itself uses.

(d) EXPECTED_EMPTY — bounded against the failure named, unfalsifiable against
the other. It cannot hide a genuine disagreement: it gates only the
overlap == before starvation branch (:52), and any pool with overlap goes
through sorted(got["main"]) == sorted(main) regardless. The gap is that the
exemption itself is never re-tested (LOW above). The comparison IS set-based on
both sides as documented — sorted() is applied to both got["main"] and main at
:44; the special is a scalar compared directly, correct because nums[-1] is the
PowerBall/bonus by position in both sources.

## Pre-pass verdicts
- None supplied, and none of the standard grep smells found: no sleep, no
  random/uuid, no except: pass, no verify=False, no hardcoded credential, no
  skip marker.

## Dimensions scanned
- 1: 5 findings — 1 HIGH, 1 MEDIUM, 3 LOW.
- 4: 1 finding (MEDIUM, conditional). Confirming the tail's count rather than
  re-deriving: CASES (:351-361) has 9 entries, every one of the 9 case-shaped
  module-level defs is registered, BREAKS has 10 entries covering all 9 cases
  (unknown_game_is_loud has two), and the only unregistered defs are ticket,
  _tmp_state, _apply_break and main. `ticket` is a genuine fixture helper — it
  returns a Ticket with the correct 11-argument signature and is called by 6
  cases. verify_sources.py has no registry, and no check in its main() can be
  skipped while still exiting 0: the only early exit is sys.exit() at :25,
  which exits 1, and the final return requires non-zero overlap.
- 5: 3 findings. No sleeps, no threads, no ports, no hash-order comparisons.
- 6: 1 finding. Otherwise clean and deliberately so — builtins.open is patched
  at :138 and restored in a finally at :143; state paths are unique per call;
  history._cache is shared between cases 1 and 3 but is a read-only memo. The
  --break mutations of module globals are process-global and unwound by
  nothing, but break mode is one-shot and its own LOW covers the consequence.
- 7: 1 finding (verify_sources' sliding-window vs frozen-archive drift).
  verify_expiry is clean — see (a). The real-data dependence of
  calendar_matches_real_draws and expired_tickets_are_silent is declared,
  argued and deliberate (module docstring :13-23), so not filed.
- 8: N/A — no framework, no skip mechanism, no marker of any kind. The three
  data-dependent cases are documented as failing rather than skipping (:23),
  the opposite of this dimension's trigger.
- 9: folded into the LOW at verify_sources.py:33. Both files reach a live
  third-party production API, intrinsic to INV-3 and INV-49/51; the finding is
  the 4 redundant calls, not the use.
- 11: clean — every one of the 9 cases asserts and returns a non-trivial detail
  string; none has a pass body or targets a function that no longer exists.
- 12: does not fire — no per-case timing supplied. verify_expiry.py's 3.5 s
  total is the fastest in the suite.
- 14: clean. The two continue-on-exception sites (:189-191 except KeyError,
  :184-185) both narrow the population rather than swallow a failure, and both
  are bounded by `assert total` at :199. unknown_game_is_loud uses the correct
  try/except/else: raise shape at :302-307 rather than a bare catch.

## Noted, not mine
- supervise.expiry_notices() writes the state file BEFORE returning the notices
  (supervise.py:362-363), so a crash between the two costs a missed notice.
  Argued at length as deliberate; mentioned only because notice_is_said_once
  cannot distinguish it from the other ordering.
- results.draws() is unmemoised where results.divisions() is memoised.

## Possibly wider
- The main()-catches-AssertionError-only shape and the membership-only red-test
  check are almost certainly in the other four registry verifiers. Not opened.
- _tmp_state()-style uncleaned mkdtemp is likely to recur wherever other
  verifiers inject temporary paths; only the verify_expiry instance writes real
  references, so far as visible from this chunk.
- The blocklist-instead-of-equality pattern for a privacy assertion may also be
  how verify_privacy.py and verify_payouts.py hold their "no ticket data"
  rules. Hypothesis only.

## Open questions — BOTH SETTLED by the orchestrator; see the two measurement
notes above (INV-49 denominators, and the 0 == 0 escalation at :218).
