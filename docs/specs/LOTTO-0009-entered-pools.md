# LOTTO-0009 — Score every pool a ticket was entered in, derived from its price

**Status:** spec draft (2026-08-01).
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
tickets hold 1233 entries, and today only 558 of them are scored. "Pool" names
the results-source side of the same thing, `(game, plus_flag, pool_id)`.

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
   multi-tier (§2.2).
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
in `tickets.py` — a `datetime`, not a `date`, because `Ticket.start` is a
`datetime` and the two types do not compare. LOTTO-0001 carries the same
handover date in its §2 and §4.3; its §4.2 distinguishes the eras by the shape
of the date line, not by a date constant.

**Two prices per tier, and they are not interchangeable.** The *increment* is
what that tier adds; the *cumulative* is what a ticket topping out at that tier
costs per board per draw. §4.3 matches on the cumulative; §4.7 apportions with
the increment. Conflating them prices a R10.00 Lotto ticket at R22.50.

| Game | Tier | plus_flag | pool_id | Ithuba incr. | Ithuba cum. | Sizekhaya incr. | Sizekhaya cum. |
|---|---|---|---|---|---|---|---|
| lotto | LOTTO | 0 | 100 | R5.00 | R5.00 | R5.00 | R5.00 |
| lotto | LOTTO PLUS 1 | 1 | 101 | R2.50 | R7.50 | R2.50 | R7.50 |
| lotto | LOTTO PLUS 2 / 5 Max | 2 | 102 | R2.50 | R10.00 | R2.50 | R10.00 |
| powerball | POWERBALL | 0 | 100 | R5.00 | R5.00 | R10.00 | R10.00 |
| powerball | POWERBALL PLUS / XTRA | 1 | 101 | R2.50 | R7.50 | R5.00 | R15.00 |
| daily | DAILY LOTTO | 0 | 100 | R3.00 | R3.00 | R3.00 | R3.00 |
| daily | DAILY LOTTO PLUS | 1 | 101 | R1.50 | R4.50 | *withdrawn* | *withdrawn* |

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

```python
paid_lines = Σ over the SMS's board lines of
                 C(n, 6) if game is lotto and n > 6 else 1     # Multiplay
unit_cents = round(cost * 100) // (paid_lines × ndraws)
top        = the tier whose cumulative price equals unit_cents, for (game, era)
pools      = [(plus_flag, pool_id) for every tier 0..top]
```

**Compare in whole cents, never in floats.** `unit` is a quotient of a parsed
decimal, so `7.50` can arrive as `7.499999…` and silently miss its tier — which
under the fallback below degrades the ticket to name-only scoring, the exact
behaviour this spec removes. The captured amount is also stripped of thousands
separators before conversion: `tickets.py`'s header pattern is `Played R[\d,.]+`,
so `R1,234.00` is admissible and `float("1,234.00")` raises.

`paid_lines` counts what was *paid for*, so it expands Multiplay the same way
LOTTO-0001 INV-2 does — a 7-number Lotto board is 7 paid lines, not one.

**`era` comes from when the ticket was bought, not from `Ticket.start`.**
`start` is the first *draw* date: 319 of 558 messages carry a start date 1–4
days after the SMS arrived, so a ticket bought days before a price change would
be priced in the old era and classified in the new one. The purchase moment is
already in the dump — `tickets.py::load()` captures `date=(\d+)`, the SMS epoch
in milliseconds, and currently discards it — so `load()` passes it to `parse()`
and `Ticket` gains `bought`. On the current dump both readings agree exactly
(558 resolved either way, 0 tickets where the two eras differ), so this is a
latent boundary defect being closed, not a live miscount.

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

Today exactly one entry per ticket is scored — 558 of 1233, 45%.

**An unresolved price is reported, never guessed.** If `unit` matches no
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

`plus_flag` and `pool_id` are retained, and are redefined as **`pools[-1]` —
the top tier the price paid for**, not the tier the SMS names. Those were the
same thing before this spec and are not any more: on 5 tickets the name states
a lower tier than the price (§2.2). Keeping them name-derived would leave a
ticket whose `plus_flag` is absent from its own `pools`.

Both known disagreement directions are handled, and only one occurs today:

