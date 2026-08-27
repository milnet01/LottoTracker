# LOTTO-0036 — Total cost against winnings over a period the user chooses

**Status:** spec draft (2026-08-27).
**Kind:** feature.
**Source:** ROADMAP LOTTO-0036 — sign of success 4 in `README.md` § How you
would know it works, asked for by the user during discovery on 2026-08-20. The
attribution rule in §3.1 was settled with the user on 2026-08-27.

**Pairs with:** LOTTO-0002 (the page and its `spend` section, which this
extends) and LOTTO-0009 (the entry-level cost this arithmetic rests on).

*Layman: see what you spent and won in any month or year, instead of only over
all time*

## 1. Goal

After this ships, the page carries a *Spend against winnings by period* section:
one row per calendar month and one per calendar year, each stating what was
spent on the draws that fell in it and what those draws won, with a dropdown
that shows one at a time. The user can answer "did August pay for itself?" and
"how did 2025 go?" without exporting anything or doing arithmetic.

## 2. Problem

`serve.py::build_model()` computes exactly three money figures and
`page.py::_spend_section()` renders them: `spend.compared_cents`,
`won.compared_cents` and `spend.lifetime_cents`. All three are lifetime totals.
There is no period concept anywhere in the pipeline — verified 2026-08-27. The
one match is a comment on the claim deadline, not a period computation:

```console
$ grep -nE '\b(year|month|period)\b' page.py serve.py check.py
check.py:18:CLAIM_DAYS = 365  # SA prizes expire a year after the draw
```

Three consequences, in the order they matter:

1. **The user cannot ask the question they said they wanted asked.** Sign of
   success 4 names four shapes — a given year, year to date, a given month,
   month to date — and none is available.
2. **A lifetime total hides a trend.** Lifetime spend is R28,704.50 against
   R3,453.90 won; that single pair says nothing about whether the last three
   months were better or worse than the three before, which is the only version
   of the question a user can act on.
3. **The data to answer it is already in the model and thrown away.**
   `check.py::check()` puts the draw date on every win (`w["date"]`), and
   `history.covered()` returns the dated draws each entry covers. Both are read
   by `build_model()` today and neither is used for anything but a count.

## 3. Scope decisions (agreed with the user)

### 3.1 A cost or a win belongs to the period of its DRAW

Taken by the user on 2026-08-27, shown the three options and their worked
example. A ticket bought on 28 January for ten draws, winning R50 on the draw
of 12 February, is attributed:

| Period | Spent | Won |
|---|---|---|
| January | the share of its draws that fell in January | R0.00 |
| February | the share that fell in February | R50.00 |
| March | the share that fell in March | R0.00 |

The two alternatives — cost by purchase date, and everything by purchase date —
are recorded in §8 with the reason each lost. The rule the user chose is the one
that makes a period's two figures describe the *same draws*, which is what makes
comparing them meaningful at all.

### 3.2 The period view is drawn over INV-16's population, not a wider one

`docs/specs/LOTTO-0002-local-web-page.md` INV-16 scopes the existing comparison
to the scorable entries of resolved tickets, and the roadmap bullet requires
that rule to survive the split. It does, unchanged. The consequence the user
should expect is stated in §4.3: the periods on offer begin in January 2025, not
in November 2022 when the first ticket was bought.

### 3.3 The dropdown offers only periods that exist

Rather than every month in the span with the empty ones reading R0.00. §4.6 and
INV-60 carry the rule; §8 carries the rejected alternative.

## 4. Design

### 4.1 The per-draw share, and why nothing is divided

`docs/specs/LOTTO-0002-local-web-page.md` §4.6 states the entry cost:

```text
entry_cost_cents = tier_increments(game, era)[plus_flag] * paid_lines * ndraws
```

The `ndraws` factor is the *only* place the number of draws enters, so the share
belonging to one draw is that same expression with the factor removed:

```text
per_draw_cents = tier_increments(game, era)[plus_flag] * len(t.boards)
```

