# LOTTO-0002 — Local web page and tray icon for tickets, results and claimable winnings

**Status:** accepted (2026-08-02) — three cold-eyes loops, converged by cap.
A split is recommended before implementation; see §12 and §13.
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
page carries two switches: start the tray at login, and open the page when the
tray starts. `check.py` keeps working
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
- **Settings render as sliding on/off switches rather than square checkboxes** —
  user preference, stated 2026-08-02. This is about the *appearance*: §4.7 keeps
  a real `<input type="checkbox">` underneath, because that is what preserves
  keyboard and screen-reader behaviour.

## 4. Design

### 4.1 Four files, the model between them, and the I/O boundary

```text
serve.py      stdlib only. Does ALL I/O: builds the model, serves it.
              Never imports PySide6.
page.py       Renders a model dict to one HTML string. Pure function, no I/O,
              no imports of check/history/results/tickets.
supervise.py  stdlib only. Mints the token, resolves the port, spawns and
              reaps the server child (§4.4). Never imports PySide6.
tray.py       PySide6. The menu and the icon, and nothing else. Calls
              supervise; never imports serve or page.
icons/        tray-running.svg, tray-stopped.svg — read by tray.py only.
```

**Whenever the tray launches the server, `supervise.py` is the sole owner of the
token, the port and the child process** — a standalone `python3 serve.py` with
no `LOTTO_TOKEN` mints its own (§4.4), which is the headless case and the only
time `serve.py` decides either for itself. `supervise.py` exists so INV-20 is
testable. The spawn-and-reap contract is
what that invariant asserts, and putting it in `tray.py` would make the check
import PySide6 and need a running display — inside an exit-code script that has
to sit beside four headless `tools/verify_*.py`. Splitting it out costs one
small module and buys a testable lifecycle; it also lets a user with no tray
supervise the server from a script.

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
| `LOTTO_PORT` | `4322` | `supervise.py` | `serve.py` | bind port; also builds §4.4's `Host` allowlist |
| `LOTTO_TOKEN` | minted per run | `supervise.py` | `serve.py` | §4.4's write token; standalone `serve.py` mints its own |
| `LOTTO_NO_BUILD` | unset | the caller | `serve.py` | bind and serve, build nothing — for INV-20 only, see §6 |

**The token is not a model key.** `page.py`'s signature is
`render(model, token)`: the model is what §7's fixtures are built to, and a
token living in it would be copied into every fixture and would leak into
anything that serialises a model. The renderer embeds it; INV-13's case asserts
the rendered page carries it, because a page without it 403s on every toggle
while all ten cases still pass.

`page.py` emits the page's inline JavaScript along with its markup. It has
exactly four jobs and no others: the two POSTs (which must carry a custom
header, §4.4), filtering the ticket table (which must not touch the URL,
INV-21), and **polling `GET /status` every 2 s while `building` is true, or
after a `POST /refresh`, reloading when `built` changes**. Without the fourth,
the opening *building* page never leaves that state and `GET /status` has no
consumer at all. It is inline rather than a served asset because a fifth route
serving files is the thing §4.3 exists to avoid.

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

### 4.3 HTTP surface

Four routes, and nothing else — every other path is 404.

| Method | Path | Returns | Changes state |
|---|---|---|---|
| GET | `/` | the page (HTML) | no |
| GET | `/status` | `{"building": bool, "built": "<ISO>"\|null, "stale": bool}` | no |
| POST | `/refresh` | 202 accepted, or 409 if one is already running | results only |
| POST | `/settings` | 200 + the settings as now stored | writes §4.7's two files |

`POST /settings` takes `{"autostart": bool, "open_on_start": bool}` as JSON and
returns the same shape **re-read from disk after writing**, not the request
echoed back — so a switch that failed to apply snaps back to the truth rather
than showing what was asked for. Both keys are optional; an absent key leaves
that setting alone, and `{}` is valid — a no-op returning 200 with the settings
unchanged. A body that is not an object of those two keys with boolean values is
400, and nothing is written. `POST /refresh` takes no body.

Any other path is **404**; a known path with the wrong method is **405** with an
`Allow` header **drawn from a fixed per-path table**, never assembled from the
request — it is the one header whose value varies by route, which is exactly the
shape INV-14 forbids building out of anything a caller sent.

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

