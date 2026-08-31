# LOTTO-0029 — Reconcile the bank's payout SMSes against every computed win

**Status:** accepted (2026-08-19)
**Kind:** implement.
**Source:** ROADMAP LOTTO-0029 (user-request-2026-08-12) and ROADMAP
LOTTO-0010 (user-correction-2026-08-02). One umbrella spec covering both ids
per `spec-format.md` §2 — the roadmap records them as "one piece of work".
**Blocker for:** LOTTO-0032 (the same data on the page), LOTTO-0011 (what the
claim wording should say), LOTTO-0006 (which uses this as its test oracle).
**Pairs with:** LOTTO-0030 (shipped) — the import fix without which the dump
holds no payout at all.

The bank texts you the amount every time it pays a prize into your account.
This puts those amounts next to the ones the app worked out for itself, so
where the two disagree you can see both instead of trusting one.

## 1. Goal

After this ships, `check.py` reads the 369 payout SMSes already sitting in
`lotto_sms_raw.txt`, joins them to tickets on the `VAS` reference, and reports
— per reference — what the bank paid beside what this project computed. Every
reference the bank paid, or the app **computed a win for**, lands in exactly
one of seven named categories. A disagreement is shown with both figures and neither is silently
preferred.

This is the first check in the project that compares its output against
something **outside itself**. `tools/verify_sources.py` compares two results
feeds, `tools/verify_coverage.py` compares scoring against its own draw
selection, `tools/verify_pools.py` compares a price against a transcribed
table — all of them verify the code against the code's own inputs. The bank's
payout messages are the only record of what this user was actually paid.

## 2. Problem

`tickets.py::parse()` returns `None` for any SMS that is not a ticket
purchase, and `tickets.py::load()` discards those. That is every payout
message. The dump holds 954 records; 369 of them state a prize the bank paid,
and all 369 are read and thrown away on every run.

They were not there until recently, and the reason matters for §6. The
documented adb import (LOTTO-0001 §4.1) filtered on
`body LIKE '%lotto%' OR body LIKE '%powerball%'`; a payout message names no
game, and `lotto` is not a substring of `lottery`. So the dump was structurally
incapable of holding one until LOTTO-0030 widened the filter. `watch_sms.py`
now collects them continuously — the count has risen by one since the roadmap's
2026-08-13 measurement, which is the watcher working.

Measured 2026-08-19 by the census in §7.1, against the current dump:

| | |
|---|---|
| dump records | 954 |
| payout messages | 369 |
| distinct references paid | 225 |
| paid lifetime | R8,332.70 |
| references paid more than once | 77 |
| tickets parsed / distinct references | 561 / 561 |
| paid references with no purchase SMS | 1 |
| references the app computes a win for | 78 |
| computed lifetime | R3,343.20 |

Joining the two sets gives four consequences, numbered because §5 traces back
to them.

1. **The app under-reports by R4,989.50 over its lifetime** — R3,343.20
   computed against R8,332.70 paid. Most of that gap is correct (see 3), but
   none of it is currently visible at all.
2. **Where both have an opinion, they mostly agree and the error is
   one-directional.** Most of the 78 references with an opinion on both sides
   agree exactly; the rest are computed **low** far more often than high, by
   R315.50 against R11.60. There are **zero** references where the app claims
   a win the bank never paid. The per-category figures are §4.3's table, and
   are not restated here.
3. **147 references were paid where the app found no win** — and for 142 of
   them the silence is *correct*: at least one entry is not scorable, so
   `history.py::scorable()` gates it out and `check.py::uncheckable_report()`
   already says so. This is the uncheckable-is-not-a-loss rule working. One
   more is a reference with no purchase SMS at all, so there was never
   anything to score. **Four are fully scorable and were still missed.** Those four are the residue of
   the investigation recorded under ROADMAP LOTTO-0029, which eliminated six
   causes — the division table, a date offset, the archive parser and store,
   the ticket board parse, the stored results themselves (checked against two
   independent sites), and a second game bought in one transaction. They
   remain unexplained.
4. **The unit is the reference, not the payment.** 77 of the 225 paid
   references carry more than one payout, because a multi-draw ticket is paid
   per draw. Anything comparing one payment against one ticket reports 77
   false shortfalls.

**Update 2026-08-31 — LOTTO-0006 drained consequence 3.** The figures above are
the shipping measurement and are left as written. Re-measured after the archive
floor moved back to the earliest purchase SMS: `unscored` fell from 142 to 3,
`agree` rose from 61 to 198, computed lifetime rose to R7,994.30 against the
same R8,332.70 paid, and the unexplained difference fell from R4,989.50 to
R338.40. `unpaid` is still zero, which is the figure that must not move. What
did **not** move is the residue LOTTO-0033 and LOTTO-0037 own: `low` is still
15, `unexplained` still 4, and `high` rose from 2 to 4. Consequence 3's argument
is unchanged — it is why the categories are separate — but its 142 is history.