**There is no rounding rule here, and no rounding hazard — which is worth
stating precisely because it looks like there should be one.** "Split a
ticket's price across its draws" sounds like division with a remainder to
apportion. It is not: `entry_cost_cents` is `per_draw_cents * ndraws` by
construction, so it is an exact multiple of `ndraws` and
`entry_cost_cents // ndraws` recovers `per_draw_cents` exactly. Measured
2026-08-27 over the live dump:

```console
$ python3 - <<'EOF'
from tickets import HANDOVER, TIER_PRICES, load
bad = n = 0
for t in load():
    era = "sizekhaya" if t.bought >= HANDOVER else "ithuba"
    inc = {pf: i for pf, _p, i in TIER_PRICES[(t.game, era)]}
    for pf, _ in t.pools:
        per_draw = inc[pf] * len(t.boards)
        n += 1
        if (per_draw * t.ndraws) // t.ndraws != per_draw:
            bad += 1
print(f"entries {n}, where entry_cost//ndraws != per_draw: {bad}")
EOF
entries 1238, where entry_cost//ndraws != per_draw: 0
```

So either direction is arithmetically sound, and an implementer must not be
sent hunting for a remainder that cannot occur. The reason to write the
multiplication out rather than divide is only that `per_draw_cents` is the
primitive the price table actually states — `tier_increments()` returns a
per-board, per-draw increment — and deriving it back out of a product it was
used to build is a round trip for nothing.

**The rounding question therefore has no bearing on INV-57**, whose real
failure is losing the not-yet-drawn residue (§4.4).

`tier_increments()` lives in `serve.py`, module level, and already returns the
whole `{plus_flag: increment}` mapping for a game and era; `build_model()`
already calls it once per ticket. Nothing new is computed — the existing product
is decomposed.

### 4.2 Which draws carry a date: `history.covered()`, never the calendar

The dates come from `history.covered(t, plus_flag)`, whose docstring calls its
return *"The draws one entry actually covers: first N on or after its start."* —
real draws with real dates, from the merged record `history.py` builds out of
the API and the scraped archive.

**`expiry.py`'s calendar is deliberately not used here, and the two must not be
merged.** `docs/specs/LOTTO-0034-ticket-expiry-warning.md` §4.3 already draws
this line for the draw *count*; this is the same line one column over. The
calendar answers *when will a draw happen* by projection, and
LOTTO-0034 measured that projection as exact 257 times in 260 and a day out in
the other 3. A day is immaterial to a warning that fires several days ahead. It
is not immaterial to a period boundary: a draw projected onto 31 July that
really fell on 1 August moves money between two of the figures this section
exists to state. Observed dates have no such error, so observed dates are what
is used.

The price of that choice is stated rather than hidden — see §4.4.

### 4.3 The population, and where the periods therefore start

Unchanged from INV-16: the scorable entries of resolved tickets. `scorable()`
excludes an entry whose pool predates all known draw data, and the merged record
begins on 2025-01-01, so no entry is scorable before then however old the ticket
is. Measured 2026-08-27:

```console
$ python3 - <<'EOF'
from history import scorable, covered
from tickets import HANDOVER, TIER_PRICES, load
import collections
months = collections.Counter()
for t in load():
    era = "sizekhaya" if t.bought >= HANDOVER else "ithuba"
    inc = {pf: i for pf, _p, i in TIER_PRICES[(t.game, era)]}
    for pf, _ in t.pools:
        if scorable(t, pf) and t.resolved:
            for d in covered(t, pf):
                months[d["date"][:7]] += inc[pf] * len(t.boards)
print(len(months), "month buckets,", min(months), "to", max(months))
EOF
20 month buckets, 2025-01 to 2026-08
```

561 tickets span 2022-11-09 to 2026-08-07 and R28,704.50 of lifetime spend, of
which R11,063.50 is in the compared population — **38.5%** of it
(`1106350/2870450`, measured in the §4.4 run). **The period section therefore
describes rather less than half the money, and says so on the page** — §4.7's caption
names LOTTO-0006 (backfill results earlier than 2025-01-01) as what would widen
it. That is the honest form of the limitation and the one the cardinal rule
requires: a period nobody can score is absent, never a row reading R0.00.

### 4.4 A draw that has not happened yet belongs to no period

