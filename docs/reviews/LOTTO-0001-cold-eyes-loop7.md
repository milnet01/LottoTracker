# LOTTO-0001 — cold-eyes loop 7 run state (2026-08-03)

**Status: UNCONVERGED, mid-loop.** Two lanes returned; **nothing below has been
verified yet** and no fix has been applied. This file exists so the lane spend
is not repeated — do **not** re-dispatch to rediscover these. Verify each
against current files (Phase 3), fix every verified one (Phase 4), then loop.

Gate context: the loop was run on the LOTTO-0026 step-1 amendment (INV-26) and
the LOTTO-0027 corrections, before LOTTO-0026 step 2 touches
`check.py::paying_combinations()`.

Deterministic pre-pass (`/doc-lint`, already settled — do not re-raise):
0 dead anchors, 0 broken links, 0 stale `path:line` citations; the 18
`invariant_id_gap` entries are ids owned by sibling specs, as §5 says.
Document size 639 lines.

Lane briefs and the scrubbed copy: `/tmp/claude-1000/-mnt-Games-Scripts-Linux-LottoTracker/577844f9-cabf-4a83-afbd-1bc3de00ac6c/scratchpad/ce/`
(session-scoped — rebuild rather than rely on it).

## Both lanes independently, and the one already known true

**A1 / B1 — INV-26 states the runtime raise in the present tense; it is not
built.** §5 INV-26, §6's new bullet and §11's row all describe
`paying_combinations()` raising, and INV-26's *Test:* names a probe that does
not exist. Only §4.4 has it as future work ("...at run time is LOTTO-0026").
`paying_combinations()` raises only on `if not rows`. **Known true — this is
LOTTO-0026 step 2, deliberately unbuilt.** Graded CRITICAL by lane A, HIGH by
lane B; both note the consequence is that a reader closes step 2 unbuilt.
Fix: either mark the raise as pending in all three places, or land step 2
first and keep the wording. Decide before anything else — several findings
below fall out differently depending on which.

**A3 / B2 — INV-26 does not bound the `(hits, special)` domain.** The reach
rule's content is in `tools/verify_pools.py` only: `mains = {"lotto": 6,
"powerball": 5, "daily": 5}` and `special` true only for lotto/powerball
(`match()` returns `special=False` for daily, so `api_label("daily", n, True)`
is unreachable in production). Unbounded → the guard silently weakens; too
narrow → it raises on healthy pools. The spec is the contract and omits it.

**A7 / B4 — §5's invariant-ownership map is stale.** It sends INV-12 to INV-21
to LOTTO-0002; LOTTO-0014 owns INV-12–14 and INV-21, LOTTO-0013 owns INV-19,
INV-20. `docs/specs/LOTTO-0014-http-surface-and-security.md` is not mentioned
anywhere in this document, §12 included. §12 also omits LOTTO-0002 despite
§4.4 declaring the win dict a contract it consumes.

**A8 / B3 — §7's `verify_coverage.py` "exception" is false.** That script's
`tickets = load()` is the cwd-relative default like every other; its
`__file__`-relative `DUMP` is used only for the `Played R` parse-count check.
`verify_privacy.py` and `verify_pools.py` also resolve from `__file__`. Lane B
adds the sharper form: a *different* dump in cwd would compare cwd tickets
against the repo dump and print a spurious PARSE GAP.

**A6 / B6 — `division` is documented as the win's own source, but always comes
from the API's newest draw.** `check.py` sets `"division": pays[label]` from
`paying_combinations()`, in both eras, so an archive-era win carries a 2026
division name (the majority case: 69 of 86 pre-LOTTO-0027 wins were archive).
Lane B's extra: with the plain-tier pricing fallback, `division` and `matched`
can name the bonus tier while the money came from the plain row — three fields
disagreeing on the money path, documented nowhere. `page.py` renders both.

**A10 / B8 — §7 misdates INV-4 (says 2026-08-02; INV-4 says 2026-08-03) and
lists no vintage for INV-26's figures.**

## Lane A only

- **A2 (HIGH)** — §4.4 describes `amount()`'s archive plain-tier fallback as
  the bottom-tier case only; the code applies it for any `hits` and both
  games, so a missing `3 + PowerBall` row prices at the plain `3` amount
  instead of raising under INV-22.
- **A5 (MED)** — the counter-example justifying INV-26's direction is wrong:
  `api_label()` cannot build `MATCH 6` for Daily Lotto (five balls, so
  `hits` ≤ 5). `MATCH 0` / `MATCH 1` are the real buildable-but-unpublished
  daily labels. Copied verbatim into `tools/verify_pools.py`'s comment too.
- **A9 (MED)** — INV-5's "Two such literals live under `tools/`" is now five
  lines; three are LOTTO-0027's own explanatory comments, which the
  paragraph's taxonomy does not cover.
- **A11 (LOW)** — §4.4 says `serve.py` "spreads" the win dict; LOTTO-0002 §4.1
  specifies it drops `amount` for `amount_cents`, and calls that deletion
  load-bearing against a 100x money error.
- **A12 (LOW)** — §10's claim that the seven `all_draws()` calls precede
  scoring is wrong; both they and the paying-set queries are lazy inside the
  same loop. The 7 + 6 = 13 total is right.
- **A13 (LOW)** — INV-26 does not say whether the raise aborts the run or
  fails one pool. Nothing catches `RuntimeError`, so today it would discard
  every win already accumulated. Step 2 needs the answer.
- **A14 (LOW)** — INV-26 says "every division the source publishes for a
  pool"; `paying_combinations()` reads `rows[0]` only, so both halves see the
  newest draw's table, not the pool's history.
- **A15 (LOW)** — §11's INV-4 row still says "not yet a pre-commit hook";
  LOTTO-0025 partly advanced this and the row does not say so.
- **A16 (INFO)** — §7 carries a doubled em dash and a stray hard wrap.

## Lane B only

- **B5 (MED)** — §4.4's win dict documents `"line"` as "the board letter";
  Multiplay lines are `A1`…`A7` (`tickets.py`), which §4.2 already corrects
  elsewhere. `check.py`'s terminal format reserves three characters.
- **B7 (MED)** — INV-26's check has no anti-vacuity floor, unlike INV-3's
  per-pool zero-overlap floor and INV-6's 90% floor. Its pool set is derived
  from tickets that `reaches()`, so a partial archive quietly shrinks what is
  checked, and §7 has already demoted the `6 live pools` count to
  non-asserted. Either assert a pool floor or §7 needs a second exception.
- **B9 (LOW)** — §11's INV-5 row says `api_label()` builds its labels with
  f-strings; since LOTTO-0027 one is a plain literal (`"MATCH POWERBALL"`).
  The row's conclusion survives, its premise does not — and it is the sentence
  LOTTO-0007(c) was closed on.
- **B10 (LOW)** — INV-22's reasoning assumes the feed pages newest-first
  (`rows[0]`, no sort). §4.3 records exactly this class of assumption for the
  special ball; this one is unrecorded.

## Verified clean by lane A (re-checking these is waste)

The three §5 one-liners were executed and match; INV-5's grep returns 0;
§4.4's corrected grammar table matches `api_label()`/`site_label()` on all
four rows; §4.2's `GAME_MAP` table matches the code; the entry arithmetic
(558/745, 963 + 11 = 974, 1233 - 974 = 259) is self-consistent and agrees
with `uncheckable_report()`; INV-22's "five checks, not four" is correct;
§10's request model (7 + 6 = 13) matches the code.