Consequence 3 is why this cannot be built as a scoring correction. An
unexplained payout is a fact about the domain — the traced case reaches no
paying division in any of its three pools against numbers now verified twice,
and was paid the next morning regardless.

## 3. Scope decisions (agreed with the user)

- **A disagreement is flagged loudly, both figures shown, and never resolved
  in the SMS's favour.** Decided by the user, 2026-08-13. This is the load-
  bearing decision: adopting the bank's figure would make every scoring defect
  invisible the moment the bank disagreed with it, which is the failure this
  project exists to prevent. It becomes INV-43.
- **An unexplained payout is its own category, never evidence that scoring is
  broken and never silently dropped.** Recorded under ROADMAP LOTTO-0029 on
  2026-08-13 as the consequence of that decision, once the archive data had
  been cleared by a second source. It becomes INV-44 and INV-45.
- **The page is deferred to LOTTO-0032**, filed 2026-08-19 in this session. It
  is a rendering surface with its own security invariants (INV-21) and its own
  `tools/verify_page.py` cases and `--break` red-tests. Building it inside this
  item doubles the work and binds the page to invariants this spec has to
  define first.
- **The reconciliation lands in `check.py`, and the parsing in `tickets.py`.**
  Chosen here, 2026-08-19, against a new `payouts.py` module (§8). `tickets.py`
  is the project's only bank-specific file and owns `rows()`, the dump's one
  reader; `check.py` is what both consumers already import.
- **Claim wording is untouched.** `check.py` prints `STILL CLAIMABLE:` and
  `CLAIM_DAYS = 365`, which LOTTO-0011 exists to correct. This spec adds a
  report beside that one and changes none of its words — settling what
  "claimable" should say needs the threshold question LOTTO-0011 names, and
  answering it here would resolve that item by side effect.

## 4. Design

### 4.1 Parsing — `tickets.py`

All 369 payout messages share exactly one shape, verified by normalising every
digit run and reference in the matching bodies and counting distinct results
(§7.1). With the reference replaced by the project's sentinel:

```
Standard Bank: The winnings of R123.45 for ticket ref: VAS00000000000 will be
paid in your account within two business days. T&C's apply. Query? 0860 123 000
```

```python
PAYOUT = re.compile(r"winnings of R([\d,]+\.?\d*) for ticket ref:\s*(VAS\d+)", re.I)


class Payout:
    def __init__(self, ref, cents, received):
        # cents is a whole number, never a float: this is the figure a
        # computed win is compared against, and money compared in rands
        # disagrees with itself (INV-42).
        self.ref, self.cents, self.received = ref, cents, received


def parse_payout(body, received=None):
    """Return a Payout, or None if this SMS is not a prize payment.

    The mirror of parse(), and the two are disjoint by construction: a
    purchase debit reads "R<amount> paid from Acc. NNNN to VAS... LOTTO" -
    money LEAVING the account - and names a game, which is why it survived
    the old import filter and a payout did not. Widening this pattern
    toward "paid" or "R... VAS..." would count spending as winning.
    LOTTO-0010 made exactly that mistake against these 14 debits before the
    real payouts existed to compare them with.
    """


def load_payouts(path="lotto_sms_raw.txt"):
    """-> [Payout], via rows() - the dump format's one reader (INV-34)."""
```

`load_payouts()` uses `tickets.py::rows()`, exactly as `load()` does. It does
not re-split the dump: a second reader of one format agrees today and drifts
later, and LOTTO-0003 INV-34 already owns that rule.

### 4.2 The join, and the unit

The join key is `Payout.ref` against `Ticket.ref`, compared as exact strings.
Both are the bare `VAS…` form — `parse()` strips the `Ref:` prefix, and the
payout pattern captures the reference without it. No fuzzy matching, no
prefix match, no fallback on amount or date: 561 tickets carry 561 distinct
references, so the reference is a key rather than a hint, and a near-match
join would attribute one ticket's money to another.

**The unit of comparison is the reference**, and every payout to one reference
is summed before comparison (§2 consequence 4, INV-41).

### 4.3 The seven categories

`check.py::reconcile(tickets, wins, payouts)` returns one record per reference
in the union of *paid* and *computed*, where:

- ***paid*** is the references `load_payouts()` found a payment for — 225.
- ***computed*** is the references carrying **at least one winning line** in
  `wins` — 78. It is **not** every reference the app scored, which is all 561
  of them; taking that reading puts 483 losing tickets into `unpaid`, the row
  §4.3 calls the dangerous direction.
- ***`wins`*** is the **whole** of `check()`'s output, expired lines included.
  `check.py::__main__` holds both that list and an unexpired `live` subset, so
  this is one identifier at the call site — and the bank's payouts are
  lifetime, so a prize paid in 2025 is still money it paid.

The record has five fields:

```python
{
    "ref":         "VAS00000000000",  # the join key, exact string match
    "paid_cents":  int | None,        # None when the bank paid nothing for it
    "computed_cents": int | None,     # three-valued; see below
    "category":    str,               # one of the seven, by the order below
    "first_win":   str | None,        # "YYYY-MM-DD" of the earliest winning
                                      # line, None where there is no win
}
```

