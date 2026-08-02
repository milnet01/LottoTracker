# LOTTO-0002 — Local web page for tickets, results and claimable winnings

**Status:** spec draft (2026-08-02) — split out of the 1,161-line original on
2026-08-02; re-entering the review gate at loop 1 on these bytes. See §13.
**Kind:** implement.
**Source:** ROADMAP LOTTO-0002 (user-request-2026-08-01; three further choices
taken with the user 2026-08-02, recorded in §3).

**Blocked by:** LOTTO-0009 (shipped 2026-08-01). **Pairs with:** LOTTO-0008
(shipped inside LOTTO-0009 — `Ticket.cost` is what §4.6 spends) and
**LOTTO-0013** (the tray, the supervisor and the headless contract — the other
half of this split; they ship together).

*Layman: a page in your browser showing every ticket, what it won and what is
still claimable.*

## 1. Goal

After this ships, `http://127.0.0.1:4322` serves every ticket, what it cost,
which pools it was entered in, which of them could be checked, what it won, and
— the actionable part — when each unclaimed prize expires. A settings panel on
the page carries two switches: start the tray at login, and open the page when
the tray starts. `check.py` keeps working exactly as it does; this adds a second
face on the same data, and no new source of truth.

`serve.py` runs standalone with no Qt imported, so the page can be served
headless (systemd, SSH, a machine with no tray). What starts it, stops it and
opens a browser at it is LOTTO-0013, which owns that contract and the invariant
that keeps this file Qt-free.

## 2. Problem

`check.py::__main__` prints a flat list and nothing else. Three consequences,
all of them worse since LOTTO-0009 multiplied the data by 2.2×:

1. **The output no longer fits a screen.** 558 tickets hold 1,233 entries and
   86 winning lines, 62 of them still claimable
   (`python3 check.py | grep "winning lines"` → `86 winning lines total; 62 still claimable`,
   2026-08-02). There is no way to sort
   by expiry, filter to one game, or see a ticket's own history — the terminal
   shows one ordering, oldest first, and that is the ordering least useful for
   deciding what to claim next.
2. **`Ticket.cost` is captured and never displayed.** LOTTO-0008 shipped the
   field precisely so prizes could be read against spend, and its only consumer
   was always going to be this item — `docs/specs/LOTTO-0009-entered-pools.md`
   §4.7 states the apportionment rule and explicitly defers the display here.
   Its §11 carries the row *"§4.7 comparison drawn only over checkable entries |
   **nothing** — this spec sets the rule; LOTTO-0002 implements the display and
   owns its check"*. INV-16 below is that check, so this spec closes one of that
   spec's four `nothing` rows and §12 records the edit that follows.
3. **The honesty rules are carried by prose that a UI can drop.** The uncheckable
   report is four printed lines. A page that renders wins into a table and
   forgets those lines converts 974 unscorable entries into implied losses —
   the exact bug this project was built after hitting, arriving through a new
   door. §4.5 and INV-15 make the rendering carry the rule instead of the prose.

## 3. Scope decisions

**From the ROADMAP bullet, taken with the user 2026-08-01 — not re-litigated
here:** a long-running local server rather than a generated static file; no
database, tickets re-parsed from `lotto_sms_raw.txt` and results left in
`archive_results.json` / `archive_cache/`; spend compared against winnings over
checkable entries only, with lifetime spend shown separately and labelled. The
security constraints in that bullet are LOTTO-0014 §4.2–§4.4. That bullet's
tray decisions — the tray is required rather than optional, it is PySide6, and
`serve.py` must not import it — are LOTTO-0013 §3.

**Taken with the user 2026-08-02:**

- **The start-at-login toggle lives on the page, in a settings panel** — chosen
  over a tickable item in the tray menu, knowing the trade: it gives the server
  its first state-changing endpoint, and therefore LOTTO-0014 §4.3's token. The
  tray-menu option would have left the HTTP surface read-only.
- **Settings render as sliding on/off switches rather than square checkboxes** —
  user preference, stated 2026-08-02. This is about the *appearance*: §4.7 keeps
  a real `<input type="checkbox">` underneath, because that is what preserves
  keyboard and screen-reader behaviour.

## 4. Design

### 4.1 Two files, the model between them, and the I/O boundary

```text
serve.py      stdlib only. Does ALL I/O: builds the model, serves it.
              Never imports PySide6.
page.py       Renders a model dict to one HTML string. Pure function, no I/O,
              no imports of check/history/results/tickets.
```

LOTTO-0013 adds `supervise.py`, `tray.py` and `icons/` around them, and the
dependency runs one way — nothing in this document's two files imports
anything in that one's three.

**When the server is launched by the tray, `supervise.py` is the sole owner of
the token, the port and the child process** (LOTTO-0013 §4.2). A standalone
`python3 serve.py` with no `LOTTO_TOKEN` mints its own (LOTTO-0014 §4.3), which
is the headless case and the only time `serve.py` decides either for itself.

**`page.py` is pure, and that is load-bearing rather than tidy.** Every figure,
string and reason it renders is already in the model — it never calls
`all_draws()`, `scorable()` or anything else that touches disk or network. That
is what lets §7 render the whole page against a fixture with no socket and no
`archive_results.json`, and it is why the derivations §4.5 and §4.6 describe
happen in `serve.py`'s builder, not in the renderer.

**The model** is a plain dict, and it is the seam every §7 fixture is built to:

```python
{
  "built":  "2026-08-02T14:31:07" | None,   # last SUCCESSFUL build (§4.2)
  "stale":  False,                          # last refresh attempt raised
  "wins":   [ {...check.py win dict..., "amount_cents": int,
               "expires_in_days": int} ],
  "entries":[ {"ref", "game", "plus_flag", "pool_id", "cost_cents",
               "scorable": bool, "reason": str|None,   # §4.5 derives these
               "won_cents": int|None,                  # None iff not scorable
               "draws_covered": int, "draws_remaining": int|None} ],
  "tickets":[ {"ref", "game", "cost_cents", "boards": int, "ndraws",
               "resolved": bool, "bought": "YYYY-MM-DD"} ],
  "uncheckable": {...counts from check.py::uncheckable_report()...},
  "spend":  {"compared_cents", "lifetime_cents", "unresolved_cents",
             "unresolved_tickets": int},
  "won":    {"lifetime_cents", "unexpired_cents"},
}
```

