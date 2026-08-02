# LOTTO-0002 — Local web page and tray icon for tickets, results and claimable winnings

**Status:** spec draft (2026-08-02).
**Kind:** implement.
**Source:** ROADMAP LOTTO-0002 (user-request-2026-08-01; three further choices
taken with the user 2026-08-02, recorded in §3).

**Blocked by:** LOTTO-0009 (shipped 2026-08-01). **Pairs with:** LOTTO-0008
(shipped inside LOTTO-0009 — `Ticket.cost` is what §4.6 spends).

*Layman: a page in your browser showing every ticket, what it won and what is
still claimable, opened from an icon next to the clock.*

## 1. Goal

After this ships, an icon sits by the clock. Clicking it opens
`http://127.0.0.1:4322` in the browser: every ticket, what it cost, which pools
it was entered in, which of them could be checked, what it won, and — the
actionable part — when each unclaimed prize expires. A settings panel on the
page turns the tray's start-at-login on and off. `check.py` keeps working
exactly as it does; this adds a second face on the same data, and no new source
of truth.

`serve.py` runs standalone with no Qt imported, so the page can also be served
headless (systemd, SSH, a machine with no tray).

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
here:** a long-running local server rather than a generated static file; the
tray icon is required, not optional, and is PySide6; `serve.py` must not import
PySide6; no database, tickets re-parsed from `lotto_sms_raw.txt` and results
left in `archive_results.json` / `archive_cache/`; spend compared against
winnings over checkable entries only, with lifetime spend shown separately and
labelled. The security constraints in that bullet are §4.4 of this document.

**Taken with the user 2026-08-02:**

- **The tray launches `serve.py` as a child process** — chosen over a systemd
  user unit (the shape the user's own `Ants_Projects_Hub_Website/tray/ants-stats-tray.py`
  uses) because it needs no install step: clone the repo, run the tray. The
  cost accepted is that the server's lifetime is the tray's; §4.8 makes that
  explicit rather than surprising. A unit remains possible for anyone who wants
  one, which is what INV-19 protects.
- **The start-at-login toggle lives on the page, in a settings panel** — chosen
  over a tickable item in the tray menu, knowing the trade: it gives the server
  its first state-changing endpoint, and therefore §4.4's token. The tray-menu
  option would have left the HTTP surface read-only.
- **Settings render as on/off switches, not checkboxes** — user preference,
  stated 2026-08-02. §4.7 fixes the accessible markup this must not cost.

## 4. Design

### 4.1 Three files, and the import direction that keeps them separable

```text
serve.py    stdlib only. Builds the model, serves it. Never imports PySide6.
page.py     Renders a model dict to one HTML string. Pure function, no I/O.
supervise.py  stdlib only. Spawns and reaps the server child; mints the token
              and the port and puts them in the child's environment (§4.4).
tray.py     PySide6. The menu and the icon. Imports supervise, never serve.
icons/      tray-running.svg, tray-stopped.svg — read by tray.py only.
```

**`supervise.py` exists so INV-20 is testable.** The spawn-and-reap contract is
what that invariant asserts, and putting it in `tray.py` would make the check
import PySide6 and need a running display — inside an exit-code script that has
to sit beside four headless `tools/verify_*.py`. Splitting it out costs one
small module and buys a testable lifecycle; it is also what lets a user with no
tray supervise the server from a script.

`page.py` emits the page's inline JavaScript along with its markup. The page
needs script for exactly three things and nothing else: the two POSTs (which
must carry a custom header, §4.4), and filtering the ticket table (which must
not touch the URL, INV-21). It is inline rather than a served asset because a
fifth route serving files is the thing §4.3 exists to avoid.

`tray.py` talks to the server the way the browser does — over HTTP on
127.0.0.1 — so there is no second code path that can disagree with the page,
which is the property the user's stats tray already relies on. The one
direction that must never appear is `serve.py → PySide6`: INV-19 asserts it,
because it is what keeps the headless case working and it would break silently
(a developer machine has Qt installed, so an accidental import is invisible
until someone runs it over SSH).

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