An entry's cost covers `ndraws` draws; `covered()` returns only those that have
been drawn. For a ticket still running, the difference is money that has been
spent and has no draw date yet. It is reported as its own figure and is in
neither side of any period — exactly the shape `spend.unresolved_cents` already
uses in `page.py::_spend_section()` for a price that matches no known tier.

Measured 2026-08-27 against the live dump: R160.00, from the two tickets
currently running. The reconciliation is exact:

```console
$ python3 - <<'EOF'
from history import scorable, covered
from tickets import HANDOVER, TIER_PRICES, load
import collections
months, years = collections.Counter(), collections.Counter()
cmp_total = not_drawn = 0
for t in load():
    era = "sizekhaya" if t.bought >= HANDOVER else "ithuba"
    inc = {pf: i for pf, _p, i in TIER_PRICES[(t.game, era)]}
    for pf, _ in t.pools:
        if not (scorable(t, pf) and t.resolved):
            continue
        per_draw = inc[pf] * len(t.boards)
        cmp_total += per_draw * t.ndraws
        cov = covered(t, pf)
        not_drawn += per_draw * (t.ndraws - len(cov))
        for d in cov:
            months[d["date"][:7]] += per_draw
            years[d["date"][:4]] += per_draw
print("compared", cmp_total, "months", sum(months.values()),
      "years", sum(years.values()), "not drawn", not_drawn)
print("reconciles:", sum(months.values()) + not_drawn == cmp_total,
      sum(years.values()) + not_drawn == cmp_total)
EOF
compared 1106350 months 1090350 years 1090350 not drawn 16000
reconciles: True True
```

### 4.5 The model shape

`build_model()` gains one key. `page.py` renders it verbatim and sums nothing —
the same single-source rule `docs/specs/LOTTO-0002-local-web-page.md` §4.6 states
for `spend.compared_cents`, and for the same reason: a renderer that adds up a
displayed column reproduces INV-16's failure one section further down.

```python
"periods": {
    # Newest first: years, then months. The list is the dropdown AND the
    # table body, in the same order, so the first row is the default view.
    "buckets": [
        {"key": "2026", "kind": "year", "label": "2026",
         "spend_cents": 0, "won_cents": 0},
        # ...
        {"key": "2026-08", "kind": "month", "label": "August 2026",
         "spend_cents": 0, "won_cents": 0},
        # ...
    ],
    # Paid for, not yet drawn: in no bucket, never subtracted from one.
    "not_drawn_cents": 0,
}
```

`spend_cents` and `won_cents` are **always integers, never `None`.** That is not
a shortcut past `page.py::_money_cell()`'s three-valued rule — it is that rule
satisfied at the source. A bucket exists only where at least one draw of a
scorable entry fell in it (§4.6), so every bucket has been scored, and `R0.00`
in one always means *checked, won nothing*. INV-60 is what stops a future change
introducing an unscored bucket by the back door.

`won_cents` is summed from `check.py::check()`'s output keyed on `w["date"]`,
which is the draw's date and not the purchase's. Every win is on a covered draw
of a scorable entry by construction — `check()` skips an entry `scorable()`
rejects — so the win side and the spend side occupy the same buckets with no
extra filtering. Measured 2026-08-27: 145 wins totalling R3,453.90, spread over
the same 20 month buckets, 2025-01 to 2026-08.

### 4.6 Bucketing, and why "to date" needs no separate concept

A month bucket is keyed `YYYY-MM` and a year bucket `YYYY`, both taken as string
prefixes of the draw date, which is already an ISO `YYYY-MM-DD` string
throughout `history.py` — no date parsing is introduced.

**A bucket can only ever contain draws that have already happened**, because
`covered()` returns nothing else. So the current year's bucket *is* year to
date, and the current month's *is* month to date. The four shapes sign of
success 4 asks for are two bucket kinds, not four. Stating this is the point:
an implementer who added `ytd` and `mtd` as separate keys would ship two figures
that are by construction equal to two others, and the first divergence between
them would be a bug nobody could explain.

A month with no scored draw produces no bucket, and a year with none produces no
year bucket either. The dropdown is built from `buckets`, so it can only offer
what exists.