`reason` is `None` for a scorable entry and otherwise the §4.5 string;
`draws_remaining` is `None` for an unscorable entry, never `0` and never
`ndraws` — the type carries the cardinal rule so a renderer cannot lose it.
`won_cents` is `None` for an entry nothing could score and an integer (possibly
`0`) for one that was scored: the same distinction, on the money column INV-15
asserts against.

**Every money value in the model is an integer of cents**, including
`tickets[].cost_cents`, which the builder computes as `round(Ticket.cost * 100)`,
and `won.*_cents` / `wins[].amount_cents`, computed as `round(w["amount"] * 100)`.
`Ticket.cost` and `check.py`'s `amount` are both **rands**, so the conversion
happens once, at the boundary, and never again. §4.6 and LOTTO-0009 §4.2 both
record that mixing the two units is a 100× error on a page whose whole subject
is money; one unit in the model is how this spec avoids re-deriving that.
`spend.unresolved_cents` is `Σ round(Ticket.cost * 100)` over unresolved
tickets — their raw price, not an apportionment, since apportioning is exactly
what fails for them (§4.6).

`uncheckable` holds **integers only**: the builder stores `len(counts["wholly"])`
and `len(counts["partly"])` rather than the ticket lists `uncheckable_report()`
returns, because the banner renders counts and because a model carrying `Ticket`
objects is not the plain dict every §7 fixture is written to.

**Environment**, the complete list — three variables, each with a default that
makes the plain `python3 serve.py` case work:

| Variable | Default | Written by | Read by | Effect |
|---|---|---|---|---|
| `LOTTO_PORT` | `4322` | `supervise.py` (LOTTO-0013) | `serve.py` | bind port; also builds §4.4's `Host` allowlist |
| `LOTTO_TOKEN` | minted per run | `supervise.py` (LOTTO-0013) | `serve.py` | §4.4's write token; standalone `serve.py` mints its own |
| `LOTTO_NO_BUILD` | unset | the caller | `serve.py` | bind and serve, build nothing — for LOTTO-0013's INV-20 case and LOTTO-0014's INV-13 child only, never for users; see §6 |

**The token is not a model key** — `page.py`'s signature is
`render(model, token)`, so the model stays exactly what §7's fixtures are built
to. LOTTO-0014 §4.3 owns that rule and the reason for it.

`page.py` emits the page's inline JavaScript along with its markup. It has
exactly four jobs and no others: the two POSTs (which must carry a custom
header, LOTTO-0014 §4.3), filtering the ticket table (which must not touch the
URL, LOTTO-0014 INV-21), and **polling `GET /status` every 2 s while `building`
is true, or after a `POST /refresh`, reloading when `built` changes**. Without
the fourth, the opening *building* page never leaves that state and
`GET /status` has no consumer at all. It is inline rather than a served asset
because a fifth route serving files is the thing LOTTO-0014 §4.1 exists to
avoid.

The one direction that must never appear is `serve.py → PySide6`. LOTTO-0013's
INV-19 asserts it, because it is what keeps the headless case working and it
would break silently — a developer machine has Qt installed, so an accidental
import is invisible until someone runs it over SSH.

`page.py` is separated from `serve.py` so rendering can be tested without a
socket, and so an HTML mistake cannot become an HTTP mistake.

### 4.2 The model is built once, because building it costs 27 requests

Run from the repository root, 2026-08-02, with `archive_results.json` and
`archive_cache/` already populated:

```console
$ python3 - <<'EOF'
import time, urllib.request
n = [0]; real = urllib.request.urlopen
def counted(*a, **k):
    n[0] += 1
    return real(*a, **k)
urllib.request.urlopen = counted
from check import check
from tickets import load
tickets = load()
t0 = time.time(); check(tickets)
print(f"build: {time.time()-t0:.1f}s, {n[0]} requests")
was = n[0]; t0 = time.time(); check(tickets)
print(f"again: {time.time()-t0:.2f}s, {n[0]-was} requests")
EOF
build: 43.0s, 27 requests
again: 0.03s, 0 requests
```

**Only the request counts are asserted.** Wall-clock was 32.1 s on one run and
43.0 s on another; it is network-bound against a third-party API and is not a
figure this spec can hold anyone to. The counts are what the design rests on:

- **Rendering per request is not an option.** 27 requests per page view against
  the operator's free public API is not a polite client, and half a minute is
  not a page load. The model is built once into memory and every request is
  served from it.
- **A refresh must clear the memos first, or it is a no-op that looks like it
  worked.** The second build made **zero** requests and returned an identical
  result in 0.03 s, because the project holds three module-level dicts that are
  never invalidated. A Refresh button wired straight to `check()` would redraw
  the same numbers, report success, and never fetch anything — the failure is
  invisible from the page, which is why INV-17 counts requests rather than
  checking that the button works.

All three, enumerated by command rather than by reading. The pattern was widened
before being trusted, so an annotated or `dict()`-built memo could not hide from
it, and the decorator forms were ruled out separately (2026-08-02):

```console
$ grep -nE "^[A-Za-z_]+ *(:[^=]+)? *= *(\{\}|dict\(\))" *.py
check.py:20:_struct = {}
history.py:37:_cache = {}
results.py:44:_divisions_cache = {}
$ grep -nE "lru_cache|@cache|functools|cached_property" *.py
$                      # no output: no decorator-based memo anywhere
```

`tickets.py` holds none, so re-parsing the dump is already unconditional — the
tickets half of a refresh needs no invalidation at all.

