# LOTTO-0013 — Tray icon and server supervisor for the local page

**Status:** accepted (2026-08-02) — five cold-eyes loops: three before
implementation (converged by cap and by the collateral trigger), then two
re-gate loops that the amendment's implementation forced. 105 verified findings
fixed, 2 dismissed on evidence, 0 deferred; 1 code gap filed as LOTTO-0017
rather than fixed in a documentation pass.
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
because nothing was sent and there is no response to report.

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
the whole budget — which is why §6 splits *died* from *hung*. That is at most 100 requests per start; together with the
Refresh POST (§10) they are the only requests this half of the split makes.
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
matters more than the rule.** `start()`, `is_ready()`, `post()` and the Stop
*menu item*'s `stop()` are dispatched through §4.3's `run_async()`, because a ten-second
`is_ready()` on the GUI thread freezes the menu on the application's most-used
interaction. **The first exception is startup**: `main()`'s own `start()` runs
inline, before `app.exec()`, because there is no event loop yet to freeze and
the icon state and the `open_on_start` open both have to follow it in a known
order. Dispatched asynchronously there, the tray would race its own first
`sync()`. The rule governs the *menu items*, which run inside the event loop. **The shutdown reap is the exception and runs synchronously**: on
the Quit item and on `aboutToQuit`, `stop()` is called inline and the shutdown
waits out its reap. **That wait is up to *two* five-second timeouts, not one** —
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
  one shows its in-flight wording and is disabled until it finishes, and the
  state poll below returns early while it is set (`self.busy` in that file).
  Without it a second Refresh click queues a second rebuild, which the server
  answers with LOTTO-0014 §4.1's 409 while the tray shows neither the refusal
  nor the fact that one is already running.

**State is polled, because the child can die without being asked to.** The tray
checks `Supervisor.is_running()` on a **5-second** `QTimer` — the interval the
stats tray uses (`POLL_MS = 5000`) — and updates icon, tooltip and the
Stop/Start wording from it, the same `sync()` shape as that file. Five seconds
is the budget: it bounds how long the icon can claim a dead server is running,
and it costs one `Popen.poll()` on a local process, which issues no request and
touches no socket. A server
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
importing it must spawn nothing — which is why §4.2's sketch defines only `HERE`
at module scope — the path constant and the port bounds, no state — and
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

## 5. Invariants

This document holds INV-19 and INV-20. LOTTO-0001 holds INV-1 to INV-6,
LOTTO-0009 INV-7 to INV-11, LOTTO-0014 INV-12 to INV-14 and INV-21, and
LOTTO-0002 INV-15 to INV-18. CHANGELOG.md cites them unqualified, so the
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
  sees a child that is no longer running, and the tray surfaces it as a
  notification and a stopped icon instead of an icon that claims to be running.
  This is the case §4.3's polling exists for.
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
- **A refresh fails or hangs.** `post()` carries an explicit 300-second timeout,
  because a rebuild is measured at 27 requests against a third-party API that
  failed four of seven attempts on 2026-08-02 (LOTTO-0002 §4.2, §6). On a
  timeout, a 403, a 409 or a 500 the busy flag is cleared, the menu item is
  re-enabled with its normal wording, and the reason goes into a notification —
  the `finished(ok, msg)` shape of the stats tray. Without the timeout a single
  hung POST wedges the one-job-at-a-time guard permanently and the Refresh item
  never comes back.
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

Both of this spec's cases live in `tools/verify_page.py`, the script LOTTO-0002
§7 introduces — **one script for all three parts of the split**, joining
`tools/verify_privacy.py`, `tools/verify_sources.py`, `tools/verify_coverage.py`
and `tools/verify_pools.py`. Exit code is the signal, as with the other four.
One script rather than three because all ten cases share their temporary-directory
setup and their fixtures (eight also share the stub builder — `no_orphan_server`
spawns a real child and `serve_is_headless` runs in a fresh interpreter), and
because CLAUDE.md's
verification block — four commands today, five once this ships — is what a
contributor actually runs.

