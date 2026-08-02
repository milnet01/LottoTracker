# LOTTO-0013 — Tray icon and server supervisor for the local page

**Status:** amended (2026-08-02), **§4.6 and INV-23 specified and not yet
implemented** — added for ROADMAP LOTTO-0018 (the tray reporting a refresh
before it has happened, and reporting a failure as a success). Until that lands,
`supervise.py` has no `refresh()`, `status()` or `REFRESH_MESSAGE`,
`tray.py::refresh()` still notifies when the POST returns, and
`tools/verify_page.py` holds ten cases rather than eleven. **Everything about
the four refresh outcomes describes what is to be built** — §4.6 entire, INV-23,
§4.1's two new methods, §6's four refresh bullets, §10's poll ceiling, §7's case
and counts, and §11's four new rows. Everything else here is accepted
(2026-08-02) and shipped.

**Eight cold-eyes loops in all** — three before implementation (converged by cap
and by the collateral trigger), two re-gate loops that the settings-reader
amendment's implementation forced, and loops 6, 7 and 8 gating this one, which
converged at the 3-loop cap with no finding outstanding. 148 verified
findings fixed, 2 dismissed on evidence, 0 deferred; 1 code gap filed as
LOTTO-0017 rather than fixed in a documentation pass. The gate stopped after the
second re-gate loop by the user's decision rather than at the 3-loop cap: no
verified finding was outstanding and CRITICALs had gone 1 -> 0, so what was
declined is one further cold read, not a known defect.
See §13.
**Kind:** implement.
**Source:** ROADMAP LOTTO-0013 — split out of LOTTO-0002 on 2026-08-02 per that
spec's §12, which recommended the split along this seam. The scope decisions in
§3 were taken with the user on 2026-08-01 and 2026-08-02 against the
undivided item.

**Pairs with:** LOTTO-0002 (the model and what the page shows) and LOTTO-0014
(the HTTP surface and security boundary) — the other two parts of the same
split, and together the thing this one starts, stops and points a browser at.
All three ship together.

*Layman: the icon next to the clock that starts the page, opens it, refreshes it
and shuts it down again — and the guarantee that nothing is left running behind
it.*

## 1. Goal

After this ships, an icon sits by the clock. Left-clicking it opens the page;
right-clicking gives a menu — Open page, Refresh results now, Stop/Start server,
Quit. The server is a child process the icon owns: it starts when the tray
starts, and quitting the tray leaves nothing behind holding the port.

`supervise.py` holds the whole lifecycle — the token, the port, the spawn and
the reap — in a module with no Qt in it, so the contract can be driven from a
headless exit-code script. `tray.py` is the menu and the icon and nothing else.
And `serve.py` stays free of Qt at every depth, so the page can still be served
over SSH, from a systemd unit, or on a machine with no tray at all.

## 2. Problem

LOTTO-0002 specifies a long-running local server and no lifecycle for it. Three
consequences, and the second and third are why this is a spec rather than a
menu:

1. **Nothing starts or stops it.** The page's server is a process that must
   outlive the command that launched it; without a supervisor the user keeps a
   terminal open for it and closes the page by finding the process.
2. **The token cannot reach the tray by accident.** LOTTO-0014 §4.3 requires a
   per-run token on every state-changing request, and the tray's *Refresh
   results now* item is exactly that — a `POST /refresh`. The token is minted
   inside a process the tray only spawns, so unless the channel is specified,
   the cheapest way to make the menu item work is to exempt `/refresh` from the
   token check, which deletes the defence for the one route that re-fetches
   (LOTTO-0014 §4.3 records how that gap was found). This spec is where the
   channel now lives.
3. **A lifecycle written into `tray.py` cannot be checked** — it would need a
   `QApplication` and a display inside a headless exit-code script. §4.1 states
   the argument and the remedy; it is why `supervise.py` is a separate module at
   all.

The headless direction is the one that fails silently. A developer machine has
Qt installed, so an accidental `serve.py → PySide6` import is invisible until
someone runs the server over SSH — which is precisely the case the split with
LOTTO-0002 exists to keep working.

## 3. Scope decisions

**From ROADMAP LOTTO-0002, taken with the user 2026-08-01 — not re-litigated
here:** the tray is required rather than optional, and is how the server is
started, stopped and the page re-opened; it is PySide6, which is already
installed (6.11.0, `python3 -c "import PySide6; print(PySide6.__version__)"`,
2026-08-02) and is what the user's existing stats tray uses; and `serve.py` must
not import PySide6.

**Taken with the user 2026-08-02:**

- **The tray launches `serve.py` as a child process** — chosen over a systemd
  user unit (the shape the user's own
  `Ants_Projects_Hub_Website/tray/ants-stats-tray.py` uses) because it needs no
  install step: clone the repo, run the tray. The cost accepted is that the
  server's lifetime is the tray's, which §4.3 makes explicit in the menu wording
  rather than leaving as a surprise. A unit remains possible for anyone who
  wants one, which is what INV-19 protects.

**Taken as part of the split, 2026-08-02:** this document owns INV-19 and
INV-20 (§5 maps the rest). All three parts are implemented in one change and
share one test script (§7).

## 4. Design

### 4.1 Three files, and the direction of the dependency

```text
supervise.py  stdlib only. Mints the token, resolves the port, spawns and
              reaps the server child, and READS the two settings — the paths
              and the reader, not their format (LOTTO-0002 §4.7 owns that).
              Never imports PySide6, serve or page.
tray.py       PySide6. The menu and the icon, and nothing else. Imports
              supervise; never imports serve or page.
icons/        tray-running.svg, tray-stopped.svg — read by tray.py only.
```

The arrow runs one way — `tray.py → supervise.py → (a child process)` — and
never back. **`serve.py → supervise.py` is a second edge into this module and
the graph is still acyclic**: `serve.py` imports the settings paths and reader
named below, and `supervise.py` imports nothing of LOTTO-0002's. That edge is
load-bearing rather than incidental — it is what makes "one reader" true instead
of aspirational, and an implementer who reads this section as forbidding it
writes the duplicate reader that §11 records as caught by nothing. What `supervise.py` must
never import is Qt, `serve` and `page`; being imported *by* `serve.py` breaks
none of that, because the import is one way. `supervise.py` reaches the server the same way the browser does,
over HTTP on 127.0.0.1, so there is no second code path that can disagree with
the page about what a refresh did. That is the property the user's existing
stats tray already relies on (`post_refresh()` in
`Ants_Projects_Hub_Website/tray/ants-stats-tray.py` POSTs to the same route its
dashboard page does).

**The settings reader lives here because of that arrow, and this is the
document that says so.** `config_home()`, `autostart_path()`, `settings_path()`
and `read_settings()` are `supervise.py`'s. `tray.py` has to read
`open_on_start` at startup (§4.3) and may not import `serve`, so a reader living
in `serve.py` leaves only two ways out, and both are worse: the import this
section forbids, or a second copy of the read in the tray. **Writing stays in
`serve.py`**, because `POST /settings` is a server route and the write needs the
lock that serialises two concurrent toggles — a lock the tray has no business
holding. So the split is by verb, not by file: one reader, one writer, and the
reader is the shared one because it has three callers — the tray at startup, the
model builder on every build, and the settings route re-reading after it writes.
That is what LOTTO-0002 §4.7's "same fallback binds all three" assumes: three
callers of one function, not three implementations of one rule. A second
implementation satisfies every case in `tools/verify_page.py` on the day it is
written and diverges later, which is why §11 tabulates it as unchecked rather
than as covered.

**`supervise.py` exists so INV-20 is testable**, and that is its whole
justification as a separate module. Putting the spawn-and-reap contract in
`tray.py` would make its check import PySide6 and need a running display,
inside a script that has to sit beside four headless `tools/verify_*.py`.
Splitting it out costs one small module and buys a testable lifecycle; it also
lets someone with no tray supervise the server from a script.

**The supervisor's whole surface is below, and it is the only place this
document states it.** §4.2 explains the rules behind it in prose and does not
restate the signatures — two copies of one contract is what a reader has to
reconcile, and reconciling them is how they drift.

```python
class Supervisor:
    """Owns the token, the port and the child process. No Qt anywhere."""

    def __init__(self, port=None)   # port or $LOTTO_PORT or 4322 (§4.5)
    port: int                       # the resolved port (§4.5); also what start()
                                    # puts in the child's LOTTO_PORT
    url: str                        # "http://127.0.0.1:<port>" — what the tray opens
    token: Optional[str]            # minted by start(); None while stopped
    child: Optional[Popen]          # the server process; survives stop() (INV-20)
    port_fallback: Optional[str]    # set when the requested port was unusable —
                                    # $LOTTO_PORT or the constructor argument,
                                    # which take the same validation path (§4.5)

    def start(self) -> None         # spawn the child; no-op if already running
    def is_running(self) -> bool    # child is not None and child.poll() is None
    def is_ready(self, timeout=10.0) -> bool   # child is ANSWERING on the port
    def stop(self, timeout=5.0) -> None        # terminate(), kill(), then wait()
    def post(self, path, timeout=300.0) -> str # POST carrying X-Lotto-Token
    def status(self, timeout=5.0) -> dict      # GET /status, parsed. No token:
                                               # it is a GET (LOTTO-0014 §4.1)
    def refresh(self, timeout=300.0, interval=2.0) -> str
                         # POST /refresh, then WAIT for the build to finish.
                         # Returns one of the four outcomes below (§4.6).
                         # `timeout` is ONE deadline over the whole call; the
                         # POST and each poll get what is left of it, capped.

POST_TIMEOUT = 30.0      # the refresh POST's own ceiling. It is answered without
                         # touching the build, so waiting longer on it only
                         # delays saying the server is not answering (§4.6).

REFRESH_DONE, REFRESH_FAILED, REFRESH_RUNNING, REFRESH_BUSY  # the four outcomes
REFRESH_MESSAGE: dict    # outcome -> the sentence the tray shows. Here rather
                         # than in tray.py so INV-23's wording half is checkable
                         # without a display (§4.6).

def free_port() -> int   # bind :0, read the number, close. Module-level, not a
                         # method: INV-20's case needs a port BEFORE it has a
                         # Supervisor to ask, and it must be a concrete number
                         # rather than LOTTO_PORT=0 (§5).
```

**`Optional[str]`, not `str | None` — a rule about notation, binding on any
annotation that is ever added.** The block above is this document's sketch of
the surface; the shipped module carries no annotations at all, so nothing in it
is subject to this today and no `typing` import is being asked for. The rule
exists for the moment someone adds one: README.md and CLAUDE.md both claim a
Python 3.8 floor, and a bare `X | Y` in a class body is evaluated at import and
raises `TypeError` before 3.10. The floor is asserted rather than tested, and
LOTTO-0014 §4.2 already declines a stdlib constant on the same ground; a type
annotation is not the place to break it either.

**`token` is a plain attribute, and a driver talking to a server it did not
spawn may set it.** `start()` is its only *minter*, and that is the rule the
per-`start()` paragraph below is about; it is not a rule that nothing else may
assign it. INV-23's case needs exactly this — a `Supervisor` pointed at the
in-process server §7's `serve_on()` already stands up, which mints its own
token and spawns no child — and a `token=` constructor argument would widen the
shipped surface for one caller that can write one line instead.

**`stop()` clears `token` and leaves `child` set.** The token must not outlive
the run that issued it; the finished `Popen` must survive, because INV-20's case
inspects `child.returncode` after `stop()` returns and there is nothing else to
inspect it on. `start()` replaces `child` with the new process.

**`post()` raises on anything that is not a 2xx** — `urllib` does this by
default and the contract keeps it, so a 403, 409, 500 or timeout arrives as an
exception whose text becomes the notification's message via §4.3's
`finished(ok, msg)`. On success it returns the response body as text. Calling it
while `token is None` (i.e. stopped) also raises rather than sending an
unauthenticated request — but a `RuntimeError` of its own, not a `urllib` error,
because nothing was sent and there is no response to report. **`refresh()` is the one caller that does not let all of that through** — §4.6
owns which status it catches and why.