```python
class State:
    """The one mutable thing in the server. All access under one lock."""
    def get(self):        ...  # -> (model|None, building: bool, built: str|None, stale: bool)
    def begin(self):      ...  # -> False if a build is already running (no concurrent builds)
    def finish(self, model):   # success: swap in, built=now, stale=False, building=False
    def fail(self):            # failure: model UNTOUCHED, stale=True, building=False
    def wait_idle(self, timeout): ...  # block until not building; -> False on timeout


def refresh(state, build_model):
    """Rebuild from the sources on a worker thread. Clears the memos first.

    The previous model keeps serving throughout, and survives a failure — that
    is INV-18, and it is why `fail()` never touches `model`.
    """
    if not state.begin():
        return False  # already building; the route answers 409, not 202, so a
                      # second Refresh click is visibly declined, not silently lost
    def work():
        import check, history, results
        history._cache.clear()            # {(game, plus_flag): [draw, ...]}
        results._divisions_cache.clear()  # {(game, issue, pool_id, plus_flag): [...]}
        check._struct.clear()             # {(game, plus_flag, pool_id): {label: div}}
        try:
            state.finish(build_model())   # atomic swap; readers never see a half-built model
        except Exception:
            state.fail()                  # keep the last good model, flag it stale
    threading.Thread(target=work, daemon=True).start()
```

**`wait_idle()` exists for the tests, and they do not work without it.**
`refresh()` starts a daemon thread and returns at once, so INV-17's "all three
memos are empty afterwards" and INV-18's "`stale: true`" are both races against
a build that may not have started, let alone finished. Every case that
refreshes calls `wait_idle(5)` first and fails on a timeout rather than
proceeding — otherwise the suite passes or fails for reasons unconnected to the
contract, which is worse than having no case.

`stale` means **the last refresh attempt raised**; it is not an age. It is set
by `fail()`, cleared by the next `finish()`, and it is the flag the page reads
to tell the user the figures are from an earlier fetch. `built` is the
timestamp of the last *successful* build and is `None` until the first one
lands — which is what `GET /status` reports while the opening build runs.

`results._divisions_cache` is the one that is easy to miss and the one that
matters most: it holds the prize breakdown per draw, so a refresh that skipped
it would fetch new draws and price them from the previous run's division
tables. `backfill.py` needs no clearing — it caches to `archive_cache/` on
disk, and archive-era draws are historic and immutable.

**Bind the port before the first build, not after** — the pattern
`serve.mjs` already uses ("Listen before refreshing, not after"). The server
starts answering immediately and serves a *building* page for the first
thirty-odd seconds, rather than leaving the browser to time out on a port
nothing is listening to yet. That opening build goes through the same
`refresh()` above, so it has one code path, one lock and one failure mode.

### 4.3 HTTP surface — LOTTO-0014

The four routes, their bodies, their status codes and the 404/405 routing floor
moved to LOTTO-0014 §4.1 in the 2026-08-02 split. The two that this document's
sections depend on: `POST /refresh` drives §4.2's rebuild, and `POST /settings`
writes §4.7's two files.

### 4.4 Security boundary — LOTTO-0014

The `Host` allowlist, the `Origin` rule, the per-run token, the anti-framing and
no-CORS rules, and the ban on request-derived data reaching a header or a file
moved to LOTTO-0014 §4.2–§4.4, along with INV-12, INV-13, INV-14 and INV-21.
Three of its rules bind this document's files:

- `page.py`'s signature is `render(model, token)` — the token is not a model
  key, so §4.1's model shape stays what every fixture is built to
  (LOTTO-0014 §4.3).
- §4.5's ticket filtering is client-side and must not touch the URL — no query
  parameter, no fragment, no `history.pushState()` (LOTTO-0014 INV-21).
- §4.7's `.desktop` bytes are asserted byte-for-byte by LOTTO-0014's INV-14,
  and this document remains the only place those bytes are written down.

### 4.5 What the page shows, and the rule it must not drop

Four sections, in this order — expiry first, because it is the only thing on
the page with a deadline:

1. **Claimable now** — every unexpired win, soonest expiry first, each naming
   its pool (`lotto/1`, not "Lotto"), its division, its amount and its expiry
   date. A prize expiring within 30 days is marked; one expiring **today** is
   marked distinctly, because §6's build-time expiry makes today's the one the
   page can be wrong about.
2. **Live tickets** — tickets with draws still to come, showing draws
   remaining. Two **scorable** ones today; the unscorable entries below are
   also listed here and are not counted by this figure:

   ```console
   $ python3 -c "
   from history import covered, scorable
   from tickets import load
   print(sum(1 for t in load() if any(
       scorable(t, pf) and len(covered(t, pf)) < t.ndraws for pf, _ in t.pools)))"
   2
   ```

   **Draws remaining is only meaningful for a scorable entry**, which is why the
   expression above tests `scorable()` first. For an entry nothing can score
   `covered()` returns `[]` by contract, so a naive `ndraws - len(covered(...))`
   reports a 2019 ticket as having all ten draws still to come. That is the
   project's cardinal error wearing a new hat — "no data" rendered as "yet to
   be drawn" instead of as "did not win" — and INV-15 is what catches it.

   **Every unscorable entry renders in this section**, unconditionally, with
   "draws remaining unknown — not checkable" and `draws_remaining: None` per
   §4.1. No "is its window still open?" test gates it, because for an
   unscorable entry that predicate cannot be computed: `covered()` returns `[]`
   by contract, and for a `no_pool` entry such as `daily/1` there is no draw
   calendar at all to measure a window against. Omitting these would be the
   cardinal error a third time — a reader takes an absence for "nothing
   outstanding".