**`computed_cents` is three-valued, and the three must not converge.** This is
`CLAUDE.md`'s cardinal rule at this layer, and `page.py::_money_cell()` already
holds the same rule for `won_cents`:

- **`None`** — *not checkable.* No entry of this reference could be scored, so
  the app has no opinion. It is not a zero.
- **`0`** — *checked, and the total prize is zero.* Either no entry reached a
  paying division, or one did and the source itself priced that division at
  R0.00 (below). **So `computed_cents` never answers "did it win?"** —
  `first_win` is the only field that does, and rows 3 to 5 key on it.
- **a positive integer** — the summed prize of its winning lines.

A reference that is only *partly* scorable carries an **integer**, never
`None`: some of it was checked, so reporting it as "not checkable" would be
the wholly-excluded reading `LOTTO-0009` INV-11 forbids. Measured 2026-08-19:
3 of the 147 paid references with no computed win are partly scorable.

**The categories are decided in this order, and the order is part of the
contract** (INV-45). Written as an unordered set of conditions they overlap: a
reference with no ticket has no entries, so "every entry is scorable" is
vacuously true of it, and it would satisfy `unexplained` as well as
`no_ticket`. Verified 2026-08-19 — `all()` over that reference's empty entry
set returns `True`.

| # | Category | Decided when | 2026-08-19 | What it means |
|---|---|---|---|---|
| 1 | `no_ticket` | no ticket carries this reference | 1 | The bank paid against a reference this dump has no purchase SMS for. |
| 2 | `unpaid` | no payout carries this reference | 0 | The dangerous direction. Reported, never asserted to be zero (INV-46). |
| 3 | `agree` | it has a winning line, and paid == computed | 61 | The bank and the app agree exactly. |
| 4 | `low` | it has a winning line, and computed < paid | 15 | The app under-counted a reference that did win. A **pricing** question, not a matching one. |
| 5 | `high` | it has a winning line, and computed > paid | 2 | The app over-counted. |
| 6 | `unexplained` | no winning line, and every entry scorable | 4 | The residue of §2 consequence 3. Its own category by the user's decision. |
| 7 | `unscored` | no winning line, and ≥1 entry not scorable | 142 | An entry nothing can score may be what the bank paid on. |

**Rows 3 to 5 turn on the *presence* of a winning line, never on its value.**
`check.py::amount()` returns `0.0` for a division the source itself states as
R0.00, so a reference can win and be priced at nothing; a bound of the form
`0 < computed` would drop it out of every category and break the partition.
None exist today (0 winning lines priced at 0.00, measured 2026-08-19), which
is exactly why the bound would have shipped unnoticed.

**Row 7 says *may*, and the word is load-bearing.** `unscored` is not a
verdict that the app was right — it is the statement that an unscorable entry
is available as an explanation, so the reference is not a clean lead.
Collapsing rows 6 and 7 buries today's 4 real leads under 142 references
carrying an excuse (INV-44).

`unpaid` carries `first_win` because the payout message promises payment
"within two business days": a win from a draw three days ago sitting here is
normal, and one from 2025 is not.

### 4.4 Reporting — `check.py`

`reconcile_report(records)` returns `(lines, counts)`, deliberately the shape
`uncheckable_report()` already returns, so `check.py::__main__` and — later —
LOTTO-0032 consume one convention rather than two. `__main__` prints it above
the existing claimable list.

**A dump with no parsable payout prints that it has none** (INV-47). This is
the cardinal rule applied to this feature: after a bank wording change the
pattern in §4.1 matches nothing, and a reconciliation that then reports
"0 disagreements" would be announcing perfect agreement on the strength of
having no data at all. LOTTO-0031 is the same class — a rebranded game name
parsed to `None` and a ticket was silently never scored.

### 4.5 Cost

`reconcile()` adds one pass over records already read by `rows()` and two
dictionaries bounded by the dump: 225 and 78 entries today. It holds no state
between runs and adds no file, no dependency and no build target. Against the
measured ~36s a full `check.py` run already takes on this dump — dominated by
scoring its 1,238 entries — it is not observable.

## 5. Invariants

- **INV-40** — A prize payment parses to a `Payout`; a purchase debit never
  does. *Test:* `tools/verify_payouts.py::purchase_is_not_a_payout` → every
  dump body matching `paid from Acc` parses to `None` as a payout; 14 such
  bodies today, 0 accepted. *Breaks when:* the pattern is widened toward
  `paid` or a bare `R… VAS…`, at which point those 14 debits — money the user
  *spent*, in three wordings naming LOTTO and PowerBall — are counted as
  winnings. **The obvious clause here is the wrong one**: asserting that no
  body parses as both a ticket and a payout is vacuous, because a debit does
  not parse as a ticket either (`parse()` accepts 0 of the 14), so it would
  pass against exactly the widening it is meant to forbid.

