# LOTTO-0002 — Local web page for tickets, results and claimable winnings

**Status:** accepted (2026-08-02) — split out of the 1,161-line original, then
four cold-eyes loops on the post-split bytes; 103 verified findings fixed, 2
dismissed on evidence, none outstanding. The gate stopped after the second
re-gate loop by the user's decision rather than at the 3-loop cap, with
CRITICALs at 1 -> 0 and nothing verified left open. The third loop was postponed once and then run: §13's `3-skipped`
row records the postponement, and its loop `3` row is that read, carried out as
the re-gate the amendment's implementation forced.
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
dependency runs one way — but *toward* that document's files, not away from
them. **`serve.py` imports the settings paths and reader from `supervise.py`**
(LOTTO-0013 §4.1, which owns the reason: `tray.py` must read `open_on_start` and
may not import `serve`, so the reader lives where both can reach it and the
*writing* stays here, behind `POST /settings`'s lock). Nothing here imports
`tray.py` or `icons/`, and nothing there imports `serve.py` or `page.py`.
Reading this section as forbidding that one import is how an implementer ends up
writing a second settings reader — the duplicate LOTTO-0013 §11 records as
caught by nothing.

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

```text
# What build_model() returns — the data half.
{
  "wins":   [ {...check.py win dict, MINUS its rands "amount"...,
               "amount_cents": int,
               "expires_in_days": int} ],   # negative for an already-expired win
  "entries":[ {"ref", "game", "plus_flag", "pool_id", "cost_cents",
               "scorable": bool, "reason": str|None,   # §4.5 derives these
               "won_cents": int|None,                  # None iff not scorable
               "draws_covered": int|None,              # None iff not scorable
               "draws_remaining": int|None} ],         # None iff not scorable
  # `ref` joins tickets[] <-> entries[] <-> wins[]. Measured 2026-08-02:
  # 558 tickets, 558 distinct refs, none falling back to tickets.py's "?".
  # If a future SMS carries no `Ref:`, several tickets collapse onto "?" and
  # the join silently merges them — report it rather than rendering the merge.
  "tickets":[ {"ref", "game", "cost_cents", "boards": int, "ndraws",
               "resolved": bool, "bought": "YYYY-MM-DD"} ],
  "uncheckable": {                          # from check.py::uncheckable_report()
    "entries": 1233, "uncheckable": 974,    # totals
    "too_old": 963, "no_pool": 11,          # the two reasons, kept apart
    "wholly": 426, "partly": 11,            # TICKET counts, len() of the lists
  },
  "spend":  {"compared_cents", "lifetime_cents", "unresolved_cents",
             "unresolved_tickets": int},
  "won":    {"compared_cents", "lifetime_cents", "unexpired_cents"},
            # compared_cents: wins on scorable entries of RESOLVED tickets only
  "settings": {"autostart": bool, "open_on_start": bool},
}

# What `State` owns, and what serve.py overlays at render time.
{
  "built":    "2026-08-02T14:31:07" | None, # last SUCCESSFUL build (§4.2)
  "stale":    False,                        # last refresh attempt raised
  "error":    None | {"what": str, "pools": [str]}, # §6's results-unavailable
  "building": False,                        # a build is running RIGHT NOW
  "no_build": True,                         # present ONLY when there is no
                                            # model, no error and no build in
                                            # flight — §6's third empty state
}

# And the OTHER shape build_model() can return, when the dump is absent (§6).
# It is not a stripped version of the model above: page.py branches on it and
# renders the notice, so a renderer expecting the full shape must not be handed
# this one and vice versa.
{"no_dump": True, "settings": {...}}
```

**The two halves are separate because only one of them can carry the failure.**
`State.fail()` leaves the model *untouched* by design (§4.2 — that is what
INV-18 rests on), so a `stale` key living inside the model could never become
true: the object that would have to be edited is precisely the one the failure
path must not edit. Same for `error`, which by definition exists only when there
is no new model. So `build_model()` returns the data keys, `State` owns the
**first four** — `built`, `stale`, `error`, `building` — `serve.py` derives
`no_build` at render time from the other three rather than storing it (there is
nothing to store: it is the absence of all of them), and `serve.py` renders
`render({**model, "built": …, "stale": …, "error": …, "building": …}, token)`,
adding `no_build` when that third state holds. `page.py` stays
pure and sees one flat dict; §7's fixtures set all of them directly.

**All five are overlaid, and the three empty-page states are told apart by
them** — which is why none may be dropped from a fixture. `building` true is
*ask again shortly*; `error` set is *the last fetch failed, these figures are
older*; `no_build` is *nothing was built and nothing is coming*. Collapse any
two and the page tells the user the wrong thing about why it is empty, which
§6 states as one rule and INV-15 as the cardinal one.

`State.fail(exc, pools)` takes the exception and, **where they are known**, the
pools it could not reach; `get()` returns the pair as `error`. Today's only
caller is `refresh()`'s `work()`, which passes the exception alone: the build
that raised touched many pools and the exception does not say which one lost,
so attributing it would be a guess. **`pools` is therefore optional, not
unpopulated-by-oversight**, and `page.py` renders the empty case as *"all
pools"* rather than as a blank — the whole point being that a failure names its
scope even when the scope is everything. The parameter stays because a
pool-attributable failure is exactly what a future caller would have, and a
signature that cannot carry it would force that caller to widen the contract.

**`settings` is in the model because `page.py` cannot go and look.** The
renderer is pure (below) and there is no `GET /settings` route — LOTTO-0014
§4.1's surface is four routes and that is deliberate — so without this key the
panel has no way to know which way either switch is currently set, and would
render both in an arbitrary state on every load. The builder reads them from
the two places §4.7 names: `autostart` is the *presence* of the `.desktop`
file, `open_on_start` is the key in `settings.json`. `POST /settings` returns
the same shape, which is what the switches snap back to.

**One state, three words, and they are deliberately not merged.**
**Unscorable** is the model's word and matches the code — `history.scorable()`
returns false, `reason` is set. **Uncheckable** is the *count's* word: §4.5's
banner and `check.py::uncheckable_report()` speak of uncheckable entries and
tickets, and a ticket can be *partly* uncheckable while no single entry can be
partly anything. **"Not checkable"** is the *page's* word — the string a reader
sees in a cell. So: unscorable entry, uncheckable count, "not checkable" on
screen. They describe the same underlying fact and are used at three different
altitudes; a fix that collapses them loses the entry/ticket distinction INV-11
rests on.

`reason` is `None` for a scorable entry and otherwise the §4.5 string;
`draws_remaining` **and `draws_covered`** are both `None` for an unscorable
entry, never `0` and never `ndraws` — the type carries the cardinal rule so a
renderer cannot lose it. `draws_covered` needs the same treatment as the others
and for the same reason: `history.py::covered()` returns `[]` by contract for an
entry nothing can score, so a bare `int` makes every unscorable entry read
"0 draws checked", which is the cardinal failure moved one column left.
`won_cents` is `None` for an entry nothing could score and an integer (possibly
`0`) for one that was scored: the same distinction, on the money column INV-15
asserts against.

**`reason` is set on exactly the entries `scorable()` rejects, and that is a
coupling rather than a coincidence.** `history.py::scorable()` returns false on
two grounds and only two — the pool has no rows at all, or the ticket predates
the first draw any source carries — which are precisely the two branches §4.5
derives `reason` from. An unscorable entry therefore always has a reason to
show. If a third rejection ground is ever added to `scorable()`, §4.5 gains a
branch in the same change, or the page renders "not checkable" with nothing
after it, which is half of INV-15 lost.

**Every money value in the model is an integer of cents**, and the builder
**drops `check.py`'s own `amount` key** when it adds `amount_cents`. That
deletion is the load-bearing part: `check.py::amount()` is documented as "What
this match paid, **in rands**", so spreading the win dict unchanged would leave a
rands float sitting beside a cents integer in the same record, and a renderer
picking the wrong one is a 100× error on a page whose whole subject is money.
`tickets[].cost_cents` is `round(Ticket.cost * 100)`, and
`won.*_cents` / `wins[].amount_cents` are `round(w["amount"] * 100)`.
`Ticket.cost` and `check.py`'s `amount` are both **rands**, so the conversion
happens once, at the boundary, and never again. LOTTO-0009 §4.7 records the same
rands-against-cents trap, on a spec whose whole subject is money; one unit in the
model is how this spec avoids re-deriving that. (§4.6 carries a *different* unit
warning — increments against cumulative totals, which misprices by roughly
2.25×, not by 100×. The two are worth keeping apart: they fail at different
magnitudes and neither one catches the other.)
`spend.unresolved_cents` is `Σ round(Ticket.cost * 100)` over unresolved
tickets — their raw price, not an apportionment, since apportioning is exactly
what fails for them (§4.6).

`uncheckable` holds **integers only**: the builder stores `len(counts["wholly"])`
and `len(counts["partly"])` rather than the ticket lists `uncheckable_report()`
returns, because the banner renders counts and because a model carrying `Ticket`
objects is not the plain dict every §7 fixture is written to.

**Environment** — the four variables `serve.py` reads for its own configuration,
each with a default that makes the plain `python3 serve.py` case work. Three of
the names are this project's to define; **`PORT` is not**, and that is the whole
reason it is honoured — it is the name an external process manager already sets,
so a manager can move this server without knowing anything about the project. It
therefore wins over the project's own `LOTTO_PORT`. `serve.py` also reads
`$XDG_CONFIG_HOME` and `$HOME`, which are not this project's either: §4.7's
two paths honour the first and fall back to the second, and §7 requires both to
be redirected for every case.

| Variable | Default | Written by | Read by | Effect |
|---|---|---|---|---|
| `PORT` | unset | an external process manager, or the user | `serve.py` | bind port, **winning over `LOTTO_PORT`** (INV-24) |
| `LOTTO_PORT` | `4322` | `supervise.py` (LOTTO-0013), or the user on the standalone path | `serve.py`, and `supervise.py` itself (LOTTO-0013 §4.5) | bind port when `$PORT` is unset or empty; also builds §4.4's `Host` allowlist |
| `LOTTO_TOKEN` | minted per run | `supervise.py` (LOTTO-0013) | `serve.py` | §4.4's write token; standalone `serve.py` mints its own |
| `LOTTO_NO_BUILD` | unset | the caller | `serve.py` | bind and serve, build nothing — for LOTTO-0013's INV-20 case and LOTTO-0014's INV-13 child only, never for users; see §6 |

**The port is resolved once, before the bind** — `serve.py::resolve_port()`, in
that order: `$PORT`, `$LOTTO_PORT`, `4322`. The resolved number is the one that
binds *and* the one that builds §4.4's `Host` allowlist, which is why it is read
once rather than at each use (LOTTO-0013 §4.5 owns what a disagreement costs).
**Unset and empty are not values** — they mean "no preference" and fall through
to the next source — while a value that was *meant* as a port and cannot be one
ends the process (INV-24, §6). Both rules apply to both variables.

**The token is not a model key** — `page.py`'s signature is
`render(model, token)`, so the model stays exactly what §7's fixtures are built
to. LOTTO-0014 §4.3 owns that rule and the reason for it.

`page.py` emits the page's inline JavaScript along with its markup. It has
exactly four jobs and no others: the two POSTs (which must carry a custom
header, LOTTO-0014 §4.3), filtering the ticket table (which must not touch the
URL, LOTTO-0014 INV-21), and **polling `GET /status` every 2 s while `building`
is true, or after a `POST /refresh`, reloading when `built` changes**. **The poll also
terminates on failure**: a refresh that raises leaves `built` unchanged and
`building` false, so a poll watching only `built` waits for a change that never
comes and the user is never told the fetch failed. When the poll sees
`building: false` with `built` unchanged and `stale: true`, it stops and shows
the stale notice INV-18 requires the page to carry. Without the fourth job the
opening *building* page never leaves that state. (The route has a second
consumer since LOTTO-0018: the tray waits on `building`, then reads `stale`,
for the same reason the poll above does not watch `built` alone —
LOTTO-0013 §4.6.) It is inline rather than a served asset
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
    def get(self):        ...  # -> (model|None, building, built, stale, error)
    def begin(self):      ...  # -> False if a build is already running (no concurrent builds)
    def finish(self, model):   # success: swap in, built=now, stale=False, building=False
    def fail(self, exc, pools=()):  # model UNTOUCHED; stale=True, building=False,
                               # error={"what": str(exc), "pools": [...]}
    def wait_idle(self, timeout): ...  # block until not building; -> False on timeout


def refresh(state, build_model_fn):
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
            state.finish(build_model_fn())  # atomic swap; readers never see a half-built model
        except Exception as exc:
            state.fail(exc)               # keep the last good model, flag it stale
    threading.Thread(target=work, daemon=True).start()
```

**`wait_idle()` exists for the tests, and they do not work without it.**
`refresh()` starts a daemon thread and returns at once, so INV-17's "all three
memos are empty afterwards" and INV-18's "`stale: true`" are both races against
a build that may not have started, let alone finished. Every case that refreshes
calls `refresh()`, then blocks on `wait_idle(5)` **before asserting**, and fails
on a timeout rather than proceeding. Otherwise the suite passes or
fails for reasons unconnected to the contract, which is worse than having no
case. (Calling `wait_idle()` *before* the refresh is a no-op — nothing is
building yet — and that is the reading which reinstates the race.)

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

**Bind the port before the first build, not after** — the pattern the user's
own `Ants_Projects_Hub_Website/serve.mjs` already uses ("Listen before
refreshing, not after"), read on 2026-08-02. It is JavaScript in a Python
project, so it is a shape rather than code to reuse; the ROADMAP bullet records
the same relationship for the tray. The server
starts answering immediately and serves a *building* page for the first
thirty-odd seconds, rather than leaving the browser to time out on a port
nothing is listening to yet. That opening build goes through the same
`refresh()` above, so it has one code path, one lock and one failure mode.

**Which makes the bind and the build two different functions' work, and that
division is part of the contract rather than an implementation detail.**
`make_server(build_model_fn, token, port)` creates the `State`, binds the
socket and returns `(server, state)`. It does **not** build. The opening
`refresh(state, build_model)` belongs to `main()`, between the bind and
`serve_forever()`, which is what "bind before the first build" means in code.
Two things follow, and the second is the one that is easy to read past:
a server that has been constructed but not run through `main()` holds no model
and is in the **no-build** state — `model is None`, `building` false, no error,
so the render carries `no_build: True` and the page says *no build was
performed* (§6). It is emphatically **not** the *building* state, and the
distinction is not academic: a page told it is building polls `/status` waiting
for a build that was never started. That no-build state is exactly what
`LOTTO_NO_BUILD` (§4.1's table, §6's third empty-page reason) produces on
purpose. And **anything driving `make_server()` directly must perform its own
first build**, because there is no opening `refresh()` to wait for. §7 carries
that as a constraint on the cases, since the cases are what drive it directly.

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
2. **Still outstanding** — two groups under one heading, because both are
   "not finished", and neither is a loss. The heading is deliberately not "Live
   tickets": a 2019 ticket has no draws still to come, and filing 974 unscorable
   entries under a heading that asserts they do would be the cardinal error
   wearing the section title. The two groups are **draws still to come**, showing
   draws remaining, and **not checkable**, showing why. Two tickets have
   **draws still to come** today — the unit here is the ticket, not the entry, because a
   ticket is what has draws left to run; the unscorable entries below are also
   listed here and are not counted by this figure:

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
entry_cost_cents = tier_increments(game, era)[plus_flag] * paid_lines * ndraws
```

**`paid_lines` is `len(Ticket.boards)`.** There is no `paid_lines` attribute —
`tickets.py::entered_pools()` takes it as a parameter and `parse()` passes
`len(boards)`, under the comment *"Multiplay is already expanded above, so one
board here is one paid line"*. So the expansion has already happened by the
time anything here sees a ticket, and `len(t.boards)` is the count that was
charged for, including each Multiplay combination. Stating it matters because
the two readings differ **only** on Multiplay tickets, which is the one place
the error would not show up in a spot check.

`tier_increments(game, era)` lives in **`serve.py`**, module level, called by
`build_model()` — the only module that computes, per §4.1 — and its result
writes `cost_cents` onto each entry.
It is **plural and takes two arguments**, returning the whole `{plus_flag:
increment}` mapping for that game and era; the per-entry value is the
`[plus_flag]` lookup on it, which is why the formula above indexes rather than
passing a third argument.

**The builder also computes `spend.compared_cents` and `won.compared_cents`, and
`page.py` renders those two verbatim rather than summing anything.** This is the
one place the document insists on a single source, because both plausible
renderer-side sums are wrong: `entries[].cost_cents` carries no `resolved` flag
(only `tickets[]` does) and no `scorable` filter is implied by summing it, so a
renderer adding that column up produces exactly INV-16's failure. `cost_cents`
on an entry is a per-row display value and nothing else.

**Both sides of the comparison are scoped the same way**, which is what makes it
a comparison at all: spend over the scorable entries of resolved tickets, and
winnings over the wins on those same entries. `won.lifetime_cents` is *not* that
figure — `tickets.py::parse()` gives an unresolved ticket a fallback single tier
so `check.py::check()` scores it like any other, and its wins land in the
lifetime total while its cost is excluded from the spend side. Comparing the two
would put an unearned surplus on the page for the same reason comparing lifetime
spend would put a false loss on it.

`tier_increments()` reads the **increment** column of `tickets.py::TIER_PRICES`
— a different column from the cumulative total `entered_pools()` matches on,
and conflating them prices a R10.00 Lotto ticket at R22.50. It is written at
this call site, as LOTTO-0009 §4.7 says it should be.

**The comparison is drawn over the checkable entries of resolved tickets only** —
both conditions, and the snippet below carries both because it is the only
executable statement of the figure an implementer will copy. `and t.resolved`
changes nothing today (`unresolved tickets 0`, measured in the same run), which
is exactly why it has to be written down rather than left to the numbers: the
day one price fails to resolve, a snippet missing that clause keeps agreeing
with itself and stops agreeing with `serve.py`.

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
        if scorable(t, pf) and t.resolved:
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
| Winnings on those entries (`won.compared_cents`) | R2,651.60 | the comparison |
| Winnings lifetime and still unexpired | R2,651.60 lifetime, R2,418.90 unexpired | separate, labelled lines — **not** the comparison (below) |
| Lifetime spend, all 1,233 entries | R28,244.50 | a separate, labelled line |

**The identity holds only where the price resolved, and the display must say so.**
LOTTO-0009 §4.7 states it with that condition — *"the entry costs sum back to
it, and only when the price resolves"* — and the condition is load-bearing:
`tickets.py::parse()` falls back to `pools = [(plus_flag, pool_id)]`, a single
name-derived tier, when `entered_pools()` comes back unresolved, and that one
tier's increment cannot sum to what the SMS charged. So:

- **Lifetime spend is the sum of the per-entry costs over all 1,233 entries**,
  not `Σ round(Ticket.cost * 100)` over tickets. The two are the same number
  exactly when every price resolves — which is the case today, `unresolved
  tickets 0` above — and they part company on the one ticket whose price does
  not, because a name-derived single tier cannot sum back to what the SMS
  charged. The entry sum is what the builder computes and what the table row
  above labels, and it is the honest one to display beside a comparison that is
  also drawn over entries. **The gap does not go unreported**: an unresolved
  ticket's full `Ticket.cost` is carried on its own line (below), so the reader
  is told what the lifetime figure could not apportion rather than left with two
  totals that quietly differ.
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

**Turning autostart off deletes the file**, and a file that was already gone is
success, not an error — `os.remove()` under `except FileNotFoundError`, this
project being `os`-based rather than `pathlib`-based throughout; it does
not rewrite `X-GNOME-Autostart-enabled` to `false`. That key is present in the
template below and is exactly what invites the wrong implementation — but a file
that exists with the key flipped breaks the "presence *is* the state" rule this
setting is built on, and leaves two places that can disagree. A failed unlink
returns 500, like a failed write. **That 500 carries no body** — LOTTO-0014
§4.1's header table gives it `Content-Length: 0` — so the reason reaches the
user by the switch snapping back to its true state on the re-read, not by text
in the response.

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

`open_on_start` defaults to **true**, and it has **three** readers: `tray.py`
at startup (LOTTO-0013 §4.3 owns what the tray *does* with it), the model
builder on every build (§4.1's `settings` key), and `POST /settings` when it
re-reads after writing.
**The same fallback binds all three: a missing, unreadable or malformed
`settings.json` yields the default rather than raising.** Stating it once, here,
matters because each reader fails differently if left to decide for itself — the
tray never appears, the build dies, or a toggle 500s — and all three would be
caused by one corrupt file that should simply have been ignored. This document
owns the file: its path, its key, that default and that fallback. Writing the file creates its directory idempotently —
`os.makedirs(dirname, exist_ok=True)` — and `exist_ok` is the load-bearing half:
without it the *second* enable raises `FileExistsError`, which is the **normal**
case, and would surface as §6's 500 on every toggle after the first.

**Accessible switch markup.** The switch is a styled
`<input type="checkbox" role="switch">`, not a `<div>` with a click handler:
`role="switch"` is the ARIA pattern for a two-state toggle, and building it on
a real checkbox keeps keyboard focus, Space to toggle, and the state a screen
reader announces. The visual is CSS; the semantics are the native control.

### 4.8 What starts and stops it — LOTTO-0013

The tray, `supervise.py`, the spawn-and-reap lifecycle and the headless
contract are LOTTO-0013. Two of its rules bear directly on this document's
files and are stated there rather than here: `serve.py` resolves its port once
(§4.1) and uses that same value both to bind and to build §4.4's `Host` allowlist
(LOTTO-0013 §4.5), and everything in `serve.py` that binds, builds or serves
sits behind `if __name__ == "__main__":` (LOTTO-0013 §4.4, which is what makes
its INV-19 observable).

## 5. Invariants

This document holds **INV-15 to INV-18** — the honesty rules on the data the
page renders — and **INV-24**, which is an honesty rule about the port the
process binds rather than about the data, and lives here because §4.1's
environment table and §6's failure mode are both this document's. LOTTO-0001
holds INV-1 to INV-6, LOTTO-0009 INV-7 to INV-11,
LOTTO-0014 INV-12 to INV-14 and INV-21, and LOTTO-0013 INV-19, INV-20, INV-23
and INV-25. No
number moved in either 2026-08-02 split — CHANGELOG.md and sibling specs cite
them unqualified.

- **INV-15** — An entry nothing can score renders as "not checkable" with its
  reason, and never as a blank, a dash, a zero, or an omission; a ticket
  checkable in one pool and not another shows both facts.
  *Test:* `tools/verify_page.py`, case `uncheckable_not_a_loss` — renders a
  fixture of **two** synthetic tickets — built by running the *real* builder
  over them under a doubled `all_draws` (§7), not by handing a finished model to
  the renderer: one two-pool ticket with one pool scorable and one not (*partly*
  uncheckable), and one whose every pool is unscorable (*wholly* uncheckable).
  **Both are needed, and the second is the one that matters most.** With only
  the partly-uncheckable ticket, a renderer that iterates tickets which produced
  at least one scorable entry — and then appends their remaining pools — passes
  the case while silently dropping every wholly uncheckable ticket. That is 426
  tickets against 11 (§4.5), and it is precisely the failure this invariant's
  *Breaks when* names. A fixture that cannot see the bug its own clause
  describes is testing something else.
  The case asserts, for **both** tickets: every unscorable pool's row is
  present, its reason string is rendered, and the text of its amount cell is
  **not** in `{"", "-", "–", "—", "0", "0.00", "R0.00", "R0", "0,00", "R 0.00",
  "n/a", "N/A"}`. It also asserts the *scorable* pool's row of the partly
  uncheckable ticket is present with a real amount — otherwise the invariant's
  second clause, that a ticket checkable in one pool and not another shows
  **both** facts, has no assertion at all and a renderer dropping the checkable
  half passes.
  Naming the forbidden strings is the assertion; "no zero-amount cell" is not
  observable, and a blank or a dash is the likelier rendering than a literal
  zero.
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
  asserts the rendered compared-spend figure **equals** a recomputation the case
  performs itself from `tickets.py::TIER_PRICES` — `Σ increment × len(boards) ×
  ndraws` over the scorable entries of resolved tickets — **never by calling
  `serve.py`'s `tier_increments()`**, which is the code under test and would make
  the case agree with whatever the builder did (§7's third constraint), and that the rendered lifetime figure is a different, larger
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
  `check._struct`, runs a refresh with a stub builder that **records whether all
  three were empty at the moment it was called**, and asserts on that recording —
  plus that the builder was called exactly once.
  **Asserting they are empty *afterwards* does not test this invariant.** The
  contract is that the memos are cleared *before* the rebuild; an implementation
  that builds first and clears second satisfies "empty afterwards" perfectly
  while doing exactly what the invariant forbids — redrawing from the previous
  run's division tables, which §4.2 calls wrong money rather than stale money.
  The stub builder is the only thing that can observe the ordering, because it is
  the only code that runs at the moment in between.
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
  original wins still render, that the page itself says the figures are from an
  **earlier fetch** — the "and says so" half of the invariant, which `stale` in
  a JSON route does not deliver to the person reading the page — that
  `GET /status` reports `stale: true`, and that `built` is unchanged from before
  the failed attempt.
  *Breaks when:* the model is cleared before the rebuild, or an exception on
  the background thread leaves `state` empty. The operator's API failed with
  `URLError(SSL: UNEXPECTED_EOF_WHILE_READING)` on **four of the seven** build
  attempts made while measuring this spec (2026-08-02), so this is a routine
  path rather than a rare one, and it is the reason §6 treats a degraded page
  as a normal state instead of an error.

- **INV-24** — The bound port is `$PORT`, else `$LOTTO_PORT`, else 4322; a value
  that is set and cannot be a port ends the process with a message naming it,
  and never falls back to another port.
  *Test:* `tools/verify_page.py`, case `port_from_environment` — two halves,
  because the invariant makes two different kinds of claim. `resolve_port()` is
  called with **explicit environment dicts** for the resolution half: neither
  variable, both empty, each alone, both together (`$PORT` wins), and an empty
  `$PORT` beside a set `$LOTTO_PORT`. Explicit dicts rather than `os.environ`,
  or the case passes or fails according to how the developer's shell happens to
  be set. Then eight rejected values — `abc`, `80`, `0`, `65536`, `-1`,
  `4322.0` on `$PORT`, and `abc` and `80` on `$LOTTO_PORT` — each of which must
  raise `SystemExit` **with the rejected value in the message**; a resolution to
  any number is the failure, and the message assertion is what distinguishes
  this from a bare crash. `$LOTTO_PORT` is in that list because the unhandled
  `ValueError` this invariant replaces was on *its* path, and fixing only the
  new variable would leave the traceback exactly where it was.
  The second half spawns two real children, because resolving a number and
  binding it are different claims and only the process can settle the second: a
  `python3 serve.py` with `$PORT` set must answer on that port, and a
  `Supervisor` started while the session exports a *different* `$PORT` must
  still land its child on the port the tray is watching (LOTTO-0013 §4.5's 421).
  Both run under `LOTTO_NO_BUILD`, like `no_orphan_server` and for the same
  reasons (§7).
  *Breaks when:* a bad value warns and serves 4322 anyway — `--break
  port_silent_fallback`, which is the failure this invariant exists for, since a
  manager that asked for port 80 and silently got 4322 has been told nothing —
  or the precedence is the other way round (`--break lotto_port_wins`), which is
  indistinguishable from correct on every machine where only one of the two is
  ever set.

## 6. Failure modes

- **The operator's API is unreachable.** Four of seven build attempts on
  2026-08-02 failed with `SSL: UNEXPECTED_EOF_WHILE_READING` — this is the
  common failure, not an edge case. **The whole build fails; there is no
  archive-only mode, and this document does not promise one.** An earlier draft
  said the page would serve from `archive_results.json` alone, which nothing in
  scope can deliver: `check.py::paying_combinations()` *raises* when the live
  feed yields no recent draw — deliberately, so an empty division table cannot
  score a pool as losses — and `history.py::all_draws()` reaches the API for
  every pool regardless of what the archive holds. Building an archive-only
  degraded mode means changing how tickets are scored, which §9 puts out of
  scope, and LOTTO-0012 (bounded retry in `results.py`) is the item that reduces
  how often this happens.
  - **On refresh:** INV-18 — the previous model keeps serving and is flagged
    stale.
  - **On the *first* build, there is no previous model to keep.** The page
    renders a **"results unavailable"** state naming the error and the pools it
    could not reach. It says explicitly that no ticket could be checked, and it
    does **not** render a ticket table, a zero total, or an empty wins list —
    all three read as "you have won nothing", which is this project's cardinal
    failure arriving through the network layer.
- **Port 4322 is in use.** `serve.py` exits with the port in the message rather
  than tracebacking. `LOTTO_PORT` overrides it; LOTTO-0013 §4.5 owns that
  variable and how the tray surfaces the failure. (4322 chosen as free on this
  machine and adjacent to the user's stats dashboard on 4321 — `ss -ltn`,
  2026-08-02.)
- **The server stops while a page is open and polling.** The tray's Stop, a
  Quit, a crash, or a logout all leave a tab whose `GET /status` now fails. The
  poll must treat a failed request as *stop polling and say the connection was
  lost*, not as "still building": a page that keeps showing the building notice
  is asserting that work is in progress on a server that no longer exists, which
  is a false statement about missing data — the cardinal rule arriving through
  the one part of this page that keeps running after the process behind it has
  gone. The notice is browser-side, so nothing mechanical checks it (§11).
- **`PORT` or `LOTTO_PORT` is set to something that is not a port**, on the
  standalone `python3 serve.py` path. This is the one launch path LOTTO-0013
  §4.5's fallback does **not** cover — that fallback lives in `Supervisor`, and
  nothing constructs one here — so `serve.py` resolves the port itself and a
  non-numeric or out-of-range value **exits non-zero before the bind, naming the
  variable and the value it rejected** (INV-24). Ending the process is the
  answer, not falling back: silently serving on 4322 puts the page somewhere
  nobody is looking, and the caller — a user one command ago, or a process
  manager that asked for a specific port — is told nothing. It is not a
  traceback either, which was what this path did until LOTTO-0024: an unhandled
  `ValueError` names the variable only by accident of the stack, and reads as a
  crash rather than as a rejected setting. Under the tray, where there is no
  terminal to read either one in, §4.5's fallback is what runs instead.
- **`lotto_sms_raw.txt` is absent.** The page renders its empty state and says
  the dump is missing and how to produce it — never "0 tickets, R0.00", which
  reads as "you have never won".
- **`LOTTO_NO_BUILD` is set** (§4.1 — it exists for LOTTO-0013's INV-20 case
  and LOTTO-0014's INV-13 child, never for users). The page renders the empty
  state with an explicit *"no build was performed"* notice. It is not an
  exception to INV-18: nothing was ever built, so there is no previous model to
  lose.

**There are exactly three states in which the page shows no ticket data, and
each is correct only because it says why**: the dump is missing, the first build
failed, or `LOTTO_NO_BUILD` was set. That is one rule rather than three
exceptions — **an empty page is correct only when it carries a notice naming the
reason**, and the reason is never "you have no wins". A page rendering zero
tickets, a zero total or an empty wins list without that notice is the cardinal
failure, whatever produced it.
- **`~/.config/autostart/` does not exist.** §4.7 states the rule; a write
  failure returns 500 — bodiless, per LOTTO-0014 §4.1 — and leaves the switch
  showing its true state, not the requested one.
- **A prize expires while the page is open.** Expiry is computed against
  `datetime.date.today()` at model-build time — day granularity, which is what
  makes "anything expiring today" coherent — so an open page can show a prize that
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
as with the other four. **One script covers all three parts of the split**:
thirteen cases, one per invariant, of which this document owns the five below,
LOTTO-0014 §7 owns `host_allowlist`, `token_required`, `no_reflected_headers`
and `nothing_in_the_url`, and LOTTO-0013 §7 owns `serve_is_headless`,
`no_orphan_server`, `refresh_reports_the_build` and
`tray_headless_when_managed`. One script rather than three because the cases
share their fixtures, their temporary-directory setup and their stub builder.

| Case | Locks |
|---|---|
| `uncheckable_not_a_loss` | INV-15 |
| `spend_over_checkable` | INV-16 |
| `refresh_refetches` | INV-17 |
| `failed_refresh_keeps_model` | INV-18 |
| `port_from_environment` | INV-24 |

Three constraints on the script, each following from something in the existing
suite, and all three binding on all thirteen cases, LOTTO-0013's and LOTTO-0014's included:

- **It must not need the network.** The seam is the **builder**, not the model:
  `make_server(build_model_fn, token, port)` takes a callable. Handing it a
  finished model would leave `POST /refresh` with nothing to invoke, so INV-17
  (count requests across two rebuilds) and INV-18 (make a rebuild raise) would
  have no rebuild to exercise — two of the thirteen cases untestable by
  construction. A stub builder gives each case what it needs: one that counts
  its calls, one that raises, one that returns a fixture.
  **`make_server()` binds but does not build (§4.2), so a case that needs a
  populated model builds one itself** — `refresh()` followed by `wait_idle()`,
  before the first assertion. Two cases need it and neither can be written
  without it: `failed_refresh_keeps_model`, whose subject is the *previous*
  model surviving a failure and which therefore has to have a previous model,
  and `nothing_in_the_url`, which needs a rendered page to find ticket data
  absent from. Read the seam the other way — as though constructing the server
  built the model — and both cases still run, still pass, and assert against
  the empty *no-build* page (§4.2) instead of the thing the invariant is about.
  **`uncheckable_not_a_loss` is the exception, and deliberately so** — it runs
  the *real* builder under a doubled `all_draws`, because its whole subject is a
  derivation the builder performs (§4.5's `reason`), and a stub returning a
  finished fixture would assert only that the fixture was rendered. It still
  costs no network: the double is exactly what `all_draws` would have gone to
  the network for. No case issues an outbound request, so a whole run costs well
  under a second against the 27 requests a real build makes. (`urllib` is not
  untouched — every case that drives a real socket speaks HTTP to it, and
  LOTTO-0013's `is_ready()` and `post()` use it too. The rule is that nothing
  leaves the loopback interface, not that the module is unimported.)

  **INV-15 needs a second seam**, because its fixture requires `scorable()` to
  differ between two pools of one ticket — a property of `history.all_draws()`,
  not of the model. Its case injects `all_draws` with a double returning draws
  for one pool and `[]` for the other, which is the `daily/0` vs `daily/1`
  shape that makes 11 real tickets partly uncheckable.
  **That double is swapped for a raising one before `render()` is called**, and
  the swap lives in one place — the `render_pure()` helper every case that
  renders `page.py` **directly** goes through — which is what makes §11's
  "`page.py` performs no I/O" row true. Scope it honestly: cases that render by
  driving the real server over HTTP (`failed_refresh_keeps_model`,
  `nothing_in_the_url`) call `render()` inside the server process, where no
  double is installed, so the guarantee those cases give is about the *response*
  and not about `page.py`'s purity. The two doubles are not interchangeable and
  the swap point matters: a raising double during the build kills every case,
  and a returning one during the render lets a renderer that calls
  `all_draws()` pass unnoticed.
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

**Each case is observed failing before the invariant is accepted, and the
breakage is a flag rather than a hand edit.** LOTTO-0009 §7's practice was to
red-test against pre-fix code; there is no pre-fix code here, because this is
greenfield. The equivalent is to break the rule deliberately — clear the model
before a rebuild, return the lifetime total from the comparison, render an
unscorable amount as a dash — confirm the named case fails, then restore.

**`tools/verify_page.py --break <name>` is that mechanism, and it is part of the
contract rather than a debugging aid.** Each break applies exactly one
deliberate defect and asserts the named case goes **red**; `--list` prints the
cases and the available breaks. A hand edit proves the same thing once, for the
person who made it; a named break proves it on every run, which is what "every
case was observed failing" has to mean on greenfield code where no case can be
red-tested against its own history. It has already earned this: one break turned
up a defect in a *case* rather than in the code — an em-dash for an unscorable
amount did not turn INV-15 red, because the assertion compared raw markup and
excluded the empty string from its own forbidden set. Adding a case means adding
its break in the same change; a case with no break is a case nobody has seen
fail. A case never seen failing is a case
that proves nothing, and on a greenfield spec that is the *only* way to know it
can fail at all.

## 8. Alternatives considered (and rejected)

- **A generated static HTML file.** Rejected by the user 2026-08-01. It cannot
  offer a Refresh button or a settings toggle without a server behind it, and a
  file on disk holding every ticket is a second copy of the data
  `tools/verify_privacy.py` exists to keep out of the repository.
- **Settings in the tray menu instead of the page.** Rejected 2026-08-02. It
  would have kept the HTTP surface read-only and removed the write token
  entirely (LOTTO-0014 §4.3, which now owns it — §4.4 here is a pointer stub);
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
| INV-24 the port comes from `$PORT`, then `$LOTTO_PORT`, then 4322, and a bad value exits | `tools/verify_page.py::port_from_environment` |
| §4.1 `page.py` performing no I/O | `tools/verify_page.py` — **two** doubles for `all_draws`, swapped between phases: a *returning* one while the builder runs (INV-15 needs draws for one pool and `[]` for the other), then a *raising* one installed before `render()` is called. Only the second proves the renderer performs no I/O, and it must not be in place during the build or every case dies there. Absent the raising double the row would be false: with no `archive_results.json`, `history.all_draws()` falls straight through to `api_draws()`, which **succeeds** on a connected machine, so a renderer calling it would pass |
| §4.1 `settings` in the model, so both switches render their real state | **nothing** — a switch rendered in the wrong state looks identical to one rendered right until the user toggles it; no case reads the panel's initial state |
| §6 the first-build failure rendering "results unavailable" rather than an empty page | **nothing** — reproducing it needs the operator's API to be down, which the suite cannot arrange and must not depend on |
| §4.7 autostart-off deleting the file rather than rewriting a key | **nothing** — LOTTO-0014's cases assert the file's *bytes* and its presence after a write, not its absence after a toggle-off; a server that rewrote the key to `false` would pass every one of them |
| §4.1 the model's key set | **nothing** — a builder and a renderer that agree on a wrong shape are consistent with each other, and every fixture is written to the same shape |
| §4.1 the page's `GET /status` poll — its cadence, its two exit conditions, and that it stops rather than spinning | **nothing** — it is browser-side JavaScript; `failed_refresh_keeps_model` asserts the rendered HTML and the `/status` JSON, neither of which exercises the poll that reads them |
| §4.2 the 27-request figure staying true | **nothing** — a dated measurement; a larger dump or an API paging change moves it without failing anything |
| §4.5 the page being *readable* — ordering, filters, marking near-expiry | **nothing** — no check can tell a clear layout from a cluttered one |
| §4.7 the written `.desktop` file actually autostarting on this desktop | **nothing mechanical** — it depends on the session's XDG implementation; verified by logging out once |

Fourteen rows, eight `nothing`.

The parent's table held twenty-two rows and six `nothing`. The three parts now
hold **53 rows and 28 `nothing` between them** — counted 2026-08-03, fourteen and
eight here, eighteen and six in LOTTO-0014 §11, twenty-one and fourteen in
LOTTO-0013 §11. (The 2026-08-02 figures this paragraph carried were 44 and 23,
and its per-document breakdown disagreed with the line above it by a row; these
are counted from the tables rather than tracked by hand.)

**That the totals grew is the point, not a regression.** The partition itself
was clean; the growth is rules the parent never tabulated at all — Qt and
desktop-session behaviours, the check order, the write lock, the settings state
— surfaced by three cold reads at a size a cold read can actually hold. A
`nothing` row is an honest gap recorded, not a gap created, and this process's
error budget is the number of them a reader can see.

## 12. Cross-doc impact

- `docs/specs/LOTTO-0013-tray-and-supervisor.md` — the other half of this split;
  it holds §4.8's subject, INV-19 and INV-20. Written 2026-08-02.
- `README.md` — a new section for the page: how to start it, the optional
  autostart switch, and the port. Shared with LOTTO-0013, which writes the tray
  half of the same section and adds PySide6 as a tray-only requirement to the
  "Needs Python 3.8+ and a Linux desktop" line.
- `CLAUDE.md` — **done 2026-08-02**: the Commands block carries `python3
  serve.py`, the verification list carries `tools/verify_page.py`, and the
  architecture diagram carries the second consumer of `check.py` (and, since the
  fold-back, the `serve.py → supervise.py` settings edge).
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

**Added by the LOTTO-0024 amendment (2026-08-03), which introduced INV-24:**

- `docs/specs/LOTTO-0013-tray-and-supervisor.md` — its §4.2 pins both port
  variables in the child and its §4.5 states the `$PORT` precedence that made
  that necessary; its new §4.7 and INV-25 own the managed run. That document's
  §12 holds the rest of this amendment's impact.
- `docs/specs/LOTTO-0014-http-surface-and-security.md` — **count-only**. Two
  citations of the shared script's case count; the `Host` allowlist still comes
  from whatever port `serve.py` bound, and that sentence needed no change
  because §4.1 kept the port a single resolved value.
- `CHANGELOG.md` — `Added` and `Fixed` entries citing LOTTO-0024.
- `ROADMAP.md` — LOTTO-0024's bullet.
- `CLAUDE.md` — **done 2026-08-03**: the port precedence, `LWSM_MANAGED`, the
  verifier's invariant range and break count, and PySide6 as a `verify_page.py`
  requirement.

**The split this section recommended was taken on 2026-08-02**, by the user —
and then taken a second time, because the first cut did not do enough.

| Part | Sections | Invariants |
|---|---|---|
| this document — the model, the build lifecycle, what the page shows | §4.1, §4.2, §4.5–§4.7 | INV-15 – INV-18 |
| LOTTO-0014 — the HTTP surface and the security boundary | its §4.1–§4.4 | INV-12 – INV-14, INV-21 |
| LOTTO-0013 — the tray, the supervisor, the headless contract | its §4.1–§4.5 | INV-19, INV-20 |

(That table records the split **as taken on 2026-08-02** and is not maintained
as an ownership index — three invariants have been added since, INV-23 and
INV-25 to LOTTO-0013 and INV-24 here. Each document's §5 is the authority on
what it holds.)

**Why twice.** The seam this section originally proposed was the one the
invariants fell along, and it moved only 66 of the parent's 1,161 lines — the
tray was never the weight. Measured after the first cut: §4 Design held 31,533
of the remaining 73,087 bytes (43%), §5 a further 11,673, and §13's historical
loop log 10,917 (15%). The second cut is along **subject** rather than
invariant count — web-security rules on one side, lottery-data honesty rules on
the other, which need different expertise to review — and the loop log was
archived to `LOTTO-0002-pre-split-review-log.md`. Together those took this
document well below the size at which the parent capped out.

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
| 4 | 2026-08-02 | 2 | 0 | 4 | 6 | 9 | Second re-gate loop. All 19 verified findings fixed; **2 dismissed on evidence**, 0 deferred. **No CRITICAL, down from one.** Origin split: roughly 5 fix collateral against 14 draft defects — the healthy direction, and the reason this loop was worth running. Dismissed: two "`§13` does not exist" findings, an artefact of the orchestrator's scrubbed review copy dropping the section number from the heading it withholds; the document numbers it §13 and always has. **The most valuable finding is one no reviewer of this document had made in four loops: §4.6's worked snippet — the only executable statement of the compared figure — filtered on `scorable()` and omitted `t.resolved`,** the clause INV-16 exists to protect and which `serve.py` applies. It reproduces R10,603.50 either way *today*, because `unresolved tickets 0`, so nothing about the number could reveal it; the day one price fails to resolve, the snippet an implementer copied keeps agreeing with itself and stops agreeing with the code. Re-run with the clause: identical figures, now for the right reason. **Its neighbour was the same shape:** the summary table labelled the *lifetime* win total as "the comparison" while §4.6's prose two paragraphs down says `won.lifetime_cents` is explicitly not that figure — split into two rows. **One HIGH was loop 3's collateral:** "`State` owns the five above" followed loop 3's addition of `no_build`, which `State` does not own — `serve.py` derives it at render time from the absence of the other three, and an implementer adding a `no_build` attribute to `State` collapses the three empty states at the seam this section calls the one every fixture is built to. Also fixed: the `uncheckable` sub-dict was the one part of the model shape left as an ellipsis, while §4.5's banner needs four of its keys and §11 records the key set as checked by nothing — now enumerated; `reason` was said to be `None` exactly for scorable entries without stating why that biconditional holds (`history.py::scorable()` rejects on exactly the two grounds §4.5 derives `reason` from, so a third ground added there silently renders "not checkable" with nothing after it — half of INV-15); §6 had no failure mode for the server stopping while a page polls `/status`, which leaves a tab asserting a build is in progress on a process that no longer exists; §7 described red-testing as a hand edit when the shipped mechanism is `--break <name>`, undocumented in any spec despite CLAUDE.md carrying it, and §11 gained the row for the browser-side poll that nothing checks — thirteen rows and eight `nothing`. Smaller: a 100× unit warning cited §4.6, whose warning is a different ~2.25× one; "two scorable tickets" where the snippet counts tickets with draws still to come; `datetime.now()` where the builder uses `date.today()`; and §12's CLAUDE.md row left in the future tense after the edit had landed. Doc grew 1,148 -> 1,201 lines. |
| 3 | 2026-08-02 | 2 | 1 | 4 | 4 | 6 | Re-gate of the `2-impl` amendment, and the third cold read the `3-skipped` row below deferred rather than declined. All 15 verified findings fixed; 0 unverified, 0 deferred. **Both lanes led on the same CRITICAL and it was this session's own collateral:** §4.1 said "nothing in this document's two files imports anything in that one's three", which the settings-reader move made false — `serve.py` imports `supervise.py`, deliberately, and LOTTO-0013 §4.1 requires it. Left standing, the sentence tells an implementer to re-implement the reader inside `serve.py`: the duplicate that shipped in `45e3fc3` and was deleted the same day. Now stated as a one-way edge *toward* LOTTO-0013's files, with the reason pointed at rather than copied. **A second finding was also mine:** the `2-impl` paragraph called a constructed-but-unrun server "building" and said `LOTTO_NO_BUILD` leaves it there. It does not — `model is None` with no error and no build in flight sets `no_build`, and §6 requires a *no build was performed* notice; a page told it is building polls `/status` forever for a build nobody started. Two states one word apart, on the rule this project calls cardinal. **The remaining HIGHs are draft defects the two prior loops walked past, all on the model seam §4.1 calls "the seam every §7 fixture is built to".** Three keys reach `page.py` that the shape block never listed — `building`, `no_build`, and `build_model()`'s entirely separate `{"no_dump": True, "settings": …}` return — and two of the three are the carriers of §6's "an empty page is correct only when it names why". Lifetime spend was defined twice in one section, as `Σ Ticket.cost` in a bullet and as the entry sum in the table two paragraphs above; the builder computes the entry sum, they diverge on any ticket whose price does not resolve, and this is a money figure on a page. And `State.fail(exc, pools)` had no producer for `pools` while §6 promised a failure "naming the pools it could not reach" — resolved by stating what the code honestly does: `pools` is optional, today's caller cannot attribute the failure, and `page.py` renders the empty case as "all pools" rather than as a blank. Also fixed: `tier_increment(game, era, plus_flag)` named at three sites including INV-16's test clause, where the function is `tier_increments(game, era)` returning a dict; §4.7 citing `pathlib` spellings against `os`-based code; no failure mode for a malformed `LOTTO_PORT` on the standalone path, which is the one launch path LOTTO-0013 §4.5's fallback does not cover; §7 and §11 claiming the raising `all_draws` double is installed "in every case" when it lives in `render_pure()` and the two socket-driven cases never see it; the environment table crediting `serve.py` as `LOTTO_PORT`'s only reader; `refresh(state, build_model)` where the parameter is `build_model_fn`; INV-18's clause omitting the "and says so" assertion its case actually makes; and unscorable / uncheckable / not-checkable used for one state at three altitudes, now glossed rather than merged — collapsing them would lose the entry-versus-ticket distinction INV-11 rests on. §11 unchanged at twelve rows and seven `nothing`. Doc grew 1,063 -> 1,148 lines. |
| 2-impl | 2026-08-02 | — | — | — | — | — | **Implementation row — no reviewer was dispatched, and this is not a review loop.** Origin is building the thing (commit `45e3fc3`), which is the reader the `3-skipped` row below said it was deferring to; this is that mechanism firing rather than a fourth opinion. **Nothing in this document said which function builds the model.** §4.2 required the bind to precede the first build and left the division of labour implicit, so an implementer could read `make_server()` as producing a ready server. It does not: it creates the `State`, binds and returns `(server, state)`, and the opening `refresh()` is `main()`'s. **Two of `tools/verify_page.py`'s cases were written to the other reading and had to run an explicit first refresh** — `failed_refresh_keeps_model`, which needs a previous model for the failure to preserve, and `nothing_in_the_url`, which needs a rendered page to find ticket data absent from. **The reason this is a contract amendment and not a note is that the wrong reading is silent**: both cases still run and still pass, asserting against the empty *building* state instead of against the thing their invariants are about — a case passing for a reason unconnected to what it locks, which is the `3-skipped` row's predicted "a fixture weaker than the one that ships", arriving exactly where it predicted. §4.2 now states the division and both of its consequences, including that `LOTTO_NO_BUILD` leaves a server in that same legitimate no-model state. **§7 carries the case-facing half inside its existing builder-seam constraint rather than as a fourth one**, deliberately: LOTTO-0014 §7 cites "the three constraints that bind all ten cases" by count, and a fourth bullet here would falsify a sibling document's sentence to say something the first bullet already owns. No invariant moved, no case was renumbered, and no shipped behaviour changed — the cases already do the right thing, and the document now says why they must. A sibling amendment landed the same day in `docs/specs/LOTTO-0013-tray-and-supervisor.md` §4.1 (the settings reader), with one real code defect fixed alongside it; that document's `3-impl` row holds the account. |
| 1-post-split | 2026-08-02 | 2 | 3 | 6 | 10 | 14 | All 33 verified findings fixed; 0 unverified, 0 deferred. First loop on the post-split bytes, and every finding was a draft defect — the split removed the collateral churn but not the document's own gaps. **Both lanes led on the same CRITICAL: §6 promised a degraded startup that nothing in scope can build.** It said the page would serve "from `archive_results.json` alone with a visible notice that live results are missing", but `check.py::paying_combinations()` *raises* when the live feed yields no recent draw — deliberately, so an empty division table cannot score a pool as losses — and `history.py::all_draws()` reaches the API for every pool regardless of what the archive holds. So the whole build fails, and §9 puts changes to scoring out of scope: the implementer would have had to either ship nothing or edit `check.py`. Replaced with the achievable behaviour, plus the case nobody had defined — **a failed FIRST build has no previous model to keep**, so INV-18's "never serves an empty or zeroed page" had no answer for the commonest failure this project sees (four of seven attempts). It now renders a named "results unavailable" state, explicitly not a zero total. **Two further CRITICALs, one per lane.** The settings panel — the feature §1 names in its first paragraph — had no state in the model at all: `page.py` is pure, there is no `GET /settings` route, so both switches would render in an arbitrary state on every load; the model gains a `settings` key. And **INV-15's fixture could not see the bug its own *Breaks when* names.** It held only a *partly* uncheckable ticket, so a renderer iterating tickets that produced at least one scorable entry, then appending their other pools, passes — while silently dropping every *wholly* uncheckable ticket. That is 426 tickets against 11, on the rule this project calls cardinal. The fixture now holds both shapes, and asserts the checkable half renders too, which the second clause of the invariant previously had no assertion for at all. **Three findings came from reading the real source rather than the document:** "Every money value in the model is an integer of cents" was false, because the win dict is spread verbatim and `check.py::amount()` returns **rands** — a 100× error waiting on a money page, now fixed by having the builder drop the key; `draws_covered` was a bare `int` while `history.py::covered()` returns `[]` for an unscorable entry, so every uncheckable row would have read "0 draws checked" — the cardinal failure moved one column left; and the winnings side of §4.6's comparison had no resolved-scoped figure, so an unresolved ticket's wins counted while its cost did not. Also fixed: turning autostart *off* was never stated as deleting the file, while the template ships `X-GNOME-Autostart-enabled=true` and actively invites rewriting the key instead — which breaks the "presence *is* the state" rule the setting is built on; a failed refresh left an open page with no way to learn it failed, since the poll watched `built` and `built` does not change on failure; §11 credited one `all_draws` double with two incompatible jobs; and the "Live tickets" heading asserted draws-still-to-come of 974 entries that by definition have none. §11 grew to twelve rows and six `nothing`. Doc grew 875 -> 980 lines. |
| 3-skipped | 2026-08-02 | — | — | — | — | — | **No reviewer was dispatched, and this is not a review loop.** The gate stopped at two post-split loops rather than the three-loop cap, on the user's decision, so the session's remaining capacity went to implementation. **What this does and does not mean:** loop 2's 36 verified findings were all fixed, so no verified finding is outstanding and nothing is deferred — what was skipped is one further cold read, not a known defect. The two loops that did run found 69 verified findings between them and the trend was falling. The document is accepted on that basis. **Implementation is the next reader**, and it catches a class no reviewer can: a signature that cannot hold its own state, a cost claim that contradicts the algorithm elsewhere in the same document, a fixture weaker than the one that ships. Anything it proves false comes back here as an amendment plus its own loop row, per the fold-back rule — that is the mechanism this stop is relying on, and it is why stopping at two is a deferral of the third read rather than a decision to do without one. |
| 2-post-split | 2026-08-02 | 2 | 6 | 8 | 9 | 13 | All 36 verified findings fixed; 0 unverified, 0 deferred. Origin split: roughly 8 fix collateral against 6 draft defects. **Both lanes led on the same CRITICAL, and loop 1 created it**: loop 1's prose established that `draws_covered` must be `None` for an unscorable entry — the cardinal rule moved one column left — and left the model literal 24 lines above it typed as a bare `int`. The literal is the artefact an implementer copies, so the document forbade a failure in prose and encoded it in the shape block. **The other CRITICALs were the same shape.** Loop 1 added an `error` key for §6's new results-unavailable state and gave it no writer: `State.fail()` takes no arguments and `get()` returns no error, so the state §6 now promises was unbuildable. `fail(exc, pools)` now carries both. And a draft defect neither earlier pass had seen — **`model["stale"]` could never become true**, because `fail()` leaves the model *untouched* by design, which is the very thing INV-18 rests on: the object that would have to be edited is the one the failure path must not edit. The model is now explicitly two halves — the data `build_model()` returns, and the `built`/`stale`/`error` triple `State` owns and `serve.py` overlays at render time — which keeps `page.py` pure while letting a failure be visible. **One HIGH was a genuine tautology, present since the parent:** INV-17 says the memos are cleared *before* rebuilding, and its case asserted they were empty *afterwards* — which a build-first-clear-second implementation satisfies perfectly while doing exactly what the invariant forbids, pricing new draws from the previous run's division tables. The stub builder now records emptiness at the moment it is called, because it is the only code that runs in between. Also fixed: three different empty-page states each carrying a mutually exclusive "this is the only one" claim, replaced by the single rule that an empty page is correct only when it names its reason; loop 1's own addition of the builder as an `open_on_start` reader left §4.7 still saying "its only reader is `tray.py`", so a corrupt settings file had no defined behaviour on a path that runs on every build; INV-16's recomputation was to use `serve.py`'s own `tier_increment()`, which is the code under test and violates §7's third constraint; a §11 row credited a LOTTO-0014 case with asserting the autostart file's *absence* after a toggle-off, which that case does not do — now an honest `nothing`; and §4.7's 500-with-a-reason contradicted LOTTO-0014's header table, which gives a 500 no body. §11 stands at twelve rows and seven `nothing`. Doc grew 980 -> 1,035 lines. |
| 0-split | 2026-08-02 | — | — | — | — | — | **Provenance row — no reviewer was dispatched, and this is not a review loop.** The split §12 recommended was taken by the user on the seam it proposed: §4.8, INV-19 and INV-20 moved to `docs/specs/LOTTO-0013-tray-and-supervisor.md`, and this document kept §4.1–§4.7 with INV-12–18 and INV-21. Invariant numbers did not move — CHANGELOG.md and sibling specs cite them unqualified. What was rewritten rather than merely cut: §4.4's token paragraph now states only `serve.py`'s side of the channel (the `Popen`, and the argv-versus-environment reasoning, are LOTTO-0013 §4.2), §4.8 became a pointer carrying the two rules that bind this document's files, §7 records that one script serves every part, and §11 lost two named-catcher rows. **A second cut followed the same day**, once the first was measured as removing only 66 of 1,161 lines: §4.3 and §4.4 became pointers to `docs/specs/LOTTO-0014-http-surface-and-security.md`, which took INV-12, INV-13, INV-14 and INV-21 with them, and §13's three historical loop rows were archived to `LOTTO-0002-pre-split-review-log.md`. Sections were deliberately not renumbered — external citations name §4.5 and §4.7 by number. One defect was found while copying rather than by review: the parent's INV-13 clause said "four POSTs" and listed five; the successor states five. §11 now reads nine rows and four `nothing`, and the three parts' tables partition the parent's twenty-two and six without overlap. The three loops below produced 83 verified findings and **converged by cap rather than clean**, with collateral outnumbering draft defects in two of them — which is what made the split the next action instead of a fourth loop. |
