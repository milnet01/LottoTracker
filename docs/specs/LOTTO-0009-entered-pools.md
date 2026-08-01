# LOTTO-0009 — Score every pool a ticket was entered in, derived from its price

**Status:** accepted (2026-08-01).
**Kind:** fix.
**Source:** ROADMAP LOTTO-0009 (in-session-2026-08-01, found while sizing LOTTO-0008).
**Covers:** LOTTO-0008 (record what each ticket cost), LOTTO-0009 (entered pools).
**Blocker for:** LOTTO-0002.
**Amends:** LOTTO-0001 §4.2 — its game-name table maps one SMS to one pool.

Layman: you paid to enter three separate lottery draws with the same numbers,
and the tool has only ever checked one of them. This fixes that, using the
price you paid to work out what you actually bought.

## 1. Goal

Every pool a ticket was entered in is scored, not just the highest-priced one.
The tiers are derived from what the ticket cost, because the printed game name
does not reliably state them. Ticket cost is recorded so winnings can be set
against spend.

**An `entry` is one `(ticket, tier)` pair** — one ticket's numbers in one game's
draw, with that game's own prize pool. It is this spec's unit of work: 558
tickets hold 1233 entries, of which today only 558 are **derived** at all — one
per ticket. "Pool" names the results-source side of the same thing,
`(game, plus_flag, pool_id)`.

**Derived is not scored, and this spec never conflates them.** Of the 558
entries derived today, only the ones on the 121 checkable tickets are actually
scored against draws; the rest are excluded by `history.py::scorable()` and
reported as uncheckable (LOTTO-0001 §4.4). Every "N of 1233" figure below is a
*derivation* count. Treating an excluded entry as scored would be the same
no-data-reads-as-a-loss error the project exists to prevent.

## 2. Problem

A PLUS game cannot be bought on its own. The operator's rules require the base
game, run a **separate draw with its own prize pool** for each tier, and enter
the same numbers in all of them:

> 1.5 There are three separate draws conducted: one for LOTTO, a second for
> LOTTO PLUS 1, and a third for LOTTO PLUS 2. While all Games use the same
> selected numbers, each Game has a distinct Prize Pool and Prize structure.
>
> 1.16 The Participant must play the LOTTO Game first in order to Play
> LOTTO PLUS 1.
> 1.17 The Participant must play LOTTO and LOTTO PLUS 1 in order to Play
> LOTTO PLUS 2.