`localhost:<port>` is allowlisted alongside the numeric form because that is
what a user types, even though the socket binds `127.0.0.1` only; on a host
whose resolver answers `localhost` with `::1` first, the browser fails to
connect at all rather than reaching a server that then rejects it — a broken
link, not a hole. The tray always opens the numeric URL, so its own path is
unaffected.

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

```python
# supervise.py — the sole owner of the token and the child (§4.1)
HERE  = os.path.dirname(os.path.abspath(__file__))
token = secrets.token_urlsafe(32)
Popen([sys.executable, os.path.join(HERE, "serve.py")],
      env={**os.environ, "LOTTO_TOKEN": token, "LOTTO_PORT": str(port)})

# serve.py
token = os.environ.get("LOTTO_TOKEN") or secrets.token_urlsafe(32)
```

`supervise.py` mints it and hands it down; a standalone `serve.py` with no
`LOTTO_TOKEN` mints its own, so the headless case is unchanged. The environment
rather than argv, because argv is world-readable through `ps` while
`/proc/<pid>/environ` is readable only by the owning user — and rather than a
file, because a token on disk outlives the run that issued it.

**Both paths are absolute and `sys.executable` is used, not `"python3"`.** The
tray is launched from an autostart entry whose working directory is not the
repository (§4.7 ships exactly that entry), so a relative `"serve.py"` fails in
the configuration this item adds; and the child must run under the interpreter
the parent is already using rather than whatever `python3` resolves to in a
session PATH.

**Every response carries `X-Frame-Options: DENY` and
`Content-Security-Policy: frame-ancestors 'none'`.** Without them the token
defends against a *forged* request and not against a real one: a hostile page
can `<iframe src="http://127.0.0.1:4322">`, the `Host` header is the
allowlisted value so the frame renders, and the framed page carries the token
in its own DOM. Every defence above survives that, and the user still clicks
§4.7's switch through an invisible overlay. Framing is the hole a `Host`
allowlist and a token cannot see, so it is closed here rather than left to the
implementer to notice. INV-12.

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
catches a wrong autostart. **§4.7 gives the file's bytes verbatim and is the
only place that does** — INV-14 asserts them byte-for-byte, so a second copy
here would be a second contract to disagree with.

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
path (INV-14 asserts these bytes):

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
interpreter is `sys.executable`, not the string `python3`, for the same reason
§4.4 gives for the `Popen`: the autostart session's `PATH` is not the one the
server was installed under, and this is precisely the launch path where that
bites. Both are substituted at write time, so the bytes on disk are constant
for a given install — which is what lets INV-14 assert them.

`open_on_start` is read by **`tray.py` at startup** and defaults to **true**: a
missing, unreadable or malformed `settings.json` falls back to the default
rather than raising, because a corrupt settings file must not be the reason the
tray fails to appear. Writing the file creates its directory with
`parents=True, exist_ok=True` — without `exist_ok` the second enable raises
`FileExistsError`, which is the *normal* case and would surface as §6's 500 on
every toggle after the first.

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

**The server is a child process, and Quit reaps it.** `supervise.py` owns the
`Popen` (§4.4 gives it verbatim), `terminate()` then `kill()` after a timeout on
quit, and the same on `aboutToQuit` so a session logout does not leave an orphan
holding the port. Because that lives in a **Qt-free module**, INV-20's case can
drive it without a `QApplication` or a display.

**One port, read once.** `supervise.py` resolves `LOTTO_PORT` (default 4322,
§4.1), passes it to the child alongside `LOTTO_TOKEN`, and hands `tray.py` the
URL to open; `serve.py` uses the same value to bind and to build the `Host`
allowlist. A tray and server disagreeing about the port fail as a 421 on every
request — the allowlist rejecting the very URL the tray just opened. The
autostart entry §4.7 writes carries no `LOTTO_PORT`, so an autostarted tray uses
the default; anyone overriding the port sets it in their session environment,
where both the entry and a manual run inherit it.

## 5. Invariants

Numbered from INV-12: LOTTO-0001 holds INV-1 to INV-6 and LOTTO-0009 holds
INV-7 to INV-11, and CHANGELOG.md cites them unqualified.