**`status()` is the read half, and it carries no token** — `GET /status` is
open, since LOTTO-0014 §4.3 guards POSTs only. It parses the JSON rather than
returning text, because its callers branch on two of its keys; a malformed body
or an unreachable server raises, and §4.6 says what `refresh()` does with that.
It is the same route `is_ready()` already polls, for the same reason — it is the
one cheap answer this server gives — but **`is_ready()` must not be refactored
onto it**: readiness counts *any* HTTP status as an answer, including the 421
and 500 that `status()` raises on, so the obvious dedup would make a server that
answers 421 look like one that is not listening.

**`is_running()` and `is_ready()` are different questions, and only the second
is safe to open a browser on.** `Popen` returns before the child has bound
anything, so `is_running()` is true during a window in which the port refuses
connections. `is_ready()` issues a loopback `GET <url>/status` **every 100 ms**
until it answers — **any** HTTP status counts as an answer, including a 421 or a
500, because the question is whether something is listening — or until the
timeout expires. **`/status`, not `/`, and the route matters:** `/` renders the
whole page, so polling it would build up to a hundred full renders per start to
answer a question about the socket. Each attempt carries its own one-second
socket timeout, so 100 ms is the gap between attempts rather than a guaranteed
cadence. **It also returns `False` the moment `is_running()` goes false**, so a
child that dies on an import error fails in milliseconds instead of consuming
the whole budget — which is why §6 splits *died* from *hung*. That is at most
100 requests per start; §10 holds the rest of what this half sends — the
Refresh POST and the `GET /status` poll §4.6 adds behind it.
Anything that shows the user the page — left-click, the `open_on_start` open at
startup, the Open page menu item — waits on `is_ready()`; only the icon state
reads `is_running()`.

**A 10-second readiness budget is only sufficient because `serve.py` binds
before it builds** — LOTTO-0002 §4.2's "Bind the port before the first build,
not after", which is what lets the server answer with a *building* page for the
thirty-odd seconds the first build takes. Against a build-then-bind server this
default would time out on every start, so the dependency is named here rather
than left for an implementer to discover from the symptom.

**Blocking calls run off the GUI thread — with two exceptions, and the second
matters more than the rule.** `start()`, `is_ready()` and `refresh()` are
dispatched through §4.3's `run_async()`, because a ten-second
`is_ready()` on the GUI thread freezes the menu on the application's most-used
interaction. `refresh()` is now the longest of them by a factor of thirty — 300 s against
`is_ready()`'s 10 s —
it waits out the build rather than the POST (§4.6) — so it is the one this rule
matters most for, and it is the only path by which the tray reaches `post()`. **The first exception is startup**: `main()`'s own `start()` runs
inline, before `app.exec()`, because there is no event loop yet to freeze and
the icon state and the `open_on_start` open both have to follow it in a known
order. Dispatched asynchronously there, the tray would race its own first
`sync()`. The rule governs the *menu items*, which run inside the event loop. **Every `stop()` is the second exception and runs synchronously** — on
the Quit item, on `aboutToQuit` **and on the Stop menu item**, `stop()` is
called inline and the caller waits out its reap. Quit's reason is that the
process would otherwise exit before `wait()` completed; the Stop item's is the
ordering that follows it — `sync()` and the *Server stopped.* notification both
describe a reap that must already have happened, and dispatched asynchronously
they would run against a child still being killed. The freeze is the same
accepted cost, and it is the same shape as `tray.py::toggle()`, which calls
`self.sup.stop()` inline and comments that it is synchronous like `quit()`. **That wait is up to *two* five-second timeouts, not one** —
`stop()` waits `timeout` after `terminate()` and, if that expires, `timeout`
again after `kill()` — so the worst case is ten seconds. Dispatched to a thread pool it would return
immediately, the event loop would end, and the process would exit before
`wait()` completed — producing precisely the orphan INV-20 forbids, on the
commonest exit path, in the one place §11 records that nothing checks. The
prior-art tray does the same thing for the same reason: its `quit()` calls
`systemctl("stop", UNIT)` inline before `QApplication.instance().quit()`. A
freeze of up to ten seconds while quitting — two five-second waits in the worst
case, and effectively instant whenever the child honours `SIGTERM` — is the
accepted cost.

**The token is minted per `start()`, not per process.** A Stop followed by a
Start is a new run and gets a new token, which is what makes the restart case
behave the way LOTTO-0014 §6 already describes for a tab left open across it:
the old tab's next toggle gets a 403 and is told to reload. Holding one token
across restarts would instead leave a stale page silently authorised against a
server it never received a token from.

### 4.2 The supervisor: token, port, spawn, reap

The one method worth writing out, because every rule below is visible in it
(§4.1 holds the rest of the surface):

```python
# supervise.py — module scope holds imports, HERE and the port constants, and
# no state or side effects: importing this file must not mint a token and must
# not spawn (§4.4). Constants are not state; nothing here reads the environment
# or touches the network at import time.
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PORT = 4322
MIN_PORT, MAX_PORT = 1024, 65535

    def start(self):
        if self.is_running():
            return
        self.token = secrets.token_urlsafe(32)   # per start(), not per process
        self.child = Popen(
            [sys.executable, os.path.join(HERE, "serve.py")],
            cwd=HERE,                            # see below — not optional
            env={**os.environ,
                 "LOTTO_TOKEN": self.token,
                 "LOTTO_PORT": str(self.port)})
```

**The channel is the environment**, and this is the second gap in §2 closed.
Not argv, which `ps` exposes to every user on the machine, while
`/proc/<pid>/environ` is
readable only by the owning user; and not a file, because a token on disk
outlives the run that issued it. A standalone `python3 serve.py` with no
`LOTTO_TOKEN` mints its own — LOTTO-0002's environment table holds that
behaviour and its defaults, and this spec does not restate them.

**Both paths are absolute and the interpreter is `sys.executable`, not
`"python3"`.** The tray is launched from an autostart entry whose working
directory is not the repository, so a relative `"serve.py"` fails in exactly the
configuration §4.5 adds; and the child must run under the interpreter the parent
is already using rather than whatever `python3` resolves to in a session `PATH`.

**`cwd=HERE` is load-bearing, and omitting it fails silently in the worst
possible way.** Fixing the *script* path is only half the problem: the data the
server reads is addressed relative to the working directory —
`history.py::ARCHIVE` is `"archive_results.json"`, `backfill.py::CACHE` is
`"archive_cache"`, and `tickets.py::load()` defaults to `"lotto_sms_raw.txt"`.
A child inheriting an autostart session's working directory finds none of them
and renders LOTTO-0002 §6's "the dump is missing" empty state. That is this
project's cardinal failure — "no data" reading as "nothing here" — arriving
through the one launch path this item adds, on a machine where running the same
server by hand from the repository works perfectly.

**Reaping is `terminate()`, then `kill()` after a timeout, then `wait()`.**
`terminate()` alone is not enough: the server may be mid-build inside a
non-interruptible fetch — LOTTO-0002 §4.2 measures a build at 27 requests
against a third-party API — and a child that ignores `SIGTERM` while blocked in
a socket read keeps the port. The `wait()` after the kill is what makes the
process actually reaped rather than left as a zombie the parent never collected,
and it is what INV-20 observes.

**The same reap runs on `aboutToQuit`, not only on the Quit menu item**, so a
session logout does not leave an orphan holding the port. A user who logs out
never clicks Quit, and that is the commonest way the orphan would be created.

### 4.3 The tray

`QSystemTrayIcon` with a right-click menu — **Open page**, **Refresh results
now**, **Stop server** / **Start server**, **Quit (stops the server)** — and
left-click opens the page. The wording of the Quit item states the consequence,
because §3's accepted cost is that the server's lifetime is the tray's, and an
icon that silently killed a server on quit would be the surprising outcome.

**The page is opened with `webbrowser.open(self.sup.url)`**, where `self.sup`
is the tray's `Supervisor` (`url` is an instance attribute, §4.1) — stdlib, and it
honours the desktop's default-browser setting the same way `xdg-open` does
without shelling out. It is called only after `is_ready()` returns true, so the
browser never lands on a port that is not answering yet; if `is_ready()` times
out, the tray says so in a notification instead of opening a tab on a refused
connection.

**The Refresh item calls `Supervisor.refresh()` and shows
`REFRESH_MESSAGE[outcome]`** — for each of the four outcomes it composes no
message of its own and reads no HTTP status. §4.6 owns the outcomes, their wording and why the wait is
not written here. **The one message the tray does build is the raise path**: a
403, a 500, a socket timeout or a dead child leaves `refresh()` with no outcome
to return, and the exception's text becomes `Refresh failed: <msg>` through the
`finished(ok, msg)` shape below — the same path every other blocking call
already uses. A rule that let the tray compose nothing at all would leave that
path silent, which is the cardinal failure §4.6 exists to close, arriving
through the fix for it.

Six details are copied from the user's existing stats tray, all six verified
in `Ants_Projects_Hub_Website/tray/ants-stats-tray.py` on 2026-08-02:

- **Long actions run on a `QThreadPool`**, never on the GUI thread. A refresh
  drives a rebuild that takes tens of seconds; doing it inline freezes the menu
  mid-click and makes Plasma offer to kill the application. The helper is
  `run_async(fn, on_done)`: it wraps `fn` in a `QRunnable`, starts it on
  `QThreadPool.globalInstance()`, and calls `on_done(ok, msg)` on the GUI thread
  — `ok` false and `msg` the exception text when `fn` raised. That is the shape
  of `run_async()` in the prior-art tray, and every notification in this section
  is an `on_done` callback.
- **A module-level set keeps each runnable's Python wrapper alive** while
  `QThreadPool` owns the C++ side (`_jobs` in that file). Without it the wrapper
  can be collected while the job is still running, which is a crash rather than
  a misbehaviour, and it is invisible in a short test.
- **`app.setQuitOnLastWindowClosed(False)`**, or dismissing a notification ends
  the application and takes the server with it.
- **The icon, the tooltip and the menu wording all state the same thing**, so
  the state is never read off a 22-pixel icon alone. The two tooltips are
  `Lotto Tracker — running on http://127.0.0.1:<port>` and
  `Lotto Tracker — server stopped`, matching the Stop/Start item's wording.
- **Open page and left-click are disabled while the server is stopped**, the
  same way Refresh is, rather than implicitly starting it or waiting out a
  ten-second `is_ready()` against a port nothing is listening on. Starting is
  what the Start item is for, and a menu that silently starts a server because
  the user asked to see a page is doing something they did not ask for.
- **One long action at a time**, guarded by a `busy` flag: the item that starts
  one is disabled and the tooltip carries the in-flight wording until it
  finishes — Refresh additionally relabels its own item to *Refreshing…* — and the
  state poll below returns early while it is set (`self.busy` in that file).
  Without it a second Refresh click queues a second job against a rebuild that
  is already running, which the server answers with LOTTO-0014 §4.1's 409. The
  guard is the tray's own half of that, and it stops at the tray's edge: the
  page's Refresh button POSTs the same route, so the 409 remains reachable and
  §4.6 owns what is said about it.

**State is polled, because the child can die without being asked to.** The tray
checks `Supervisor.is_running()` on a **5-second** `QTimer` — the interval the
stats tray uses (`POLL_MS = 5000`) — and updates icon, tooltip and the
Stop/Start wording from it, the same `sync()` shape as that file. Five seconds
is the budget: it bounds how long the icon can claim a dead server is running,
and it costs one `Popen.poll()` on a local process, which issues no request and
touches no socket. **The bound holds except while a long action holds `busy`**,
when this poll returns early and the action itself is what notices — during a
refresh that is one 2 s poll interval and not the 300 s budget, because §4.6's
case 1 raises the moment a `/status` poll cannot reach a child that has died. A server
that exited on its own (port taken, an unhandled error at startup) otherwise
leaves an icon claiming it is running, and the Refresh item failing for a reason
the user cannot see.