All three, enumerated by command rather than by reading — and the pattern was
widened to `^[A-Za-z_]+ *(:[^=]+)? *= *(\{\}|dict\(\))` before being trusted,
so an annotated or `dict()`-built memo could not hide from it. Three matches,
in `history.py`, `check.py` and `results.py`; `tickets.py` holds none, so
re-parsing the dump is already unconditional (2026-08-02):

```python
class State:
    """The one mutable thing in the server. All access under one lock."""
    def get(self):        ...  # -> (model|None, building: bool, built: str|None, stale: bool)
    def begin(self):      ...  # -> False if a build is already running (no concurrent builds)
    def finish(self, model):   # success: swap in, built=now, stale=False, building=False
    def fail(self):            # failure: model UNTOUCHED, stale=True, building=False


def refresh(state, build_model):
    """Rebuild from the sources on a worker thread. Clears the memos first.

    The previous model keeps serving throughout, and survives a failure — that
    is INV-18, and it is why `fail()` never touches `model`.
    """
    if not state.begin():
        return  # a build is already running; a second Refresh click is a no-op
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

### 4.3 HTTP surface

Four routes, and nothing else — every other path is 404.

| Method | Path | Returns | Changes state |
|---|---|---|---|
| GET | `/` | the page (HTML) | no |
| GET | `/status` | `{"building": bool, "built": "<ISO>"\|null, "stale": bool}` | no |
| POST | `/refresh` | 202, starts a rebuild | results only |
| POST | `/settings` | 200 + the settings as now stored | writes §4.7's two files |

`POST /settings` takes `{"autostart": bool, "open_on_start": bool}` as JSON and
returns the same shape **re-read from disk after writing**, not the request
echoed back — so a switch that failed to apply snaps back to the truth rather
than showing what was asked for. Both keys are optional; an absent key leaves
that setting alone. A body that is not an object of those two keys with boolean
values is 400, and nothing is written. `POST /refresh` takes no body.

Any other path is **404**; a known path with the wrong method is **405** with an
`Allow` header. Both are literal responses that name nothing from the request.

`SimpleHTTPRequestHandler` is not used and no path from a request is ever
joined to a filesystem path; the handler subclasses `BaseHTTPRequestHandler`
and every response body is built in memory. That removes path traversal as a
class rather than defending against it. `ThreadingHTTPServer`, because browsers
pre-open sockets they do not send on and a single-threaded server hangs on them.

### 4.4 Security boundary

The server holds every ticket the user owns, on a port any page in the user's
browser can reach. A `127.0.0.1` bind stops the network; it does not stop the
user's own browser being aimed at the port by a hostile site.

**Host allowlist, exact match, 421 otherwise.** The allowlist is
`{"127.0.0.1:<port>", "localhost:<port>"}`, compared as whole strings — not a
prefix, suffix or substring test, each of which `evil.example:4322` or
`127.0.0.1.evil.example` defeats. A non-matching `Host` gets `421 Misdirected
Request` and no body. This is exactly CVE-2026-46611 (Glances: a localhost XML-RPC
server with no `Host` validation, exfiltrated by DNS rebinding — hostname, full
process list with credentials in argv, open ports).
*Source: https://github.com/nicolargo/glances/security/advisories/GHSA-w856-8p3r-p338*
Glances answers 400; 421 is used here because it is the status that means
"this host is not one I serve", and the distinction matters when reading a log.

The response is the bare status line with no body. `421` is sent as the integer
rather than through `HTTPStatus.MISDIRECTED_REQUEST`, so the code does not
depend on when that constant entered the standard library — README.md claims a
Python 3.8 floor and this is not the place to test it.

**`Origin` is not a substitute and is not accepted as one.** A top-level
navigation carries no `Origin` header, so any rule that trusts its absence
admits the rebinding case unchanged. `Origin` is checked *in addition* on the
two POST routes and never instead, with an explicit rule for absence:

| `Origin` on a POST | Result |
|---|---|
| exactly `http://127.0.0.1:<port>` or `http://localhost:<port>` | allowed |
| present, any other value | 403 |
| **absent** | **allowed** — the token below is what covers this case |

Absent must be allowed or the tray's own `urllib` POST is rejected, and a rule
that broke the Refresh menu item would be quietly deleted by the first person
to hit it. That is why the token, not `Origin`, is the load-bearing defence.