| Direction | Occurs in dump | Behaviour |
|---|---|---|
| name states a **lower** tier than the price | 5 tickets | price wins; ticket is scored in every tier it paid for |
| name states a **higher** tier than the price | 0 tickets | price wins; the named-but-unpaid tier is **not** scored, and the ticket is counted as a name/price disagreement |

`pools` is what scoring iterates; `plus_flag`/`pool_id` are for display only.

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
separately as *fully* and *partly* uncheckable. A partly-uncheckable ticket must
never be counted as wholly uncheckable, and must never be counted as scored.

The report shape is part of the contract, because INV-11 is an assertion about
it. Angle brackets are counts the run produces; the wording is fixed:

```
<e> of 1233 ENTRIES CANNOT BE CHECKED. They are not counted below, and are NOT losses.
  <a> predate all draw data for their pool (earliest: YYYY-MM-DD)
  <b> in a pool no results source carries: daily/1
  affecting <f> tickets fully and <p> tickets partly
    a partly-checkable ticket IS scored on its remaining pools, below
```

`<f> + <p>` is the ticket count touched by uncheckable entries; only `<f>`
tickets are excluded from scoring entirely. LOTTO-0001's two reasons
(`too_old`, `no_pool`) survive unchanged — they are now properties of an entry
rather than of a ticket, which is the whole of the change.

### 4.7 Spend against winnings

Per-entry cost is that tier's own board price:

```python
entry_cost = tier_increment(game, era, plus_flag) × paid_lines × ndraws
```

`tier_increment()` reads §4.2's **increment** column — what that one tier adds —
and is a different function from the cumulative lookup §4.3 matches on. Summing
cumulatives here would price a R10.00 Lotto ticket at R22.50 and break INV-10.

`Ticket.cost` is the sum of its entries' costs, which is what the SMS charged.
Apportioning
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
  PLUS — the shape of the 5 real disagreeing messages in §2.2.

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
  The script runs `check.py`'s report path — the thing this invariant is about —
  and asserts the two zero-terms; asserting only the derivation would test a
  different claim from the one stated.
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
- **An unresolved price.** Falls back as §4.3 specifies and is counted; INV-7
  asserts the count is zero, so price rot fails the check rather than quietly
  reverting the project to name-only scoring.

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

Red-test each invariant before accepting the fix: INV-8 against the current
top-tier-only mapping (expect 675 entries missing), INV-9 against a name-first
derivation (expect the R22.50 fixture to return one pool), INV-11 against a
per-ticket uncheckable report (expect the 11 Daily tickets to be double-counted).

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
this fix adds 226 entries in it. It costs one extra
`issueWinPoolInfoPageQuery` (via `all_draws()`) plus one
`getIssueDrawResultDetail` (via `paying_combinations()`). Beyond that, the added
cost is one `getIssueDrawResultDetail` per distinct draw a *new* win lands on.

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
  expected line is restated in entry terms; its 90% floor and its rule against
  importing `history.scorable()` both stand unchanged.
- `ROADMAP.md` — LOTTO-0008 and LOTTO-0009 flip on ship; LOTTO-0002 unblocks.
- `README.md` — the sample output and the uncheckable wording change.
- `CHANGELOG.md` — a `Fixed` entry; this changes reported winnings.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 1 | 2026-08-01 | 2 | 1 | 5 | 7 | 5 | All 18 verified findings fixed; 0 unverified, 1 dismissed (no TOC — the sibling LOTTO-0001 carries none at 394 lines, and it changes nothing an implementer builds). Both lanes independently found the same CRITICAL: §4.5 re-pointed the scoring loop at the entry but left `check.py::amount()` reading `ticket.pool_id`/`ticket.plus_flag`, so all 675 newly-scored entries would have been priced from the top tier's division table — wrong money in both directions. Also: §4.2 conflated incremental and cumulative board prices, which would have priced a R10.00 Lotto ticket at R22.50; the era was taken from `Ticket.start`, which is the first draw date rather than the purchase date (319 of 558 differ by 1–4 days — the SMS epoch was available and discarded); INV-11 asserted a property of the derivation while claiming one about `check.py`'s report, and §11 credited a catcher that did not exist; §12 omitted LOTTO-0001 INV-6, whose `tools/verify_coverage.py` imports the `covered()` this spec re-signatures; `tools/verify_pools.py` was quoted as measured when it does not exist yet; float equality on a divided price could silently degrade a ticket to name-only scoring; and §2 said 444 tickets were under-scored where 449 are. |
