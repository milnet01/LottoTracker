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
   Its §11 carries the row *"§4.7 comparison drawn only over checkable entries —
   **nothing**; LOTTO-0002 implements the display and owns its check"*. INV-16
   below is that check, so this spec closes one of that spec's four `nothing`
   rows.
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
  cost accepted is that the server's lifetime is the tray's; §4.7 makes that
  explicit rather than surprising. A unit remains possible for anyone who wants
  one, which is what INV-19 protects.
- **The start-at-login toggle lives on the page, in a settings panel** — chosen
  over a tickable item in the tray menu, knowing the trade: it gives the server
  its first state-changing endpoint, and therefore §4.4's token. The tray-menu
  option would have left the HTTP surface read-only.
- **Settings render as on/off switches, not checkboxes** — user preference,
  stated 2026-08-02. §4.6 fixes the accessible markup this must not cost.

## 4. Design

### 4.1 Three files, and the import direction that keeps them separable

```text
serve.py    stdlib only. Builds the model, serves it. Never imports PySide6.
tray.py     PySide6. Spawns and reaps `python3 serve.py`. Never imports serve.
page.py     Renders a model dict to one HTML string. Pure function, no I/O.
```

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

All three, enumerated by command rather than by reading
(`grep -n "^[A-Za-z_]* *= *{}" *.py`, 2026-08-02):

```python
def refresh(state):
    """Rebuild the model from the sources. Clears the in-process memos first."""
    import check, history, results
    history._cache.clear()           # {(game, plus_flag): [draw, ...]}
    results._divisions_cache.clear() # {(game, issue, pool_id, plus_flag): [level, ...]}
    check._struct.clear()            # {(game, plus_flag, pool_id): {label: division}}
    state.set(build_model())         # atomic swap; readers never see a half-built model
```

`results._divisions_cache` is the one that is easy to miss and the one that
matters most: it holds the prize breakdown per draw, so a refresh that skipped
it would fetch new draws and price them from the previous run's division
tables. `backfill.py` needs no clearing — it caches to `archive_cache/` on
disk, and archive-era draws are historic and immutable.

**Bind the port before the first build, not after** — the pattern
`serve.mjs` already uses ("Listen before refreshing, not after"). The server
starts answering immediately and serves a *building* page for the first ~32
seconds, rather than leaving the browser to time out on a port nothing is
listening to yet. The build runs on a background thread; `state` is swapped
under a lock.

### 4.3 HTTP surface

Four routes, and nothing else — every other path is 404.

| Method | Path | Returns | Changes state |
|---|---|---|---|
| GET | `/` | the page (HTML) | no |
| GET | `/status` | `{"building": bool, "built": "<ISO>", "stale": bool}` | no |
| POST | `/refresh` | 202, starts a rebuild | results only |
| POST | `/settings` | 200 + the new settings | writes §4.6's two files |

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

**`Origin` is not a substitute and is not accepted as one.** A top-level
navigation carries no `Origin` header, so any rule that trusts its absence
admits the rebinding case unchanged. `Origin` is checked *in addition* on the
two POST routes and never instead.

**A per-run token on every state-changing request.** `secrets.token_urlsafe(32)`,
generated once per process, never written to disk, embedded in the page and
required back in an `X-Lotto-Token` header. Two properties: a custom header
cannot be set by a cross-origin form post, and a page that never received the
token cannot guess it. A POST without the exact token returns 403 and changes
nothing. INV-13.