- **INV-41** — The unit of reconciliation is the reference, and every payout to
  one reference is summed before comparison. *Test:*
  `tools/verify_payouts.py::multiple_payouts_sum` → a reference with two
  payments reconciles against their total. *Breaks when:* the payout list is
  keyed by message; 77 of 225 references today carry more than one payment and
  each would read as a shortfall.

- **INV-42** — Money is compared in whole cents. *Test:*
  `tools/verify_payouts.py::cents_not_floats` → a computed win and a payment
  equal in cents but unequal as float rands categorise as `agree`.
  *Breaks when:* the comparison is written against `win["amount"]`, which `amount()`
  returns as a float, so a sum of three prize divisions can miss its equal by
  one part in 10^13 and report a phantom disagreement.

- **INV-43** — A disagreement carries both figures, and the computed figure is
  never replaced by the bank's. *Test:*
  `tools/verify_payouts.py::disagreement_keeps_both` → a **synthetic** reference
  whose payout and winning lines differ categorises `low` or `high` and carries
  `computed_cents` equal to the summed cents of **its own winning lines**, not
  to `paid_cents`; every non-`agree` record carries both fields with `None`
  distinguishable from `0`; and the `wins` list `reconcile()` was passed is
  unchanged when it returns. **The quantifier alone is the wrong clause**:
  adopting the bank's figure turns those references into `agree`, so they leave
  the "every non-`agree` record" set and the case passes against the one change
  this invariant exists to forbid. *Breaks when:* a later change adopts the SMS
  amount as authoritative for its own ticket — the 15 `low` references would
  read as agreement, and the pricing defect behind them would stop being
  visible anywhere.

- **INV-44** — A paid reference with an unscorable entry is reported apart from
  one where every entry is scorable. *Test:*
  `tools/verify_payouts.py::unscored_is_not_unexplained` → a **synthetic** paid
  reference whose every entry is scorable and which has no winning line lands
  in `unexplained`, and one carrying an unscorable entry lands in `unscored`.
  The real-dump counts (4 and 142 today) are printed, never asserted — §7 says
  why. *Breaks when:*
  the two are merged, which buries four real leads under 142 references
  carrying an excuse. **A disjointness assertion is the wrong clause here**:
  merging empties `unexplained`, and the empty set is disjoint from everything,
  so the obvious test passes against precisely the merge it forbids.

- **INV-45** — Every reference in the union of paid and computed lands in
  exactly one category, and none is dropped. *Test:*
  `tools/verify_payouts.py::categories_partition` → the seven counts sum to
  `len(paid ∪ computed)`, that union built **independently** — from
  `load_payouts()` and `check()` directly, never from `reconcile()`'s own
  output — and taken after the `"?"` sentinel of §6 is excluded from both
  sides; 1 + 0 + 61 + 15 + 2 + 4 + 142 = 225 today, in §4.3's decision order.
  *Breaks when:* the conditions are evaluated as an unordered set, so the one
  no-ticket reference matches `unexplained` too and is counted twice; or the
  `no_ticket` case is filtered out at the join, which is the likely one, since
  dropping references with no ticket is the obvious way to write the loop and
  discards money the bank actually paid. **Taking the denominator from
  `reconcile()`'s output is the wrong clause**: dropping a reference then
  shrinks both sides equally and the count passes against exactly that defect —
  the rule `tools/verify_pools.py` states as never importing the thing under
  test.

- **INV-46** — An `unpaid` record carries `first_win`, the date of its earliest
  winning line, and its count is never asserted to be zero. *Test:*
  `tools/verify_payouts.py::unpaid_carries_draw_date` → against a **synthetic**
  computed win with no payout, the record's `first_win` is set; the real count
  is printed, not asserted. The fixture must be synthetic: the category is
  empty today, so a case run over real data alone would pass without executing
  the rule. *Breaks when:* the record
  is reduced to a reference and an amount, leaving a reader unable to tell a
  three-day-old win awaiting its two business days from a prize never paid.

- **INV-47** — A dump from which no payout parses is reported as carrying no
  payout data, never as agreement. *Test:*
  `tools/verify_payouts.py::no_payouts_is_not_agreement` → against a dump with
  every payout removed, `reconcile()` itself returns **no records** rather than
  78 `unpaid` ones, and the report names the absence and emits no category
  census. **The guard belongs in `reconcile()`, not only in the report**:
  §4.4's whole point is that `check.py::__main__` and LOTTO-0032 consume one
  convention, so a check living in the report leaves the page rendering the
  fictions and every consumer re-inventing its own "is this data real?" test. *Breaks when:* the bank changes its wording and the report
  degrades to "0 disagreements over 0 references" — the same silent parse
  failure LOTTO-0031 shipped, on the surface built to catch it. **Suppressing
  the census is the half that is easy to miss:** with no payout parsed every
  reference the app computed a win for satisfies `unpaid`'s condition, so a
  report that keeps the table announces 78 prizes the bank never paid — the category §4.3
  calls the dangerous direction, filled entirely with fiction.

## 6. Failure modes