3. **Every ticket** — filterable by game and pool, showing cost, boards, the
   pools its price paid for, and per pool one row with **two** cells that
   matter: what it won (`won_cents`, §4.1) and, when nothing could score it,
   the reason. The won cell is the one INV-15 asserts against, and it is why
   the entry shape carries `won_cents: int|None` rather than a bare integer —
   `0` and "not checkable" must not render the same.
   **Filtering is client-side**, over rows already in the document, and must
   leave the URL byte-identical — LOTTO-0014 §4.4 states that rule and INV-21
   asserts it, including the markup forms (a `href="?…"` link, a GET form) that
   are easier to reach for than a `pushState`.
4. **Spend against winnings** — §4.6.

**The uncheckable rule is structural here, not prose.** `check.py::uncheckable_report()`
returns `(lines, counts)`, and `counts["wholly"]` / `counts["partly"]` are the
ticket lists themselves — which is what the banner needs. **It is not the source
for the per-entry reason**: `counts["too_old"]` and `counts["no_pool"]` are
integers (`"too_old": len(too_old)`), and the `(ticket, plus_flag)` lists behind
them are local to the function. So **`serve.py`'s builder** derives each entry's
reason into `model["entries"][i]["reason"]` (§4.1); `page.py` only renders what
it finds there:

```python
rows = all_draws(t.game, plus_flag)                      # in serve.py's builder
reason = ("no results source carries this pool" if not rows
          else f"predates all draw data for this pool (earliest {rows[0]['date']})"
          if t.start.strftime("%Y-%m-%d") < rows[0]["date"] else None)
```

That is the same two-way split `uncheckable_report()` makes, recomputed rather
than imported — which §7 requires anyway, and which keeps `check.py`'s return
shape unchanged, since §9 puts changes to scoring out of scope. The banner's
totals still come from `uncheckable_report()`, so the page cannot disagree with
`check.py` about how many entries are excluded.

The page renders per entry:

- An entry nothing can score renders as **"not checkable"** with its reason —
  never as a blank cell, a dash, a zero, or an absence from the table. A blank
  cell in a money column reads as nil, which is the failure this project exists
  to prevent.
- A ticket checkable in one pool and not another renders **both** facts on the
  same row. All 11 `Daily Lotto Plus` tickets are this shape; a page that files
  each ticket under one heading would have to pick a wrong one.
- The counts banner (974 of 1,233 entries, 426 tickets wholly and 11 partly)
  renders above the wins, not below, and is not collapsible.

INV-15 asserts this against a fixture built for it, because it is the one rule
here that no compiler, linter or type check can see.

### 4.6 Spend against winnings

Per `docs/specs/LOTTO-0009-entered-pools.md` §4.7 — that spec owns the rule,
this one implements it and provides its check. Per-entry cost is that tier's own
board price, in cents:

```text
entry_cost_cents = tier_increment(game, era, plus_flag) * paid_lines * ndraws
```

**`paid_lines` is `len(Ticket.boards)`.** There is no `paid_lines` attribute —
`tickets.py::entered_pools()` takes it as a parameter and `parse()` passes
`len(boards)`, under the comment *"Multiplay is already expanded above, so one
board here is one paid line"*. So the expansion has already happened by the
time anything here sees a ticket, and `len(t.boards)` is the count that was
charged for, including each Multiplay combination. Stating it matters because
the two readings differ **only** on Multiplay tickets, which is the one place
the error would not show up in a spot check.

`tier_increment()` lives in **`serve.py`, in the model builder** — the only
module that computes, per §4.1 — and writes `cost_cents` onto each entry.
`page.py` sums what it is given.

`tier_increment()` reads the **increment** column of `tickets.py::TIER_PRICES`
— a different column from the cumulative total `entered_pools()` matches on,
and conflating them prices a R10.00 Lotto ticket at R22.50. It is written at
this call site, as §4.7 says it should be.

**The comparison is drawn over checkable entries only.**

```console
$ python3 - <<'EOF'
from history import scorable
from tickets import HANDOVER, TIER_PRICES, load
life = chk = cost = 0
for t in load():
    era = "sizekhaya" if t.bought >= HANDOVER else "ithuba"
    inc = {pf: i for pf, _p, i in TIER_PRICES[(t.game, era)]}
    cost += round(t.cost * 100)
    for pf, _ in t.pools:
        c = inc[pf] * len(t.boards) * t.ndraws
        life += c
        if scorable(t, pf):
            chk += c
print(f"lifetime R{life/100:,.2f}, checkable R{chk/100:,.2f}, sums back: {life == cost}")
EOF
lifetime R28,244.50, checkable R10,603.50, sums back: True
```

The winnings side, from the same run (all wins are on checkable entries by
construction — `check.py::check()` skips an entry `scorable()` rejects):

```console
$ python3 -c "
from check import check
from tickets import load
tickets = load(); wins = check(tickets)
live = [w for w in wins if not w['expired']]
print(f\"won lifetime R{sum(w['amount'] for w in wins):,.2f}, \"
      f\"unexpired R{sum(w['amount'] for w in live):,.2f}, \"
      f\"unresolved tickets {len([t for t in tickets if not t.resolved])}\")"
won lifetime R2,651.60, unexpired R2,418.90, unresolved tickets 0
```

| Figure | Value | Shown as |
|---|---|---|
| Spend on entries that could be scored | R10,603.50 | the comparison |
| Winnings on those entries | R2,651.60 lifetime, R2,418.90 unexpired | the comparison |
| Lifetime spend, all 1,233 entries | R28,244.50 | a separate, labelled line |

**The identity holds only where the price resolved, and the display must say so.**
LOTTO-0009 §4.7 states it with that condition — *"the entry costs sum back to
it, and only when the price resolves"* — and the condition is load-bearing:
`tickets.py::parse()` falls back to `pools = [(plus_flag, pool_id)]`, a single
name-derived tier, when `entered_pools()` comes back unresolved, and that one
tier's increment cannot sum to what the SMS charged. So:

- **Lifetime spend is `Σ round(Ticket.cost * 100)` over every ticket** — always
  correct, because `Ticket.cost` is what the bank charged and needs no
  apportionment (INV-10).