| Case | Locks |
|---|---|
| `serve_is_headless` | INV-19 |
| `no_orphan_server` | INV-20 |

LOTTO-0002 §7 states the three constraints binding all ten cases — no network,
no real data, and recomputing rather than importing the judgement under test —
and names its own four cases; LOTTO-0014 §7 names the other four. Two points
apply to this document's two cases specifically:

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
  running the suite. By the time the other nine cases have run, the suite's own
  process has imported whatever they needed — including `supervise`, which
  `no_orphan_server` drives directly — so asserting on `sys.modules` there would
  measure the test harness rather than the modules under test.

**Each case is observed failing before the invariant is accepted**, per
LOTTO-0002 §7, which owns that rule and the reasoning for it. The deliberate
breakages, and the last three matter because the obvious ones do not go red:

**The breakages are named flags, not hand edits** — `tools/verify_page.py
--break <name>` applies one deliberate defect and asserts the named case goes
red, and `--list` prints them. LOTTO-0002 §7 owns the reasoning; what matters
here is that this document's two cases are covered by `qt_import` and
`terminate_only`, and that adding a case means adding its break in the same
change.

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
  its §10 budgets;
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
| §4.3 the busy guard admitting one long action at a time | **nothing** — a second click needs a running tray and a display. The server's 409 (LOTTO-0014 §4.1) is the backstop; it is the tray's *reporting* of it that goes unchecked |
| §4.3 `tray.py` reading `open_on_start`, and its fallback on a corrupt file | **nothing mechanical** — needs a tray and a session. The fallback is what stops a bad settings file hiding the icon, so it is verified by writing a malformed `settings.json` and starting the tray once |
| §4.1 one reader, with no second copy of it in `serve.py` or `tray.py` | **nothing** — a duplicate that agrees on the day it is written passes every case in `tools/verify_page.py`, because agreeing readers are indistinguishable from one reader until one of them is edited. Found once, by reading, in shipped code (§13) |
| §4.5 the port being read once and agreeing end to end | **nothing** — a disagreement surfaces as a 421 on every request, which is loud at run time and invisible to a check that supplies the port itself |
| §6 the tray exiting non-zero with no system tray | **nothing mechanical** — depends on the session's tray implementation; verified by running it under a session with no tray |