### 4.7 The control, and why it is not a query parameter

`page.py` gains `_periods_section(model)`, rendering a `<select
id="periodfilter">` with two `<optgroup>`s (Years, Months) and a table
`id="periods"` whose rows carry `data-period="<key>"`. All rows but the first
are hidden at render; the `change` handler toggles `style.display`, exactly as
the existing `#gamefilter` handler does over `#entries tbody tr`.

**The selection must not reach the URL.** `docs/specs/LOTTO-0014-http-surface-and-security.md`
INV-21 forbids ticket data in any URL, fragment or title, and `page.py`'s
existing filter carries the comment saying so. So: no query parameter, no
fragment, no `history.pushState()`, and no `<form>`. This is not a new rule and
gets no new invariant — LOTTO-0014 INV-21 owns it, and
`tools/verify_page.py::nothing_in_the_url` already scans the whole rendered page
for `pushState`, `location.search`, `href="?`, `href="#` and `<form>`, so a
period control that reached for any of them fails an existing case.

The section carries one caption line naming the span it covers and why it starts
there, so a user does not read the absence of 2023 as a claim about 2023.

## 5. Invariants

- **INV-57** — The month buckets plus `periods.not_drawn_cents` sum exactly to
  `spend.compared_cents`, and so do the year buckets. No cent is in two buckets
  of the same kind and none is lost.
  *Test:* the §4.4 command → `compared 1106350 months 1090350 years 1090350 not
  drawn 16000` / `reconciles: True True`. Locked in the suite by
  `tools/verify_page.py::periods_reconcile`.
  *Breaks when:* `periods.not_drawn_cents` is dropped, or folded into a bucket
  instead of reported beside them — measured 2026-08-27, the month buckets alone
  come to 1090350 against a compared total of 1106350, short by the 16000 the
  residue holds. Or the builder iterates `history.all_draws()` rather than
  `history.covered()`, counting every draw in the pool instead of the `ndraws`
  the ticket paid for, which makes the buckets exceed the total instead.
  **Not** broken by deriving the share as `entry_cost_cents // ndraws` — §4.1
  measures that as exact on all 1,238 entries, and a clause naming it would be
  one no implementation could fail.

- **INV-58** — A cost and a win are attributed to the period of the draw, never
  of the purchase. An entry whose draws span two months contributes to both.
  *Test:* `tools/verify_page.py::periods_by_draw_date`, and its
  `--break attribute_by_purchase`.
  *Breaks when:* the builder keys a bucket on `t.bought` or `t.start` rather
  than on `d["date"]` and `w["date"]`. The fixture is a single ticket bought in
  the last days of a month whose ten draws run into the next, so a
  purchase-dated implementation produces one bucket where the contract requires
  two — a difference no other rule in the builder can produce.

- **INV-59** — Every bucket is drawn over INV-16's population, the scorable
  entries of resolved tickets, and `page.py` renders `spend_cents` and
  `won_cents` verbatim without summing any displayed column.
  *Test:* `tools/verify_page.py::periods_over_checkable`, and its
  `--break period_spend_is_lifetime`.
  *Breaks when:* the builder drops the `and t.resolved` clause, or drops the
  `scorable()` gate, so an entry nothing can score contributes spend to a period
  against winnings that could never be computed for it — the period-level form
  of the failure INV-16 exists to catch.

- **INV-60** — A bucket exists only where at least one draw of a scorable entry
  fell in it. The page shows no period whose figures are unknown, so `R0.00` in
  a bucket always means *checked, won nothing*.
  *Test:* `tools/verify_page.py::empty_period_is_absent`, and its
  `--break zero_bucket_for_empty_period`.
  *Breaks when:* the builder enumerates every month between the first and last
  scored draw rather than only the months that carry one, so a gap month renders
  as R0.00 spent and R0.00 won — the cardinal rule breached one section below
  where INV-15 catches it. The fixture is a model whose scored draws skip a
  month; nothing else in the builder can emit a bucket for a month with no draw.

## 6. Failure modes