Source: https://content.nationallottery.co.za/images/docs/LOTTO_LOTTO_PLUS1_LOTTO_PLUS2_Rules_and_Regulations_21Sep25.pdf
The same add-on rule holds for PowerBall
(https://www.powerball.net/southafrica/rules) and for Daily Lotto Plus
(https://www.lottery.co.za/daily-lotto-plus).

`tickets.py::GAME_MAP` maps each SMS game name to exactly one
`(game, plusFlag, winPoolId)`, so a `Lotto Plus 2` purchase is scored against
`lotto/2` alone and its `lotto/0` and `lotto/1` entries are never checked.

Three consequences, each shaping the design:

1. **Most tickets are under-scored.** 449 of 558 were entered in more than one
   pool: 444 name a PLUS tier, and 5 more name a bare game but are priced as
   multi-tier (consequence 2 below).
   Measured **before** this fix — §4.4 redefines `plus_flag`, after which the
   first command returns 449:
   `python3 -c "from tickets import load; print(sum(1 for t in load() if t.plus_flag > 0))"` → `444`
   `python3 -c "from tickets import load; print(len(load()))"` → `558`
   The remaining 5 are counted by `tools/verify_pools.py`'s disagreement line.
2. **The printed name is not a reliable signal.** It disagrees with the price
   on 5 of 558 tickets — 3 before the 2026-06-01 handover and 2 after it. The
   post-handover sample is small but one-sided: all 6 post-handover messages in
   the dump name a bare game with no `Plus` suffix, including the 2 that were
   paid for as multi-tier tickets. After the handover the name cannot
   distinguish a base-only purchase from a multi-tier one even in principle.
3. **11 tickets are reported uncheckable when they are not.** `daily/1` has no
   results source (LOTTO-0001 §4.2), so `Daily Lotto Plus` tickets report as
   uncheckable — but their `daily/0` entry is scorable, and is being discarded.

The prize claim deadline is 365 days (LOTTO-0001 §4.4), so an unscored entry
is not merely missing information; it expires.

## 3. Scope decisions (agreed with the user)

- **Price decides the tiers; the name is a cross-check.** User's decision,
  2026-08-01, over "name decides" and "score only what both agree on". The
  latter was rejected because it re-hides exactly the post-handover wins this
  fix exists to surface (§8).
- **Fix this before the web page.** User's decision, 2026-08-01. LOTTO-0002
  would otherwise render totals already known to be low.
- **Ticket cost (LOTTO-0008) is specified here rather than alone**, because the
  price is the signal for both readings; two documents would state the same
  price table twice.
- **A disagreement between name and price is surfaced, never silently
  resolved.** A ticket reinterpreted without a trace is how a wrong price table
  becomes invisible.

## 4. Design

### 4.1 What the price proves

The tiers of a game are bought in a fixed order, each adding a fixed amount per
board per draw. A ticket's price per board per draw is therefore the *cumulative
sum* of the tiers bought, and each cumulative sum is distinct within a game and
era. The price is a complete statement of which tiers were bought; the name
states only the highest.

### 4.2 Board prices, by era

Prices are per board, per draw, VAT inclusive. The operator changed on
2026-06-01 and PowerBall's price changed with it; `HANDOVER = datetime(2026, 6, 1)`
in `tickets.py` — a `datetime`, not a `date`, because `bought` is built from an
epoch and the two types do not compare. **`bought >= HANDOVER` is the Sizekhaya
era**; the boundary is inclusive, and it matters because PowerBall's cumulative
moves from R7.50 to R15.00 across it. LOTTO-0001 carries the same handover date
in its §2 and §4.3; its §4.2 distinguishes the eras by the shape of the date
line, not by a date constant.

**Two prices per tier, and they are not interchangeable.** The *increment* is
what that tier adds; the *cumulative* is what a ticket topping out at that tier
costs per board per draw. §4.3 matches on the cumulative; §4.7 apportions with
the increment. Conflating them prices a R10.00 Lotto ticket at R22.50.

**All values are given in whole cents**, because that is the unit §4.3 compares
in; the rand figures are the same number for a human reader. A table in rands
alone would force the implementer to convert with `float × 100` and reintroduce
the representation error §4.3 forbids.

| Game | Tier | plus_flag | pool_id | Ithuba incr. | Ithuba cum. | Sizekhaya incr. | Sizekhaya cum. |
|---|---|---|---|---|---|---|---|
| lotto | LOTTO | 0 | 100 | 500 (R5.00) | **500** | 500 (R5.00) | **500** |
| lotto | LOTTO PLUS 1 | 1 | 101 | 250 (R2.50) | **750** | 250 (R2.50) | **750** |
| lotto | LOTTO PLUS 2 / 5 Max | 2 | 102 | 250 (R2.50) | **1000** | 250 (R2.50) | **1000** |
| powerball | POWERBALL | 0 | 100 | 500 (R5.00) | **500** | 1000 (R10.00) | **1000** |
| powerball | POWERBALL PLUS / XTRA | 1 | 101 | 250 (R2.50) | **750** | 500 (R5.00) | **1500** |
| daily | DAILY LOTTO | 0 | 100 | 300 (R3.00) | **300** | 300 (R3.00) | **300** |
| daily | DAILY LOTTO PLUS | 1 | 101 | 150 (R1.50) | **450** | *withdrawn* | *withdrawn* |

Every cumulative value is distinct within a `(game, era)` pair, which is what
makes the match in §4.3 unambiguous.

Sources: the game rules PDFs cited in §2 for the Ithuba figures;
https://www.lottery.co.za/2026-south-africa-lottery-changes for the handover
change. Daily Lotto Plus ran 2025-09-21 to 2026-05-31 only.

**These prices are hardcoded, and that is a rot risk with a named guard.** They
are not published in any results feed, so there is nothing to read them from at
runtime — unlike prize divisions, which LOTTO-0001 INV-5 requires be read live.
INV-7 is what makes a price change loud instead of silent.

### 4.3 Deriving the entered pools

```text
paid_lines          = Σ over the SMS's board lines of
                          C(n, 6) if game is lotto and n > 6 else 1   # Multiplay
if paid_lines == 0  -> unresolved                    # no board lines: never divide
unit_cents, remain  = divmod(round(cost * 100), paid_lines * ndraws)
if remain != 0      -> unresolved                    # not divisible: never guess
top                 = the tier whose CUMULATIVE cents equals unit_cents,
                      for (game, era)                # §4.2's bold column
pools               = [(plus_flag, pool_id) for every tier 0..top]
```

**Compare in whole cents, never in floats,** and take the cumulative from
§4.2's bold column rather than converting its rand figures. A quotient of a
parsed decimal can arrive as `7.499999…` and silently miss its tier, which
under the fallback below degrades the ticket to name-only scoring — the exact
behaviour this spec removes.

**A non-zero remainder is `unresolved`, not a rounded-down match.** Floor
division alone would let a price that is not an exact multiple land on a valid
tier and be reported as resolved, which is precisely the guessing INV-7 exists
to prevent. It would also break §4.7's identity that a resolved ticket's entry
costs sum to its charged amount.

The captured amount is stripped of thousands separators before conversion, and
capturing it **shifts every existing group index**. `tickets.py::parse()` today
matches `Played R[\d,.]+` with no group, so `head.group(1)` is the game name and
`head.group(2)` the draw count. Adding a capture for the amount — named or not —
makes the amount group 1 and pushes those to 2 and 3: in Python a
`(?P<name>…)` group is numbered alongside the unnamed ones, and only `(?:…)` is
non-capturing. Left unadjusted, `parse()` reads `"30.00"` as the game name, misses
`GAME_MAP`, and returns `None` for **every** message — 558 tickets silently gone,
which LOTTO-0001 INV-6's parsed-count assertion would then fail.

So name all three groups and read them by name:

```text
Played R(?P<cost>[\d,.]+) (?P<name>[A-Za-z0-9 ]+?)(?: for (?P<ndraws>\d+) draw\(?s?\)?)?\s*$
```

with `head["cost"]`, `head["name"]`, `head["ndraws"]` replacing the positional
reads. Naming them removes the ordering hazard permanently rather than trading
one index arithmetic for another.

`paid_lines` counts what was *paid for*, so it expands Multiplay the same way
LOTTO-0001 INV-2 does — a 7-number Lotto board is 7 paid lines, not one.

**`era` comes from when the ticket was bought, not from `Ticket.start`.**
`start` is the first *draw* date: 319 of 558 messages carry a start date 1–4
days after the SMS arrived, so a ticket bought days before a price change would
be priced in the old era and classified in the new one. That figure and the
agreement figure below are reported by `tools/verify_pools.py --era-audit`,
alongside the counts INV-7 asserts.

The purchase moment is already in the dump — `tickets.py::load()` captures
`date=(\d+)`, the Android SMS timestamp in **milliseconds since the Unix
epoch**, and currently discards it — so `load()` passes it to `parse()` and
`Ticket` gains `bought`:

```text
bought = datetime.fromtimestamp(int(ms) / 1000)
```

**Local time on both sides of the comparison.** `fromtimestamp()` yields local
time (SAST, UTC+2) and `HANDOVER` is a naive local `datetime`, so the two are in
the same frame. Using `utcfromtimestamp()` instead would put a ticket bought
between 00:00 and 02:00 SAST on 2026-06-01 in the wrong era — the single case
this field exists to get right. On the current dump both readings agree exactly
(558 resolved either way, 0 tickets where the two eras differ), so this is a
latent boundary defect being closed, not a live miscount.

**The signature is `parse(body, bought=None)`, and an absent `bought` falls
back to the parsed start date.** `parse()` is called directly — by every §5
invariant fixture, and by anything bypassing `load()` — so the fallback is part
of the contract, not an implementation detail. Without it the era of a
one-argument `parse()` is undefined, and the era decides the tier table: INV-9's
R22.50 PowerBall fixture resolves to two pools under Ithuba and to *none* under
Sizekhaya. Every §5 fixture is dated before the handover, so all of them resolve
in the Ithuba column under this rule.

`tools/verify_pools.py` **does not exist yet**; this spec creates it (§7). The
figures below were measured before drafting by an equivalent standalone
computation over the dump, and become that script's output:

`python3 tools/verify_pools.py` → `558 tickets, 1233 entries, 0 unresolved, 5 name/price disagreements (3 pre-handover, 2 post-handover)`

| pool | entries after the fix |
|---|---|
| lotto/0 | 232 |
| lotto/1 | 226 |
| lotto/2 | 226 |
| powerball/0 | 229 |
| powerball/1 | 212 |
| daily/0 | 97 |
| daily/1 | 11 |
| **total** | **1233** |

Today exactly one entry per ticket is **derived** — 558 of 1233, 45%. How many
of those are then *scored* is a separate and smaller number, gated by
`history.py::scorable()`; §1 keeps the two apart.

**An unresolved price is reported, never guessed.** If `unit_cents` matches no
cumulative total, `pools` falls back to the single name-derived pool, the ticket
is added to an `unresolved` list, and `check.py` prints the count. INV-7 asserts
that count is zero, so a future price change fails the check rather than
quietly reverting the project to its current behaviour.

### 4.4 Ticket shape

`tickets.py::Ticket` gains three fields:

```python
self.cost    # float, rands, the total charged for the whole ticket
self.pools   # [(plus_flag, pool_id), ...] base tier first
self.bought  # datetime, from the SMS epoch — selects the era (§4.3)
```

`cost` is **the amount the SMS charged**, parsed from the header — that is its
definition, and it is canonical. §4.7 derives per-entry costs that sum back to
it, an identity that holds only when the price resolves; for an unresolved
ticket no entry costs are defined and `cost` still stands alone.

`plus_flag` and `pool_id` are retained and redefined as
**`plus_flag, pool_id = pools[-1]`** — the top tier the price paid for, not the
tier the SMS names. Those were the same thing before this spec and are not any
more: on 5 tickets the name states a lower tier than the price (§2,
consequence 2). Keeping them name-derived would leave a ticket whose
`plus_flag` is absent from its own `pools`.

Both known disagreement directions are handled, and only one occurs today:

| Direction | Occurs in dump | Behaviour |
|---|---|---|
| name states a **lower** tier than the price | 5 tickets | price wins; ticket is scored in every tier it paid for |
| name states a **higher** tier than the price | 0 tickets | price wins; the named-but-unpaid tier is **not** scored, and the ticket is counted as a name/price disagreement |

`pools` is what scoring iterates; `plus_flag`/`pool_id` are for display and
per-ticket summary counts, never for choosing which pools to score.

### 4.5 Scoring is per entry, not per ticket

`check.py::check()` gains one loop level:

```python
for t in tickets:
    for plus_flag, pool_id in t.pools:
        if not scorable(t, plus_flag):
            continue                      # reported per entry; never a loss
        pays = paying_combinations(t.game, plus_flag, pool_id)
        for board in t.boards:
            for d in covered(t, plus_flag):
                ...
                amount(t, plus_flag, pool_id, d, hits, special)
```

`history.py::scorable()` and `history.py::covered()` take the pool explicitly
rather than reading `ticket.plus_flag`. A ticket has no single answer to "is
this scorable?" any more — that is now a property of an entry.

**`check.py::amount()` takes the entry's pool as arguments and must stop reading
it off the ticket.** Its signature becomes
`amount(ticket, plus_flag, pool_id, draw, hits, special)`, and *both* of its
branches change: the API branch calls
`divisions(ticket.game, draw["issue"], pool_id, plus_flag)` and the archive
branch calls `payouts(ticket.game, plus_flag, draw["date"])`. Left reading
`ticket.pool_id` / `ticket.plus_flag`, every one of the 675 entries this fix
adds would be priced against the **top** tier's division table — a `lotto/0` win
on a Lotto Plus 2 ticket priced from pool 102. That is wrong money in both
directions, which is a worse failure than the under-scoring this spec exists to
correct, so it is called out rather than left implied by the loop.

The win dict's `plus_flag` key keeps its name and changes its source — the entry
rather than the ticket — and gains `pool_id` alongside it, so every win states
the pool it was actually won in.

### 4.6 Reporting stays honest at the new granularity

LOTTO-0001's load-bearing rule is that no-data must never read as a loss. It now
has a case it did not have before: **a ticket can be checkable in one pool and
not another.** All 11 `Daily Lotto Plus` tickets are exactly this.

So `check.py` reports uncheckable **entries**, and states the ticket count
separately as *wholly* and *partly* uncheckable. A partly-uncheckable ticket must
never be counted as wholly uncheckable, and must never be counted as scored.

The report shape is part of the contract, because INV-11 is an assertion about
it. Angle brackets are counts the run produces; the wording is fixed:

```
<e> of <n> ENTRIES CANNOT BE CHECKED. They are not counted below, and are NOT losses.
  <a> predate all draw data for their pool (earliest: <date>)
  <b> in a pool no results source carries: <pools>
  affecting <f> tickets wholly and <p> tickets partly
    a partly-checkable ticket IS scored on its remaining pools, below
```

**Wholly** is the word throughout — the report, the prose and INV-11 — against
`partly`. **Double-counted** means a ticket appearing in both `<f>` and `<p>`;
the two tallies partition the affected tickets, so their overlap is always zero
and INV-11 asserts it.

Today `<n>` is 1233 and `<pools>` is `daily/1`, but both are computed. The pool
list must be derived **per entry**, not per ticket: today's
`sorted({f"{t.game}/{t.plus_flag}" ...})` reads the top tier, so under §4.4's
redefinition a ticket uncheckable only in `lotto/1` would report `lotto/2`. It
becomes `sorted({f"{t.game}/{pf}" for t, pf in uncheckable_entries})`.

**The report body moves out of `__main__` into a function**, because INV-11
asserts against it and `check.py`'s reporting block is currently unreachable by
any importer. `check.py::uncheckable_report(tickets) -> (lines, counts)` returns
the rendered lines and the counts above; `__main__` prints them and
`tools/verify_pools.py` calls it. Without this the invariant has no test path.

`<f> + <p>` is the ticket count touched by uncheckable entries; only `<f>`
tickets are excluded from scoring entirely. LOTTO-0001's two reasons
(`too_old`, `no_pool`) survive unchanged — they are now properties of an entry
rather than of a ticket, which is the whole of the change.

### 4.7 Spend against winnings

Per-entry cost is that tier's own board price:

```text
entry_cost_cents = tier_increment(game, era, plus_flag) * paid_lines * ndraws
```

**Both sides in cents.** `tier_increment()` reads §4.2, which is a cents table,
while `Ticket.cost` is rands — so the identity is
`round(Ticket.cost * 100) == Σ entry_cost_cents`, not a bare sum. Mixing the two
units is a 100× error in the spend total, on a spec whose whole subject is
reported money.

`tier_increment()` reads §4.2's **increment** column — what that one tier adds —
and is a different function from the cumulative lookup §4.3 matches on. §4.2
gives the worked example of conflating them; doing so here breaks INV-10.

`Ticket.cost` stays canonical as §4.4 defines it; the entry costs sum *back* to
it, and only when the price resolves. Apportioning
this way is what lets a partly-checkable ticket contribute only its checkable
tiers to a spend-versus-winnings comparison.

**A comparison is only ever drawn over checkable entries.** Cost is known for
every entry; winnings are known only where results exist. Comparing total spend
against visible winnings would convert every unscorable entry into a loss —
LOTTO-0002 owns the display, this spec owns the rule.

## 5. Invariants

Numbered from INV-7 because LOTTO-0001 holds INV-1 to INV-6 and CHANGELOG.md
cites them unqualified; restarting at INV-1 would make two live contracts share
a handle.

- **INV-7** — Every parsed ticket's price resolves to exactly one cumulative
  tier total for its game and era.
  *Test:* `python3 tools/verify_pools.py` → `558 tickets, 1233 entries, 0 unresolved, 5 name/price disagreements (3 pre-handover, 2 post-handover)`
  Only `0 unresolved` and the exit code are asserted. The ticket, entry and
  disagreement figures are informational and move as messages arrive (§7).
  *Breaks when:* the operator changes a board price, as happened on 2026-06-01,
  or a Multiplay shape appears that `paid_lines` does not model — a >6-number
  PowerBall board would land here rather than silently collapsing to one line
  (LOTTO-0007 (d)). Both surface as a non-zero unresolved count and a non-zero
  exit, instead of a silent reversion to name-only scoring.

- **INV-8** — A ticket is entered in every tier up to the one its price paid
  for, base tier first.
  *Test:* `python3 -c "from tickets import parse; t=parse('Standard Bank: Played R30.00 Lotto Plus 2 for 3 draw(s)\nDate 01/01/2020 to 01/01/2020\nA: 07 11 19 23 31 44\nRef:VAS00000000000.'); print(t.pools)"` → `[(0, 100), (1, 101), (2, 102)]`
  *Breaks when:* the derivation returns only the top tier — the current
  behaviour — which drops 675 of 1233 paid entries.

- **INV-9** — The price decides the tiers; the printed name does not.
  *Test:* `python3 -c "from tickets import parse; t=parse('Standard Bank: Played R22.50 Powerball for 3 draw(s)\nDate 01/01/2020 to 01/01/2020\nA: 08 14 27 33 41 05\nRef:VAS00000000000.'); print(t.pools)"` → `[(0, 100), (1, 101)]`
  *Breaks when:* the name is treated as authoritative. This fixture names the
  base game only and is priced at R7.50 per board per draw, which is base plus
  PLUS — the shape of the 5 real disagreeing messages in §2, consequence 2.

- **INV-10** — `Ticket.cost` is the total rands the SMS charged for the whole
  ticket, across all boards, draws and tiers.
  *Test:* `python3 -c "from tickets import parse; t=parse('Standard Bank: Played R13.50 Daily Lotto Plus for 3 draw(s)\nDate 02/10/2025 to 02/10/2025\nA: 04 13 22 29 35\nRef:VAS00000000000.'); print(t.cost)"` → `13.5`
  (dated inside the 2025-09-21 – 2026-05-31 window in which Daily Lotto Plus
  actually ran, per §4.2.)
  *Breaks when:* cost is stored per draw or per board, making every
  spend-versus-winnings figure wrong by a factor of `ndraws × paid_lines`.

- **INV-11** — An entry in a pool with no results is reported as uncheckable at
  entry granularity, and a ticket checkable in one pool is never reported as
  wholly uncheckable.
  *Test:* `python3 tools/verify_pools.py` → a second line of its own,
  `11 partly-uncheckable tickets, 0 reported as wholly uncheckable, 0 double-counted`.
  The script calls `check.py::uncheckable_report()` — the thing this invariant
  is about (§4.6) — and asserts the two zero-terms; asserting only the
  derivation would test a different claim from the one stated. The `11` is
  informational and moves with the dump; it holds today because `daily/1` is the
  only pool with no results at all, every other pool sharing its game's earliest
  known draw (`lotto:0/1/2` all 2025-01-01, `powerball:0/1` both 2025-01-03, per
  `archive_results.json`), so no other pool can make a ticket partly uncheckable.
  *Breaks when:* the uncheckable report is written per ticket, as it is today,
  so the 11 `Daily Lotto Plus` tickets keep reporting as uncheckable while
  their base entries are scored — the two statements contradicting each other
  in the same output.

## 6. Failure modes

- **A board price changes again.** INV-7 fires: unresolved is non-zero and
  `tools/verify_pools.py` exits 1. The fix is a row in §4.2's table, not code.
- **A renamed game appears.** Sizekhaya renamed Lotto Plus 2 to `LOTTO 5 Max`
  and PowerBall Plus to `PowerBall XTRA`. Neither string is in `GAME_MAP`, so
  `parse()` returns `None` and the ticket is dropped — caught by LOTTO-0001
  INV-6, which asserts the parsed count. No such message is in the dump yet.
- **The rules reading is wrong.** If a PLUS purchase did not in fact enter the
  base draws, this fix would report wins that cannot be claimed — the opposite
  and worse failure direction. Three independent things agree it is right: the
  operator's rules quoted in §2, the price arithmetic resolving 558 of 558, and
  the two cheap-and-dear variants of each game overlapping in time, which rules
  out inflation as the explanation. Each win names the pool it was won in, so a
  claim can be checked against the right draw.
- **A ticket is bought just before a price change.** The era comes from the
  purchase timestamp rather than the first draw date, for the reason §4.3 gives.
  Both readings agree on every ticket in the dump today.
- **An unresolved price** — a total matching no tier, one not divisible by
  `paid_lines × ndraws`, or a message with no board lines at all
  (`paid_lines == 0`, which must never reach the division). Handled as §4.3
  specifies; INV-7 is what makes it loud.

## 7. Tests

`tools/verify_pools.py` joins `tools/verify_sources.py`,
`tools/verify_coverage.py` and `tools/verify_privacy.py` as an executable
check. It must be run from the repository root after `python3 backfill.py`,
like its siblings (LOTTO-0001 §7), and is dependency-free — there is still no
test framework and adding one is still out of scope.

It must **not** import the derivation it is testing. `verify_coverage.py`
already carries this lesson: an earlier version imported `history.scorable()`,
the predicate under test, and would have passed a regressed one (LOTTO-0001
INV-6). `verify_pools.py` recomputes the cumulative price totals from §4.2's
table independently and compares.

Counts move as tickets are added; what the check asserts is the zero-terms —
`0 unresolved`, `0 reported as wholly uncheckable`, `0 double-counted` — and the
exit code. The disagreement count is reported, not
asserted, because it is a property of the bank's wording rather than of this
code; it is printed split by era, since a post-handover disagreement means
something different from a pre-handover one (§2).

Red-test all five invariants before accepting the fix:

| INV | Red-test against | Expect |
|---|---|---|
| 7 | §4.2's table with the Sizekhaya PowerBall row removed | the post-handover **PowerBall** tickets land in `unresolved`, exit 1 (Lotto and Daily prices are unchanged across the handover, so their tickets still resolve) |
| 8 | the current top-tier-only mapping | 675 entries missing |
| 9 | a name-first derivation | the R22.50 fixture returns one pool, not two |
| 10 | `cost` stored per draw | `4.5` instead of `13.5` |
| 11 | a per-ticket uncheckable report | the 11 Daily tickets reported as wholly uncheckable, exit 1 |

## 8. Alternatives considered (and rejected)

- **Keep the name as the signal** — today's behaviour. Rejected: the bank
  stopped printing the suffix after 2026-06-01, so this is knowingly wrong for
  every future ticket, and already wrong for 5.
- **Score only pools where name and price agree.** Rejected by the user,
  2026-08-01: it re-hides the post-handover wins this fix exists to surface.
- **Ask the operator which pools a reference covers.** No such endpoint exists;
  the API serves draw results, not ticket lookups.
- **Infer tiers from the number of boards or draws.** Neither varies with tier;
  only price does.

## 9. Out of scope

- Displaying any of this — LOTTO-0002.
- The rest of the LOTTO-0007 tail. INV-7 incidentally makes item (d) loud
  rather than silent, but does not implement Multiplay for non-Lotto games.
- Widening results coverage before 2025-01-01 — LOTTO-0006. Entries this fix
  adds to tickets that predate all draw data remain unscorable.
- A test framework — LOTTO-0001 §9.

## 10. Resource cost

No new dependency; standard library only, Python 3.8+, consistent with
LOTTO-0001 §10.

Scoring roughly 2.2× the entries costs more prize-division lookups, but not
proportionally: `results.divisions()` is memoised per
`(game, issue, pool, plus_flag)` and `history.all_draws()` caches per
`(game, plus_flag)`.

Six of the seven pools are already fetched today — `history.scorable()` calls
`all_draws()` for every ticket, so each pool named by at least one SMS is
loaded whether or not it is scored. **`lotto/1` is the exception**: no message
in the dump names `Lotto Plus 1`, so that pool is fetched by nothing today and
this fix adds 226 entries in it. It costs **two** extra
`issueWinPoolInfoPageQuery` calls, not one: `results.py::draws()` is not
memoised (LOTTO-0001 §10), and both `history.all_draws()` and
`check.paying_combinations()` call it for the pool. Add one
`getIssueDrawResultDetail` to establish that pool's paying set. Beyond that, the
added cost is one `getIssueDrawResultDetail` per distinct draw a *new* win
lands on.

**This figure is not yet measured.** LOTTO-0001 §10 states about 12 requests
before scoring; the post-fix number is to be measured against the shipped
implementation and folded back here, rather than estimated now.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-7 | `tools/verify_pools.py` |
| INV-8 | §5 command, `tickets.py::parse()` |
| INV-9 | §5 command, `tickets.py::parse()` |
| INV-10 | §5 command, `tickets.py::parse()` |
| INV-11 | `tools/verify_pools.py` |
| §4.2 price table fitting every ticket in the dump | `tools/verify_pools.py` |
| §4.2 price table matching the operator's published prices | **nothing** — a table wrong in a way the dump cannot distinguish would pass |
| §4.3 era taken from the purchase timestamp, not the start date | `tools/verify_pools.py` — a ticket priced in one era and classified in the other resolves to no tier, so it lands in `unresolved` |
| §4.5 `amount()` pricing each win from its **entry's** pool | **nothing** — a win priced from the wrong pool's division table is a plausible-looking number, and nothing compares it against the right one |
| §4.6 partly-uncheckable never counted as wholly uncheckable | `tools/verify_pools.py` (INV-11) |
| §4.7 comparison drawn only over checkable entries | **nothing** — this spec sets the rule; LOTTO-0002 implements the display and owns its check |
| §2 the rules reading itself | **nothing mechanical** — three agreeing lines of evidence (§6), and each win names its pool so a claim is checkable |

Twelve rows, four `nothing`.

## 12. Cross-doc impact

- `docs/specs/LOTTO-0001-lottery-ticket-tracker.md` §4.2 — its game-name table
  maps one SMS to one pool and must be amended to point here. Its INV-1 and
  INV-2 are unaffected; INV-5 is unaffected, since board prices are not prize
  divisions.
- **LOTTO-0001 INV-6 is affected twice, and both must land in the same change.**
  `tools/verify_coverage.py` imports `covered` from `history` directly
  (`from history import all_draws, covered`), so §4.5's signature change breaks
  it until it passes a pool. And its expected output
  `558 tickets, 437 unscorable (excluded), 0 with wrong draw coverage` is a
  per-ticket count that no longer describes what is excluded — the 11
  `Daily Lotto Plus` tickets inside that 437 become partly scorable. INV-6's
  expected line is restated in entry terms and its new figures are **measured
  against the shipped implementation**, not predicted here — this spec does not
  invent another contract's expected output. Its 90% floor and its rule against
  importing `history.scorable()` both stand unchanged.
- `ROADMAP.md` — LOTTO-0008 and LOTTO-0009 flip on ship; LOTTO-0002 unblocks.
- `README.md` — the sample output and the uncheckable wording change.
- `CHANGELOG.md` — a `Fixed` entry; this changes reported winnings.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 3 | 2026-08-01 | 2 | 2 | 3 | 6 | 5 | **Converged by cap (3 loops).** All 16 verified findings fixed; 0 deferred. Both lanes found the same CRITICAL, again self-inflicted: loop 2 said capturing the ticket price as a *named* group would leave `parse()`'s positional indices untouched. It does not — Python numbers named groups alongside unnamed ones, so `head.group(1)` would return `"30.00"`, miss `GAME_MAP`, and return `None` for **every** message (verified by running both patterns; 558 tickets silently dropped, which LOTTO-0001 INV-6 would then fail). Second CRITICAL: §4.7's cost identity mixed units — §4.2 became a cents table in loop 2 while `Ticket.cost` stayed rands, a 100× error in the spend total. Also: the epoch→`datetime` conversion had no divisor and no timezone, the one detail `bought` was added for; INV-11 asserted against `check.py`'s report, which lives in `__main__` and no importer can reach, so §4.6 now moves it into `uncheckable_report()`; §4.6's only implementation hint quoted the per-ticket pool expression its own thesis obsoletes; and `paid_lines == 0` reached a `divmod` that would raise rather than resolving to `unresolved`. Dismissed on evidence (both lanes, twice now): INV-11's `11` is not a lower bound — `archive_results.json` shows `lotto:0/1/2` all start 2025-01-01 and `powerball:0/1` both 2025-01-03, so `daily/1` is the only pool that can make a ticket partly uncheckable; the evidence is now stated in INV-11 so it stops being re-raised. **Collateral outnumbered draft defects for a second consecutive loop (≈9:2, after 14:4), which is this skill's stop-and-split trigger** — the run exits at the cap rather than looping a fourth time, and §4 should be split before implementation (see the run's closing note). |
| 2 | 2026-08-01 | 2 | 1 | 4 | 6 | 7 | 17 verified fixed, 1 dismissed on evidence (INV-11's literal `11` was called a lower bound; `archive_results.json` shows every pool within a game shares an earliest draw date — `lotto:0/1/2` all 2025-01-01, `powerball:0/1` both 2025-01-03 — so `daily/1`, the one empty pool, is the only source of partial uncheckability). **14 of 18 were collateral from loop 1's own fixes**, 4 were draft defects — the signal that the loop-1 sweep under-ran, answered here by a whole-document consistency pass rather than by looping harder. Both lanes again found the same CRITICAL, this time self-inflicted: loop 1 added `bought` for the era but left `parse()`'s signature and its era default unstated, and all three §5 fixtures call `parse()` with one argument — INV-9's R22.50 PowerBall resolves to two pools under Ithuba and none under Sizekhaya, so the invariant passed or failed on an unspecified default. Also collateral: three references to a `§2.2` that does not exist; `//` floor division silently rounding a non-divisible price onto a valid tier, defeating the guard INV-7 exists to be; a cents comparison rule against a rands-only table, forcing the `float × 100` it forbids; and `pools[-1]` assigned to two scalars. Draft defects: "558 of 1233 **scored**" counted 437 excluded tickets as scored — the project's one forbidden conflation, in the figure the fix is justified by; §10 undercounted `lotto/1` by one request because `results.draws()` is not memoised; §7 red-tested 3 of 5 invariants. |
| 1 | 2026-08-01 | 2 | 1 | 5 | 7 | 5 | All 18 verified findings fixed; 0 unverified, 1 dismissed (no TOC — the sibling LOTTO-0001 carries none at 394 lines, and it changes nothing an implementer builds). Both lanes independently found the same CRITICAL: §4.5 re-pointed the scoring loop at the entry but left `check.py::amount()` reading `ticket.pool_id`/`ticket.plus_flag`, so all 675 newly-scored entries would have been priced from the top tier's division table — wrong money in both directions. Also: §4.2 conflated incremental and cumulative board prices, which would have priced a R10.00 Lotto ticket at R22.50; the era was taken from `Ticket.start`, which is the first draw date rather than the purchase date (319 of 558 differ by 1–4 days — the SMS epoch was available and discarded); INV-11 asserted a property of the derivation while claiming one about `check.py`'s report, and §11 credited a catcher that did not exist; §12 omitted LOTTO-0001 INV-6, whose `tools/verify_coverage.py` imports the `covered()` this spec re-signatures; `tools/verify_pools.py` was quoted as measured when it does not exist yet; float equality on a divided price could silently degrade a ticket to name-only scoring; and §2 said 444 tickets were under-scored where 449 are. |