- **The comparison is over resolved tickets' checkable entries only.** An
  unresolved ticket contributes to neither side of it.
- **Unresolved tickets get their own labelled line** — count and total cost —
  in the same spirit as INV-7's "reported, never guessed at". Silently dropping
  them from the comparison while their cost sits inside the lifetime figure
  would make the two lines disagree with no explanation.

`sums back: True` in the run above is the identity holding across all 558
tickets *today*, and it holds because **`unresolved tickets 0`** — measured in
the same breath, because the first figure means nothing without the second. One
unresolved ticket falsifies the identity without changing anything else on the
page, which is exactly the silent case INV-16 is scoped to exclude. Comparing R28,244.50 against R2,651.60 would convert 974 unscorable
entries into losses and put a false −R25,592.90 on the page; the two totals
never appear in the same subtraction. INV-16.

### 4.7 Settings panel

Two settings, both booleans, rendered as on/off switches:

| Setting | Stored as |
|---|---|
| Start the tray at login | presence of `~/.config/autostart/lotto-tracker-tray.desktop` |
| Open the page when the tray starts | `open_on_start` in `~/.config/lotto-tracker/settings.json` |

The autostart setting has no separate record — the file *is* the state, so the
switch cannot drift from what the desktop actually does. Both paths honour
`$XDG_CONFIG_HOME` and fall back to `~/.config`.

The written file, verbatim and entirely constant apart from the one derived
path — **this is the only place these bytes are written down**, and
LOTTO-0014's INV-14 asserts them byte-for-byte:

```ini
[Desktop Entry]
Type=Application
Name=Lotto Tracker
Comment=Tray control for the local lottery page
Exec="<sys.executable>" "<dirname(abspath(serve.__file__))>/tray.py"
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
```

Both fields are quoted, because a repository directory containing a space would
otherwise split into two arguments and the entry would silently do nothing. The
interpreter is `sys.executable`, not the string `python3`: the autostart
session's `PATH` is not the one the server was installed under, and this is
precisely the launch path where that bites. (LOTTO-0013 §4.2 applies the same
rule to the child it spawns, for the same reason.) Both are substituted at write
time, so the bytes on disk are constant for a given install — which is what lets
LOTTO-0014's INV-14 assert them.

`open_on_start` defaults to **true**. Its only reader is `tray.py`, so
**LOTTO-0013 §4.3 owns what happens when it is read** — including the rule that
a missing, unreadable or malformed `settings.json` falls back to the default
rather than raising, since the consequence of getting that wrong is a tray that
never appears. This document owns the file: its path, its key and that default. Writing the file creates its directory with
`parents=True, exist_ok=True` — without `exist_ok` the second enable raises
`FileExistsError`, which is the *normal* case and would surface as §6's 500 on
every toggle after the first.

**Accessible switch markup.** The switch is a styled
`<input type="checkbox" role="switch">`, not a `<div>` with a click handler:
`role="switch"` is the ARIA pattern for a two-state toggle, and building it on
a real checkbox keeps keyboard focus, Space to toggle, and the state a screen
reader announces. The visual is CSS; the semantics are the native control.

### 4.8 What starts and stops it — LOTTO-0013

The tray, `supervise.py`, the spawn-and-reap lifecycle and the headless
contract are LOTTO-0013. Two of its rules bear directly on this document's
files and are stated there rather than here: `serve.py` reads `LOTTO_PORT` once
and uses that same value both to bind and to build §4.4's `Host` allowlist
(LOTTO-0013 §4.5), and everything in `serve.py` that binds, builds or serves
sits behind `if __name__ == "__main__":` (LOTTO-0013 §4.4, which is what makes
its INV-19 observable).

## 5. Invariants

This document holds **INV-15 to INV-18** — the honesty rules on the data the
page renders. LOTTO-0001 holds INV-1 to INV-6, LOTTO-0009 INV-7 to INV-11,
LOTTO-0014 INV-12 to INV-14 and INV-21, and LOTTO-0013 INV-19 and INV-20. No
number moved in either 2026-08-02 split — CHANGELOG.md and sibling specs cite
them unqualified.

- **INV-15** — An entry nothing can score renders as "not checkable" with its
  reason, and never as a blank, a dash, a zero, or an omission; a ticket
  checkable in one pool and not another shows both facts.
  *Test:* `tools/verify_page.py`, case `uncheckable_not_a_loss` — renders a
  synthetic two-pool ticket, one pool scorable and one not, and asserts the
  unscorable pool's row is present, that its reason string is rendered, and
  that the text of its amount cell is **not** in
  `{"", "-", "–", "—", "0", "0.00", "R0.00"}`. Naming the forbidden strings is
  the assertion; "no zero-amount cell" is not observable, and a blank or a dash
  is the likelier rendering than a literal zero.
  *Breaks when:* the renderer iterates wins rather than entries, so an entry
  with no win simply does not appear — the failure mode that needs no bug, only
  an omission.

- **INV-16** — The compared spend is the apportioned cost of the checkable
  entries of resolved tickets, and nothing else; lifetime spend appears only as
  a separately labelled figure.
  *Test:* `tools/verify_page.py`, case `spend_over_checkable` — over a fixture
  of **four** tickets (one fully checkable, one partly, one wholly unscorable,
  and one whose price resolves to no tier), asserting the unresolved one
  contributes to neither side of the comparison and appears on §4.6's separate
  labelled line. Without that fourth ticket the "of resolved tickets" clause
  cannot fail, and the real dump supplies no case — it currently holds
  **`unresolved tickets 0`**, so this fixture is the only place the rule is
  ever exercised. The case
  asserts the rendered compared-spend figure **equals** an independently
  recomputed `Σ tier_increment × paid_lines × ndraws` over scorable entries of
  resolved tickets, and that the rendered lifetime figure is a different, larger
  number. Equality against a recomputed value is the assertion; "the lifetime
  total never appears as an operand" is not something a test can observe.
  *Breaks when:* the comparison uses `sum(t.cost for t in tickets)` — the
  obvious expression, and the lifetime figure — which puts a false loss of
  R25,592.90 on the page; or an unresolved ticket is folded into the compared
  spend, where its name-derived single tier cannot sum to what it cost (§4.6).