**No `Access-Control-Allow-*` header is ever sent, on any route, including
errors.** One such header hands a hostile origin the ability to *read* the
response, which defeats the `Host` allowlist, the same-origin policy and the
token together. It is a plausible thing to add while debugging the page's own
`fetch()` calls — which are same-origin and need no CORS — so it is named here
as forbidden rather than left to judgement. INV-12.

**A per-run token on every state-changing request.** `secrets.token_urlsafe(32)`,
embedded in the page and required back in an `X-Lotto-Token` header. Two
properties: a custom header cannot be set by a cross-origin form post, and a
page that never received the token cannot guess it. A POST without the exact
token returns 403 and changes nothing, and the comparison is
`secrets.compare_digest`, not `==`. INV-13.

**The tray needs the same token, and the channel is the environment.** This is
not optional: §4.8 gives the tray a *Refresh results now* item, which is a
`POST /refresh`, and the token is generated inside a process the tray only
spawns. Left unstated, an implementer resolves it by exempting the tray — which
deletes the defence this section is built on.

```text
tray.py   token = secrets.token_urlsafe(32)
          Popen(["python3", "serve.py"], env={**os.environ, "LOTTO_TOKEN": token})
serve.py  token = os.environ.get("LOTTO_TOKEN") or secrets.token_urlsafe(32)
```

The tray mints it and hands it down; a standalone `serve.py` with no
`LOTTO_TOKEN` mints its own, so the headless case is unchanged. The environment
rather than argv, because argv is world-readable through `ps` while
`/proc/<pid>/environ` is readable only by the owning user — and rather than a
file, because a token on disk outlives the run that issued it.