| Assumption | When it breaks | What happens |
|---|---|---|
| `history.covered()` returns dated draws | the merged record is empty (no `archive_results.json` and the API refused) | `scorable()` rejects every entry, `buckets` is empty, `not_drawn_cents` is 0. The section renders its caption and no table. It must not render an empty table with a dropdown that offers nothing. |
| Every win sits on a covered draw | a future change scores an entry `scorable()` rejects | a win would have no bucket to land in. The builder sums winnings by iterating the buckets it built from spend, so such a win is silently dropped. INV-57 does not catch it — it checks the spend side. Named here rather than papered over; the guard is that `check.py::check()` skips unscorable entries at the top of its loop, which LOTTO-0009 INV-11 already holds. |
| The dump exists | it does not | `build_model()` returns `{"no_dump": True, ...}` before any of this runs, and `_periods_section()` is never called. Unchanged behaviour. |
| A ticket is resolved | a price matches no known tier | it is excluded from every bucket, exactly as it is excluded from `spend.compared_cents` today, and its cost is already reported by the existing `unresolved_cents` row. It is **not** added to `not_drawn_cents`, which would give one ticket two explanations. |
| The span is short enough for a dropdown | it grows | 22 buckets today, growing by about 13 a year (12 months and a year). §13 carries the arithmetic. |

## 7. Tests

All four cases join `tools/verify_page.py`, which already holds INV-15, INV-16,
INV-21 and INV-29 and carries the `--break` registry the project uses in place
of a red run against pre-fix code. Each case is registered in `CASES` with its
invariant id, and each break in `BREAKS` against exactly the case it must fail.

| Case | Invariant | What it exercises |
|---|---|---|
| `periods_reconcile` | INV-57 | recomputes the buckets from `TIER_PRICES` and `covered()` and asserts the two sums against `spend.compared_cents` — recomputed, never read back out of the model it is checking |
| `periods_by_draw_date` | INV-58 | a fixture ticket whose ten draws straddle a month end; asserts two buckets, with the split falling where the draw dates fall |
| `periods_over_checkable` | INV-59 | asserts the rendered figure equals the recomputed scorable-and-resolved figure, and that it is strictly less than the lifetime figure, so the fixture cannot be degenerate |
| `empty_period_is_absent` | INV-60 | a fixture whose scored draws skip a month; asserts no row and no `<option>` for that month, and that the forbidden-strings list still holds |

**Every case must be observed failing under its own break before it is
believed.** These are greenfield, so there is no pre-fix code to red-test
against — the `--break` flag is what makes "observed failing" reproducible, and
`docs/specs/LOTTO-0034-ticket-expiry-warning.md` records the same reasoning for
`tools/verify_expiry.py`.

## 8. Alternatives considered (and rejected)

- **Cost by purchase date, winnings by draw date.** Rejected by the user on
  2026-08-27. The spend column would match the bank statement exactly, which is
  its attraction, but a period's two figures then describe different tickets —
  the month you bought looks like a total loss and the month you won looks like
  pure profit. The comparison is the feature; a comparison of unlike things is
  not one.
- **Everything by purchase date.** Rejected by the user the same day. One
  ticket would live in exactly one period, which reads simply, but a period's
  total keeps moving for weeks after the period ends — a January figure that
  changes in February is not a figure anyone can act on.
- **A `?period=2026-08` query parameter.** Rejected on LOTTO-0014 INV-21: a
  query string lands in browser history, which is where the browser syncs it.
  `docs/specs/LOTTO-0014-http-surface-and-security.md` §8 rejected the same
  shape for the game filter and this inherits that decision rather than
  relitigating it.
- **`expiry.py`'s calendar as the date source, so every paid-for draw lands in a
  period including those not yet drawn.** Rejected in §4.2: the calendar is a
  projection with a measured one-day error, and a one-day error at a month
  boundary moves money between the two figures this section exists to state.
  The cost of rejecting it is the not-yet-drawn residue, which is reported
  rather than hidden.
- **A bucket for every month in the span, empty ones reading R0.00.** Rejected
  on the project's cardinal rule: a month with no scorable draw is a month
  nothing is known about, and R0.00 is the rendering of *checked, won nothing*.
  `page.py::_money_cell()` keeps those two apart one section up; emitting a zero
  bucket would collapse them here.
