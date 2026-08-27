# LOTTO-0036 — Total cost against winnings over a period the user chooses

**Status:** accepted (2026-08-27). Gated by `review-contract` (genre spec):
two loops, three cold lanes each, 18 verified findings all fixed, 3 dismissed.
Reached the 2-loop cap for a spec, which is the normal exit — implementation is
the third reviewer. Loop 2 was a **violent** cap (5 of 9 findings landed on
loop 1's own text), so this document's review ends here rather than looping
again; see §12.
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

`serve.py::build_model()` computes six money figures; the three
`page.py::_spend_section()` draws its comparison from are
`spend.compared_cents`, `won.compared_cents` and `spend.lifetime_cents`, and all
three are lifetime totals. (The other three — `spend.unresolved_cents`,
`won.lifetime_cents` and `won.unexpired_cents` — are lifetime figures too; §4.4
relies on the first of them.)
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
apportion. It is not, and the reason is algebraic rather than empirical:
`entry_cost_cents` is *defined* as `per_draw_cents * ndraws`, so it is an exact
multiple of `ndraws` and `entry_cost_cents // ndraws` recovers `per_draw_cents`
for every possible input. **No measurement is offered for this and none would
mean anything** — a script checking `(x * n) // n == x` over the dump is an
integer identity that cannot report a failure whatever the data, so quoting its
zero as evidence would be dressing algebra as observation.

So either direction is arithmetically sound, and an implementer must not be
sent hunting for a remainder that cannot occur. The reason to write the
multiplication out rather than divide is only that `per_draw_cents` is the
primitive the price table actually states — `tier_increments()` returns a
per-board, per-draw increment — and deriving it back out of a product it was
used to build is a round trip for nothing.

**The rounding question therefore has no bearing on INV-57**, whose real
failure is losing the no-result residue (§4.4).

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

### 4.4 A draw with no result yet belongs to no period

An entry's cost covers `ndraws` draws; `covered()` returns those of them
**present in the merged record**. The difference is money that has been spent
and has no draw date to file it under. It is reported as its own figure and is
in neither side of any period — exactly the shape `spend.unresolved_cents`
already uses in `page.py::_spend_section()` for a price that matches no known
tier.

**The figure is `no_result_cents`, and it must not be called "not yet drawn".**
`covered()` filters `history.all_draws()`, so it answers *has this draw been
scored*, not *has this draw happened* — LOTTO-0034 §4.3 keeps exactly those two
apart (`draws_remaining` against `draws_left`) and §4.2 above invokes that
section, so conflating them here would breach the rule this document cites in
its own defence. The two cases fall together: a draw still in the future, and a
draw that has happened while the results record is stale or a refresh failed
(`page.py` already carries LOTTO-0002 INV-18's stale notice for the second).
Labelling the row "not yet drawn" would render the second case as a fact about
the lottery rather than a fact about our data — the cardinal rule breached one
row down. The row reads **"paid for, no result yet"**.

Measured 2026-08-27 against the live dump: R160.00, across 2 tickets. The
reconciliation is exact:

```console
$ python3 - <<'EOF'
from history import scorable, covered
from tickets import HANDOVER, TIER_PRICES, load
import collections
months, years = collections.Counter(), collections.Counter()
cmp_total = no_result = 0
for t in load():
    era = "sizekhaya" if t.bought >= HANDOVER else "ithuba"
    inc = {pf: i for pf, _p, i in TIER_PRICES[(t.game, era)]}
    for pf, _ in t.pools:
        if not (scorable(t, pf) and t.resolved):
            continue
        per_draw = inc[pf] * len(t.boards)
        cmp_total += per_draw * t.ndraws
        cov = covered(t, pf)
        no_result += per_draw * (t.ndraws - len(cov))
        for d in cov:
            months[d["date"][:7]] += per_draw
            years[d["date"][:4]] += per_draw
print("compared", cmp_total, "months", sum(months.values()),
      "years", sum(years.values()), "no result", no_result)
print("reconciles:", sum(months.values()) + no_result == cmp_total,
      sum(years.values()) + no_result == cmp_total)
EOF
compared 1106350 months 1090350 years 1090350 no result 16000
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
    # Paid for, no result yet: in no bucket, never subtracted from one.
    "no_result_cents": 0,
}
```

`spend_cents` and `won_cents` are **always integers, never `None`.** That is not
a shortcut past `page.py::_money_cell()`'s three-valued rule — it is that rule
satisfied at the source. A bucket exists only where at least one draw of a
scorable entry fell in it (§4.6), so every bucket has been scored, and `R0.00`
in one always means *checked, won nothing*. INV-60 is what stops a future change
introducing an unscored bucket by the back door.

`won_cents` is summed from `check.py::check()`'s output keyed on `w["date"]`,
which is the draw's date and not the purchase's.

**The win side takes BOTH of INV-16's conditions, and `scorable()` is only one
of them.** `check()` skips an entry `scorable()` rejects, so every win is on a
covered draw of a scorable entry by construction — but `check()` applies no
`resolved` test at all, which is precisely why `build_model()` already writes
its **compared** figure as
`won_cmp = sum(round(w["amount"] * 100) for w in wins if w["ref"] in resolved_refs)`,
stored as `won.compared_cents`. The unfiltered sum is `won_life`, stored as
`won.lifetime_cents`, which LOTTO-0002 §4.6 says outright "is *not* that
figure" — an implementer reaching for the lifetime key to fill a bucket gets the
unfiltered total and ships this invariant's failure.

**The bucket key set is built from the SPEND side, and the win side only adds
into keys that already exist.** A win whose key is absent is dropped rather than
creating a bucket: §6's second row states that consequence and depends on this
being the algorithm, where keying a `Counter` on `w["date"]` instead would
create a spend-less bucket and breach INV-60. So a bucket's `won_cents` sums the
wins whose `ref` is in that same resolved set, and an implementer writing `for w in wins:` with no such filter has built
the wrong thing. `tickets.py::parse()` gives an unresolved ticket a fallback
single tier so `check()` scores it like any other; its winnings would then land
in a bucket whose matching cost was excluded, which is LOTTO-0002 §4.6's
"unearned surplus" reproduced one section down and per period. **It changes
nothing today — `unresolved tickets` is 0 — which is exactly why it has to be
written down rather than left to the numbers.**

Measured 2026-08-27: 145 wins totalling R3,453.90. Their month buckets are the
same 20 the spend side occupies — verified as an identical set, not merely an
equal count — 2025-01 to 2026-08.

### 4.6 Bucketing, and why "to date" needs no separate concept

A month bucket is keyed `YYYY-MM` and a year bucket `YYYY`, both taken as string
prefixes of the draw date, which is already an ISO `YYYY-MM-DD` string
throughout `history.py` — no date parsing is introduced.

**A bucket can only ever contain draws that are IN THE RESULTS RECORD**, because
`covered()` returns nothing else. So the current year's bucket *is* year to
date, and the current month's *is* month to date — **as far as the record
goes.** That qualification is not pedantry: it is §4.4's distinction one section
on, and a lagging or failed refresh makes the current bucket trail the real
month. The page already tells the user when that is so, via LOTTO-0002 INV-18's
stale notice; this section adds no second opinion about freshness and must not
be read as claiming the record is current. The four shapes sign of
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

- **INV-57** — The month buckets plus `periods.no_result_cents` sum exactly to
  `spend.compared_cents`, and so do the year buckets. No cent is in two buckets
  of the same kind and none is lost.
  *Test:* `tools/verify_periods.py::periods_reconcile`, and its
  `--break fold_residue_into_bucket`.
  *Breaks when:* `periods.no_result_cents` is dropped, or folded into a bucket
  instead of reported beside them — against the live dump on 2026-08-27 the
  month buckets alone come to 1090350 against a compared total of 1106350,
  short by the 16000 the residue holds. Or the builder iterates
  `history.all_draws()` rather than `history.covered()`, counting every draw in
  the pool instead of the `ndraws` the ticket paid for, which makes the buckets
  exceed the total instead.
  **Not** broken by deriving the share as `entry_cost_cents // ndraws` — §4.1
  shows that is an algebraic identity, so a clause naming it would be one no
  implementation could fail.

  **This case lives in a NEW verifier, `tools/verify_periods.py`, and not in
  `tools/verify_page.py`.** §7 owns the reasoning; the short form is that every
  case in `verify_page.py` is renderer-only — `fixture_model()` is a
  hand-authored dict and `render_pure()` installs an `all_draws` double that
  *raises* — so no case there can observe a defect that lives in the builder,
  and a builder-side break is exactly what this invariant names.

- **INV-58** — A cost and a win are attributed to the period of the draw, never
  of the purchase. An entry whose draws span two months contributes to both.
  *Test:* `tools/verify_periods.py::periods_by_draw_date`, and its
  `--break attribute_by_purchase`.
  *Breaks when:* the builder keys a bucket on `t.bought` or `t.start` rather
  than on `d["date"]` and `w["date"]`. The fixture is a single ticket bought in
  the last days of a month whose ten draws run into the next, so a
  purchase-dated implementation produces one bucket where the contract requires
  two — a difference no other rule in the builder can produce.
  **The fixture's ticket must WIN on a draw in the second month, and the case
  must assert which bucket that win lands in.** Without it the invariant's "and
  a win" half has no assertion at all, and a builder keying `won_cents` on the
  purchase date passes — the same hole LOTTO-0002 INV-16 pins its fourth ticket
  to close.

- **INV-59** — Every bucket is drawn over INV-16's population, the scorable
  entries of resolved tickets, and `page.py` renders `spend_cents` and
  `won_cents` verbatim without summing any displayed column.
  *Test:* `tools/verify_periods.py::periods_over_checkable`, and its two
  breaks, `--break period_spend_is_lifetime` and
  `--break period_won_unfiltered`.
  *Breaks when:* on the **spend** side, the builder drops the `and t.resolved`
  clause or the `scorable()` gate, so an entry nothing can score contributes
  spend to a period against winnings that could never be computed for it — the
  period-level form of the failure INV-16 exists to catch. On the **win** side,
  the builder sums `check()`'s output with no `w["ref"] in resolved_refs`
  filter: `check()` gates on `scorable()` alone, so an unresolved ticket's
  winnings enter a bucket whose cost was excluded, and the period shows a
  surplus nobody earned (§4.5). The two sides fail independently and the case
  must assert both, under a break each — which is why this invariant is the one
  with two. **The fixture must therefore carry an unresolved ticket that WINS.**
  With `unresolved tickets` at 0 the live dump supplies no such case, so without
  that fixture the win-side clause cannot fail and is unfalsifiable; LOTTO-0002
  INV-16 pins its fourth ticket for exactly this reason.

- **INV-60** — A bucket exists only where at least one draw of a scorable entry
  **of a resolved ticket** fell in it. The page shows no period whose figures are unknown, so `R0.00` in
  a bucket always means *checked, won nothing*.
  *Test:* `tools/verify_periods.py::empty_period_is_absent`, and its
  `--break zero_bucket_for_empty_period`.
  *Breaks when:* the builder enumerates every month between the first and last
  scored draw rather than only the months that carry one, so a gap month renders
  as R0.00 spent and R0.00 won — the cardinal rule breached one section below
  where INV-15 catches it.

  **The population clause is load-bearing and was nearly dropped here.** Keying
  bucket existence on `scorable()` alone satisfies the first sentence while
  letting a month whose only draws belong to an *unresolved* ticket produce a
  bucket reading R0.00 spent and R0.00 won — an R0.00 that means *excluded*,
  which is precisely what the second sentence forbids. It cannot happen today
  (`unresolved tickets` is 0), which is the same reason §4.5 gives for writing
  the win-side filter down rather than leaving it to the numbers.

## 6. Failure modes

| Assumption | When it breaks | What happens |
|---|---|---|
| `history.covered()` returns dated draws | the merged record is empty (no `archive_results.json` and the API refused) | `scorable()` rejects every entry, `buckets` is empty, `no_result_cents` is 0. The section renders its caption and no table. It must not render an empty table with a dropdown that offers nothing. |
| Every win sits on a covered draw | a future change scores an entry `scorable()` rejects | a win would have no bucket to land in. The builder sums winnings by iterating the buckets it built from spend, so such a win is silently dropped. INV-57 does not catch it — it checks the spend side. Named here rather than papered over. The guard is `check.py::check()`'s `if not scorable(...): continue`, and it is **unasserted** — LOTTO-0009 INV-11 does not hold it, being an assertion about `check.py::uncheckable_report()` at entry granularity whose *Breaks when* is the report being written per ticket. Removing `check()`'s `continue` would leave INV-11 green. |
| The dump exists | it does not | `build_model()` returns `{"no_dump": True, ...}` before any of this runs, and `_periods_section()` is never called. Unchanged behaviour. |
| A ticket is resolved | a price matches no known tier | it is excluded from every bucket, exactly as it is excluded from `spend.compared_cents` today, and its cost is already reported by the existing `unresolved_cents` row. It is **not** added to `no_result_cents`, which would give one ticket two explanations. |
| The span is short enough for a dropdown | it grows | 22 buckets today, growing by about 13 a year (12 months and a year). §13 carries the arithmetic. |

## 7. Tests

**The four invariants go in a NEW verifier, `tools/verify_periods.py`, not in
`tools/verify_page.py`** — and that is the correction this document's own draft
got wrong twice. `verify_page.py` is one of the three verifiers `CLAUDE.md`
§ Commands puts in the CI lane, because it needs neither `lotto_sms_raw.txt` nor
`archive_results.json`. It buys that by being **renderer-only**: `fixture_model()`
is a hand-authored dict and `render_pure()` installs an `all_draws` double that
*raises* to prove `page.py` performs no I/O. **No case in that file calls
`serve.build_model()` at all.** So a break living in the builder — which is
where all four of these live — cannot be observed there, and a case placed there
would assert only what its own author typed.

**Do not reach for `spend_over_checkable` or `uncheckable_not_a_loss` as the
real-builder pattern; neither is one.** LOTTO-0002 INV-15's prose describes its
fixture as *"built by running the real builder over them under a doubled
`all_draws`"*, and the shipped case does not do that — it calls
`fixture_model()` and `render_pure()`. That sibling claim is false and is filed
against LOTTO-0007 rather than fixed here.

`tools/verify_periods.py` therefore joins the **data-dependent** group, taking
the count named in `local-CI.sh`'s header from five to six and the verifier
scripts from eight to nine. That is the ordinary shape for this project:
`tools/verify_expiry.py` (LOTTO-0034) is exactly such a verifier, with the same
`--break` / `--list` flags, and is in that group for the same reason.

| Case | Invariant | What it exercises |
|---|---|---|
| `periods_reconcile` | INV-57 | recomputes the expected buckets from `tickets.py::TIER_PRICES` and `history.covered()` — never by calling `serve.py`'s own `tier_increments()`, which is the code under test — and asserts month buckets + `no_result_cents`, and year buckets + `no_result_cents`, both equal to `spend.compared_cents` |
| `periods_by_draw_date` | INV-58 | a ticket bought in the last days of a month whose ten draws run into the next, **winning on a draw in the second month**; asserts two buckets, the spend split falling where the draw dates fall, and the win landing in the second bucket |
| `periods_over_checkable` | INV-59 | asserts the bucket spend equals the recomputed scorable-and-resolved figure and is strictly less than the lifetime figure (so the fixture cannot be degenerate), **and** that a bucket's `won_cents` excludes the winnings of an unresolved ticket the fixture carries for that purpose |
| `empty_period_is_absent` | INV-60 | a fixture whose scored draws skip a month; asserts no bucket, no row and no `<option>` for that month, and that a month reachable only through an unresolved ticket produces no bucket either |

**The rendering side stays in `tools/verify_page.py`**, where it belongs: the
period control is scanned by the existing `nothing_in_the_url` case (§10), which
needs `fixture_model()` to carry a `periods` key or there is no control in the
bytes it scans. Adding that key is part of this item.

**Every case must be observed failing under its own break before it is
believed.** These are greenfield, so there is no pre-fix code to red-test
against — the `--break` flag is what makes "observed failing" reproducible, and
`docs/specs/LOTTO-0034-ticket-expiry-warning.md` records the same reasoning for
`tools/verify_expiry.py`. Five breaks for four cases, INV-59 carrying two.

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
| INV-57 | `tools/verify_periods.py::periods_reconcile` |
| INV-58 | `tools/verify_periods.py::periods_by_draw_date` |
| INV-59 | `tools/verify_periods.py::periods_over_checkable` |
| INV-60 | `tools/verify_periods.py::empty_period_is_absent` |
| §4.7 the period control puts nothing in the URL | `tools/verify_page.py::nothing_in_the_url` — LOTTO-0014 INV-21's existing case scans the whole rendered body, so it covers the control **once the fixture renders it**. It renders through `serve_on(Stub())` and `serve.refresh()`, and `Stub()` with no argument returns `fixture_model()` — a hand-authored dict, never the dump — so that fixture must gain `periods` buckets or the control is simply absent from the bytes being scanned and the row is empty cover. Wiring that is part of this item |
| §4.6 the current period's bucket is year/month to date, as far as the record goes | **nothing** — it is a property of `covered()` returning only draws in the record, not a separate computation, so there is nothing to assert that INV-57 does not already cover. The freshness half is LOTTO-0002 INV-18's stale notice, which this document adds no opinion to |
| §4.3's caption naming the span and LOTTO-0006 | **nothing** — no case reads the caption text; code review only. The exposure is a stale sentence, not a wrong figure |
| §6's second row — a win on an unscorable entry having no bucket | **nothing** — the `scorable()` gate in `check.py::check()` is code-comment discipline with no invariant behind it. LOTTO-0009 INV-11 does NOT cover it (§6). Not tracked; file it if the gate is ever touched |

## 11. Cross-doc impact

- **`CLAUDE.md`** — the `serve.py` bullet gains `periods`, and the cardinal-rule
  paragraph gains `_periods_section()` beside `_money_cell()` and `_draws_cell()`,
  since §4.5 resolves the three-valued question at the source rather than at the
  cell. **Three counted claims in § Commands move and must be re-measured, not
  adjusted by arithmetic:** "these eight scripts *are* the test suite" goes to
  nine, the data-dependent group goes from five to six (the CI lane stays at
  three), and the `verify_page.py` line's invariant range — today
  "INV-12..INV-21, INV-23..INV-25 and INV-27..INV-30" — is unchanged, because
  INV-57..INV-60 land in `tools/verify_periods.py`, which needs its own entry in
  that list.
- **`README.md`** — sign of success 4 moves from open to done in
  § How you would know it works, and the standing "**Where it stands against
  those today**" line goes from "4 and 5 are open" to 5 alone. The §4.3
  limitation is named there too, or the sign reads as covering money it does not.
- **`CHANGELOG.md`** — one entry citing LOTTO-0036.
- **`CLAUDE.md`** again — § Verification states "`--list` shows the thirty-one
  breaks" of `verify_page.py`. That count does **not** move: the five new breaks
  belong to `tools/verify_periods.py::BREAKS`. The sentence must be re-read
  rather than edited, and the new verifier's own break count stated beside it.
- **`local-CI.sh`** — its header states which verifiers are data-dependent and
  why, and carries the count as prose ("Five of the eight verifiers"). Both
  numbers move, and the header's own note records that this exact sentence was
  stale for months before LOTTO-0034 corrected it.
- **`docs/specs/LOTTO-0007`** — gains a deferred item: LOTTO-0002 INV-15's prose
  claims its case is "built by running the real builder", and the shipped case
  calls `fixture_model()` and `render_pure()`. Found by this gate, not fixed by
  it.
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
| 1 | 2026-08-27 | 3, cold — genre pinned `spec` | 2 | 3 | 1 | 3 | **Nine verified, nine fixed; two dismissed.** **All three lanes independently found the same defect**, the run's strongest signal: §4.5 said the win side needed "no extra filtering" because `check()` skips unscorable entries, while INV-59 scopes every bucket to *resolved* tickets and `build_model()` already writes `won_cmp` with an explicit `w["ref"] in resolved_refs`. `check()` gates on `scorable()` alone, so an implementer following §4.5 literally puts an unresolved ticket's winnings in a bucket whose cost was excluded — LOTTO-0002 §4.6's unearned surplus, per period. Invisible today at 0 unresolved tickets, which is why it had to be written down. **Two lanes each found four more.** `covered()` filters the merged RECORD, not the calendar, so the residue was mislabelled "not yet drawn" and "month to date" was unqualified — while §4.2 cites LOTTO-0034 §4.3, the section that exists to keep `draws_remaining` and `draws_left` apart; renamed `no_result_cents` and both claims qualified. INV-57's case as specified recomputed from the live dump, which would have taken `verify_page.py` out of the three-verifier CI lane `CLAUDE.md` puts it in, or passed on the runner asserting nothing. INV-60's fixture was a hand-authored model while its break lives in the builder — LOTTO-0002 INV-15 pins the real-builder pattern for exactly this. And INV-57 named no `--break` where its three siblings each do, against a registry whose own comment says breaks are named in the *Test:* clauses. **Two single-lane findings were wrong-owner claims:** §6 and §10 credited LOTTO-0009 INV-11 with holding `check()`'s `scorable()` gate — INV-11 is an assertion about `uncheckable_report()` and would stay green if that `continue` were deleted, so §10 now reads **nothing**; and §10 claimed `nothing_in_the_url` "already covers" the new control, when it renders `fixture_model()` and covers it only once that fixture carries buckets. **Dismissed:** all three lanes noticed §4.1 quoted a measurement of `(x*n)//n == x` — an integer identity that cannot fail on any data — and all three correctly declined to file it since the conclusion holds and nothing built changes; corrected in passing to state the algebra instead. Also dismissed: one lane read INV-15's forbidden-strings list as page-wide and therefore unsatisfiable against a bucket rendering R0.00; it is per-cell on unscorable *entry* rows and in fact requires R0.00 for a scored-but-lost entry, so the design is safe — but the clause was vacuous for the period table and was dropped. Three lane open questions resolved clean and are not counted: the 145 wins do occupy the same 20 month buckets as the spend side (verified as an identical set, not an equal count), §2's grep negative re-ran true, and LOTTO-0032 does own the per-period payout surface. |
| 2 | 2026-08-27 | 3, cold — identical brief, packet rebuilt from disk | 3 | 4 | 0 | 2 | **Nine verified, nine fixed; one dismissed. Cap reached (2 for a spec); the run ships.** **A VIOLENT cap: 5 of the 9 findings landed on text loop 1 wrote** — each anchor checked against loop 1's ledger, not recalled — so the run was repairing itself rather than converging, and this document's review ends here rather than buying a third loop. **The run's most consequential finding is the one two lanes got RIGHT and then both prescribed the wrong fix for.** Loop 1 sent the implementer to `spend_over_checkable` as the real-builder pattern; it is renderer-only (`fixture_model()` + `render_pure()`). Both lanes caught that and both pointed instead at INV-15's `uncheckable_not_a_loss` — which is renderer-only too. Opening the file settled it: **no case in `verify_page.py` calls `serve.build_model()` at all**, `render_pure()` installs an `all_draws` double that *raises*, and LOTTO-0002 INV-15's own prose ("built by running the real builder over them") is false about its shipped case — filed against LOTTO-0007, not fixed here. So all four invariants moved to a NEW data-dependent verifier `tools/verify_periods.py`, which is what LOTTO-0034 did with `verify_expiry.py`, leaving the CI lane at three. **Two lanes each found three more.** INV-60 governed bucket existence by `scorable()` alone while INV-59 scopes the population to *resolved* tickets — so a month reachable only through an unresolved ticket would render R0.00/R0.00, an R0.00 meaning *excluded*, which INV-60's own second sentence forbids. §4.5 keyed winnings on `w["date"]` (which CREATES a bucket) while §6 described iterating spend-built buckets (which DROPS the win) — two algorithms, one of which breaches INV-60; the spend side now owns the key set. And §7's row for `periods_over_checkable` described the spend assertion only, against INV-59's own "the case must assert both". **Two Q1s were mine from loop 1**: `won_cmp` was called the *lifetime* figure when it is `won.compared_cents` (the lifetime key is the UNFILTERED `won_life`, and LOTTO-0002 §4.6 says so outright — an implementer reaching for it ships exactly the failure INV-59 names), and §2's "exactly three money figures" undercounted six. **Two Q4s closed unfalsifiable clauses**: INV-58's "and a win" half had no assertion at all, and INV-59's win side had no break and no fixture — its fixture must now carry an unresolved ticket that WINS, since the live dump holds 0 unresolved and supplies no such case. **Dismissed:** two lanes called §10's "builds its page from `fixture_model()`" false because they could not see `Stub`; `Stub()` with no argument returns `fixture_model()`, so the claim was true and both prescribed remedies were wrong — the sentence was sharpened to name the path rather than corrected. Three lane open questions resolved clean and are not counted. |

## 13. Resource cost

No new dependency and no new file. The state added is one list on the model,
rebuilt on every build alongside everything else and never persisted.

Measured 2026-08-27: 20 month buckets and 2 year buckets, 22 rows. The span
grows by 13 buckets a year (twelve months and a year), so the dropdown reaches
about 100 entries in six years — still one `<select>`, and the table body is
four short cells per row. The buckets are accumulated inside the loop over
`t.pools` that `build_model()` already runs, so the work is two `Counter`
increments per covered draw and no additional pass over the tickets.