- **The bank changes the payout wording.** `parse_payout()` returns `None` for
  every message and the category counts all fall to zero. INV-47 is the guard
  and it is the only one: nothing can validate a pattern against wording that
  does not exist yet. This is the same exposure `GAME_MAP` carries, and it cost
  a silently unscored ticket in LOTTO-0031.
- **A payout arrives before its ticket.** `watch_sms.py` appends in arrival
  order, and the join is over the whole dump rather than a window, so ordering
  cannot matter. A payout whose purchase SMS was never collected is `no_ticket`
  — one today — and is reported rather than dropped.
- **The amount cannot be read.** A body matching the pattern whose amount does
  not parse as a number is a corrupt record, not a zero payment.
  `parse_payout()` returns `None`, which routes it to INV-47's census rather
  than reporting a prize of R0.00. `check.py::amount()` already sets this
  precedent under INV-22: a price that cannot be looked up raises rather than
  pricing at zero.
- **A ticket carries no reference.** `tickets.py::parse()` falls back to the
  sentinel `"?"` when no `Ref:VAS…` matches. No payout can ever carry that
  string, so such a ticket simply never joins — but two of them would sum
  their computed wins under one `"?"` key and surface as a single spurious
  `unpaid`. `reconcile()` therefore excludes `"?"` from the join outright.
  None exist today (0 of 561, measured 2026-08-19).
- **Two tickets share a reference.** They do not today — 561 tickets, 561
  distinct references — but if the bank ever reissued one, the reference stops
  being a key and both tickets' computed wins would sum against one payment.
  `reconcile()` therefore compares against the sum of computed wins for the
  reference, which is correct under either reading, and the duplicate itself is
  a `tools/verify_payouts.py` census line rather than a crash.
- **The dump is missing.** `load_payouts()` fails exactly as `load()` does, and
  `serve.py`'s existing "nothing has been imported" notice already covers the
  page. No new empty state is introduced.

## 7. Tests

`tools/verify_payouts.py`, run from the repository root after `backfill.py`
and with `lotto_sms_raw.txt` present. It joins the five verifiers that need the
dump, so it belongs in `local-CI.sh`'s local-only lane beside
`verify_sources.py`, `verify_coverage.py` and `verify_pools.py` — never in the
CI lane, which has no dump and no archive.

The exit code is the signal; the census counts are printed and move as
messages arrive, following `tools/verify_pools.py`'s stated convention. The
asserted terms are named rather than left to "the zero-terms", because a count
that happens to be zero today is not thereby a contract. What is asserted:
**0** purchase debits accepted as payouts, **0** references dropped by the
partition, and the **synthetic** fixtures of INV-43, INV-44 and INV-46.

**Every real-dump category count is printed and none is asserted** — not
`unpaid`, and not `unexplained` or `unscored` either. §8 rejects
`assert unpaid == 0` because it is true today and is not a contract, and the
same reasoning covers the other two from the other direction: `unexplained` is
a defect residue this project intends to explain away, and LOTTO-0006's whole
value (§9) was turning the `unscored` references into an oracle — which it did
on 2026-08-31, draining most of that category. An
assertion that either stays non-empty goes red on the exact progress this spec
exists to enable, in `local-CI.sh`'s local-only lane, blocking a push.

It carries a `--break <name>` flag applying one deliberate defect and asserting
the named case goes red, and a `--list`. This follows `verify_page.py`, and for
the same recorded reason: this work is greenfield, so there is no pre-fix code
to red-test against, and the flag is what makes "every case observed failing"
reproducible rather than a one-off hand edit.

**Amended 2026-08-19 by the implementation, and it is a real limitation rather
than a detail.** Only `--break accept_debits` patches the production path (the
`PAYOUT` pattern itself). The other seven patch `reconcile()`'s *output* to
produce what the named defect would produce, which is indistinguishable from
the buggy code at the boundary the case observes — but is not the same thing as
executing it. The file says so in its own header rather than implying otherwise.
One of the eight was written wrong first time and is worth recording: the
`compare_in_rands` break converted already-rounded cents back to rands, where
`30/100` is exactly `0.3`, so the float error the rule exists to catch had
already been rounded away and the break **confirmed** the invariant instead of
refuting it. The defect is in how the win amounts are *accumulated*, not in how
they are compared. A break that does not go red is a break that is wrong.

**It prints no message body and no amount against a reference.** The census is
counts and totals only. `tools/verify_privacy.py` compares tracked files
against the dump, and a verifier that echoed a payout line into a CI log would
be putting real content where that check cannot see it.

| Case | Invariant |
|---|---|
| `purchase_is_not_a_payout` | INV-40 |
| `multiple_payouts_sum` | INV-41 |
| `cents_not_floats` | INV-42 |
| `disagreement_keeps_both` | INV-43 |
| `unscored_is_not_unexplained` | INV-44 |
| `categories_partition` | INV-45 |
| `unpaid_carries_draw_date` | INV-46 |
| `no_payouts_is_not_agreement` | INV-47 |

### 7.1 The census command