- **INV-17** — A refresh empties **all three** of §4.2's memos before rebuilding,
  which is what makes it re-fetch rather than redraw.
  *Test:* `tools/verify_page.py`, case `refresh_refetches` — puts a sentinel
  entry in each of `history._cache`, `results._divisions_cache` and
  `check._struct`, runs a refresh with a stub builder, and asserts all three are
  empty afterwards and the builder was called once.
  Counting `urlopen` calls would be the obvious test and cannot work here: §7's
  seam replaces the builder, so no request is ever issued and the count is zero
  on every refresh whether or not the memos were cleared — a case that can
  never pass, let alone fail for the right reason. Asserting the memos are
  empty tests the contract §4.2 actually states, and it is the assertion that
  distinguishes clearing three from clearing two.
  *Breaks when:* any of the three memos in §4.2 is not cleared —
  `history._cache`, `results._divisions_cache` or `check._struct`. Measured: a
  second build in the same process makes 0 requests and returns an identical
  result, so this failure is invisible from the page. Clearing two of the three
  is the likelier bug than clearing none, and it is worse: the page would show
  new draws priced from the previous run's division tables, which is wrong
  money rather than stale money.

- **INV-18** — A failed refresh leaves the previous model serving and says so;
  it never serves an empty or zeroed page.
  *Test:* `tools/verify_page.py`, case `failed_refresh_keeps_model` — serves a
  fixture model, refreshes with a **stub builder that raises**, and asserts the
  original wins still render, that `GET /status` reports `stale: true`, and that
  `built` is unchanged from before the failed attempt.
  *Breaks when:* the model is cleared before the rebuild, or an exception on
  the background thread leaves `state` empty. The operator's API failed with
  `URLError(SSL: UNEXPECTED_EOF_WHILE_READING)` on **four of the seven** build
  attempts made while measuring this spec (2026-08-02), so this is a routine
  path rather than a rare one, and it is the reason §6 treats a degraded page
  as a normal state instead of an error.

## 6. Failure modes

- **The operator's API is unreachable.** Four of seven build attempts on
  2026-08-02 failed with `SSL: UNEXPECTED_EOF_WHILE_READING` — this is the
  common failure, not an edge case. At startup: the page serves
  from `archive_results.json` alone with a visible notice that live results are
  missing, and says which pools are affected — it does not show zero wins. On
  refresh: INV-18.
- **Port 4322 is in use.** `serve.py` exits with the port in the message rather
  than tracebacking. `LOTTO_PORT` overrides it; LOTTO-0013 §4.5 owns that
  variable and how the tray surfaces the failure. (4322 chosen as free on this
  machine and adjacent to the user's stats dashboard on 4321 — `ss -ltn`,
  2026-08-02.)
- **`lotto_sms_raw.txt` is absent.** The page renders its empty state and says
  the dump is missing and how to produce it — never "0 tickets, R0.00", which
  reads as "you have never won".
- **`LOTTO_NO_BUILD` is set** (§4.1 — it exists for LOTTO-0013's INV-20 case,
  not for users). The page renders that same empty state with an explicit *"no
  build was performed"* notice. This is the one situation in which an empty page
  is correct, and it is not an exception to INV-18: nothing was ever built, so
  there is no previous model to lose. The notice is what keeps it from reading
  as "no wins".
- **`~/.config/autostart/` does not exist.** Created with
  `parents=True, exist_ok=True` on first enable; a write failure returns 500
  with the reason and leaves the switch showing its true state, not the
  requested one.
- **A prize expires while the page is open.** Expiry is computed against
  `datetime.now()` at model-build time, so an open page can show a prize that
  has since lapsed — observed during this session, where the claimable line
  count and total both moved between two runs a few hours apart as a win
  crossed the 365-day boundary. (No amount or date is given for it: a single
  win's amount and its draw date identify one real ticket, which CLAUDE.md's
  privacy rule forbids in a public repo, and `tools/verify_privacy.py` cannot
  catch it because it compares against the dump's text rather than against what
  the text implies.) The page therefore stamps the build time and marks
  anything expiring today, rather than implying the figure is live.
- **A tab left open across a server restart holds a stale token** — its next
  toggle gets a 403 and renders as "this page is from an earlier session —
  reload it". LOTTO-0014 §6 owns that behaviour; it is listed here only because
  the toggle the user clicks is §4.7's.

## 7. Tests

`tools/verify_page.py` joins `tools/verify_privacy.py`, `tools/verify_sources.py`,
`tools/verify_coverage.py` and `tools/verify_pools.py`. Exit code is the signal,
as with the other four. **One script covers all three parts of the split**: ten
cases, one per invariant, of which this document owns the four below,
LOTTO-0014 §7 owns `host_allowlist`, `token_required`, `no_reflected_headers`
and `nothing_in_the_url`, and LOTTO-0013 §7 owns `serve_is_headless` and
`no_orphan_server`. One script rather than three because the cases share their
fixtures, their temporary-directory setup and their stub builder.

| Case | Locks |
|---|---|
| `uncheckable_not_a_loss` | INV-15 |
| `spend_over_checkable` | INV-16 |
| `refresh_refetches` | INV-17 |
| `failed_refresh_keeps_model` | INV-18 |

Three constraints on the script, each following from something in the existing
suite, and all three binding on LOTTO-0013's two cases as well:

- **It must not need the network.** The seam is the **builder**, not the model:
  `make_server(build_model, token, port)` takes a callable. Handing it a
  finished model would leave `POST /refresh` with nothing to invoke, so INV-17
  (count requests across two rebuilds) and INV-18 (make a rebuild raise) would
  have no rebuild to exercise — two of the ten cases untestable by
  construction. A stub builder gives each case what it needs: one that counts
  its calls, one that raises, one that returns a fixture. None touches
  `urllib`, so a whole run costs well under a second against the 27 requests a
  real build makes.

  **INV-15 needs a second seam**, because its fixture requires `scorable()` to
  differ between two pools of one ticket — a property of `history.all_draws()`,
  not of the model. Its case injects `all_draws` with a double returning draws
  for one pool and `[]` for the other, which is the `daily/0` vs `daily/1`
  shape that makes 11 real tickets partly uncheckable.
- **It must not touch real data.** Cases run with **both `$HOME` and
  `$XDG_CONFIG_HOME`** pointed at a
  temporary directory and tickets built from the `VAS00000000000` sentinel, not
  from `lotto_sms_raw.txt`. **Both variables, not just `$HOME`** — §4.7's paths
  honour `$XDG_CONFIG_HOME` first, and KDE and GNOME both export it, so
  redirecting `$HOME` alone leaves every case writing to the user's real
  `~/.config/autostart/`: a test that changes the system it measures, in the
  configuration this project is actually developed on.
- **It must not import the thing it tests where the thing is the judgement.**
  `tools/verify_coverage.py` and `tools/verify_pools.py` both carry this rule:
  INV-15 and INV-16 recompute what should be rendered rather than importing the
  renderer's own opinion of it.

**Each case is observed failing before the invariant is accepted.** LOTTO-0009
§7's practice was to red-test against pre-fix code; there is no pre-fix code
here, because this is greenfield. The equivalent is to break the rule
deliberately — widen the `Host` comparison to `endswith`, drop the token check,
clear the model before a rebuild, return the lifetime total from the comparison
— confirm the case fails, then restore. A case never seen failing is a case
that proves nothing, and on a greenfield spec that is the *only* way to know it
can fail at all.

## 8. Alternatives considered (and rejected)

- **A generated static HTML file.** Rejected by the user 2026-08-01. It cannot
  offer a Refresh button or a settings toggle without a server behind it, and a
  file on disk holding every ticket is a second copy of the data
  `tools/verify_privacy.py` exists to keep out of the repository.
- **Settings in the tray menu instead of the page.** Rejected 2026-08-02. It
  would have kept the HTTP surface read-only and removed §4.4's token entirely;
  the user chose the panel knowing that.
- **A `<div role="switch">` toggle.** Rejected: rebuilding focus, keyboard and
  announcement on a div is how toggles become unreachable. Same visual on a real
  checkbox (§4.7).

(The alternatives about the *tray* — a systemd user unit, a detached child,
Electron — are LOTTO-0013 §8. Those about the *security boundary* — `Origin`
instead of `Host`, `SimpleHTTPRequestHandler`, a token in a query string — are
LOTTO-0014 §8.)

## 9. Out of scope

- The HTTP surface, the `Host` allowlist, the token and the response-header
  rules — LOTTO-0014.
- The tray, the supervisor, the spawn-and-reap lifecycle and the headless
  contract — LOTTO-0013.
- Marking a prize as claimed, which needs persistent state — deferred; ROADMAP
  LOTTO-0002 names `sqlite3` and a separate item for it.
- Picking up new SMSes without the phone plugged in — LOTTO-0003.
- Any change to how tickets are parsed, scored or priced. This item adds a face
  on `check.py`'s output and no new source of truth; a wrong number on the page
  is a bug in this spec's rendering or in LOTTO-0001/LOTTO-0009, never a third
  opinion.
- Serving to any host but the loopback interface, now or later.

## 10. Resource cost

- **Memory:** one model in memory, plus one being built during a refresh. The
  model is the 558 tickets, 1,233 entries and 86 wins already held by
  `check.py`, plus the rendered HTML string; the process holds at most two
  models briefly at swap time, and no history of them. No unbounded growth: the
  cap is the dump's size.
- **Network:** 27 requests per build (measured, §4.2), and a build happens at
  startup and on explicit refresh only — never per page view. This is the same
  27 requests `check.py` already makes per run, so the page costs the operator
  nothing extra unless the user presses Refresh. §4.1's `GET /status` poll is
  loopback-only and runs at 2 s **only while a build is in flight**, so it costs
  the operator nothing and the machine one loopback request per two seconds of
  build; an idle page polls nothing. Not stated as a count, because the count is
  a function of the wall-clock §4.2 explicitly declines to assert.
- **Disk:** two files under `$XDG_CONFIG_HOME` (§4.7), both a few hundred bytes.
  Nothing written to the repository, which `tools/verify_privacy.py` continues
  to assert.
- **Dependencies:** none. `serve.py` and `page.py` are standard library, which
  keeps the project's "Python 3.8+ stdlib" claim in README.md true for the
  headless path. PySide6 enters through LOTTO-0013's `tray.py` alone.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-15 uncheckable never a loss | `tools/verify_page.py::uncheckable_not_a_loss` |
| INV-16 spend over checkable only | `tools/verify_page.py::spend_over_checkable` — also closes LOTTO-0009 §11's `nothing` row for its §4.7 |
| INV-17 refresh re-fetches | `tools/verify_page.py::refresh_refetches` |
| INV-18 failed refresh keeps the model | `tools/verify_page.py::failed_refresh_keeps_model` |
| §4.1 `page.py` performing no I/O | `tools/verify_page.py` — every case renders with `all_draws` replaced by a double that raises (the seam INV-15 already needs). Absent that double the row would be false: with no `archive_results.json`, `history.all_draws()` falls straight through to `api_draws()`, which **succeeds** on a connected machine, so a renderer calling it would pass |
| §4.1 the model's key set | **nothing** — a builder and a renderer that agree on a wrong shape are consistent with each other, and every fixture is written to the same shape |
| §4.2 the 27-request figure staying true | **nothing** — a dated measurement; a larger dump or an API paging change moves it without failing anything |
| §4.5 the page being *readable* — ordering, filters, marking near-expiry | **nothing** — no check can tell a clear layout from a cluttered one |
| §4.7 the written `.desktop` file actually autostarting on this desktop | **nothing mechanical** — it depends on the session's XDG implementation; verified by logging out once |