**No request-derived data reaches a response header or a written file.**
Header values come from a fixed table of literals; `send_header()` is never
called with anything derived from the request, which removes header injection
(Python's `BaseHTTPRequestHandler` does not validate CRLF in header values).
The `.desktop` file §4.7 writes is built entirely from constants and a path
derived from the server's own location; the only thing a request can influence
is **whether it exists**, never its contents. INV-14.

**That file names `tray.py`, not the module that writes it.** The writer is
`serve.py` — `POST /settings` is a server route — so `os.path.abspath(__file__)`
resolves to the *server*, while the setting is "start the **tray** at login".
Built from `__file__` directly, the switch would autostart a headless server and
no icon would ever appear, and §11 already records that nothing mechanical
catches a wrong autostart. The `Exec` line is therefore:

```text
Exec=python3 <dirname(abspath(serve.__file__))>/tray.py
```

**Nothing about a ticket leaves in a URL, a title or a cache.** No ticket reference,
number, amount or date appears in a URL or a query string, the `<title>` is the
constant `Lotto Tracker`, and every response carries `Cache-Control: no-store`.
Browsers sync history and titles to a vendor account and offer them to search
suggestions; a URL is the one part of a local page that routinely escapes the
machine. INV-21. This is the same rule as `tools/verify_privacy.py` enforces
for the repository, applied to the other exit.

### 4.5 What the page shows, and the rule it must not drop

Four sections, in this order — expiry first, because it is the only thing on
the page with a deadline:

1. **Claimable now** — every unexpired win, soonest expiry first, each naming
   its pool (`lotto/1`, not "Lotto"), its division, its amount and its expiry
   date. A prize expiring within 30 days is marked; one expiring **today** is
   marked distinctly, because §6's build-time expiry makes today's the one the
   page can be wrong about.
2. **Live tickets** — tickets with draws still to come, showing draws
   remaining. Two today:

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
3. **Every ticket** — filterable by game and pool, showing cost, boards, the
   pools its price paid for, and per pool: scored, or the reason it could not be.
   **Filtering is client-side**, over rows already in the document: it must not
   add a query parameter, a fragment or a `history.pushState()` entry, because
   all three put ticket data somewhere the browser syncs (INV-21). The URL is
   the same string before and after every interaction with the page.
4. **Spend against winnings** — §4.6.

**The uncheckable rule is structural here, not prose.** `check.py::uncheckable_report()`
returns `(lines, counts)`, and `counts["wholly"]` / `counts["partly"]` are the
ticket lists themselves — which is what the banner needs. **It is not the source
for the per-entry reason**: `counts["too_old"]` and `counts["no_pool"]` are
integers (`"too_old": len(too_old)`), and the `(ticket, plus_flag)` lists behind
them are local to the function. So `page.py` derives each entry's reason itself:

```python
rows = all_draws(t.game, plus_flag)
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

**Accessible switch markup.** The switch is a styled
`<input type="checkbox" role="switch">`, not a `<div>` with a click handler:
`role="switch"` is the ARIA pattern for a two-state toggle, and building it on
a real checkbox keeps keyboard focus, Space to toggle, and the state a screen
reader announces. The visual is CSS; the semantics are the native control.

### 4.8 The tray

`QSystemTrayIcon` with a right-click menu — Open page, Refresh results now,
Stop/Start server, Quit — matching the user's existing stats tray, including
its two working details: long actions run on a `QThreadPool` so the menu never
freezes mid-click, and the icon, tooltip and menu wording all state the same
thing so state is never read off a 22-pixel icon alone. Left-click opens the
page. Two SVG icons, `icons/tray-running.svg` and `icons/tray-stopped.svg`,
resolved relative to `tray.py` rather than to the working directory — the tray
is launched from an autostart entry whose CWD is not the repository.

**The server is a child process, and Quit reaps it.** `subprocess.Popen(["python3", "serve.py"], env=…)`,
`terminate()` then `kill()` after a timeout on quit, and the same on
`aboutToQuit` so a session logout does not leave an orphan holding the port.
The spawn and reap live in a **Qt-free module** that `tray.py` imports, so
INV-20's case can drive them without a `QApplication` or a display.

**One port, read once.** `LOTTO_PORT` is an environment variable defaulting to
4322. `tray.py` reads it, passes it to the child alongside `LOTTO_TOKEN`
(§4.4), and uses the same value for the URL it opens; `serve.py` uses it to
bind and to build the `Host` allowlist. A tray and server disagreeing about the
port fail as a 421 on every request — the allowlist rejecting the very URL the
tray just opened.

## 5. Invariants

Numbered from INV-12: LOTTO-0001 holds INV-1 to INV-6 and LOTTO-0009 holds
INV-7 to INV-11, and CHANGELOG.md cites them unqualified.

- **INV-12** — A request whose `Host` header is not exactly `127.0.0.1:<port>`
  or `localhost:<port>` is answered 421 and served no body; a request with a
  correct `Host` is answered normally.
  *Test:* `tools/verify_page.py`, case `host_allowlist` — four requests in one
  case: a good `Host` (expect 200), `evil.example:4322` (421),
  `127.0.0.1.evil.example:4322` (421, the suffix-test trap), and **no `Host`
  header at all** (421). The good request is what stops the case passing
  against a server that answers 421 to everything. The same case asserts no
  `Access-Control-Allow-*` header on any of the four responses.
  *Breaks when:* the check becomes a substring or suffix test, admitting
  `127.0.0.1.evil.example`; the header is absent and treated as trusted; or a
  CORS header is added while debugging the page's own `fetch()` calls, which
  would let a hostile origin read what the allowlist stopped it reaching.

- **INV-13** — A POST to `/settings` or `/refresh` without the run's exact
  token returns 403 and changes nothing on disk.
  *Test:* `tools/verify_page.py`, case `token_required` — four POSTs, all with
  a valid `Host`: no token (403), a wrong token (403), a wrong `Origin` with the
  right token (403, §4.4's table), and the right token with no `Origin` (accepted
  — the tray's own case). Each 403 also asserts the autostart file is
  byte-identical, so "changes nothing" is observed rather than assumed. The
  valid `Host` is what isolates this rule: with a bad one INV-12 answers 421
  first and the case passes without the token check existing at all.
  The same case spawns a child with `LOTTO_TOKEN` in its environment and
  asserts that token is accepted — the §4.4 channel the tray depends on, which
  would otherwise be the one link in the chain nothing exercises.
  *Breaks when:* the token is compared with `startswith` or `==` rather than
  `secrets.compare_digest`, read from a query string (where it lands in browser
  history), or checked on `/settings` only. The likeliest breach is not a
  coding slip but §4.4's tray problem resolved the wrong way — exempting
  `/refresh` so the tray's menu item works, which removes the defence for the
  one route that re-fetches.

- **INV-14** — No value derived from a request reaches a response header or a
  file written by the server.
  *Test:* `tools/verify_page.py`, case `no_reflected_headers` — the poison is
  **percent-encoded** (`/a%0d%0aX-Injected:+yes`), not raw, and the `Host`
  header is valid on every request. Asserts no `X-Injected` header appears in
  any response, and that the `.desktop` file is byte-identical across a
  settings write attempted with a poisoned path. It asserts the file's content
  outright, not merely that it did not change: the `Exec` line must name
  `tray.py`. Byte-equality alone passes a file that has been wrong since it was
  first written — which is exactly §4.4's `__file__` trap, where the constant
  content is the bug.
  Two ways this case can test nothing, both measured on Python 3.13 rather than
  reasoned about: put the payload in `Host` and INV-12 answers 421 first, so it
  passes against a server with no header hygiene at all. Send **raw** CRLF and
  the request line is simply truncated — the handler receives path `/a`, the
  injected line is swallowed as a malformed header, and the response is a
  perfectly ordinary `200`. Nothing reaches the code under test, and the case
  passes for that reason. Only the percent-encoded form arrives intact:
  `self.path` is literally `/a%0d%0aX-Injected:+yes`, which is what a handler
  that decodes and reflects would turn into a header.
  *Breaks when:* an error page echoes the requested path into a header, or the
  `.desktop` file gains a field built from a request.

- **INV-15** — An entry nothing can score renders as "not checkable" with its
  reason, and never as a blank, a dash, a zero, or an omission; a ticket
  checkable in one pool and not another shows both facts.
  *Test:* `tools/verify_page.py`, case `uncheckable_not_a_loss` — renders a
  synthetic two-pool ticket, one pool scorable and one not, and asserts the
  reason string is present and no zero-amount cell stands in for the unscorable
  pool.
  *Breaks when:* the renderer iterates wins rather than entries, so an entry
  with no win simply does not appear — the failure mode that needs no bug, only
  an omission.

- **INV-16** — The compared spend is the apportioned cost of the checkable
  entries of resolved tickets, and nothing else; lifetime spend appears only as
  a separately labelled figure.
  *Test:* `tools/verify_page.py`, case `spend_over_checkable` — over a fixture
  of three tickets (one fully checkable, one partly, one wholly unscorable),
  asserts the rendered compared-spend figure **equals** an independently
  recomputed `Σ tier_increment × paid_lines × ndraws` over scorable entries of
  resolved tickets, and that the rendered lifetime figure is a different, larger
  number. Equality against a recomputed value is the assertion; "the lifetime
  total never appears as an operand" is not something a test can observe.
  *Breaks when:* the comparison uses `sum(t.cost for t in tickets)` — the
  obvious expression, and the lifetime figure — which puts a false loss of
  R25,592.90 on the page; or an unresolved ticket is folded into the compared
  spend, where its name-derived single tier cannot sum to what it cost (§4.6).

- **INV-17** — A refresh re-fetches from the sources rather than redrawing the
  memoised model.
  *Test:* `tools/verify_page.py`, case `refresh_refetches` — counts
  `urllib.request.urlopen` calls across two consecutive refreshes and asserts
  the second is non-zero.
  *Breaks when:* any of the three memos in §4.2 is not cleared —
  `history._cache`, `results._divisions_cache` or `check._struct`. Measured: a
  second build in the same process makes 0 requests and returns an identical
  result, so this failure is invisible from the page. Clearing two of the three
  is the likelier bug than clearing none, and it is worse: the page would show
  new draws priced from the previous run's division tables, which is wrong
  money rather than stale money.

- **INV-18** — A failed refresh leaves the previous model serving and says so;
  it never serves an empty or zeroed page.
  *Test:* `tools/verify_page.py`, case `failed_refresh_keeps_model` — patches
  the fetch to raise, refreshes, and asserts the wins still render and a
  staleness notice is present.
  *Breaks when:* the model is cleared before the rebuild, or an exception on
  the background thread leaves `state` empty. The operator's API failed with
  `URLError(SSL: UNEXPECTED_EOF_WHILE_READING)` on **four of the seven** build
  attempts made while measuring this spec (2026-08-02), so this is a routine
  path rather than a rare one, and it is the reason §6 treats a degraded page
  as a normal state instead of an error.

- **INV-19** — `serve.py` imports no Qt or PySide6 module at any depth, and
  importing it starts no server.
  *Test:* `tools/verify_page.py`, case `serve_is_headless` — imports `serve`
  in a fresh interpreter and asserts no module name matching `PySide|Qt` is in
  `sys.modules`, and that the import returns rather than blocking. Everything
  that binds, builds or serves sits behind `if __name__ == "__main__":`, which
  is what makes the import safe to perform at all — without it this case hangs
  instead of failing, and a hanging check reads as a broken test rather than a
  broken contract.
  *Breaks when:* a shared helper grows a Qt import, or `serve.py` imports
  `tray.py` for a constant. Invisible on a desktop with Qt installed.

- **INV-20** — Quitting the tray leaves no server process holding the port.
  *Test:* `tools/verify_page.py`, case `no_orphan_server` — spawns and reaps a
  real child, then asserts it has exited and the port accepts a fresh bind.
  Two constraints make this runnable inside a headless exit-code script beside
  the other four `tools/verify_*.py`, and both are requirements on the code,
  not on the test: the spawn/reap helper lives in a **Qt-free module** that
  `tray.py` imports (importing `tray.py` itself would need a `QApplication`
  and a display), and `serve.py` honours `LOTTO_NO_BUILD=1`, binding the port
  and serving an empty model without touching the network or
  `lotto_sms_raw.txt`. Without the second, this one case would cost the 27
  requests and the real dump that §7's other two constraints forbid.
  *Breaks when:* the child is left to `SIGHUP`, or `terminate()` is sent without
  a `kill()` fallback and the server is mid-build in a non-interruptible fetch.

- **INV-21** — No ticket data appears in any URL, fragment or page `<title>`,
  and every response carries `Cache-Control: no-store`.
  *Test:* `tools/verify_page.py`, case `nothing_in_the_url` — asserts each of
  the four routes serves identically with and without a query string appended
  (so no parameter can be load-bearing), that the rendered `<title>` is the
  constant `Lotto Tracker`, that `no-store` is on all four responses, and that
  the page's inline script contains no `pushState`, `replaceState` or
  `location.hash` assignment. It also asserts §4.3's routing floor — an unknown
  path is 404 and a known path with the wrong method is 405 — since both are
  responses that must name nothing from the request.
  *Breaks when:* filtering is implemented as `/?game=lotto&ref=…`, the natural
  first implementation, which writes a ticket reference into browser history —
  or as a `#ref=…` fragment, which looks safer and is not: the fragment is in
  the URL the browser stores and syncs, it is merely not sent to the server.

## 6. Failure modes

- **The operator's API is unreachable.** Four of seven build attempts on
  2026-08-02 failed with `SSL: UNEXPECTED_EOF_WHILE_READING` — this is the
  common failure, not an edge case. At startup: the page serves
  from `archive_results.json` alone with a visible notice that live results are
  missing, and says which pools are affected — it does not show zero wins. On
  refresh: INV-18.
- **Port 4322 is in use.** `serve.py` exits with the port in the message rather
  than tracebacking; the tray shows it in a notification instead of dying
  silently. `LOTTO_PORT` overrides it, per §4.8. (4322 chosen as free on this
  machine and adjacent to the user's stats dashboard on 4321 — `ss -ltn`,
  2026-08-02.)
- **`lotto_sms_raw.txt` is absent.** The page renders its empty state and says
  the dump is missing and how to produce it — never "0 tickets, R0.00", which
  reads as "you have never won".
- **No system tray on the desktop.** `QSystemTrayIcon.isSystemTrayAvailable()`
  is false: the tray reports it and exits non-zero, as the stats tray does.
  `serve.py` is unaffected, which is the point of INV-19.
- **`~/.config/autostart/` does not exist.** Created with `parents=True` on
  first enable; a write failure returns 500 with the reason and leaves the
  switch showing its true state, not the requested one.
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
- **A tab left open across a server restart holds a stale token.** The token is
  per process, not per page — so every tab of one run shares one token, and a
  tab that outlives the run holds one nothing will accept. Its next toggle gets
  a 403, which renders as "this page is from an earlier session — reload it",
  not as a failure of the setting.

## 7. Tests

`tools/verify_page.py` joins `tools/verify_privacy.py`, `tools/verify_sources.py`,
`tools/verify_coverage.py` and `tools/verify_pools.py`. Exit code is the signal,
as with the other four. Ten cases, one per invariant — the same ten §11 names:

| Case | Locks |
|---|---|
| `host_allowlist` | INV-12 |
| `token_required` | INV-13 |
| `no_reflected_headers` | INV-14 |
| `uncheckable_not_a_loss` | INV-15 |
| `spend_over_checkable` | INV-16 |
| `refresh_refetches` | INV-17 |
| `failed_refresh_keeps_model` | INV-18 |
| `serve_is_headless` | INV-19 |
| `no_orphan_server` | INV-20 |
| `nothing_in_the_url` | INV-21 |

Three constraints on it, each following from something in the existing suite:

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
- **It must not touch real data.** Cases run against a `$HOME` pointed at a
  temporary directory and tickets built from the `VAS00000000000` sentinel, not
  from `lotto_sms_raw.txt`. A test that writes to the user's real
  `~/.config/autostart/` while asserting about it is a test that changes the
  system it measures.
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
- **A systemd user unit driven by the tray**, as the user's stats tray does.
  Rejected 2026-08-02 for the install step. Still available to anyone who wants
  it precisely because INV-19 keeps `serve.py` Qt-free — the alternative is
  preserved rather than closed off.
- **Settings in the tray menu instead of the page.** Rejected 2026-08-02. It
  would have kept the HTTP surface read-only and removed §4.4's token entirely;
  the user chose the panel knowing that.
- **`Origin` checking instead of `Host`.** Rejected on evidence: a top-level
  navigation sends no `Origin`, so the rebinding case passes a check that trusts
  its absence. Kept as an additional check on POSTs (§4.4).
- **`SimpleHTTPRequestHandler` serving a directory.** Rejected: it reintroduces
  path traversal as a class, for the convenience of not writing four routes.
- **A `<div role="switch">` toggle.** Rejected: rebuilding focus, keyboard and
  announcement on a div is how toggles become unreachable. Same visual on a real
  checkbox (§4.7).
- **Electron.** Rejected — a browser bundled for one menu, where PySide6 is
  already installed and is what KDE Plasma itself is built on.

## 9. Out of scope

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
  nothing extra unless the user presses Refresh.
- **Disk:** two files under `$XDG_CONFIG_HOME` (§4.7), both a few hundred bytes.
  Nothing written to the repository, which `tools/verify_privacy.py` continues
  to assert.
- **Dependencies:** PySide6 for `tray.py` only, already installed (6.11.0,
  `python3 -c "import PySide6; print(PySide6.__version__)"`). `serve.py` and
  `page.py` are standard library, keeping the project's "Python 3.8+ stdlib"
  claim in README.md true for the headless path.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-12 Host allowlist | `tools/verify_page.py::host_allowlist` |
| INV-13 token on writes | `tools/verify_page.py::token_required` |
| INV-14 no reflected data | `tools/verify_page.py::no_reflected_headers` |
| INV-15 uncheckable never a loss | `tools/verify_page.py::uncheckable_not_a_loss` |
| INV-16 spend over checkable only | `tools/verify_page.py::spend_over_checkable` — also closes LOTTO-0009 §11's `nothing` row for its §4.7 |
| INV-17 refresh re-fetches | `tools/verify_page.py::refresh_refetches` |
| INV-18 failed refresh keeps the model | `tools/verify_page.py::failed_refresh_keeps_model` |
| INV-19 `serve.py` is Qt-free | `tools/verify_page.py::serve_is_headless` |
| INV-20 no orphan server | `tools/verify_page.py::no_orphan_server` |
| INV-21 nothing in the URL | `tools/verify_page.py::nothing_in_the_url` |
| §4.4 `Origin` rule on POSTs, incl. absent-is-allowed | `tools/verify_page.py::token_required` |
| §4.4 the tray's `LOTTO_TOKEN` channel | `tools/verify_page.py::token_required` — a child spawned with the variable accepts that token |
| §4.3 404 / 405 routing floor | `tools/verify_page.py::nothing_in_the_url` |
| §4.7 the `.desktop` `Exec` naming `tray.py`, not the writing module | `tools/verify_page.py::no_reflected_headers` — the file's content is asserted byte-for-byte |
| §4.2 the 27-request figure staying true | **nothing** — a dated measurement; a larger dump or an API paging change moves it without failing anything |
| §4.5 the page being *readable* — ordering, filters, marking near-expiry | **nothing** — no check can tell a clear layout from a cluttered one |
| §4.7 the written `.desktop` file actually autostarting on this desktop | **nothing mechanical** — it depends on the session's XDG implementation; verified by logging out once |
| §4.4 the token surviving a browser that strips custom headers | **nothing** — no such browser is known, and the failure is visible (403 on every toggle) rather than silent |

Eighteen rows, four `nothing`.

## 12. Cross-doc impact

- `README.md` — a new section for the page and tray: how to start it, the
  optional autostart switch, and the port. Its "Needs Python 3.8+ and a Linux
  desktop" line gains PySide6 as a tray-only requirement.
- `CLAUDE.md` — the Commands block gains `python3 serve.py` and
  `python3 tray.py`, and the verification list gains `tools/verify_page.py`.
  Its architecture diagram gains the second consumer of `check.py`.
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

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 1 | 2026-08-02 | 2 | 3 | 7 | 13 | 8 | All 31 verified findings fixed; 0 unverified, 0 deferred. **Both lanes independently found the same three CRITICALs, and all three were contract gaps that an implementer would have closed by weakening the security model.** (a) The tray has a *Refresh results now* item, which is a `POST /refresh`, and §4.4 generated the token inside a process the tray only spawns — so the one menu item that needed the token could not obtain it, and the cheap fix is exempting `/refresh`. The channel is now specified (`LOTTO_TOKEN` in the child's environment; env rather than argv, which `ps` exposes, and rather than a file, which outlives the run). (b) §4.4 built the autostart `.desktop` from `os.path.abspath(__file__)`, but the writer is `serve.py` while the setting is "start the **tray** at login" — the switch would have autostarted a headless server and no icon would ever have appeared, and §11 already admitted nothing mechanical catches a wrong autostart. `Exec` now names `tray.py`, and INV-14 asserts the file's content outright rather than only that it did not change: byte-equality passes a file wrong since first written, which is exactly this bug. (c) §7's test seam took a finished model (`make_server(model, …)`), leaving `POST /refresh` nothing to invoke — so INV-17 and INV-18 had no rebuild to exercise and INV-15 needed a stubbed `all_draws`, three of ten cases untestable while §11 credited the script with locking them. The seam is now the builder. **One lane finding was upheld with its reasoning replaced by measurement:** INV-14's fixture was called vacuous because raw CRLF supposedly draws a 400 before the handler runs. Measured on 3.13 — no 400: the request line is truncated, the handler sees path `/a`, the injected line is swallowed as a malformed header and the response is an ordinary 200. Vacuous for the opposite reason, and the fix (percent-encoded `%0d%0a`, which *does* arrive intact) is the same either way. Also fixed: §4.6 dropped LOTTO-0009 §4.7's "only when the price resolves" qualifier and left an unresolved ticket's rendering undefined on a money display; two privacy defects that `tools/verify_privacy.py` cannot see because it compares against the dump's text rather than what the text implies (a purchase week plus draw count over a two-ticket population, and one win's exact amount with a derivable draw date); `check.py::uncheckable_report()` was named as the source of §4.5's per-entry reasons when its `too_old`/`no_pool` are integers, so `page.py` now recomputes them; the `refresh()` sketch was synchronous with no lock and no `try` while the prose two paragraphs above promised a background thread and a lock, and INV-18 depends entirely on the exception path it omitted; `/settings` had no request body format and no client-side JS was mentioned though three features require it; and four section cross-references were off by one, all landing an implementer chasing the settings contract in the money section. **The sweep caught one defect created by these fixes**: requiring a Qt-free spawn/reap module for INV-20 left it absent from §4.1's file list — now `supervise.py`. Doc grew 624 → 880 lines. |