Every figure in §2 and §4.3 is this script's output, run 2026-08-19 from the
repository root. It applies §4.3's decision order, so it is also the check that
the seven categories partition. `tools/verify_payouts.py` prints the same
census once built, which is what removes the hand step.

```python
import re, sys, collections; sys.path.insert(0, ".")
from tickets import rows, load
from history import scorable
import check
raw = open("lotto_sms_raw.txt", errors="replace").read()
PAY = re.compile(r"winnings of R([\d,]+\.?\d*) for ticket ref:\s*(VAS\d+)", re.I)
recs = rows(raw)
paid, times = collections.defaultdict(int), collections.Counter()
for _a, _ms, body in recs:
    if m := PAY.search(body):
        paid[m.group(2)] += round(float(m.group(1).replace(",", "")) * 100)
        times[m.group(2)] += 1
tk = load()
by = collections.defaultdict(list)
for t in tk: by[t.ref].append(t)
won = collections.defaultdict(int)
for w in check.check(tk): won[w["ref"]] += round(w["amount"] * 100)
cat, lo, hi = collections.Counter(), 0, 0
for r in set(paid) | set(won):
    if r not in by:                      cat["no_ticket"] += 1
    elif r not in paid:                  cat["unpaid"] += 1
    elif r in won:
        p, c = paid[r], won[r]
        cat["agree" if p == c else "low" if c < p else "high"] += 1
        lo += max(0, p - c); hi += max(0, c - p)
    elif all(scorable(t, pf) for t in by[r] for pf, _ in t.pools):
                                         cat["unexplained"] += 1
    else:                                cat["unscored"] += 1
print(f"records {len(recs)}  payouts {sum(times.values())}  refs {len(paid)}  "
      f"paid {sum(paid.values())}c  multi {sum(1 for r in times if times[r]>1)}")
print(f"tickets {len(tk)}  distinct {len({t.ref for t in tk})}  "
      f"won-refs {len(won)}  computed {sum(won.values())}c  entries {sum(len(t.pools) for t in tk)}")
print("  ".join(f"{k} {cat[k]}" for k in
      ("agree","low","high","unscored","unexplained","no_ticket","unpaid")),
      f" sum {sum(cat.values())} of {len(set(paid)|set(won))}")
print(f"low short by {lo}c   high over by {hi}c")
```

Its output, 2026-08-19:

```
records 954  payouts 369  refs 225  paid 833270c  multi 77
tickets 561  distinct 561  won-refs 78  computed 334320c  entries 1238
agree 61  low 15  high 2  unscored 142  unexplained 4  no_ticket 1  unpaid 0  sum 225 of 225
low short by 31550c   high over by 1160c
```

**It needs the live results API**, because `check.check()` reads prize
divisions from it (INV-5 — divisions are never hardcoded). That API returned
`HTTP 504` twice while this spec was being written and succeeded on the next
attempt, so a failure here is not evidence about the dump.

The payout wording is uniform and no message is both a purchase and a payout:

```bash
python3 -c "
import re,sys,collections; sys.path.insert(0,'.')
from tickets import rows, parse
P=re.compile(r'winnings of R[\d,.]+ for ticket ref:\s*VAS\d+',re.I)
b=[x[2] for x in rows(open('lotto_sms_raw.txt',errors='replace').read())]
p=[x for x in b if P.search(x)]
print(len(p), len({re.sub(r'VAS\d+','R',re.sub(r'[\d][\d,.]*','N',x)).strip() for x in p}),
      sum(1 for x in p if parse(x)))"
# -> 369 1 0
```

## 8. Alternatives considered (and rejected)

- **Treat the payout as authoritative for its own ticket.** Rejected by the
  user on 2026-08-13. It would price the whole archive era with no payout-page
  scrape, which is genuinely attractive — and it would erase the 15 `low`
  references, which is the evidence that something in pricing is wrong. A
  scoring bug that hides is worse than one that is visible and unfixed.
- **A new `payouts.py` module.** Rejected here. The parsing is bank wording,
  which `tickets.py` already owns as the project's only bank-specific file, and
  splitting it out would give the dump a second reader — the thing LOTTO-0003
  INV-34 forbids. The reconciliation is a comparison against `check()`'s
  output, and a third module between them would leave `serve.py` importing two
  things to answer one question.
- **Fold the payout into `wins` as a synthetic entry.** Rejected: it makes
  R8,332.70 the reported total by construction and there is no longer anything
  to disagree with. This is INV-43 stated as a design, and it is the shape a
  future session is most likely to reach for.
- **Compare per payment rather than per reference.** Rejected on the data: 77
  of 225 references carry more than one payment (§2 consequence 4).
- **Assert `unpaid == 0` as a regression check.** Rejected. It is true today
  and it is not a contract: a win from a draw in the last two business days
  legitimately sits there, so the assertion would fail on correct behaviour and
  be disabled the first time it fired. Reported instead (INV-46).