**`open_on_start` is acted on here, because `tray.py` is the file that acts on
it.** LOTTO-0002 §4.7 owns the setting — its path, its key, its default of
**true** and the fallback below — and this document owns what the tray does with
it: at startup, after `start()` and once `is_ready()` returns true, the tray
opens the page if the setting is true and does not if it is false. It gets the
value from `supervise.read_settings()` (§4.1) and never opens the file itself.
**A missing, unreadable or malformed `settings.json` falls back to the default
rather than raising** — one rule, stated by §4.7 and implemented once in the one
reader, so what is left to say here is the tray's *consequence*: a corrupt
settings file must never be the reason no icon appears. Without this paragraph
the setting has a writer (LOTTO-0002's settings panel) and nothing that acts on
what it reads.

**Two SVG icons, `icons/tray-running.svg` and `icons/tray-stopped.svg`,
resolved relative to `tray.py`** — `os.path.dirname(os.path.abspath(__file__))`,
not the working directory, which under §4.5's autostart entry is not the
repository.

### 4.4 The headless contract

`serve.py` imports no Qt, transitively — not directly and not through anything
it imports. The rule is stated here rather than in
LOTTO-0002 because it exists only because this spec introduces a Qt process at
all, and because it is what keeps the rejected systemd-unit shape (§8) available
rather than closed off.

**Everything in `serve.py` that binds, builds or serves sits behind
`if __name__ == "__main__":`.** That is a requirement on the code, not a note
about style: INV-19's check imports the module in a fresh interpreter and looks
at `sys.modules`, and without the guard that import blocks in `serve_forever()`.
A check that hangs reads as a broken test rather than a broken contract, so the
guard is what makes the invariant observable at all.

**The same two rules bind `supervise.py`**: it imports no Qt either, and
importing it must spawn nothing — which is why §4.2's sketch defines only
constants at module scope — the path and the port bounds, no state — and
mints the token inside `start()`. INV-19 covers both
modules, and the reason is §4.1's second edge: **`serve.py` imports
`supervise.py`**, so a Qt import here is a Qt import in `serve.py` at one
remove, and the headless server this whole contract protects would break without
anything in `serve.py` itself changing. (`tools/verify_page.py` imports it too,
which is why the case can reach it — but that is how the breach is *observed*,
not why it matters.)

### 4.5 One port, and the environment an autostarted tray inherits

`supervise.py` resolves the port once — `LOTTO_PORT`, default 4322 — passes it
to the child alongside `LOTTO_TOKEN`, and exposes `url` for the tray to open.
`serve.py` uses that same value both to bind and to build LOTTO-0014 §4.2's
`Host` allowlist. **A tray and a server disagreeing about the port fail as a 421
on every request** — the allowlist rejecting the very URL the tray just opened —
which is a confusing failure to debug and a trivial one to prevent by reading
the value once.

**An unusable `LOTTO_PORT` reaching `Supervisor` falls back to 4322 and says
so; it never raises.** (The standalone `python3 serve.py` path constructs no
`Supervisor` and does raise — LOTTO-0002 §6 owns that case and why a traceback
is the right answer there.)
A `ValueError` out of `Supervisor.__init__` means no icon appears at all, which
is the same outcome §4.3 refuses for a corrupt `settings.json`. Unusable means
non-numeric, or outside **1024–65535** — below 1024 a non-root tray cannot bind,
so accepting it only defers the failure to a confusing "port in use".
**Unset and empty are not unusable.** Both mean "no preference": they take the
default and set no `port_fallback` message, because there is nothing the user
got wrong to tell them about. Only a value that was *meant* as a port and cannot
be one produces the message. The
fallback is recorded on `port_fallback` (§4.1) rather than printed, because
`supervise.py` is Qt-free and has no notification channel of its own; `tray.py`
reads that attribute at startup and raises §4.3's notification. Recording it on
an attribute is what keeps the module Qt-free without swallowing the fact.

(4322 was chosen as free on this machine and adjacent to the user's stats
dashboard on 4321. Verified 2026-08-02: `ss -ltn` shows `127.0.0.1:4321`
LISTEN and a `socket.bind(('127.0.0.1', 4322))` succeeds.)

**The start-at-login entry is written by the page, not by the tray.**
LOTTO-0002 §4.7's settings panel owns `~/.config/autostart/lotto-tracker-tray.desktop`
— it holds that file's bytes verbatim and LOTTO-0014's INV-14 asserts them
byte-for-byte, so this spec does not restate them. Two obligations follow from
that entry naming `tray.py`, because it is what makes an autostart session a
launch path for this document's files at all:

- The autostart session's working directory is not the repository, which is why
  §4.2's paths are absolute and §4.3's icon paths resolve against `__file__`.
- The autostart entry carries no `LOTTO_PORT`, so an autostarted tray uses the
  default. Anyone overriding the port sets it in their session environment,
  where both the entry and a manual run inherit it.

### 4.6 Reporting a refresh, not merely starting one

**`POST /refresh` answers 202, and 202 means accepted rather than finished.**
`serve.py::refresh()` starts a daemon thread and returns at once (LOTTO-0002
§4.2), so the POST is answered in milliseconds while the build
behind it still has thirty-odd seconds to run. A tray that notifies when that
POST returns therefore says *Results refreshed.* before a single result has been
fetched — and says exactly the same thing when the build then raises, which four
of seven measured attempts did (LOTTO-0002 §4.2). **That is this project's
cardinal rule in notification form**: a failure reported as a success is worse
than a blank, because it stops the user looking. ROADMAP LOTTO-0018 records it
as shipped behaviour; this section is the fix.

**The honest signal already exists, and the page already uses it.** `GET /status`
reports `{building, built, stale}` (LOTTO-0014 §4.1). `State.begin()` sets
`building` **before** the POST is answered — so there is no window in which a
started build reads as idle — and `State.fail()` sets `stale` while leaving the
model untouched, which is what INV-18 rests on. A build's completion and its
outcome are therefore both observable from outside the process, and this section
adds no route, no state and no second opinion: only a wait on the signal
LOTTO-0002 §4.1 already has the page polling.

**The wait lives in `supervise.py` and the tray reports what it returns.**
`Supervisor.refresh()` POSTs, then polls `GET /status` until `building` goes
false, and returns one of four outcomes. **A 409 returns `REFRESH_BUSY` at once
and polls nothing** — the build it names is not this call's, and waiting on it
would report someone else's build as the answer to a request that was declined:

| Outcome | Reached when | What the tray shows |
|---|---|---|
| `REFRESH_DONE` | `building` false, `stale` false | Results refreshed. |
| `REFRESH_FAILED` | `building` false, `stale` true | The refresh failed. The page still shows what it had before, and says so. |
| `REFRESH_RUNNING` | the budget expired with no observation of `building` false | Still refreshing. The page shows the result when it finishes. |
| `REFRESH_BUSY` | the POST answered 409 | A refresh is already running. The page shows the result when it finishes. |

**`REFRESH_FAILED`'s sentence must not name a previous *model***, and that is
why it says *what it had before* rather than *the previous results*. A first
build that failed leaves `model is None` with `stale` true (LOTTO-0002 §6's
results-unavailable state), and a user Refresh that also fails reaches this same
outcome — so a sentence promising previous results would describe data the page
does not have, on the commonest failure path this project measures. The page is
unchanged and says why, in both states, which is what the wording claims and all
it claims.

Putting the wait here rather than in `tray.py` is §4.1's argument for the module
applied to the one piece of it that can silently lie: a wait written into the
tray needs a `QApplication` and a display to check, and §11 would record it as
another `nothing`. It runs through `run_async()` like every other blocking call.

**A timeout reports *still running* — never success, and never failure either.**
Nothing has been observed about a build that is still going, so both claims
would be invented. The budget is `post()`'s existing **300 s** rather than a
second number: a build is thirty-odd seconds and the API failed four of seven
attempts when measured, so the generous budget is the one that makes this
outcome rare, not the one that makes it frequent. **It is one deadline covering
the whole call**, not one for the POST and another for the poll — `refresh()`
starts its clock before the POST, issues that POST with the smaller of 30 s and
the budget remaining, and polls until the same deadline. Two independent 300 s
budgets would put the worst case at ten minutes with the tray's `busy` flag held
throughout, which is the wedge this bounded wait exists to prevent. **The 30 s
on the POST — `POST_TIMEOUT` in §4.1's block — is a socket budget, not a build
budget**: the handler answers
without touching the build — `serve.py::refresh()` starts the thread and returns
— so a POST unanswered after 30 s means the server is not answering at all, and
waiting the remaining 270 s would only delay saying so. **It is a ceiling with
no floor**, which is what keeps the one-deadline rule true: a caller passing a
`timeout` under 30 s gives the POST that smaller number, and INV-23's 0.5 s case
is safe on the same ground the 30 s rests on — the answer is a status line
computed without I/O, on loopback. A floor would let a call outlive its own
deadline. **Each poll's own 5 s socket timeout is clamped the same way**, to
whatever the budget has left, so the last poll cannot overrun the deadline it
was issued under. It raises like any other
POST failure and is reported as a failure; the build may nonetheless have
started, which the page will show, and reporting a failure the tray cannot
disprove is the one direction §4.6 permits — it is claiming success that is
forbidden. The flag
clears when `refresh()` returns, so the item comes back and a second click is
answered by the 409 path below rather than by a second build.

**The deadline is tested after a poll attempt, never before**, and the first
poll is issued immediately after the POST rather than one interval later. So
`REFRESH_RUNNING` always follows at least one attempt to look, and a build that
finishes in under one interval is reported as `DONE` on that first poll rather
than waited on. **An *attempt*, not an observation** — the poll-failure cases
below can consume the whole budget without a single `/status` answering, and
that run returns `REFRESH_RUNNING` too. It is the honest outcome in both
shapes: the tray knows the build has not been seen to finish, and does not know
that it failed.

**The poll cadence is 2 s, which is the page's** (LOTTO-0002 §4.1). One number
for one behaviour: `/status` is a constant-size JSON answer that builds nothing,
the notification's latency against a thirty-second build is irrelevant, and the
ceiling is §10's, not restated here. It is a gap
between attempts rather than a guaranteed cadence, each carrying `status()`'s
own **5 s** socket timeout — the same shape as `is_ready()`, whose gap is
100 ms and whose per-attempt timeout is 1 s. Two different budgets for two
different questions: readiness asks whether anything is listening at all and
wants to fail fast, the refresh poll is talking to a server it already knows is
up.

**A poll that fails is not by itself an answer — three cases, and only one of
them stops the wait.** A `status()` call can fail by being unreachable or by
returning a body that will not parse, and neither says anything about the build:

1. **The `Supervisor` owns a child that is no longer running** → `refresh()`
   raises at once rather than spending the remaining budget. The *died* against
   *hung* split §6 already draws for `is_ready()`. **The exception is a
   `RuntimeError("the server stopped while refreshing")`, not the `urllib` error
   the poll caught** — the same choice §4.1 makes for `post()` with no token,
   and for the same reason: its text is what the user reads
   (`Refresh failed: the server stopped while refreshing`), and
   `<urlopen error [Errno 111] Connection refused>` describes the socket rather
   than what happened. It is the one refresh sentence not in `REFRESH_MESSAGE`,
   because it is not an outcome — nothing was determined about the build.
2. **The child is alive** → keep polling to the deadline. One dropped loopback
   response, or one malformed body, is not evidence that a thirty-second build
   failed, and turning it into *Refresh failed* would report a verdict nobody
   observed.
3. **This `Supervisor` owns no child at all** (a script driving a server it did
   not spawn — INV-23's case is one) → it cannot ask question 1, so it behaves
   as case 2 and reports *still running* if the deadline arrives. That is the
   honest answer when nothing has been observed.

**409 is an outcome, not an error.** `post()` raises on anything but a 2xx
(§4.1), so a refresh requested while one is in flight surfaces today as the
notification `Refresh failed: HTTP Error 409: Conflict` — a status code shown to
a user, describing something that is not a failure and needs no action. The
tray's own busy guard does not prevent it: the page's Refresh button POSTs the
same route (LOTTO-0014 §4.1), so two clicks a second apart in two places reach
it. `refresh()` catches the 409 **alone** and returns `REFRESH_BUSY`; a 403 on a
stale token, a 500 or a timeout still raise and are still reported as failures.

**What is reported is the state of the data, not the fate of one attempt.** The
wait resolves on the first observation of `building: false`, and `stale` at that
moment is the flag of whichever build most recently finished. If the page starts
a second build in the gap, the outcome describes *that* build — which is the one
whose result is now on the page, so the report stays true of what the user would
see. Naming this rather than defending against it is deliberate: distinguishing
the attempts needs a build identity in the model, which LOTTO-0002 does not
carry and which would exist only to report on a result that has already been
superseded.

**The four sentences live in `supervise.py` too, in `REFRESH_MESSAGE`.** The
module already carries one user-facing string for exactly this reason —
`port_fallback` (§4.5), recorded on an attribute rather than printed because the
module is Qt-free and has no notification channel of its own. The wording
follows it for a second reason: a map from outcome to sentence in a Qt-free
module can be asserted by a headless case, which is what makes INV-23's wording
half checkable at all, where the same table inside `tray.py` needs a display to
read. **The wording rule is the cardinal one**: only `REFRESH_DONE` may read as
success. The other three name what is *not* known — a failure, an unfinished
build, someone else's build — and none of them may be phrased so that a user who
reads only the first few words takes it for a completed refresh.

## 5. Invariants

This document holds INV-19, INV-20 and INV-23. LOTTO-0001 holds INV-1 to INV-6
and INV-22, LOTTO-0009 INV-7 to INV-11, LOTTO-0014 INV-12 to INV-14 and INV-21,
and LOTTO-0002 INV-15 to INV-18. CHANGELOG.md cites them unqualified, so the
numbers do not move on a split.

- **INV-19** — Importing `serve.py` or `supervise.py` pulls in no Qt or PySide6
  module, starts no server and spawns no process.
  *Test:* `tools/verify_page.py`, case `serve_is_headless` — imports each module
  in a **fresh interpreter** (not the suite's own, which by then has imported
  whatever the other cases needed) and asserts three things about that
  subprocess: that its `sys.modules` holds no name containing `PySide` and no
  module whose **top-level package** is exactly `Qt`, that the import returns rather than blocking, and that it
  spawned nothing — observed by having the subprocess read
  `/proc/self/task/*/children` after the import and print it, so the parent
  asserts on an empty list rather than on the absence of evidence. Everything
  that binds, builds or serves sits behind `if __name__ == "__main__":`, which
  is what makes the import safe to perform at all; §4.4 states why.
  **The check sees import-time depth only.** A Qt import performed lazily inside
  a function body is invisible to it, and that limit is stated rather than
  papered over: what the case actually forbids is a module-level import, which
  is the shape the failure takes in practice.
  **It is PySide-shaped, and that is a live gap rather than a theoretical
  one.** A `PyQt6.QtCore` import satisfies neither test — the name contains no
  `PySide`, and its top-level package is `PyQt6`, not `Qt` — so it would pass a
  check whose invariant says "no Qt". Measured 2026-08-02: **PyQt6 6.x is
  importable on this development machine** (`/home/ants/.local/lib/python3.13/
  site-packages/PyQt6/`), so the breach is reachable today by anyone who reaches
  for the wrong binding. §3 pins the project to PySide6, which is why nothing
  imports PyQt now; the predicate should gain a `PyQt` arm, and until it does
  this paragraph is what stands between the invariant's wording and its reach.
  **Filed as ROADMAP LOTTO-0017**, which carries the fix and the red-test it
  needs — it is a code change and does not belong in a documentation pass.
  *Breaks when:* a shared helper grows a Qt import; `serve.py` imports `tray.py`
  for a constant such as the port default or an icon path; or `supervise.py`
  reaches for `QDesktopServices` instead of `webbrowser`. Invisible on a desktop
  with Qt installed, which is every desktop this is developed on — importing
  PySide6 headless **succeeds**, so nothing about running it elsewhere reveals
  the breach.

- **INV-20** — A `Supervisor` that started a server and then stopped it leaves
  no process holding the port.
  *Test:* `tools/verify_page.py`, case `no_orphan_server` — drives
  `supervise.Supervisor` to spawn a real child, **waits for `is_ready()` and
  fails if it never comes up**, then stops it and asserts three things, **in this
  order**: that the process is gone (`os.kill(child.pid, 0)` raises
  `ProcessLookupError` — polled for up to 5 seconds rather than once, since exit
  is not instantaneous, and `PermissionError` counts as gone because the pid has
  been recycled to another owner), that **its exit status was collected**
  (`child.returncode is not None`), and that the port accepts a fresh bind.
  **The order is the whole assertion, and getting it wrong makes the case
  self-satisfying.** `Popen.poll()` *reaps* — measured: `returncode` is `None`
  before the call and set after it — so checking "has it exited?" through
  `poll()` or `is_running()` collects the status itself, and the returncode
  assertion that follows can then never fail. `os.kill(pid, 0)` is the
  independent observation: it succeeds against a zombie, because the pid is still
  in the process table, and raises once the status has been collected — and it
  never reaps. Without this ordering the invariant's headline promise is
  unchecked, since an unreaped zombie has exited and holds no socket, satisfying
  a naive version of all three assertions exactly as a properly reaped child
  does.
  **The readiness wait is what stops the case being a tautology.** Without it, a
  `serve.py` that dies instantly on an import error satisfies both closing
  assertions — the process has certainly exited and the port is certainly free —
  so the case would pass against a server that never worked at all. It is the
  same trap `tools/verify_coverage.py` was rewritten to escape, and it is the
  likelier failure here than a genuine orphan.
  **The confirming bind retries for up to 5 seconds** rather than asserting on
  one attempt, and it sets `SO_REUSEADDR` — which is what makes the retry short.
  The obvious reason to give is `TIME_WAIT`, and it is **wrong**: measured
  2026-08-02, a bind with `SO_REUSEADDR` over a socket confirmed in `TIME_WAIT`
  by `ss -tan` **succeeds**. The retry covers the real window instead — between
  the parent collecting the exit status and the kernel finishing its teardown of
  the listening socket — which is short, and unbounded only if something else
  genuinely holds the port, which is the failure the assertion is for.
  The invariant is worded as the *supervisor's* contract, not the tray's,
  because that is what the case can drive: reaching the Qt shutdown path needs a
  `QApplication` and a display, and §11 records that as an unchecked gap rather
  than claiming this case covers it.
  The case **picks a free port itself** — `supervise.free_port()` (§4.1) binds a
  socket to port 0, reads the number the kernel assigned and closes it, and the
  case passes that concrete number to `Supervisor(port=…)`, which is what puts
  it in the child's environment as `LOTTO_PORT` (§4.2) — rather than running on
  4322, where a developer with their own
  tray up fails this check for a reason unrelated to the contract. (The gap
  between closing that probe socket and the child binding is a race the readiness
  wait already absorbs: if something else took the port, `is_ready()` never
  succeeds and the case fails loudly rather than silently measuring nothing.)
  It must be a concrete number and not `LOTTO_PORT=0`: §4.5 has `serve.py` build
  the `Host` allowlist from that same value, so port 0 would produce the
  allowlist `{"127.0.0.1:0", "localhost:0"}` and answer 421 to everything, and
  nothing in this design reports a kernel-assigned port back to the parent.
  Two conditions make it runnable inside a headless exit-code script beside the
  other four `tools/verify_*.py`, and both are requirements on the code rather
  than on the test: the spawn/reap contract lives in `supervise.py`, which is
  Qt-free (§4.1), and `serve.py` honours `LOTTO_NO_BUILD` (LOTTO-0002 §4.1).
  Without the second, this one case would cost the 27 requests and the real
  ticket dump that §7's constraints forbid.
  *Breaks when:* the child is left to `SIGHUP`; `terminate()` is sent without a
  `kill()` fallback and the server is mid-build in a non-interruptible fetch; or
  the reap is wired to the Quit menu item alone, so a session logout — the
  commonest exit, and the one nobody clicks Quit for — orphans the child.

- **INV-23** — A refresh is reported as *done* only after the build it refers to
  has finished, and a build that failed, that is still running or that was never
  started is never reported as a success. (The other three outcomes are reports
  too, and three of the four are issued while a build may still be going — what
  the invariant forbids is calling any of those a completed refresh.)
  *Test:* `tools/verify_page.py`, case `refresh_reports_the_build` — drives
  `supervise.Supervisor.refresh()` against **two** in-process servers on
  ephemeral ports (§7's `serve_on()` stub-builder seam: no child, no network, no
  real data), one whose stub builder waits on a `threading.Event` the case
  controls and one whose builder raises. Two rather than one because
  `make_server()` binds its builder at construction and `POST /refresh`
  re-invokes that same callable, so a single server cannot both block and raise;
  the event is `clear()`ed again between uses so the builder blocks afresh, which
  is what lets the blocking server serve assertions 1, 2, 4 and 5. It asserts five things about the wait and two
  about the wording:
  1. with the builder still blocked, a `refresh()` running on its own thread
     **has not returned** after three poll intervals — the case passes
     `interval=0.2`, so this costs 0.6 s rather than the 2 s cadence §4.6 pins
     for the tray;
  2. once the builder is released it returns `REFRESH_DONE`;
  3. against the raising builder it returns `REFRESH_FAILED` — the outcome only,
     since INV-18 and `failed_refresh_keeps_model` already own the claim that
     the previous model survives, and a server whose bound builder raises on
     every call has no previous model to survive;
  4. against a builder still blocked when a deliberately short `timeout`
     (0.5 s, against the same 0.2 s interval, so at least one poll happens)
     expires it returns `REFRESH_RUNNING` — neither DONE nor FAILED;
  5. a second `refresh()` issued while that build is in flight returns
     `REFRESH_BUSY` rather than raising `HTTPError`, and returns it without
     waiting for the build it was refused behind.
  Then, with no server at all: every outcome has a non-empty sentence in
  `REFRESH_MESSAGE`, and no sentence but `REFRESH_DONE`'s contains any of
  `refreshed`, `updated`, `up to date` or `success` — **case-folded**, or a
  sentence opening *Refreshed…* passes a check written against the lower-case
  form.
  **The first assertion is the one that states the property** — it observes
  *reported* against *finished* directly, where the others catch the same defect
  through the outcomes a missing wait gets wrong. §7's `notify_on_202` bullet
  works that through assertion by assertion; it is not restated here.
  **The wording half is not decoration.** The timing half guarantees only that
  the notification arrives at the right moment; nothing in it stops all four
  outcomes from being phrased as success, which is the same cardinal breach one
  layer up. Keeping the sentences in Qt-free `supervise.py` (§4.6) is what lets
  a headless case assert this at all.
  *Breaks when:* the wait is dropped and the 202 is treated as completion (the
  shipped behaviour, `--break notify_on_202`); the wait polls correctly but
  ignores `stale`, so a failed build reads as a completed one
  (`--break stale_is_success`); or a non-DONE outcome is given success wording
  (`--break success_wording`). Two of the three are silent by construction — the
  user is told the thing they wanted to hear — and the third is silent until a
  build actually fails, which is four times in seven.

## 6. Failure modes

- **No system tray on the desktop.** `QSystemTrayIcon.isSystemTrayAvailable()`
  is false: the tray reports it and exits non-zero, as the stats tray does.
  **That check runs before `Supervisor.start()`**, which is an ordering
  requirement rather than a stylistic one — starting the server first and then
  exiting non-zero orphans a live child holding the port, an INV-20 breach on a
  documented failure path. The prior-art `main()` checks availability before it
  constructs the tray. `serve.py` is unaffected, which is the point of INV-19.
- **The port is already in use.** The child exits with the port in its message
  rather than tracebacking (LOTTO-0002 §6 owns that behaviour); the supervisor
  sees a child that is no longer running, and within one poll interval the icon,
  the tooltip and the menu wording all say *stopped* instead of claiming to be
  running. This is the case §4.3's polling exists for. **The poll changes state;
  it raises no notification** — §4.3 gives it icon, tooltip and wording and
  nothing else, and a notification on a transition nobody asked for would fire
  on every ordinary Stop. What notifies is an action the user took: Open page,
  Refresh, Start.
- **The child dies on its own, for any other reason.** Identical handling — the
  poll notices, the icon and menu wording change, and the Refresh item is
  disabled rather than failing when clicked.
- **The session logs out without a Quit.** `aboutToQuit` runs the same reap
  (§4.2). If the session is killed hard enough that no Qt shutdown signal fires,
  the child is orphaned and the next start reports the port in use — which is a
  visible, recoverable state rather than a silent one.
- **`terminate()` does not stop the child.** `kill()` after the timeout, then
  `wait()`. The user sees the quit take up to two timeouts (ten seconds, §4.1)
  rather than the tray vanishing and the server surviving it.
- **The child died.** An import error in `serve.py`, or a `SystemExit` because
  the port was already bound. `is_ready()` returns `False` at once rather than
  waiting out its budget, because it re-checks `is_running()` on every attempt
  (§4.1). The tray reports it and leaves the icon in its stopped state.
- **The child is alive but never answers.** A machine under enough load to miss
  the window, or a bind that succeeded against a socket nothing then served.
  Here `is_ready()` does spend its full timeout. Same outcome for the user —
  reported, icon stopped, no browser tab on a refused connection — but a
  different wait, which is why the two are separate bullets. Both are the case
  the `is_running()` / `is_ready()` split (§4.1) exists for.
- **A refresh fails.** The build raises — 27 requests against a third-party API
  that failed four of seven attempts on 2026-08-02 (LOTTO-0002 §4.2, §6) — and
  `GET /status` reports `building: false` with `stale: true`. `refresh()`
  returns `REFRESH_FAILED` and the tray says so, naming that the page still
  shows what it had before — which is the previous model, or LOTTO-0002 §6's
  results-unavailable state if the first build was the one that failed, and the
  sentence is worded to be true of both (§4.6). This is the failure mode the item exists
  for: it is silent by construction, because the user was already told it
  worked.
- **A refresh is still running when the wait runs out.** `refresh()` returns
  `REFRESH_RUNNING` after its 300-second budget and the tray says *still
  refreshing* — which claims only that the build has not been seen to finish,
  and is true whether the polls answered or not (§4.6). The busy flag is cleared and the
  menu item comes back either way, so no outcome wedges the one-job-at-a-time
  guard; without a bounded wait it would be wedged permanently.
- **A refresh is declined because one is already running.** The 409 of
  LOTTO-0014 §4.1, reachable from the page's own Refresh button even while the
  tray's busy guard holds. `REFRESH_BUSY`, reported as *already running* rather
  than as the HTTP status it is (§4.6).
- **A refresh raises for any other reason** — a 403 on a stale token, a 500, a
  socket timeout, or the child dying mid-build. The busy flag is cleared, the
  menu item is re-enabled with its normal wording, and the exception's text goes
  into a notification through the `finished(ok, msg)` shape of the stats tray.
  The dying-child case is detected by the poll rather than waited out (§4.6).
- **No browser could be opened.** `webbrowser.open()` returns false or raises:
  reported in a notification with the URL, so the user can paste it. The server
  is unaffected and the icon keeps its running state, because the server *is*
  running — a failure to open a browser is not a failure of the server.
- **PySide6 is not installed.** `tray.py` fails at import with the standard
  `ModuleNotFoundError`. Nothing else in the project imports it, so `check.py`,
  the four existing `tools/verify_*.py` and the headless `serve.py` path are
  unaffected — CLAUDE.md's claim that the project is "Pure Python 3.8+ standard
  library plus `dbus-python`" stays true for everything except this one file.
  (README.md:55's own line is narrower — "Needs Python 3.8+ and a Linux desktop"
  — and §12 lists both edits.)

## 7. Tests

All three of this spec's cases live in `tools/verify_page.py`, the script
LOTTO-0002 §7 introduces — **one script for all three parts of the split**, joining
`tools/verify_privacy.py`, `tools/verify_sources.py`, `tools/verify_coverage.py`
and `tools/verify_pools.py`. Exit code is the signal, as with the other four.
One script rather than three because all eleven cases share their temporary-directory
setup and their fixtures (nine also share the stub builder — `no_orphan_server`
spawns a real child and `serve_is_headless` runs in a fresh interpreter), and
because CLAUDE.md's
verification block — five commands — is what a contributor actually runs.

| Case | Locks |
|---|---|
| `serve_is_headless` | INV-19 |
| `no_orphan_server` | INV-20 |
| `refresh_reports_the_build` | INV-23 |

LOTTO-0002 §7 states the three constraints binding all eleven cases — no network,
no real data, and recomputing rather than importing the judgement under test —
and names its own four cases; LOTTO-0014 §7 names the other four. Three points
apply to this document's three cases specifically:

- **`no_orphan_server` spawns a real child**, which is the one case that does
  not use the stub-builder seam. `LOTTO_NO_BUILD` is what keeps it cheap *and*
  what satisfies the no-real-data constraint: the child binds and serves without
  building, so it reads neither `lotto_sms_raw.txt` nor `archive_results.json`
  and costs a process spawn rather than 27 network requests. That reconciliation
  is necessary rather than incidental — §4.2 fixes the child's `cwd` to the
  repository, so the real dump is exactly where it would look if it built.
  **LOTTO-0002 §7's redirect still applies and is not waived**: the child
  inherits the suite's temporary `$HOME` and `$XDG_CONFIG_HOME` through
  `{**os.environ}`, so it cannot write to the developer's real config either.
  `LOTTO_NO_BUILD` is the *additional* guard that `cwd=HERE` makes necessary,
  covering the one thing a redirected `$HOME` does not — the repository's own
  data files.
- **`serve_is_headless` must run in a fresh interpreter**, not in the one
  running the suite. By the time the other ten cases have run, the suite's own
  process has imported whatever they needed — including `supervise`, which
  `no_orphan_server` drives directly — so asserting on `sys.modules` there would
  measure the test harness rather than the modules under test.
- **`refresh_reports_the_build` drives a `Supervisor` at a server it did not
  spawn.** It stands up two `serve_on()` servers on ephemeral ports — one
  builder that blocks, one that raises, because `make_server()` binds its
  builder at construction — and for each one constructs a `Supervisor(port=…)`
  and assigns `sup.token` to match (§4.1 sanctions that; the constructor mints
  nothing). No child, so the case costs no process spawn and needs no
  `LOTTO_NO_BUILD`, and `refresh()`
  reaches the server over loopback exactly as it would reach a real child. **The
  blocking stub waits on a `threading.Event` rather than sleeping**, which is what
  makes the timing assertions exact rather than racy: the case controls when the
  build finishes instead of guessing how long it takes, and a machine under load
  cannot turn assertion 1 into a flake. The event is released in a `finally`, or
  a failed assertion leaves a server thread parked inside the builder for the
  rest of the run.

**Each case is observed failing before the invariant is accepted**, per
LOTTO-0002 §7, which owns that rule and the reasoning for it. The deliberate
breakages below, of which three are stated at length because the obvious edit
does **not** go red: `terminate_only` and its `SIGTERM`-handler precondition,
and `notify_on_202`, which must fail on one specific assertion out of five:

**The breakages are named flags, not hand edits** — `tools/verify_page.py
--break <name>` applies one deliberate defect and asserts the named case goes
red, and `--list` prints them. LOTTO-0002 §7 owns the reasoning; what matters
here is that this document's three cases are covered by `qt_import`,
`terminate_only` and INV-23's three, and that adding a case means adding its
break in the same change. **Two of the bullets below are deliberately not
flags** — the `SIGTERM`-handler variant and the exit-immediately server are
one-off manual confirmations, stated because they are what makes the two flagged
INV-20 breakages meaningful, and neither is a defect a flag could install
without shipping a second `serve.py`.

- `--break qt_import` adds `import PySide6.QtCore` to a shared helper and
  `serve_is_headless` must fail.
- **Dropping `kill()` alone does not fail anything** — a `serve.py` that honours
  `SIGTERM` exits on `terminate()`, so the fallback is never reached. Install a
  no-op `SIGTERM` handler in the child *and* drop `kill()`; that is the state
  INV-20's *Breaks when* actually names.
- **`--break terminate_only` replaces `stop()`'s body with a bare
  `terminate()`** — nothing that collects the status afterwards — and
  `no_orphan_server` must fail. **It fails on the *process-table* assertion,
  which is the first of the three**: an unreaped child becomes a zombie, and §5
  says exactly that `os.kill(pid, 0)` succeeds against a zombie, so the case
  never reaches the returncode line. Naming the wrong assertion here would send
  an implementer hunting a broken harness; the returncode assertion is what the
  *ordering* protects, not what this break fires. This is the breakage that
  proves the reap is checked, and it must be
  stated this precisely: any variant that still calls `wait(timeout)` or polls in
  a loop has already collected the status on the ordinary SIGTERM-honoured path,
  so it goes green and reads as a broken harness.
- **`--break notify_on_202` is the shipped defect itself**, and it is the only
  break in this script that reproduces behaviour that actually went out:
  `refresh()` returns `REFRESH_DONE` the moment the POST is answered, and
  `refresh_reports_the_build` must fail. **It fails first on assertion 1** — the
  call returning while the builder is still blocked — and would also fail
  assertions 3 and 4 if it reached them, since both expect an outcome the
  202 cannot know. Assertions 2 and 5 pass under it. Naming the wrong one here
  would send an implementer hunting a broken harness, which is the trap §7's
  `terminate_only` bullet already records.
- **`--break stale_is_success` keeps the wait and drops the `stale` read**, so
  every finished build returns `REFRESH_DONE`, and assertion 3 must fail. The
  wait alone is not the fix; a patient lie is still a lie.
- **`--break success_wording` rewrites `REFRESH_MESSAGE[REFRESH_RUNNING]` to
  `"Results refreshed."`** — the timing half stays correct and the wording half
  fails. The two halves are broken separately because they can break separately.
- Make `serve.py` exit immediately at startup and confirm `no_orphan_server`
  fails on the **readiness wait** rather than passing on assertions a dead child
  satisfies trivially.

## 8. Alternatives considered (and rejected)

- **A systemd user unit driven by the tray**, as the user's stats tray does.
  Rejected 2026-08-02 for the install step: it turns "clone the repo and run the
  tray" into a unit file to write, a `systemctl --user daemon-reload` and an
  enable. Still available to anyone who wants it, precisely because INV-19 keeps
  `serve.py` Qt-free — the alternative is preserved rather than closed off.
- **The lifecycle inside `tray.py`, with no `supervise.py`.** Rejected on §4.1's
  argument — the module is small enough that its testability is the whole case.
- **A detached child that outlives the tray.** Rejected: it makes Quit a lie and
  leaves the port held by a process with no visible owner — the exact state
  INV-20 exists to forbid.
- **One token minted per tray session rather than per server start.** Rejected:
  a tab open across a Stop/Start would keep working against a server that never
  issued it a token, which is the property the token exists to deny (§4.1).
- **Electron.** Rejected — a browser bundled for one menu, where PySide6 is
  already installed and is what KDE Plasma itself is built on.

## 9. Out of scope

- The model, the refresh lifecycle, what the page renders and its settings
  panel — LOTTO-0002.
- The HTTP surface, the `Host` allowlist, the token and the response-header
  rules — LOTTO-0014.
- Any change to how tickets are parsed, scored or priced. This item starts and
  stops a process; it computes nothing.
- Marking a prize as claimed — deferred, per LOTTO-0002 §9.
- Serving to any host but the loopback interface, now or later.

## 10. Resource cost

- **Memory:** one `QSystemTrayIcon`, two SVG icons and a `QThreadPool` with at
  most one job in flight (§4.3 refuses a second while one is running). The
  server's own memory is LOTTO-0002 §10.
- **Processes:** exactly one child at a time, owned by one `Supervisor`. No
  growth: `start()` is a no-op while `is_running()`.
- **Network:** loopback only, and bounded. `is_ready()` issues one `GET` per
  100 ms until the server answers — a ceiling of 100 per start rather than a
  guaranteed cadence (§4.1: each attempt carries its own 1 s timeout), and in practice a
  handful, since the server binds before it builds (§4.1). Nothing leaves the
  machine. The tray's Refresh item is one loopback POST
  that causes the server to make the 27 requests LOTTO-0002 §4.2 measures and
  its §10 budgets, **followed by one `GET /status` every 2 s until the build
  finishes** (§4.6) — a ceiling of 150 per refresh at the 300 s budget, and
  fifteen-odd for a build that takes the thirty seconds it usually takes. Each
  answers from memory and builds nothing, and they run only while a refresh the
  user asked for is in flight;
  the state poll is a `Popen.poll()` on a local process and issues no request at
  all.
- **Disk:** nothing written by this half. The `.desktop` file is written by the
  page's settings route (LOTTO-0002 §4.7).
- **Dependencies:** PySide6 for `tray.py` only, already installed (6.11.0,
  measured §3). `supervise.py` is standard library, which is what lets
  `tools/verify_page.py` drive it.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-19 both modules Qt-free, and neither spawns on import | `tools/verify_page.py::serve_is_headless`, each module in a fresh interpreter — **except a `PyQt*` import**, which the predicate cannot see (§5, LOTTO-0017) |
| INV-20 no orphan server | `tools/verify_page.py::no_orphan_server` |
| §4.1 `is_ready()` reporting readiness correctly | `tools/verify_page.py::no_orphan_server` — the case fails if the child never answers |
| §4.1 the tray *gating* every browser open on `is_ready()` | **nothing** — the function is checked above, but that `tray.py` waits on it before opening a browser needs a display, like every other `tray.py` rule here |
| §4.1 the blocking calls running off the GUI thread | **nothing** — a frozen menu needs a running tray to observe; it is the most visible failure in this document and the least checkable |
| §4.1 a new token per `start()` | **nothing** — a supervisor that reused one token across restarts would pass every case here; the stale-tab 403 it would suppress is a browser-side behaviour no exit-code script observes |
| §4.2 the reap also running on `aboutToQuit` | **nothing** — INV-20 drives `Supervisor.stop()` directly, because reaching the Qt shutdown signal needs a `QApplication` and a display, which is what §4.1 split the module to avoid. Code review only |
| §4.3 four of the six copied Qt details — live wrapper set, quit-on-close, wording agreement, Open-page disabled while stopped (the thread pool and the busy guard have their own rows) | **nothing** — each is a Qt runtime behaviour needing a display; the wrapper-lifetime one is a crash that a short run does not reproduce |
| §4.3 the state poll noticing a child that died on its own | **nothing mechanical** — driving it needs a tray; observable by starting the tray with the port already occupied |
| §4.3 the busy guard admitting one long action at a time | **nothing** — a second click needs a running tray and a display. The server's 409 (LOTTO-0014 §4.1) is the backstop, and what it *says* is no longer unchecked: `refresh_reports_the_build` asserts the `REFRESH_BUSY` outcome and its sentence (§4.6). The guard itself stays unchecked, and its breach is now benign |
| INV-23 a refresh reported only after its build finished, and a failed or unfinished build never reported as a success | `tools/verify_page.py::refresh_reports_the_build` |
| §4.6 the wording of the four outcomes — only `REFRESH_DONE` reading as success | `tools/verify_page.py::refresh_reports_the_build` — checkable only because `REFRESH_MESSAGE` lives in Qt-free `supervise.py` |
| §4.6 the tray *showing* the sentence it is handed, rather than composing one | **nothing** — `tray.py` needs a display. The case proves the outcome and the sentence; the `showMessage()` that displays them is code review, like every other `tray.py` row here |
| §4.6 a child that dies mid-build being reported rather than waited out | **nothing** — INV-23's case drives a `Supervisor` that owns no child, precisely so it needs no spawn, so it cannot reach the branch. Loud at run time: the notification arrives in seconds instead of at the 300 s budget |
| §4.3 `tray.py` reading `open_on_start`, and its fallback on a corrupt file | **nothing mechanical** — needs a tray and a session. The fallback is what stops a bad settings file hiding the icon, so it is verified by writing a malformed `settings.json` and starting the tray once |
| §4.1 one reader, with no second copy of it in `serve.py` or `tray.py` | **nothing** — a duplicate that agrees on the day it is written passes every case in `tools/verify_page.py`, because agreeing readers are indistinguishable from one reader until one of them is edited. Found once, by reading, in shipped code (§13) |
| §4.5 the port being read once and agreeing end to end | **nothing** — a disagreement surfaces as a 421 on every request, which is loud at run time and invisible to a check that supplies the port itself |
| §6 the tray exiting non-zero with no system tray | **nothing mechanical** — depends on the session's tray implementation; verified by running it under a session with no tray |

Eighteen rows, thirteen `nothing`. (§4.2's environment channel for the token is not
tabulated here — LOTTO-0014 §11 owns that row, since the rule it states is the
token's, and a rule tabulated twice becomes two rules that disagree.)

That ratio is high, and it is honest rather than alarming: this part of the
split is the one needing a display and a desktop session, and its mechanically
checkable contracts — the headless imports, the reaped child and now the
refresh's outcome — are exactly the ones that fail silently. **Nine of the
thirteen `nothing` rows are wholly loud at run time**, and the four *items* that
are not are the ones worth knowing about, all code-review only — items rather
than rows because the bundled Qt-details row holds three loud details and one
silent one:

- the **per-`start()` token**, whose breach is silent by construction — a
  supervisor reusing one token across restarts leaves a stale page authorised
  against a server that never issued it one;
- the **tray showing the sentence it is handed**, since a tray that composed its
  own *Results refreshed.* over any outcome is the exact breach §4.6 exists to
  close, and the user is told the thing they wanted to hear;
- the **runnable-wrapper lifetime**, which is a crash a short run does not
  reproduce rather than an error anyone sees;
- the **single reader**, whose breach is silent for exactly as long as the two
  copies agree — and which shipped broken, undetected by all five checks, until
  a read caught it (§13).

## 12. Cross-doc impact

- `docs/specs/LOTTO-0002-local-web-page.md` — the parent of the split; it loses
  INV-19 and INV-20, its §4.8 is reduced to a pointer at this file, and its §4.7
  hands the *reading* of `open_on_start` to this document's §4.3 while keeping
  the setting's path, key and default.
- `docs/specs/LOTTO-0014-http-surface-and-security.md` — the second cut of the
  same parent; its §4.3 receives the token this document's §4.2 mints, and its
  §4.2 builds the `Host` allowlist from the port §4.5 resolves.
- `README.md` — the tray's own section: how to start it, the autostart switch,
  and PySide6 as a tray-only requirement. Shared with LOTTO-0002, which writes
  the page half of the same section.
- `CLAUDE.md` — the Commands block gains `python3 tray.py`; the verification
  list gains `tools/verify_page.py` (shared with LOTTO-0002). Its opening claim
  that the project is "Pure Python 3.8+ standard library plus `dbus-python`"
  goes stale the moment `tray.py` lands and must gain PySide6 as a tray-only
  requirement — the same edit README.md:55's "Needs Python 3.8+" line needs.
- `CHANGELOG.md` — an `Added` entry citing LOTTO-0013.
- `ROADMAP.md` — LOTTO-0013's bullet flips to shipped.

**Added by the LOTTO-0018 amendment (2026-08-02), which introduced §4.6 and
INV-23:**

- `docs/specs/LOTTO-0002-local-web-page.md` and
  `docs/specs/LOTTO-0014-http-surface-and-security.md` — **count-only edits**.
  Both cite the shared script's case count ("all ten cases") in prose about
  constraints they own; the eleventh case makes the number wrong. Neither
  document's contract moves, and LOTTO-0002 §4.1's remark that `GET /status`
  would otherwise have no consumer gains the tray as its second one (§4.6). A
  number and a pointer, not a rule.
- `CHANGELOG.md` — a `Fixed` entry citing LOTTO-0018.
- `ROADMAP.md` — LOTTO-0018's bullet flips to shipped, which unblocks LOTTO-0019.
- `CLAUDE.md` — the verification block runs the same five commands, but names
  `tools/verify_page.py`'s range as `INV-12..INV-21` and counts its breaks; both
  go stale with an eleventh case and three more breaks.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 6 | 2026-08-02 | 2 | 0 | 4 | 6 | 9 | Gate for the `5-amend` LOTTO-0018 amendment. All 19 verified findings fixed; 0 unverified, 0 deferred. **No CRITICAL.** Origin split: roughly 12 draft defects against 7 fix collateral — the healthy direction, and both lanes led on the same three HIGHs. **The sharpest was §4.3's new rule eating the failure path it was written to protect.** "It composes no message of its own and reads no HTTP status" is true of the four outcomes and false of everything that raises — a 403, a 500, a dead child — and an implementer obeying it literally deletes the `Refresh failed: <msg>` composition, leaving the raise path silent. The cardinal failure arriving through the fix for the cardinal failure, which is why both lanes ranked it top three. **The second was doc-versus-code and predates the amendment:** §4.1 has put the Stop *menu item*'s `stop()` through `run_async()` since loop 3, while `tray.py::toggle()` calls it inline and says so in a comment; the paragraph now states that **every** `stop()` is synchronous and gives the Stop item's own reason — `sync()` and the *Server stopped.* notification describe a reap that must already have happened. **Two contract gaps in the new material, both of which would have stopped an implementer.** INV-23's case needs a `Supervisor` pointed at a server it did not spawn, and §4.1's surface mints the token only inside `start()`, so the case as written was unbuildable — `token` is now stated to be a plain attribute a driver may assign, chosen over widening the constructor for one caller. And `refresh(timeout=300.0)` sat beside "the budget is `post()`'s existing 300 s" without saying whether that is one deadline or two: read as two, the worst case is ten minutes with the busy flag held, which is the wedge the bounded wait exists to prevent. It is now explicitly one deadline, with the POST issued on the smaller of 30 s and the remainder. **One finding was the case being unrunnable as specified:** `make_server()` binds its builder at construction, so a single `serve_on()` server cannot both block and raise — the case now stands up two. Also fixed: §5's INV-23 headline said a refresh "is reported only after the build has finished" while three of its four outcomes are reports issued mid-build, which read literally makes `REFRESH_BUSY` wait; §6 promised a notification on the state poll that no section specifies and `tray.py::sync()` does not raise; §11 had no row for §4.6's dying-child branch, which INV-23's childless case provably cannot reach (eighteen rows, thirteen `nothing`); §4.1's "at most 100 requests … the only requests this half makes" was left closed against §10's new 150-per-refresh poll; §7's "the last three" pointed at three bullets the amendment had displaced; the wording assertion did not say it is case-folded, so *Refreshed…* would pass it; and the header now says outright that §4.6 and INV-23 are **specified and not yet implemented**, a lane having had to ask whether there was work to do. Doc grew 1,043 -> 1,107 lines. |
| 7 | 2026-08-02 | 2 | 0 | 2 | 6 | 5 | Second gate loop on the amendment. All 13 verified findings fixed; 0 unverified, 0 deferred. **No CRITICAL for the second loop running, and both HIGHs were in the new material rather than collateral** — draft defects roughly 10 against 3, so the sweep is keeping up. **Both lanes led on the same one: INV-23's case could not assert what it claimed.** Assertion 3 said the failed refresh leaves "the model the server still serves is the previous one", but `make_server()` binds its builder at construction and the raising server's builder raises on *every* call, so that server never has a model to preserve. The clause is now deleted rather than repaired: INV-18 and `failed_refresh_keeps_model` already own it, and INV-23 is about the report. **The second HIGH was the cardinal rule inside the fix for the cardinal rule.** `REFRESH_FAILED`'s sentence promised "the page still shows the previous results" — false whenever the *first* build is the one that failed, which is the commonest failure this project measures (four of seven): there is no previous model, the page is in LOTTO-0002 §6's results-unavailable state, and the notification would describe data that does not exist. Reworded to be true of both states, and §6 now says which two states those are. **The MEDIUMs were all unstated behaviour an implementer would have had to invent:** whether a 409 polls before returning `REFRESH_BUSY` (it must not — the build it names is not this call's); what a poll failure means while the child is still alive (three cases now, and only a dead child stops the wait — one dropped loopback response is not evidence a build failed); why the POST carries 30 s inside a 300 s budget, and what a POST timeout reports; whether `REFRESH_RUNNING` requires an observation (the deadline is now tested *after* a poll, never before, so it cannot report on a build nobody looked at); and LOTTO-0002 §5's invariant-ownership sentence, which the new INV-23 made stale. **One finding was this document overclaiming its own red test:** §5 and §7 both said the four assertions after the first "go green" under `--break notify_on_202`. Two of them do; 3 and 4 fail, because a 202 cannot know an outcome. Corrected in both places, and assertion 1 is now justified as the one that observes the property directly rather than as the only one that catches the defect. Also fixed: §4.1's surface block omitted the `port` attribute §4.2 and §4.5 both use; "two orders of magnitude" for a 30× difference; the ceiling §4.6 restated after §4.1 had just pointed at §10 as the inventory; §4.3 saying the tray shows "the sentence it is handed" where `refresh()` returns an outcome constant; §11's loud/silent split counting rows where one row bundles four items, and missing the tray-wording row from the silent list (nine loud, four silent, thirteen `nothing`); and the Status header now enumerates every part of the document describing unbuilt behaviour rather than three of them. Doc grew 1,107 -> 1,158 lines. |
| 8 | 2026-08-02 | 2 | 0 | 2 | 3 | 6 | Third and final gate loop on the amendment, stopped at the run's 3-loop cap with **nothing outstanding** — every verified finding fixed, 0 unverified, 0 deferred. The trend across the three is 4/6/9 → 2/6/5 → 2/3/6 with no CRITICAL after the first, and the last loop's HIGHs are both in §4.6 rather than anywhere the fixes reached, so the sweep held. **Both lanes led on the same contradiction, and loop 7 created it.** Loop 7 ruled that "`REFRESH_RUNNING` means `building` was observed true at least once" — which the same section's own poll-failure cases contradict three paragraphs later, since a run whose every `/status` attempt failed observes nothing and still has to return something. The stronger claim left that path with **no defined return value**, and the outcome table repeated the false condition. Now stated as an *attempt*, not an observation: the deadline is never tested before at least one poll attempt, the first poll goes out immediately after the POST, and a run that never got an answer returns `REFRESH_RUNNING` too — which is honest in both shapes, since the tray knows the build has not been seen to finish and does not know that it failed. **The second HIGH is collateral of the amendment as a whole rather than of one fix:** §4.3 has said since the split that the 5-second state poll "bounds how long the icon can claim a dead server is running", and `sync()` returns early while `busy` is set — which a 30-second refresh now holds. The bound is qualified rather than the code changed, because §4.6's case 1 already closes the real exposure: a dead child is caught by the *refresh* poll within one 2 s interval, not left to the icon timer. **The MEDIUMs were three interactions nobody had pinned:** each poll's 5 s socket timeout was unclamped, so the last poll could overrun the deadline the section calls single (now clamped, and `POST_TIMEOUT` is named in §4.1's surface block rather than living in one prose sentence); the dead-child branch raised an unspecified exception whose text §4.3 routes to the user, which would have shown `<urlopen error [Errno 111] Connection refused>` (now a `RuntimeError` with its own sentence, the choice §4.1 already makes for `post()`); and the 409 rule was stated in full in both §4.1 and §4.6, against §4.1's own warning that two copies of one contract are how contracts drift — §4.1 is now a pointer, and §5's assertion-by-assertion account of `notify_on_202` was collapsed into §7 for the same reason. Also fixed: "an order of magnitude" for a 30× difference; "the only caller of `post()` the tray has", which the tray no longer is; §4.3's busy bullet claiming every long action relabels its menu item when only Refresh does; §11's loud/silent split now counting rows and items in the units it means; and §7's "the gate is cleared again", which reads as *released* to anyone who has just read assertion 2 and means the opposite. **Declined, with the reason recorded:** a table of contents for a 1,182-line document — neither sibling spec of the same split has one, and adding it to one of three is a consistency cost for a navigation gain, so it belongs to a pass over all three or to none. Doc grew 1,158 -> 1,182 lines. |
| 5-amend | 2026-08-02 | — | — | — | — | — | **Amendment row — no reviewer was dispatched, and this is not a review loop.** Origin is ROADMAP LOTTO-0018, filed by the session that verified the path end to end: `POST /refresh` answers **202 = accepted**, `serve.py::refresh()` having only started a daemon thread, and `tray.py::refresh()` treated that 202 as completion — so the tray said *Results refreshed.* about a second into a thirty-second build, and said the same thing when the build raised, which four of seven measured attempts did. **This is the cardinal rule in notification form**, and unlike the page half (INV-18, which the page already honours by polling `GET /status`) nothing in this document said what the tray must wait for. The amendment adds **§4.6** — the four outcomes, the 2-second cadence borrowed from the page's own poll, the 300-second budget that must report *still running* rather than either verdict, the 409 that is an outcome and not an `HTTP Error 409: Conflict` shown to a user, and the rule that only `REFRESH_DONE` may read as success — plus **INV-23**, its case `refresh_reports_the_build` and three breaks. **Two design calls worth naming.** The wait lives in `supervise.py` and not in `tray.py`, by §4.1's own argument: a wait written into the tray needs a display to check and would have joined §11's `nothing` rows, and this is the half that can silently lie. And `REFRESH_MESSAGE` lives there too, following the precedent `port_fallback` set (§4.5) — a Qt-free module already carries one user-facing string because it has no notification channel of its own — which is what lets a headless case assert the wording half at all. §11 gains three rows (seventeen, twelve `nothing`) and **loses one of its four silent breaches**: the busy guard's *reporting* of a 409 is now defined and checked, leaving the guard itself, whose breach is benign. Written before implementation, per rule 14's cold-eyes-then-implement ordering; loop 6 below is the gate. |
| 5 | 2026-08-02 | 2 | 0 | 2 | 6 | 7 | Second re-gate loop. All 15 verified findings fixed; **2 dismissed on evidence**, 0 deferred. **No CRITICAL, down from one** — the trend the loop is watching. Origin split: roughly 7 fix collateral against 8 draft defects, so the collateral trigger did not fire. **Both lanes reported the same false finding, and it was the review harness rather than the document:** three "`§13` resolves to nothing" findings, because the orchestrator's scrubbed copy — which withholds this log from a cold reader — replaced the heading with an *unnumbered* `## Cold-eyes loop log`. The document has always numbered it §13. Dismissed, and the packet builder was fixed so the artefact cannot recur; recording it because a lane finding that contradicts the brief is evidence against the brief first. **Two HIGHs, both about a rule whose stated exception list was short by one.** §4.1 said blocking calls run off the GUI thread "with one exception"; `tray.py::main()` calls `start()` inline before `app.exec()`, correctly — there is no event loop yet, and the icon sync and the `open_on_start` open must follow it in order — so an implementer obeying the text asynchronously would race the tray's own first `sync()`. And §7's `terminate_only` breakage named the wrong failing assertion: an unreaped child is a **zombie**, `os.kill(pid, 0)` succeeds against one (this document's own §5 says so), so the case fails on the process-table assertion and never reaches the returncode line the text promised. An implementer reproducing it would have doubted the harness. **The §11 table carried the same rule twice, twice** — INV-19's row and a §4.4 row naming one checker for one rule, and the GUI-thread row against the thread pool bundled into §4.3's detail row — against the table's own footnote that a rule tabulated twice becomes two rules that disagree. Deleted rather than reconciled; the table is now fourteen rows and eleven `nothing`. Also fixed: §4.4 still said §4.2's sketch defines "only `HERE`" at module scope after loop 4 added the port constants to it — loop 4's own collateral, in the sentence justifying the no-side-effects-on-import contract; §11's INV-19 row claimed unqualified coverage while §5 documents the PyQt blind spot, now cross-referenced and filed as LOTTO-0017 so the header's "0 deferred" stays honest; §7 described its breakages as hand edits when the shipped mechanism is `--break <name>`, which no spec mentioned at all though CLAUDE.md does; §4.5's "an unusable `LOTTO_PORT` never raises" read project-wide when it governs `Supervisor` only; §10 restated the 100-requests-per-start ceiling without §4.1's per-attempt-timeout qualifier; and the `TIME_WAIT` comment in `tools/verify_page.py`'s bind loop was corrected to match loop 4's measurement, the code having been left asserting the rationale the spec had just disproved. Doc grew 785 -> 812 lines. |
| 4 | 2026-08-02 | 2 | 1 | 2 | 5 | 8 | Re-gate of the `3-impl` amendment. All 16 verified findings fixed; 0 unverified, 0 deferred. **The CRITICAL was the amendment's own collateral, and both lanes reached it from opposite ends.** `3-impl` moved the settings reader here and never recorded the edge that makes the move work: §4.1's "the arrow runs one way — `tray.py → supervise.py` — and never back" reads as forbidding `serve.py → supervise.py`, which is exactly the import the amendment depends on. An implementer obeying the section as written writes the second reader the same amendment had just deleted. §4.1 now names the edge and says the graph is still acyclic; §4.4's reason for INV-19 covering this module was restated from it (it had cited `tools/verify_page.py` importing the module — how the breach is observed, not why it matters). **Two HIGHs, both numbers the document asserted and the code contradicts.** `is_ready()` polls `<url>/status`, not `url`: against `/` it would build up to a hundred full page renders per start to answer a question about a socket. And the shutdown freeze is up to **ten** seconds, not five — `stop()` waits its timeout after `terminate()` and again after `kill()` — understated in §4.1 and §6 alike, on the one path where the user is watching. **Two findings came from running things rather than reading them.** The `TIME_WAIT` rationale for INV-20's bind retry is false: measured, a bind with `SO_REUSEADDR` over a socket `ss -tan` confirms in `TIME_WAIT` **succeeds**, so the retry was justified by the wrong mechanism and now names the real one. And checking INV-19's `PySide|Qt` description against the predicate turned up a live gap rather than a wording slip — the case tests `PySide` as a substring **or** a top-level package named exactly `Qt`, so `PyQt6.QtCore` passes it, and PyQt6 is importable on this machine (verified). Stated as a gap with the fix named, not papered over; the predicate change is code and belongs to a code pass — filed as ROADMAP LOTTO-0017. Also fixed: §4.1 claimed to hold the supervisor's whole surface and omitted `free_port()`, which INV-20's own case calls; §4.3 said "five details" above six bullets, leaving Open-page-disabled-while-stopped in no §11 row (the row now reads five of six, table unchanged at fifteen rows and eleven `nothing`); §5 said the free port is passed "as `LOTTO_PORT`" where the case passes `Supervisor(port=…)`; §6 presented every not-answering child as a timeout when `is_ready()` returns `False` at once on a dead one, so *died* and *hung* are now separate bullets with different waits; `post()`'s "raises the same way" invited `HTTPError` where the code raises `RuntimeError`; the `Optional[str]` rule read as a requirement on a module that carries no annotations at all; empty and unset `LOTTO_PORT` were folded in with unusable ones though they fall back silently by design; and §4.2's restatement of `stop()` clearing the token was deleted rather than reconciled, against §4.1's own promise not to restate. Doc grew 724 -> 785 lines. |
| 3-impl | 2026-08-02 | — | — | — | — | — | **Implementation row — no reviewer was dispatched, and this is not a review loop.** Origin is building the thing (commit `45e3fc3`), not reading it, which is why it hangs off loop 3 rather than numbering as loop 4. **§4.1's file-role line was false the moment the code shipped.** It described `supervise.py` as minting the token, resolving the port and spawning and reaping the child — and implementation put `config_home()`, `autostart_path()`, `settings_path()` and `read_settings()` there too, because `tray.py` must read `open_on_start` at startup (§4.3) and may not import `serve` (this section's one-way arrow). The two ways out of that were an import §4.1 forbids or a second copy of the read in the tray, so the reader moved and the *writing* stayed in `serve.py`, where `POST /settings` has the lock that serialises two concurrent toggles. The split is by verb, not by file, and §4.1 now says so; §4.3 gains the clause that the tray reads through `supervise.read_settings()` rather than opening the file. **Writing the amendment then found something the implementation had not: the single reader it was about did not exist.** `serve.py` imported `read_settings` from `supervise` and redefined it twenty lines later, and in Python the local definition wins — so the file that the amendment credits with having *one* reader shipped with two. Both bodies were identical, nothing misbehaved, and all five `tools/verify_*.py` were green over it, which is exactly the failure's shape: agreeing duplicates are indistinguishable from one reader until somebody edits one of them, and then the divergence surfaces as a settings panel and a tray that disagree about `open_on_start`. The duplicate was deleted in the same change — `serve.py` now imports the reader and defines only `write_settings()` — and the five checks are green after it, one of them re-run against a deliberate break to confirm the suite can still go red. **§11 gained the row that says nothing catches this**, taking the table to fifteen rows and eleven `nothing`, and the silent-breach list from three entries to four. No invariant moved, no case changed, and no behaviour changed: the deletion is inert at run time and the amendment is the contract catching up with the code. |
| 1 | 2026-08-02 | 2 | 4 | 4 | 9 | 8 | All 27 verified findings fixed; 0 unverified, 0 deferred. Both lanes independently led on the same two CRITICALs, and both were about the one code block an implementer copies. **§4.2's sketch minted the token and called `Popen` at module scope**, contradicting §4.1's "minted per `start()`" and §4.4's "importing it must spawn nothing" — and encoding precisely the alternative §8 rejects; it is now a `Supervisor` class with the mint inside `start()`. **The same `Popen` set no `cwd`.** The spec had already identified the hazard — an autostart entry's working directory is not the repository — and closed only the half about the *script* path. Verified: `history.py::ARCHIVE` is `"archive_results.json"`, `backfill.py::CACHE` is `"archive_cache"` and `tickets.py::load()` defaults to `"lotto_sms_raw.txt"`, all cwd-relative, so an autostarted tray would spawn a server that finds no data and renders the empty state — this project's cardinal failure arriving through the one launch path this item adds, on a machine where running the same server by hand works. `cwd=HERE` added. **Two further CRITICALs, one per lane.** §11 credited `no_orphan_server` with catching a Qt import in `supervise.py`; measured (`env -u DISPLAY python3 -c "import PySide6.QtWidgets"` succeeds — only constructing a `QApplication` needs a display), so the row was false in the one table whose purpose is saying what is *not* checked. INV-19 now covers both modules and the row cites it. And `open_on_start` was orphaned across the split: LOTTO-0002 §4.7 states it is "read by **`tray.py`** at startup", while this document — which owns `tray.py` — never mentioned it, so an implementer reading only this spec ships a tray that ignores the setting the other spec promises. §4.3 now owns the reading and the corrupt-file fallback; §4.7 keeps the file. **One HIGH was a live tautology:** `no_orphan_server` asserted the child had exited and the port was free, both of which a `serve.py` that dies instantly on an import error satisfies — the case would have passed against a server that never worked. It now waits on a new `is_ready()` and fails if the child never answers. That split also fixed a real design gap neither lane framed as one: `Popen` returns before the child binds, so every browser open raced the bind. Also fixed: `token: str | None` in the surface block, a runtime `TypeError` before 3.10 against a floor both README.md:55 and CLAUDE.md:9 assert; §10 cited a busy guard §4.3 never stated (the prior art has one, the spec dropped it); §11's "The six are all loud at run time" was false of the per-`start()` token row, whose own text calls the breach silent; and §7's constraint sentence left "Two of them" with no referent. Doc grew 443 -> 580 lines, most of it §4.1's readiness contract and §6's three new failure modes. |
| 2 | 2026-08-02 | 2 | 1 | 5 | 8 | 10 | All 24 verified findings fixed; 0 unverified, 0 deferred. **Origin split: roughly 9 fix collateral against 5 draft defects**, so the batch was answered by re-sweeping wholesale rather than item by item. Loop 1's own `is_ready()` and `cwd=HERE` additions generated most of it, which is the expected shape and worth watching: a second consecutive loop like this is the stop-and-consolidate signal. **The CRITICAL was a draft defect both loops had walked past.** §4.2 claimed the `wait()` after the kill "is what INV-20 observes", but INV-20's case asserted only that the child had exited and the port was free — and an unreaped zombie satisfies both, having exited and holding no socket. The reap, the invariant's headline promise, was unchecked. Verified that `Popen.returncode` stays `None` until a `wait()` or `poll()` collects the status, so the case now asserts `child.returncode is not None` and the reap became observable. **A related HIGH: neither red-test breakage §7 prescribed could go red.** Dropping `kill()` fails nothing, because a `serve.py` honouring `SIGTERM` exits on `terminate()` and the fallback is never reached — INV-20's own *Breaks when* names the missing precondition (a child mid-fetch) that §7 had dropped. The breakage is now "install a no-op `SIGTERM` handler *and* drop `kill()`". So the one case justifying `supervise.py`'s existence could have been accepted without ever failing. **The largest collateral was loop 1's `is_ready()`**, which is a blocking ten-second poll: §4.3 put only *long* actions on a `QThreadPool`, so an implementer would call it inline from the left-click handler and freeze the menu on the application's most-used interaction. §4.1 now puts `start()`, `is_ready()`, `stop()` and `post()` all through `run_async()`. It also made §10's "Network: none of its own" false — the readiness poll is loopback traffic — and left the retry interval the only unpinned budget in a document that numbers every other one; both fixed, at 100 ms. `webbrowser.open(supervise.url)` named a module attribute §4.4 forbids, `url` being an instance attribute. **A dedup rather than a reconciliation:** the argument for `supervise.py` being a separate module was stated in four places (§2, §4.1, §8, §11); §4.1 keeps it and the rest point there, deleting three future sources of "these disagree" findings rather than aligning them. §11 grew to fourteen rows and ten `nothing` — one loop-1 row overclaimed, crediting `no_orphan_server` with proving the *tray* gates browser opens on `is_ready()`, which needs a display like every other `tray.py` rule; split into the checkable half and two honest gaps. Doc grew 580 -> 639 lines. |
| 3 | 2026-08-02 | 2 | 2 | 4 | 10 | 7 | **Converged by cap, and by the collateral trigger — both fired together.** All 23 verified findings fixed; 0 unverified, 0 deferred. Origin split: **roughly 11 fix collateral against 4 draft defects**, after loop 2's 9-against-5 — collateral outnumbering draft defects two loops running, which is the stop-and-consolidate signal, reached on the same pass as the 3-loop cap. **Both lanes led on the same CRITICAL, and loop 2 had created it.** Loop 2 ruled that `start()`, `is_ready()`, `stop()` and `post()` all run through `run_async()` to keep the GUI thread free — which collides with §4.2's rule that the reap also runs on `aboutToQuit`. Dispatched to a thread pool, that handler returns immediately, the event loop ends and the process exits before `wait()` completes, producing exactly the orphan INV-20 forbids, on the commonest exit path, in the one place §11 already recorded that nothing checks. The shutdown reap is now explicitly synchronous and the up-to-5-second freeze is named as the accepted cost; the prior-art tray does the same thing, calling `systemctl("stop")` inline before `QApplication.quit()`. **The second CRITICAL was loop 2's other fix eating itself.** Loop 2 added `child.returncode is not None` to INV-20 to make the reap observable — but the case observes exit through `is_running()`, which calls `Popen.poll()`, and **`poll()` reaps**. Measured: `returncode` is `None` before the call and set after it. So the assertion could never fail, and the fix that was meant to close the tautology reinstated it one line later. The case now checks `os.kill(child.pid, 0)` first, which succeeds against a zombie and does not collect — verified — and only then reads `returncode`. The order is the assertion. Its red-test was restated for the same reason: only replacing `stop()`'s body with a bare `terminate()` goes red, since any variant still calling `wait(timeout)` has already collected the status. **The consolidation this trigger calls for was done rather than deferred:** the `Supervisor` contract had been stated twice — a surface block in §4.1 and a fuller class sketch in §4.2 — and every loop's edits to one drifted from the other, which is where most of three loops' collateral came from. §4.1 is now the only statement of it, carrying `child`, `port_fallback`, the `post()` error contract and the `stop()` semantics that were previously implied; §4.2 keeps one method and prose. Genuine draft defects, all present since the split: the tray availability check had no stated ordering against `start()`, so a desktop with no tray would exit non-zero having already orphaned a live child; `post()` had no error contract while §6 branched on 403/409/500; nothing said what Open page does while the server is stopped; and `run_async()` was named four times and never defined, existing only as a reference to a file in another repository. Doc grew 639 -> 696 lines. **Stopping here is the right call, not a budget compromise** — three loops have produced a document whose remaining findings are its own fixes, and the consolidation above removes the duplication that was generating them. |
| 0-split | 2026-08-02 | — | — | — | — | — | **Provenance row — no reviewer was dispatched, and this is not a review loop.** Split out of `docs/specs/LOTTO-0002-local-web-page.md` on the seam that spec's §12 recommended and the user chose: this document takes §4.8, INV-19 and INV-20 — the tray, the supervisor and the headless contract — and LOTTO-0002 kept §4.1–§4.7 with INV-12–18 and INV-21. **A second cut the same day** moved that spec's §4.3–§4.4 and INV-12–14 and INV-21 again, into `docs/specs/LOTTO-0014-http-surface-and-security.md`, once the first cut proved to remove only 66 of the parent's 1,161 lines; this document was unaffected by it beyond cross-references. The parent had run three cold-eyes loops (83 verified findings fixed, 0 deferred) and **converged by cap rather than clean**, with two of the three loops producing more defects from their own fixes than from the draft. **Those loops confer nothing on this document**: they were run against 1,161 lines that no longer exist, so the gate starts again from loop 1 on these bytes. Content carried over was re-grounded rather than trusted — PySide6 6.11.0 and `QSystemTrayIcon.isSystemTrayAvailable` confirmed by import, the port claim re-measured against `ss -ltn` and a real bind, and the four Qt details in §4.3 read out of `Ants_Projects_Hub_Website/tray/ants-stats-tray.py` rather than recalled. Two of those four (the runnable-wrapper set and `setQuitOnLastWindowClosed(False)`) are new here — the parent named the prior art without carrying them. |