Nine rows, four `nothing`.

The parent's table held twenty-two rows and six `nothing`, and the three tables
partition it without overlap: nine rows and four `nothing` here, eleven and two
in LOTTO-0014 §11, and the two INV-19/INV-20 rows in LOTTO-0013 §11. LOTTO-0013
then added seven rows of its own — one named catcher and six `nothing` — for Qt
and desktop-session behaviours the parent had never tabulated, which is why its
own tally reads nine and six.

## 12. Cross-doc impact

- `docs/specs/LOTTO-0013-tray-and-supervisor.md` — the other half of this split;
  it holds §4.8's subject, INV-19 and INV-20. Written 2026-08-02.
- `README.md` — a new section for the page: how to start it, the optional
  autostart switch, and the port. Shared with LOTTO-0013, which writes the tray
  half of the same section and adds PySide6 as a tray-only requirement to the
  "Needs Python 3.8+ and a Linux desktop" line.
- `CLAUDE.md` — the Commands block gains `python3 serve.py` and the verification
  list gains `tools/verify_page.py`. Its architecture diagram gains the second
  consumer of `check.py`.
- `CHANGELOG.md` — an `Added` entry citing LOTTO-0002.
- `ROADMAP.md` — LOTTO-0002 flips to shipped; its "Spec:" line already points
  at this file.
- `docs/specs/LOTTO-0009-entered-pools.md` — **two edits to its §11, both in the
  same change**, or that table contradicts itself. The row
  *"§4.7 comparison drawn only over checkable entries | **nothing** — this spec
  sets the rule; LOTTO-0002 implements the display and owns its check"* gains
  `tools/verify_page.py` (INV-16) as its catcher; and the tally line beneath it,
  *"Twelve rows, four `nothing`."*, becomes *"Twelve rows, three `nothing`."* —
  that spec states its own `nothing` count, which is the figure its §0 checklist
  calls the honest error budget, so leaving it at four would misreport the one
  number the convention exists to track.
- `docs/specs/LOTTO-0001-lottery-ticket-tracker.md` — unaffected. This item adds
  no parsing, scoring or pricing behaviour, so none of INV-1 to INV-6 moves.

**The split this section recommended was taken on 2026-08-02**, by the user —
and then taken a second time, because the first cut did not do enough.

| Part | Sections | Invariants | Lines |
|---|---|---|---|
| this document — the model, the build lifecycle, what the page shows | §4.1, §4.2, §4.5–§4.7 | INV-15 – INV-18 | 862 |
| LOTTO-0014 — the HTTP surface and the security boundary | its §4.1–§4.4 | INV-12 – INV-14, INV-21 | 466 |
| LOTTO-0013 — the tray, the supervisor, the headless contract | its §4.1–§4.5 | INV-19, INV-20 | 442 |

**Why twice.** The seam this section originally proposed was the one the
invariants fell along, and it moved only 66 of the parent's 1,161 lines — the
tray was never the weight. Measured after the first cut: §4 Design held 31,533
of the remaining 73,087 bytes (43%), §5 a further 11,673, and §13's historical
loop log 10,917 (15%). The second cut is along **subject** rather than
invariant count — web-security rules on one side, lottery-data honesty rules on
the other, which need different expertise to review — and the loop log was
archived to `LOTTO-0002-pre-split-review-log.md`. Together those took this
document from 1,161 lines to 862.

Sections were **not renumbered**. §4.3 and §4.4 remain in place as pointers to
LOTTO-0014, because ROADMAP LOTTO-0011 and sibling specs cite §4.5 and §4.7 by
number, and renumbering would silently redirect every one of those citations.

All three parts run the gate from loop 1 on their own bytes.

## 13. Cold-eyes loop log

The three cold-eyes loops run against the undivided 1,161-line document are
archived at [`LOTTO-0002-pre-split-review-log.md`](LOTTO-0002-pre-split-review-log.md).
**They confer no review credit here** — they were run against bytes this
document no longer has. Review loops below number from 1 on these bytes.

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 0-split | 2026-08-02 | — | — | — | — | — | **Provenance row — no reviewer was dispatched, and this is not a review loop.** The split §12 recommended was taken by the user on the seam it proposed: §4.8, INV-19 and INV-20 moved to `docs/specs/LOTTO-0013-tray-and-supervisor.md`, and this document kept §4.1–§4.7 with INV-12–18 and INV-21. Invariant numbers did not move — CHANGELOG.md and sibling specs cite them unqualified. What was rewritten rather than merely cut: §4.4's token paragraph now states only `serve.py`'s side of the channel (the `Popen`, and the argv-versus-environment reasoning, are LOTTO-0013 §4.2), §4.8 became a pointer carrying the two rules that bind this document's files, §7 records that one script serves every part, and §11 lost two named-catcher rows. **A second cut followed the same day**, once the first was measured as removing only 66 of 1,161 lines: §4.3 and §4.4 became pointers to `docs/specs/LOTTO-0014-http-surface-and-security.md`, which took INV-12, INV-13, INV-14 and INV-21 with them, and §13's three historical loop rows were archived to `LOTTO-0002-pre-split-review-log.md`. Sections were deliberately not renumbered — external citations name §4.5 and §4.7 by number. One defect was found while copying rather than by review: the parent's INV-13 clause said "four POSTs" and listed five; the successor states five. §11 now reads nine rows and four `nothing`, and the three parts' tables partition the parent's twenty-two and six without overlap. The three loops below produced 83 verified findings and **converged by cap rather than clean**, with collateral outnumbering draft defects in two of them — which is what made the split the next action instead of a fourth loop. |