- **Fix the four unexplained payouts as part of this item.** Rejected: six
  causes have been eliminated against them and the remaining explanation is
  about the domain rather than the code. Building the category is what makes
  the fifth cause findable; guessing at one now is what §2 consequence 3 warns
  against.

## 9. Out of scope

- **The page** — LOTTO-0032. This spec puts the reconciliation in the model
  and the terminal; rendering it is a separate surface with its own security
  invariants.
- **Correcting the 15 `low` references, and explaining the 4 `unexplained`
  ones** — LOTTO-0033, filed 2026-08-19 when this shipped. This item makes both
  populations visible and counted; it does not explain either. LOTTO-0010 is
  closed with this spec and is not the owner.
- **The claim wording and `CLAIM_DAYS`** — LOTTO-0011, per §3.
- **Backfilling further back** — LOTTO-0006, shipped 2026-08-31. That item's
  value was that this reconciliation turns the `unscored` references (plus the
  `no_ticket` one) into an oracle, so it was downstream of this, not part of
  it.
- **Anything that writes to the dump** — LOTTO-0003 owns the only writer.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-40 | `tools/verify_payouts.py::purchase_is_not_a_payout` |
| INV-41 | `tools/verify_payouts.py::multiple_payouts_sum` |
| INV-42 | `tools/verify_payouts.py::cents_not_floats` |
| INV-43 | `tools/verify_payouts.py::disagreement_keeps_both` |
| INV-44 | `tools/verify_payouts.py::unscored_is_not_unexplained` |
| INV-45 | `tools/verify_payouts.py::categories_partition` |
| INV-46 | `tools/verify_payouts.py::unpaid_carries_draw_date` |
| INV-47 | `tools/verify_payouts.py::no_payouts_is_not_agreement` |
| §4.1 — the payout pattern still matches the bank's wording | **nothing** — INV-47 catches the *consequence* (a census of zero) but nothing validates the pattern against wording that has not been written yet. Same exposure as `GAME_MAP`, which cost LOTTO-0031. |
| §4.3 — that the seven categories are the *right* seven | **nothing** — INV-45 checks they partition, not that the split is meaningful. A category nobody reads is invisible to every check here. |
| §4.4 — the report's wording | **nothing** — `reconcile_report()` returns lines, so a case could assert them, and this spec does not require one. Deferred deliberately: LOTTO-0032 renders the same data and its wording rules belong with it. |

Three of eleven rows say `nothing`. All three are about the boundary between
this project and the bank's wording, or about a judgement no assertion can make.

## 11. Cross-doc impact

- `CLAUDE.md` — the verifier list gains `tools/verify_payouts.py` with its
  invariant range; the architecture diagram's `lotto_sms_raw.txt` line gains
  the payout reader beside `tickets.py::rows()`; and the load-bearing-decisions
  list gains the rule that the bank's figure never replaces the computed one.
- `local-CI.sh` — one `run` line in the local-only lane (after
  `verify_pools.py`), and its header's check count.
- `README.md` — the command list, and the layman description of what the tool
  reports.
- `CHANGELOG.md` — an `Added` entry citing LOTTO-0029 and LOTTO-0010.
- `ROADMAP.md` — LOTTO-0029 and LOTTO-0010 both flip on this item shipping;
  LOTTO-0032 is filed and blocked by it.
- `docs/specs/LOTTO-0001-lottery-ticket-tracker.md` — §4.1 describes the adb
  import filter and the message shapes it collects; the payout shape is a
  second shape that filter now admits. Its §11 gains no row: the invariants
  here are this spec's.
- `docs/specs/LOTTO-0009-entered-pools.md` — untouched. Reconciliation reads
  `Ticket.pools` and changes nothing about how they are derived.

## 12. Cold-eyes loop log