- **Server-side period selection over POST.** Rejected as more machinery for
  nothing: all 22 buckets are a few hundred bytes, the client-side filter
  pattern already exists in `page.py` for `#gamefilter`, and a POST would need a
  token, a route and a place in `docs/specs/LOTTO-0014-http-surface-and-security.md`'s
  route table.

## 9. Out of scope

- **Periods before 2025-01.** Not deferrable by this item: it needs draw data
  that does not exist locally. Tracked by LOTTO-0006 (backfill results earlier
  than 2025-01-01), which is what widens §4.3's span.
- **A custom date range** ("2026-03-01 to 2026-06-14"). The user asked for
  years and months; a free range is a different control and a different
  contract. Not tracked — file it if it is wanted.
- **The bank's own payout record per period.** Tracked by LOTTO-0032, which
  owns putting the reconciliation on the page at all.
- **Charting the periods.** Out of scope; the project ships no chart and adding
  one is a dependency decision, not a display change.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-57 | `tools/verify_page.py::periods_reconcile` |
| INV-58 | `tools/verify_page.py::periods_by_draw_date` |
| INV-59 | `tools/verify_page.py::periods_over_checkable` |
| INV-60 | `tools/verify_page.py::empty_period_is_absent` |
| §4.7 the period control puts nothing in the URL | `tools/verify_page.py::nothing_in_the_url` — LOTTO-0014 INV-21's existing case, which scans the whole rendered page for the forbidden forms and so already covers a control that did not exist when it was written |
| §4.6 the current period's bucket is year/month to date | **nothing** — it is a property of `covered()` returning only drawn draws, not a separate computation, so there is nothing to assert that INV-57 does not already cover |
| §4.3's caption naming the span and LOTTO-0006 | **nothing** — no case reads the caption text; code review only. The exposure is a stale sentence, not a wrong figure |
| §6's second row — a win on an unscorable entry having no bucket | **nothing here** — held upstream by LOTTO-0009 INV-11 and `check.py::check()`'s `scorable()` gate |

## 11. Cross-doc impact

- **`CLAUDE.md`** — the `serve.py` bullet gains `periods`, and the cardinal-rule
  paragraph gains `_periods_section()` beside `_money_cell()` and `_draws_cell()`,
  since §4.5 resolves the three-valued question at the source rather than at the
  cell. The § Verification list's count of verifier *scripts* does not move —
  these are cases inside an existing one.
- **`README.md`** — sign of success 4 moves from open to done in
  § How you would know it works, and the standing "**Where it stands against
  those today**" line goes from "4 and 5 are open" to 5 alone. The §4.3
  limitation is named there too, or the sign reads as covering money it does not.
- **`CHANGELOG.md`** — one entry citing LOTTO-0036.
- **`docs/specs/LOTTO-0002-local-web-page.md` §4.6** — gains a cross-reference
  to §4.1 here, so the entry-cost formula and its per-draw decomposition are not
  independently maintained. Its INV-16 is unchanged in force.
- **`docs/specs/LOTTO-0034-ticket-expiry-warning.md` §4.3** — unchanged in
  force, but §4.2 here extends its `draws_left` / `draws_remaining` reasoning to
  the date column; a cross-reference stops the two being read as one rule.
- **`ROADMAP.md`** — LOTTO-0036 flips to shipped; LOTTO-0006 gains no change but
  is now cited by §9 as the unlock for the pre-2025 span.

## 12. Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|

## 13. Resource cost

No new dependency and no new file. The state added is one list on the model,
rebuilt on every build alongside everything else and never persisted.

Measured 2026-08-27: 20 month buckets and 2 year buckets, 22 rows. The span
grows by 13 buckets a year (twelve months and a year), so the dropdown reaches
about 100 entries in six years — still one `<select>`, and the table body is
four short cells per row. The buckets are accumulated inside the loop over
`t.pools` that `build_model()` already runs, so the work is two `Counter`
increments per covered draw and no additional pass over the tickets.