- **INV-12** — A request whose `Host` header is not exactly `127.0.0.1:<port>`
  or `localhost:<port>` is answered 421 and served no body; a request with a
  correct `Host` is answered normally.
  *Test:* `tools/verify_page.py`, case `host_allowlist` — four `Host` values: a
  good one (expect 200), `evil.example:4322` (421),
  `127.0.0.1.evil.example:4322` (421, the suffix-test trap), and **no `Host`
  header at all** (421). The good request is what stops the case passing
  against a server that answers 421 to everything.
  **Each of the four is fired at `GET /`, at `GET /status` and at a POST route**,
  because a `Host` check written into `do_GET` alone passes a `GET /`-only case
  while leaving both write routes reachable from a rebound origin. The
  allowlist is the stated first line of defence; a case that only proves it for
  one method has not proved it. The same case asserts, on
  every one of the four responses, that no `Access-Control-Allow-*` header is
  present and that both `X-Frame-Options: DENY` and
  `Content-Security-Policy: frame-ancestors 'none'` are.
  *Breaks when:* the check becomes a substring or suffix test, admitting
  `127.0.0.1.evil.example`; the header is absent and treated as trusted; or a
  CORS header is added while debugging the page's own `fetch()` calls, which
  would let a hostile origin read what the allowlist stopped it reaching.