Fourteen rows, eleven `nothing`. (§4.2's environment channel for the token is not
tabulated here — LOTTO-0014 §11 owns that row, since the rule it states is the
token's, and a rule tabulated twice becomes two rules that disagree.)

That ratio is high, and it is honest rather than alarming: this part of the
split is the one needing a display and a desktop session, and its mechanically
checkable contracts — the headless imports and the reaped child — are exactly
the ones that fail silently. **Seven of the eleven `nothing` rows are loud at
run time**, and
the four that are not are the ones worth knowing about, all code-review only:

- the **per-`start()` token**, whose breach is silent by construction — a
  supervisor reusing one token across restarts leaves a stale page authorised
  against a server that never issued it one;
- the **busy guard's reporting**, since a dropped second Refresh draws
  LOTTO-0014 §4.1's 409 and the failure is that the tray says nothing about it;
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

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 5 | 2026-08-02 | 2 | 0 | 2 | 6 | 7 | Second re-gate loop. All 15 verified findings fixed; **2 dismissed on evidence**, 0 deferred. **No CRITICAL, down from one** — the trend the loop is watching. Origin split: roughly 7 fix collateral against 8 draft defects, so the collateral trigger did not fire. **Both lanes reported the same false finding, and it was the review harness rather than the document:** three "`§13` resolves to nothing" findings, because the orchestrator's scrubbed copy — which withholds this log from a cold reader — replaced the heading with an *unnumbered* `## Cold-eyes loop log`. The document has always numbered it §13. Dismissed, and the packet builder was fixed so the artefact cannot recur; recording it because a lane finding that contradicts the brief is evidence against the brief first. **Two HIGHs, both about a rule whose stated exception list was short by one.** §4.1 said blocking calls run off the GUI thread "with one exception"; `tray.py::main()` calls `start()` inline before `app.exec()`, correctly — there is no event loop yet, and the icon sync and the `open_on_start` open must follow it in order — so an implementer obeying the text asynchronously would race the tray's own first `sync()`. And §7's `terminate_only` breakage named the wrong failing assertion: an unreaped child is a **zombie**, `os.kill(pid, 0)` succeeds against one (this document's own §5 says so), so the case fails on the process-table assertion and never reaches the returncode line the text promised. An implementer reproducing it would have doubted the harness. **The §11 table carried the same rule twice, twice** — INV-19's row and a §4.4 row naming one checker for one rule, and the GUI-thread row against the thread pool bundled into §4.3's detail row — against the table's own footnote that a rule tabulated twice becomes two rules that disagree. Deleted rather than reconciled; the table is now fourteen rows and eleven `nothing`. Also fixed: §4.4 still said §4.2's sketch defines "only `HERE`" at module scope after loop 4 added the port constants to it — loop 4's own collateral, in the sentence justifying the no-side-effects-on-import contract; §11's INV-19 row claimed unqualified coverage while §5 documents the PyQt blind spot, now cross-referenced and filed as LOTTO-0017 so the header's "0 deferred" stays honest; §7 described its breakages as hand edits when the shipped mechanism is `--break <name>`, which no spec mentioned at all though CLAUDE.md does; §4.5's "an unusable `LOTTO_PORT` never raises" read project-wide when it governs `Supervisor` only; §10 restated the 100-requests-per-start ceiling without §4.1's per-attempt-timeout qualifier; and the `TIME_WAIT` comment in `tools/verify_page.py`'s bind loop was corrected to match loop 4's measurement, the code having been left asserting the rationale the spec had just disproved. Doc grew 785 -> 812 lines. |
| 4 | 2026-08-02 | 2 | 1 | 2 | 5 | 8 | Re-gate of the `3-impl` amendment. All 16 verified findings fixed; 0 unverified, 0 deferred. **The CRITICAL was the amendment's own collateral, and both lanes reached it from opposite ends.** `3-impl` moved the settings reader here and never recorded the edge that makes the move work: §4.1's "the arrow runs one way — `tray.py → supervise.py` — and never back" reads as forbidding `serve.py → supervise.py`, which is exactly the import the amendment depends on. An implementer obeying the section as written writes the second reader the same amendment had just deleted. §4.1 now names the edge and says the graph is still acyclic; §4.4's reason for INV-19 covering this module was restated from it (it had cited `tools/verify_page.py` importing the module — how the breach is observed, not why it matters). **Two HIGHs, both numbers the document asserted and the code contradicts.** `is_ready()` polls `<url>/status`, not `url`: against `/` it would build up to a hundred full page renders per start to answer a question about a socket. And the shutdown freeze is up to **ten** seconds, not five — `stop()` waits its timeout after `terminate()` and again after `kill()` — understated in §4.1 and §6 alike, on the one path where the user is watching. **Two findings came from running things rather than reading them.** The `TIME_WAIT` rationale for INV-20's bind retry is false: measured, a bind with `SO_REUSEADDR` over a socket `ss -tan` confirms in `TIME_WAIT` **succeeds**, so the retry was justified by the wrong mechanism and now names the real one. And checking INV-19's `PySide|Qt` description against the predicate turned up a live gap rather than a wording slip — the case tests `PySide` as a substring **or** a top-level package named exactly `Qt`, so `PyQt6.QtCore` passes it, and PyQt6 is importable on this machine (verified). Stated as a gap with the fix named, not papered over; the predicate change is code and belongs to a code pass — filed as ROADMAP LOTTO-0017. Also fixed: §4.1 claimed to hold the supervisor's whole surface and omitted `free_port()`, which INV-20's own case calls; §4.3 said "five details" above six bullets, leaving Open-page-disabled-while-stopped in no §11 row (the row now reads five of six, table unchanged at fifteen rows and eleven `nothing`); §5 said the free port is passed "as `LOTTO_PORT`" where the case passes `Supervisor(port=…)`; §6 presented every not-answering child as a timeout when `is_ready()` returns `False` at once on a dead one, so *died* and *hung* are now separate bullets with different waits; `post()`'s "raises the same way" invited `HTTPError` where the code raises `RuntimeError`; the `Optional[str]` rule read as a requirement on a module that carries no annotations at all; empty and unset `LOTTO_PORT` were folded in with unusable ones though they fall back silently by design; and §4.2's restatement of `stop()` clearing the token was deleted rather than reconciled, against §4.1's own promise not to restate. Doc grew 724 -> 785 lines. |
| 3-impl | 2026-08-02 | — | — | — | — | — | **Implementation row — no reviewer was dispatched, and this is not a review loop.** Origin is building the thing (commit `45e3fc3`), not reading it, which is why it hangs off loop 3 rather than numbering as loop 4. **§4.1's file-role line was false the moment the code shipped.** It described `supervise.py` as minting the token, resolving the port and spawning and reaping the child — and implementation put `config_home()`, `autostart_path()`, `settings_path()` and `read_settings()` there too, because `tray.py` must read `open_on_start` at startup (§4.3) and may not import `serve` (this section's one-way arrow). The two ways out of that were an import §4.1 forbids or a second copy of the read in the tray, so the reader moved and the *writing* stayed in `serve.py`, where `POST /settings` has the lock that serialises two concurrent toggles. The split is by verb, not by file, and §4.1 now says so; §4.3 gains the clause that the tray reads through `supervise.read_settings()` rather than opening the file. **Writing the amendment then found something the implementation had not: the single reader it was about did not exist.** `serve.py` imported `read_settings` from `supervise` and redefined it twenty lines later, and in Python the local definition wins — so the file that the amendment credits with having *one* reader shipped with two. Both bodies were identical, nothing misbehaved, and all five `tools/verify_*.py` were green over it, which is exactly the failure's shape: agreeing duplicates are indistinguishable from one reader until somebody edits one of them, and then the divergence surfaces as a settings panel and a tray that disagree about `open_on_start`. The duplicate was deleted in the same change — `serve.py` now imports the reader and defines only `write_settings()` — and the five checks are green after it, one of them re-run against a deliberate break to confirm the suite can still go red. **§11 gained the row that says nothing catches this**, taking the table to fifteen rows and eleven `nothing`, and the silent-breach list from three entries to four. No invariant moved, no case changed, and no behaviour changed: the deletion is inert at run time and the amendment is the contract catching up with the code. |
| 1 | 2026-08-02 | 2 | 4 | 4 | 9 | 8 | All 27 verified findings fixed; 0 unverified, 0 deferred. Both lanes independently led on the same two CRITICALs, and both were about the one code block an implementer copies. **§4.2's sketch minted the token and called `Popen` at module scope**, contradicting §4.1's "minted per `start()`" and §4.4's "importing it must spawn nothing" — and encoding precisely the alternative §8 rejects; it is now a `Supervisor` class with the mint inside `start()`. **The same `Popen` set no `cwd`.** The spec had already identified the hazard — an autostart entry's working directory is not the repository — and closed only the half about the *script* path. Verified: `history.py::ARCHIVE` is `"archive_results.json"`, `backfill.py::CACHE` is `"archive_cache"` and `tickets.py::load()` defaults to `"lotto_sms_raw.txt"`, all cwd-relative, so an autostarted tray would spawn a server that finds no data and renders the empty state — this project's cardinal failure arriving through the one launch path this item adds, on a machine where running the same server by hand works. `cwd=HERE` added. **Two further CRITICALs, one per lane.** §11 credited `no_orphan_server` with catching a Qt import in `supervise.py`; measured (`env -u DISPLAY python3 -c "import PySide6.QtWidgets"` succeeds — only constructing a `QApplication` needs a display), so the row was false in the one table whose purpose is saying what is *not* checked. INV-19 now covers both modules and the row cites it. And `open_on_start` was orphaned across the split: LOTTO-0002 §4.7 states it is "read by **`tray.py`** at startup", while this document — which owns `tray.py` — never mentioned it, so an implementer reading only this spec ships a tray that ignores the setting the other spec promises. §4.3 now owns the reading and the corrupt-file fallback; §4.7 keeps the file. **One HIGH was a live tautology:** `no_orphan_server` asserted the child had exited and the port was free, both of which a `serve.py` that dies instantly on an import error satisfies — the case would have passed against a server that never worked. It now waits on a new `is_ready()` and fails if the child never answers. That split also fixed a real design gap neither lane framed as one: `Popen` returns before the child binds, so every browser open raced the bind. Also fixed: `token: str | None` in the surface block, a runtime `TypeError` before 3.10 against a floor both README.md:55 and CLAUDE.md:9 assert; §10 cited a busy guard §4.3 never stated (the prior art has one, the spec dropped it); §11's "The six are all loud at run time" was false of the per-`start()` token row, whose own text calls the breach silent; and §7's constraint sentence left "Two of them" with no referent. Doc grew 443 -> 580 lines, most of it §4.1's readiness contract and §6's three new failure modes. |
| 2 | 2026-08-02 | 2 | 1 | 5 | 8 | 10 | All 24 verified findings fixed; 0 unverified, 0 deferred. **Origin split: roughly 9 fix collateral against 5 draft defects**, so the batch was answered by re-sweeping wholesale rather than item by item. Loop 1's own `is_ready()` and `cwd=HERE` additions generated most of it, which is the expected shape and worth watching: a second consecutive loop like this is the stop-and-consolidate signal. **The CRITICAL was a draft defect both loops had walked past.** §4.2 claimed the `wait()` after the kill "is what INV-20 observes", but INV-20's case asserted only that the child had exited and the port was free — and an unreaped zombie satisfies both, having exited and holding no socket. The reap, the invariant's headline promise, was unchecked. Verified that `Popen.returncode` stays `None` until a `wait()` or `poll()` collects the status, so the case now asserts `child.returncode is not None` and the reap became observable. **A related HIGH: neither red-test breakage §7 prescribed could go red.** Dropping `kill()` fails nothing, because a `serve.py` honouring `SIGTERM` exits on `terminate()` and the fallback is never reached — INV-20's own *Breaks when* names the missing precondition (a child mid-fetch) that §7 had dropped. The breakage is now "install a no-op `SIGTERM` handler *and* drop `kill()`". So the one case justifying `supervise.py`'s existence could have been accepted without ever failing. **The largest collateral was loop 1's `is_ready()`**, which is a blocking ten-second poll: §4.3 put only *long* actions on a `QThreadPool`, so an implementer would call it inline from the left-click handler and freeze the menu on the application's most-used interaction. §4.1 now puts `start()`, `is_ready()`, `stop()` and `post()` all through `run_async()`. It also made §10's "Network: none of its own" false — the readiness poll is loopback traffic — and left the retry interval the only unpinned budget in a document that numbers every other one; both fixed, at 100 ms. `webbrowser.open(supervise.url)` named a module attribute §4.4 forbids, `url` being an instance attribute. **A dedup rather than a reconciliation:** the argument for `supervise.py` being a separate module was stated in four places (§2, §4.1, §8, §11); §4.1 keeps it and the rest point there, deleting three future sources of "these disagree" findings rather than aligning them. §11 grew to fourteen rows and ten `nothing` — one loop-1 row overclaimed, crediting `no_orphan_server` with proving the *tray* gates browser opens on `is_ready()`, which needs a display like every other `tray.py` rule; split into the checkable half and two honest gaps. Doc grew 580 -> 639 lines. |
| 3 | 2026-08-02 | 2 | 2 | 4 | 10 | 7 | **Converged by cap, and by the collateral trigger — both fired together.** All 23 verified findings fixed; 0 unverified, 0 deferred. Origin split: **roughly 11 fix collateral against 4 draft defects**, after loop 2's 9-against-5 — collateral outnumbering draft defects two loops running, which is the stop-and-consolidate signal, reached on the same pass as the 3-loop cap. **Both lanes led on the same CRITICAL, and loop 2 had created it.** Loop 2 ruled that `start()`, `is_ready()`, `stop()` and `post()` all run through `run_async()` to keep the GUI thread free — which collides with §4.2's rule that the reap also runs on `aboutToQuit`. Dispatched to a thread pool, that handler returns immediately, the event loop ends and the process exits before `wait()` completes, producing exactly the orphan INV-20 forbids, on the commonest exit path, in the one place §11 already recorded that nothing checks. The shutdown reap is now explicitly synchronous and the up-to-5-second freeze is named as the accepted cost; the prior-art tray does the same thing, calling `systemctl("stop")` inline before `QApplication.quit()`. **The second CRITICAL was loop 2's other fix eating itself.** Loop 2 added `child.returncode is not None` to INV-20 to make the reap observable — but the case observes exit through `is_running()`, which calls `Popen.poll()`, and **`poll()` reaps**. Measured: `returncode` is `None` before the call and set after it. So the assertion could never fail, and the fix that was meant to close the tautology reinstated it one line later. The case now checks `os.kill(child.pid, 0)` first, which succeeds against a zombie and does not collect — verified — and only then reads `returncode`. The order is the assertion. Its red-test was restated for the same reason: only replacing `stop()`'s body with a bare `terminate()` goes red, since any variant still calling `wait(timeout)` has already collected the status. **The consolidation this trigger calls for was done rather than deferred:** the `Supervisor` contract had been stated twice — a surface block in §4.1 and a fuller class sketch in §4.2 — and every loop's edits to one drifted from the other, which is where most of three loops' collateral came from. §4.1 is now the only statement of it, carrying `child`, `port_fallback`, the `post()` error contract and the `stop()` semantics that were previously implied; §4.2 keeps one method and prose. Genuine draft defects, all present since the split: the tray availability check had no stated ordering against `start()`, so a desktop with no tray would exit non-zero having already orphaned a live child; `post()` had no error contract while §6 branched on 403/409/500; nothing said what Open page does while the server is stopped; and `run_async()` was named four times and never defined, existing only as a reference to a file in another repository. Doc grew 639 -> 696 lines. **Stopping here is the right call, not a budget compromise** — three loops have produced a document whose remaining findings are its own fixes, and the consolidation above removes the duplication that was generating them. |
| 0-split | 2026-08-02 | — | — | — | — | — | **Provenance row — no reviewer was dispatched, and this is not a review loop.** Split out of `docs/specs/LOTTO-0002-local-web-page.md` on the seam that spec's §12 recommended and the user chose: this document takes §4.8, INV-19 and INV-20 — the tray, the supervisor and the headless contract — and LOTTO-0002 kept §4.1–§4.7 with INV-12–18 and INV-21. **A second cut the same day** moved that spec's §4.3–§4.4 and INV-12–14 and INV-21 again, into `docs/specs/LOTTO-0014-http-surface-and-security.md`, once the first cut proved to remove only 66 of the parent's 1,161 lines; this document was unaffected by it beyond cross-references. The parent had run three cold-eyes loops (83 verified findings fixed, 0 deferred) and **converged by cap rather than clean**, with two of the three loops producing more defects from their own fixes than from the draft. **Those loops confer nothing on this document**: they were run against 1,161 lines that no longer exist, so the gate starts again from loop 1 on these bytes. Content carried over was re-grounded rather than trusted — PySide6 6.11.0 and `QSystemTrayIcon.isSystemTrayAvailable` confirmed by import, the port claim re-measured against `ss -ltn` and a real bind, and the four Qt details in §4.3 read out of `Ants_Projects_Hub_Website/tray/ants-stats-tray.py` rather than recalled. Two of those four (the runnable-wrapper set and `setQuitOnLastWindowClosed(False)`) are new here — the parent named the prior art without carrying them. |