| Loop | Date | Reviewer | Findings | Outcome |
|------|------|----------|----------|---------|
| 1 | 2026-08-19 | 3 cold lanes + `check-doc-facts` | **Q1 2 · Q2 3 · Q3 4 · Q4 1** (verified 10 / dismissed 1) | **All ten fixed.** **Three lanes independently found the same defect**, which is the run's strongest signal: §4.3 enumerated the record as four fields while INV-46 required a fifth, so a builder ships four keys and `unpaid_carries_draw_date` has nothing to assert — the field is now named `first_win` in §4.3's schema. **Two lanes found the category overlap**, and it verified empirically: a reference with no ticket has no entries, so `all(scorable(...))` over the empty set returns `True` and the one `no_ticket` reference satisfied `unexplained` too. §4.3 now fixes a decision ORDER and says so. **The best single finding was one lane's alone** — the spec never said what `computed_cents` holds where nothing was scorable, so a builder writes `0` and LOTTO-0032's `_money_cell()` renders R0.00: "no data" as "did not win", on the surface built to expose it. It is now three-valued (`None` / `0` / positive) against `CLAUDE.md`'s cardinal rule, and a *partly* scorable reference carries an integer so LOTTO-0009 INV-11 is not breached — 3 of the 147 are partly scorable, measured. **Two vacuous test clauses**, the same class the draft had already self-caught twice: INV-44 asserted disjointness, which holds against the merge it forbids because the empty set is disjoint from everything, and is now a positive assertion; and §7's unnamed "zero-terms" would have had a builder write `assert unpaid == 0`, the exact assertion §8 rejects, so the asserted terms are now named. **A latent partition hole**: `low`/`high` were bounded `0 < computed`, and `amount()` returns `0.0` for a division the source states as R0.00, so a zero-priced win matched no category at all — rows 3-5 now turn on the presence of a winning line, never its value. None exist today, which is why it would have shipped. Also fixed: INV-47 was silent on the category census when zero payouts parse, where every scored reference satisfies `unpaid` and the report would announce 78 prizes the bank never paid; INV-43 carried a second, conflicting return contract; §9 said 143 where §4.3 says 142 + 1; and a ref-less ticket's `"?"` sentinel is now excluded from the join (§6). **§7.1's census script was my own Q1** — it asserted it produced every figure in §2 and §4.3 and produced neither the scorability split nor the no-ticket count, importing `scorable` without calling it. Rewritten to apply §4.3's decision order, and the script pasted into the spec was extracted and RUN: its output is byte-identical to the output the spec claims. One dismissal, true but immaterial: INV-40's "three wordings" for the debits. `check-doc-facts` clean both before and after; its test-surface check did not run (ANTS-4393) so the clauses were checked by hand. |
| 2 | 2026-08-19 | 3 cold lanes (identical brief, packet rebuilt from disk) | **Q1 0 · Q2 4 · Q3 2 · Q4 2** (verified 8 / dismissed 0) | **All eight fixed. Cap reached (2 for a spec); the run files its tail — which is empty — and exits.** **A HIGH-COLLATERAL CAP, not a calm one: 5 of the 8 findings landed on text loop 1 wrote**, each anchor checked against loop 1's ledger rather than recalled. Per `review-contract` § At the cap this document does not get a third cold read; it goes to implementation, which exercises the contract against real code. **Size is not the problem** — at 616 lines it is the shortest substantive spec in `docs/specs/`. **All three lanes independently found the same defect, and it is the most severe of the run:** §1 said every reference *"the app scored"* lands in a category, while INV-45 and §7.1's census build the union from references carrying a **winning line**. The app scores 561 references and 78 carry a win, so a builder taking §1 adds **483 losing tickets to `unpaid`** — the row §4.3 itself calls the dangerous direction — announcing hundreds of prizes the bank never paid. *paid*, *computed* and the `wins` argument are now defined where a builder implements from. **Three of the five collateral findings are loop 1's fixes being subtly wrong rather than incomplete.** Loop 1 defined `computed_cents == 0` as *"checked, and it did not win"*, which a zero-priced win also satisfies — so the three values converged in the very section forbidding convergence; `first_win` is now the sole has-a-win signal and `0` means *total prize is zero*. Loop 1's §7 asserted `unexplained` and `unscored` stay non-empty, which is the shape §8 rejects for `unpaid`, pointed the other way: both are counts this project intends to **drain** (LOTTO-0006 turns the 142 into an oracle), so the assertion would go red on correct progress and block a push. And loop 1's `"?"`-sentinel exclusion in §6 contradicted INV-45's denominator. **A third vacuous test clause in three loops**, this time two at once: INV-43's *"every non-`agree` record"* quantifier cannot falsify its own stated break, because adopting the bank's figure turns those references into `agree` and they leave the set; and INV-45's partition passes if the union is taken from `reconcile()`'s own output, since dropping a reference shrinks both sides — the rule `tools/verify_pools.py` already states as never importing the thing under test. Both are now positive and synthetic. Also fixed: INV-47's guard sat on the report only, leaving `reconcile()` handing LOTTO-0032 78 fictional `unpaid` records. `check-doc-facts` clean before and after; its test-surface check did not run (ANTS-4393), so all eight clauses were checked by hand. |
| impl | 2026-08-19 | none dispatched — implementation | 1 clause amended | **Implementation row, not a review loop: no reviewer was dispatched.** The contract survived the build with one clause amended and no design change. §7 promised a `--break` per case; seven of the eight patch `reconcile()`'s output rather than the production path, which the spec now says outright. Two defects the build found were in the TEST rather than in the contract or the code, and both are the class this document already names twice: the INV-44 fixture used `lotto/1` for its "unscorable" entry, which has 171 draws — the pool no source carries is `daily/1` — so both entries were scorable and `unexplained` was the correct answer; and INV-47's assertion forbade the substring `agree`, which fires on the report's own sentence *"This is NOT agreement"*. Everything else built as specified: the seven categories reproduce §4.3's census exactly (61·15·2·142·4·1·0 = 225, R8,332.70 paid against R3,343.20 computed), and `computed_cents` is genuinely three-valued in the real data — 140 `None`, 7 exactly `0`, 78 positive — so the distinction the cardinal rule protects is live rather than theoretical. Eight cases green; eight observed failing under their own break. `./local-CI.sh --force` 10/10 PASS. |