**No request-derived data reaches a response header or a written file.**
Header values come from a fixed table of literals; `send_header()` is never
called with anything derived from the request, which removes header injection
(Python's `BaseHTTPRequestHandler` does not validate CRLF in header values).
The `.desktop` file §4.6 writes is built entirely from constants and
`os.path.abspath(__file__)`; the only thing a request can influence is whether
it exists. INV-14.

**Nothing about a ticket leaves the response body.** No ticket reference,
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
   date. A prize expiring within 30 days is marked.
2. **Live tickets** — tickets with draws still to come, showing draws
   remaining. Two today, both bought in the week of 2026-07-07 with 2 of 10
   draws left:

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
4. **Spend against winnings** — §4.6.

**The uncheckable rule is structural here, not prose.** `check.py::uncheckable_report()`
already returns `(lines, counts)` with `counts["wholly"]` and `counts["partly"]`
as the ticket lists themselves. The page renders per entry:

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

| Figure | Value | Shown as |
|---|---|---|
| Spend on entries that could be scored | R10,603.50 | the comparison |
| Winnings on those entries | R2,651.60 lifetime, R2,418.90 unexpired | the comparison |
| Lifetime spend, all 1,233 entries | R28,244.50 | a separate, labelled line |

`Σ entry_cost_cents == round(Ticket.cost * 100)` across all 558 tickets — the
`sums back: True` above — which is what makes the apportionment safe to show:
the per-entry split never invents or loses money against the price the SMS
actually charged. Comparing R28,244.50 against R2,651.60 would convert 974 unscorable
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
page. Two SVG icons, running and stopped.

**The server is a child process, and Quit reaps it.** `subprocess.Popen(["python3", "serve.py"])`,
`terminate()` then `kill()` after a timeout on quit, and the same on
`aboutToQuit` so a session logout does not leave an orphan holding port 4322.
INV-20.

## 5. Invariants

Numbered from INV-12: LOTTO-0001 holds INV-1 to INV-6 and LOTTO-0009 holds
INV-7 to INV-11, and CHANGELOG.md cites them unqualified.

- **INV-12** — A request whose `Host` header is not exactly `127.0.0.1:<port>`
  or `localhost:<port>` is answered 421 and served no body; a request with a
  correct `Host` is answered normally.
  *Test:* `tools/verify_page.py`, case `host_allowlist` — both halves asserted
  in the same case. Asserting only the rejection would pass against a server
  that answers 421 to everything.
  *Breaks when:* the check becomes a substring or suffix test, admitting
  `127.0.0.1.evil.example`; or the header is absent and treated as trusted.

- **INV-13** — A POST to `/settings` or `/refresh` without the run's exact
  token returns 403 and changes nothing on disk.
  *Test:* `tools/verify_page.py`, case `token_required` — POSTs with a valid
  `Host` and no token, then asserts both the status and that the autostart file
  is byte-identical. The valid `Host` is what isolates this rule: with a bad one
  INV-12 would answer 421 first and the case would pass without the token check
  existing at all.
  *Breaks when:* the token is compared with `startswith`, read from a query
  string (where it lands in browser history), or checked on `/settings` only.

- **INV-14** — No value derived from a request reaches a response header or a
  file written by the server.
  *Test:* `tools/verify_page.py`, case `no_reflected_headers` — requests
  carrying CRLF and header-like content in the path and query, asserting no
  injected header appears in any response and that the `.desktop` file content
  is byte-identical across a settings write attempted with a poisoned path.
  The `Host` header is valid on every request in this case, and the poisoned
  values go in the path rather than in `Host`: a request with a malformed
  `Host` is answered 421 by INV-12 before this rule is reached, so putting the
  payload there would pass the case against a server with no header hygiene at
  all.
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

- **INV-16** — Spend is compared against winnings over checkable entries only,
  and lifetime spend appears only as a separately labelled figure.
  *Test:* `tools/verify_page.py`, case `spend_over_checkable` — asserts the
  compared spend equals the sum over scorable entries, and that the lifetime
  total never appears as an operand of the comparison.
  *Breaks when:* the comparison uses `sum(t.cost for t in tickets)`, the
  obvious expression, which is the lifetime figure and puts a false loss of
  R25,592.90 on the page.

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

- **INV-19** — `serve.py` imports no Qt or PySide6 module at any depth.
  *Test:* `tools/verify_page.py`, case `serve_is_headless` — imports `serve`
  in a fresh interpreter and asserts no module name matching `PySide|Qt` is in
  `sys.modules`.
  *Breaks when:* a shared helper grows a Qt import, or `serve.py` imports
  `tray.py` for a constant. Invisible on a desktop with Qt installed.

- **INV-20** — Quitting the tray leaves no server process holding the port.
  *Test:* `tools/verify_page.py`, case `no_orphan_server` — starts the tray's
  spawn/reap helper, quits, and asserts the child has exited and the port
  accepts a fresh bind.
  *Breaks when:* the child is left to `SIGHUP`, or `terminate()` is sent without
  a `kill()` fallback and the server is mid-build in a non-interruptible fetch.

- **INV-21** — No ticket data appears in any URL or in the page `<title>`, and
  every response carries `Cache-Control: no-store`.
  *Test:* `tools/verify_page.py`, case `nothing_in_the_url` — asserts the four
  routes take no query parameters, the rendered title is the constant, and the
  header is present on all four.
  *Breaks when:* filtering is implemented as `/?game=lotto&ref=…`, the natural
  first implementation, which writes a ticket reference into browser history.

## 6. Failure modes

- **The operator's API is unreachable.** Four of seven build attempts on
  2026-08-02 failed with `SSL: UNEXPECTED_EOF_WHILE_READING` — this is the
  common failure, not an edge case. At startup: the page serves
  from `archive_results.json` alone with a visible notice that live results are
  missing, and says which pools are affected — it does not show zero wins. On
  refresh: INV-18.
- **Port 4322 is in use.** `serve.py` exits with the port in the message rather
  than tracebacking; the tray shows it in a notification instead of dying
  silently. `LOTTO_PORT` overrides. (4322 chosen as free on this machine and
  adjacent to the user's stats dashboard on 4321 — `ss -ltn`, 2026-08-02.)
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
  has since lapsed — observed during this session, where the claimable total
  moved R2,423.00 → R2,418.90 and 63 → 62 lines as a R4.10 win crossed 365 days
  mid-session. The page therefore stamps the build time and marks anything
  expiring today, rather than implying the figure is live.
- **Two browser tabs, two tokens.** The token is per process, not per page, so
  a tab opened before a server restart holds a stale one. A 403 renders as
  "reload the page", not as a failure of the setting.

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

- **It must not need the network.** The model builder is injectable —
  `make_server(model, token, port)` takes a model rather than building one — so
  every case above runs against a synthetic model in well under a second. A
  check that costs 32 seconds and 27 requests will not be run.
- **It must not touch real data.** Cases run against a `$HOME` pointed at a
  temporary directory and tickets built from the `VAS00000000000` sentinel, not
  from `lotto_sms_raw.txt`. A test that writes to the user's real
  `~/.config/autostart/` while asserting about it is a test that changes the
  system it measures.
- **It must not import the thing it tests where the thing is the judgement.**
  `tools/verify_coverage.py` and `tools/verify_pools.py` both carry this rule:
  INV-15 and INV-16 recompute what should be rendered rather than importing the
  renderer's own opinion of it.

Each case is red-tested against pre-fix code before the invariant is accepted,
per the practice LOTTO-0009 §7 established and its five invariants followed.

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
| §4.2 the 32s / 27-request figures staying true | **nothing** — they are a dated measurement; a slower API or a larger dump moves them without failing anything |
| §4.5 the page being *readable* — ordering, filters, marking near-expiry | **nothing** — no check can tell a clear layout from a cluttered one |
| §4.7 the written `.desktop` file actually autostarting on this desktop | **nothing mechanical** — it depends on the session's XDG implementation; verified by logging out once |
| §4.4 the token surviving a browser that strips custom headers | **nothing** — no such browser is known, and the failure is visible (403 on every toggle) rather than silent |

Fourteen rows, four `nothing`.

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
- `docs/specs/LOTTO-0009-entered-pools.md` — its §11 row *"§4.7 comparison
  drawn only over checkable entries — **nothing**"* becomes
  `tools/verify_page.py` (INV-16). That is an edit to a shipped spec's table
  and lands in the same change, so the two documents never disagree about who
  checks that rule.
- `docs/specs/LOTTO-0001-lottery-ticket-tracker.md` — unaffected. This item adds
  no parsing, scoring or pricing behaviour, so none of INV-1 to INV-6 moves.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