- **INV-13** — A POST to `/settings` or `/refresh` without the run's exact
  token returns 403 and changes nothing on disk.
  *Test:* `tools/verify_page.py`, case `token_required` — four POSTs, all with
  a valid `Host`: no token (403), a wrong token (403), a wrong `Origin` with the
  right token (403, §4.4's table), the right token with no `Origin` (accepted —
  the tray's own case), and the right token with `Origin: http://127.0.0.1:<port>`
  (accepted — the browser's own case, and the row that stops a handler which
  403s *every* present `Origin` from passing while every in-page toggle fails).
  **The wrong token is a proper prefix of the real one**, so `startswith` is
  actually caught; a random wrong token passes a `startswith` implementation.
  The case also asserts the rendered page contains the run token, since a
  renderer that never embeds it (§4.1) 403s every toggle while all ten cases
  otherwise pass.
  **Every one of them is fired at both `/settings` and `/refresh`.** The
  *Breaks when* below names exempting `/refresh` as the likeliest breach, so a
  case that only ever POSTs to `/settings` cannot catch the very failure it is
  written for. "Changes nothing" is observed per route: for `/settings`, the
  autostart file is byte-identical; for `/refresh`, the stub builder's call
  count is unchanged.
  The valid `Host` is what isolates this rule: with a bad one INV-12 answers 421
  first and the case passes without the token check existing at all.
  The same case spawns a child with `LOTTO_TOKEN` in its environment and
  asserts that token is accepted — the §4.4 channel the tray depends on, which
  would otherwise be the one link in the chain nothing exercises.
  *Breaks when:* the token is compared with `startswith`, read from a query
  string (where it lands in browser history), or checked on `/settings` only.
  (`==` instead of `secrets.compare_digest` is a real defect and **not** one
  this or any black-box case can observe — the two agree on every input and
  differ only in timing. It is a code-review item, and §11 records that nothing
  mechanical catches it.) The likeliest breach is not a
  coding slip but §4.4's tray problem resolved the wrong way — exempting
  `/refresh` so the tray's menu item works, which removes the defence for the
  one route that re-fetches.

- **INV-14** — No request-derived **string** reaches a response header or a
  written file. The only request-derived values ever written are §4.3's two
  validated booleans; the `.desktop` file's contents are constant.
  *Test:* `tools/verify_page.py`, case `no_reflected_headers` — the poison is
  **percent-encoded** (`/a%0d%0aX-Injected:+yes`), not raw, and the `Host`
  header is valid on every request. The case **first issues a valid
  `POST /settings {"autostart": true}` with the run token**, so the `.desktop`
  file exists to be asserted about — a poisoned path is not `/settings`, it
  404s, and nothing would be written for the assertion to have a subject. It
  then asserts no `X-Injected` header appears in any response, and that the
  file is byte-identical afterwards. It asserts the file's content outright
  against §4.7's listing, not merely that it did not change: the `Exec` line
  must name `tray.py`. Byte-equality alone passes a file that has been wrong since it was
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
  The case **picks a free port itself** — bind a socket to port 0, read the
  number the kernel assigned, close it, and pass that concrete number as
  `LOTTO_PORT` — rather than running the server on 4322, where a developer with
  their own tray up fails this check for a reason unrelated to the contract.
  It must be a concrete number and not `LOTTO_PORT=0`: §4.8 has `serve.py` build
  the `Host` allowlist from that same value, so port 0 would produce the
  allowlist `{"127.0.0.1:0", "localhost:0"}` and answer 421 to everything, and
  nothing in this design reports a kernel-assigned port back to the parent.
  Two conditions make it runnable inside a headless exit-code script beside the
  other four `tools/verify_*.py`, and both are requirements on the code rather
  than on the test: the spawn/reap contract lives in `supervise.py`, which is
  Qt-free (driving it through `tray.py` would need a `QApplication` and a
  display), and `serve.py` honours `LOTTO_NO_BUILD` (§4.1). Without the second,
  this one case would cost the 27 requests and the real dump that §7's other two
  constraints forbid.
  *Breaks when:* the child is left to `SIGHUP`, or `terminate()` is sent without
  a `kill()` fallback and the server is mid-build in a non-interruptible fetch.

- **INV-21** — No ticket data appears in any URL, fragment or page `<title>`,
  and every response carries `Cache-Control: no-store`.
  *Test:* `tools/verify_page.py`, case `nothing_in_the_url` — asserts `GET /`
  serves a byte-identical body with and without a query string appended, and
  that `GET /status` returns the same JSON key set and the same `stale` value
  either way (its `built` and `building` legitimately move between calls, so
  byte-equality there would be flaky rather than strict). It asserts the
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
- **`LOTTO_NO_BUILD` is set** (§4.1 — it exists for INV-20's case, not for
  users). The page renders that same empty state with an explicit *"no build
  was performed"* notice. This is the one situation in which an empty page is
  correct, and it is not an exception to INV-18: nothing was ever built, so
  there is no previous model to lose. The notice is what keeps it from reading
  as "no wins".
- **No system tray on the desktop.** `QSystemTrayIcon.isSystemTrayAvailable()`
  is false: the tray reports it and exits non-zero, as the stats tray does.
  `serve.py` is unaffected, which is the point of INV-19.
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
  nothing extra unless the user presses Refresh. §4.1's `GET /status` poll is
  loopback-only and runs at 2 s **only while a build is in flight**, so it costs
  the operator nothing and the machine one loopback request per two seconds of
  build; an idle page polls nothing. Not stated as a count, because the count is
  a function of the wall-clock §4.2 explicitly declines to assert.
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
| §4.4 anti-framing headers on every response | `tools/verify_page.py::host_allowlist` |
| §4.4 the `.desktop` `Exec` naming `tray.py`, not the writing module | `tools/verify_page.py::no_reflected_headers` — §4.7's body is asserted byte-for-byte |
| §4.1 `page.py` performing no I/O | `tools/verify_page.py` — every case renders with `all_draws` replaced by a double that raises (the seam INV-15 already needs). Absent that double the row would be false: with no `archive_results.json`, `history.all_draws()` falls straight through to `api_draws()`, which **succeeds** on a connected machine, so a renderer calling it would pass |
| §4.4 `secrets.compare_digest` rather than `==` | **nothing** — the two agree on every input and differ only in timing, so no black-box case can tell them apart; code review only |
| §4.1 the model's key set | **nothing** — a builder and a renderer that agree on a wrong shape are consistent with each other, and every fixture is written to the same shape |
| §4.2 the 27-request figure staying true | **nothing** — a dated measurement; a larger dump or an API paging change moves it without failing anything |
| §4.5 the page being *readable* — ordering, filters, marking near-expiry | **nothing** — no check can tell a clear layout from a cluttered one |
| §4.7 the written `.desktop` file actually autostarting on this desktop | **nothing mechanical** — it depends on the session's XDG implementation; verified by logging out once |
| §4.4 the token surviving a browser that strips custom headers | **nothing** — no such browser is known, and the failure is visible (403 on every toggle) rather than silent |

Twenty-two rows, six `nothing`.

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

**Recommended before implementation: split this document in two.** At 1,143
lines it is past the review gate's design point, and §13 records why that is a
conclusion rather than an impression — three loops did not exhaust it and the
last two produced more defects from their own fixes than from the draft. The
seam is clean, and it is the one the invariants already fall along:

| Part | Sections | Invariants |
|---|---|---|
| the page and its security boundary | §4.1–§4.7 | INV-12 – INV-18, INV-21 |
| the tray, the supervisor and the headless contract | §4.8 | INV-19, INV-20 |

Each part then runs the gate from loop 1 on its own bytes; the parent's loops
were run against a document that would no longer exist. This is a
recommendation, not a decision — LOTTO-0002 is one roadmap item and splitting it
means allocating a second id, which is the user's call.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 3 | 2026-08-02 | 2 | 2 | 8 | 11 | 5 | **Converged by cap, and by the collateral trigger — both fired together.** All 26 verified findings fixed; 0 unverified, 0 deferred. Origin split: **≈19 fix collateral against ≈7 draft defects**, after loop 2's 14-against-13 — collateral outnumbering draft defects two loops running, which is the stop-and-consolidate signal, reached on the same pass as the 3-loop cap. Both lanes led on the same CRITICAL, and it was a duplicate paragraph loop 2 created: §4.1 gained a "`page.py` … has exactly four jobs and no others" paragraph including the `GET /status` poll, while the original "exactly three things and nothing else" paragraph was left in place eight lines below. Both closed forms, contradicting each other, and the later one ships a page permanently stuck on *building* — the document even states that consequence between them. Deleted. Second CRITICAL, also collateral: loop 2 required INV-20 to bind `LOTTO_PORT=0` while §4.8 builds the `Host` allowlist from that same value, so the allowlist would read `127.0.0.1:0` and 421 everything, and nothing reports a kernel-assigned port back — the case now picks a concrete free port itself. The `.desktop` bytes had drifted into two disagreeing verbatim copies (quoted in §4.7, unquoted in §4.4) under an invariant asserting them byte-for-byte, so §4.7 is now the only statement of them; and loop 2's own `sys.executable`-not-`python3` rule was contradicted four paragraphs later by the `Exec=python3` line it wrote, in the autostart path the rule exists for. **Three findings were caught by running rather than reading:** `Path.mkdir(parents=True)` raises `FileExistsError` on the normal repeat case (needs `exist_ok=True`, else §6's 500 on every toggle after the first); `history.all_draws()` with no `archive_results.json` does not raise but falls through to a live API call that *succeeds*, so §11's new purity row credited a check that does not fire and now names the raising double instead; and `==` versus `secrets.compare_digest` is unobservable to any black-box case, so it moved out of INV-13's *Breaks when* into a `nothing` row rather than being claimed as tested. Genuine draft defects, all present since loop 1: INV-12's requests were all `GET /`, so a `Host` check written only into `do_GET` passed while both write routes stayed reachable; INV-13 never fired the *allowed* `Origin` row, so a handler rejecting every present `Origin` passed while every in-page toggle failed; INV-13's "wrong token" was unspecified and only a proper prefix catches `startswith`; INV-14 asserted a `.desktop` file no step created; and INV-15 asserted an amount cell no part of the design defined, now `won_cents: int\|None` with `None` and `0` deliberately distinct. Doc grew 1,057 → 1,143 lines. **The size is the finding.** Three loops have not exhausted it, the last two were majority self-inflicted, and 1,143 lines is past this gate's design point — the split recommendation is in §12 and on the ROADMAP bullet, and it is the next action on this document, not a fourth loop. |
| 2 | 2026-08-02 | 2 | 3 | 8 | 6 | 9 | All 26 verified findings fixed; 0 unverified, 0 deferred. **Roughly half were collateral from loop 1's own fixes — 14 against 13 draft defects — and they shared one root cause: the model dict passed between `serve.py` and `page.py` had never been written down.** Loop 1 moved reason-derivation into `page.py` (which §4.1 calls a pure function while `history.all_draws()` reads disk *and* network), changed §7's seam from a model to a builder, and added `supervise.py`; each of the three then contradicted passages elsewhere. Answered wholesale rather than item by item: §4.1 now defines the four modules, the I/O boundary, the model's key set and the complete environment contract, and the derivations moved to `serve.py`'s builder where they were always going to run. **Both lanes found the same CRITICAL, which loop 1 created:** INV-17 counted `urlopen` calls across two refreshes, but under the new stub-builder seam no request is ever issued — so the case could never *pass*, let alone fail for the right reason, and §11 credited it with catching the one bug §4.2 calls invisible from the page. Restated as the assertion that actually tests the contract: sentinel entries in all three memos, empty after a refresh. Second CRITICAL, also collateral: INV-14 claimed no request-derived value reaches a written file while §4.3 — added in loop 1 — has `/settings` write two request-derived booleans, so an implementer had to break settings writes or treat the invariant as decorative; now scoped to strings. **One genuine draft defect was the most serious security finding of the run:** no anti-framing header anywhere, so a hostile page could `<iframe>` the port, the `Host` allowlist passes because the header *is* the allowlisted value, the framed page holds the token in its own DOM, and the whole §4.4 boundary survives while the user clicks the autostart switch through an overlay. `X-Frame-Options: DENY` and `frame-ancestors 'none'` added and asserted in INV-12's case. Also draft defects: nothing ever polled `GET /status`, so the opening *building* page had no defined way to leave that state and the route had no consumer at all; `paid_lines` in §4.6's formula is not a `Ticket` attribute (verified — `parse()` passes `len(boards)` with Multiplay already expanded, so the two readings differ only on Multiplay tickets); `open_on_start` had no reader and no default; and INV-16's fixture held no unresolved ticket, so its "of resolved tickets" clause — added in loop 1 — could not fail, and the real dump supplies no case since it holds 0 unresolved. Lane B's open question about decorator-based memos was checked and closed: `grep -nE "lru_cache\|@cache\|functools\|cached_property" *.py` returns nothing, so §4.2's three dicts are provably the complete set, and that command is now in the document beside the figure it warrants. Doc grew 880 → 1,057 lines. |
| 1 | 2026-08-02 | 2 | 3 | 7 | 13 | 8 | All 31 verified findings fixed; 0 unverified, 0 deferred. **Both lanes independently found the same three CRITICALs, and all three were contract gaps that an implementer would have closed by weakening the security model.** (a) The tray has a *Refresh results now* item, which is a `POST /refresh`, and §4.4 generated the token inside a process the tray only spawns — so the one menu item that needed the token could not obtain it, and the cheap fix is exempting `/refresh`. The channel is now specified (`LOTTO_TOKEN` in the child's environment; env rather than argv, which `ps` exposes, and rather than a file, which outlives the run). (b) §4.4 built the autostart `.desktop` from `os.path.abspath(__file__)`, but the writer is `serve.py` while the setting is "start the **tray** at login" — the switch would have autostarted a headless server and no icon would ever have appeared, and §11 already admitted nothing mechanical catches a wrong autostart. `Exec` now names `tray.py`, and INV-14 asserts the file's content outright rather than only that it did not change: byte-equality passes a file wrong since first written, which is exactly this bug. (c) §7's test seam took a finished model (`make_server(model, …)`), leaving `POST /refresh` nothing to invoke — so INV-17 and INV-18 had no rebuild to exercise and INV-15 needed a stubbed `all_draws`, three of ten cases untestable while §11 credited the script with locking them. The seam is now the builder. **One lane finding was upheld with its reasoning replaced by measurement:** INV-14's fixture was called vacuous because raw CRLF supposedly draws a 400 before the handler runs. Measured on 3.13 — no 400: the request line is truncated, the handler sees path `/a`, the injected line is swallowed as a malformed header and the response is an ordinary 200. Vacuous for the opposite reason, and the fix (percent-encoded `%0d%0a`, which *does* arrive intact) is the same either way. Also fixed: §4.6 dropped LOTTO-0009 §4.7's "only when the price resolves" qualifier and left an unresolved ticket's rendering undefined on a money display; two privacy defects that `tools/verify_privacy.py` cannot see because it compares against the dump's text rather than what the text implies (a purchase week plus draw count over a two-ticket population, and one win's exact amount with a derivable draw date); `check.py::uncheckable_report()` was named as the source of §4.5's per-entry reasons when its `too_old`/`no_pool` are integers, so `page.py` now recomputes them; the `refresh()` sketch was synchronous with no lock and no `try` while the prose two paragraphs above promised a background thread and a lock, and INV-18 depends entirely on the exception path it omitted; `/settings` had no request body format and no client-side JS was mentioned though three features require it; and four section cross-references were off by one, all landing an implementer chasing the settings contract in the money section. **The sweep caught one defect created by these fixes**: requiring a Qt-free spawn/reap module for INV-20 left it absent from §4.1's file list — now `supervise.py`. Doc grew 624 → 880 lines. |
