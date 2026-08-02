# LOTTO-0013 — Tray icon and server supervisor for the local page

**Status:** spec draft (2026-08-02).
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
   token check, which deletes the defence for the one route that re-fetches.
   That was one of the three CRITICALs both lanes found in LOTTO-0002's first
   review loop; this spec is where the channel now lives.
3. **A lifecycle written into `tray.py` cannot be checked.** Driving a spawn and
   a reap through the tray needs a `QApplication` and a display, inside
   `tools/verify_page.py` — an exit-code script that sits beside four headless
   siblings and runs with no session. Splitting the lifecycle into a Qt-free
   module is what makes INV-20 a check rather than a paragraph. (Referred to
   below as the third gap in §2.)

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
              reaps the server child. Never imports PySide6, serve or page.
tray.py       PySide6. The menu and the icon, and nothing else. Imports
              supervise; never imports serve or page.
icons/        tray-running.svg, tray-stopped.svg — read by tray.py only.
```

The arrow runs one way — `tray.py → supervise.py → (a child process)` — and
never back. `supervise.py` reaches the server the same way the browser does,
over HTTP on 127.0.0.1, so there is no second code path that can disagree with
the page about what a refresh did. That is the property the user's existing
stats tray already relies on (`post_refresh()` in
`Ants_Projects_Hub_Website/tray/ants-stats-tray.py` POSTs to the same route its
dashboard page does).

**`supervise.py` exists so INV-20 is testable**, and that is its whole
justification as a separate module. Putting the spawn-and-reap contract in
`tray.py` would make its check import PySide6 and need a running display,
inside a script that has to sit beside four headless `tools/verify_*.py`.
Splitting it out costs one small module and buys a testable lifecycle; it also
lets someone with no tray supervise the server from a script.

The supervisor's surface, and nothing beyond it:

```python
class Supervisor:
    """Owns the token, the port and the child process. No Qt anywhere."""

    def __init__(self, port=None)   # port or $LOTTO_PORT or 4322 (§4.5)
    url: str                        # "http://127.0.0.1:<port>" — what the tray opens
    token: Optional[str]            # minted by start(); None while stopped

    def start(self) -> None         # spawn the child; no-op if already running
    def is_running(self) -> bool    # child is not None and child.poll() is None
    def is_ready(self, timeout=10.0) -> bool   # child is ANSWERING on the port
    def stop(self, timeout=5.0) -> None        # terminate(), kill(), then wait()
    def post(self, path, timeout=300.0) -> str # POST carrying X-Lotto-Token
```

**`Optional[str]`, not `str | None`.** README.md and CLAUDE.md both claim a
Python 3.8 floor, and a bare `X | Y` in a class body is evaluated at import and
raises `TypeError` before 3.10. The floor is asserted rather than tested, and
LOTTO-0014 §4.2 already declines a stdlib constant on the same ground; a type
annotation is not the place to break it either.

**`is_running()` and `is_ready()` are different questions, and only the second
is safe to open a browser on.** `Popen` returns before the child has bound
anything, so `is_running()` is true during a window in which the port refuses
connections. `is_ready()` polls the URL until it answers or the timeout expires.
Anything that shows the user the page — left-click, the `open_on_start` open at
startup, the Open page menu item — waits on `is_ready()`; only the icon state
reads `is_running()`.

**The token is minted per `start()`, not per process.** A Stop followed by a
Start is a new run and gets a new token, which is what makes the restart case
behave the way LOTTO-0014 §6 already describes for a tab left open across it:
the old tab's next toggle gets a 403 and is told to reload. Holding one token
across restarts would instead leave a stale page silently authorised against a
server it never received a token from.

### 4.2 The supervisor: token, port, spawn, reap

```python
# supervise.py — the sole owner of the token and the child.
# Module scope defines HERE and nothing else: importing this file must not
# mint a token and must not spawn anything (§4.4).
HERE = os.path.dirname(os.path.abspath(__file__))

class Supervisor:
    def __init__(self, port=None):
        self.port = int(port or os.environ.get("LOTTO_PORT") or 4322)
        self.url = f"http://127.0.0.1:{self.port}"
        self.token = None
        self.child = None

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

**The page is opened with `webbrowser.open(supervise.url)`** — stdlib, and it
honours the desktop's default-browser setting the same way `xdg-open` does
without shelling out. It is called only after `is_ready()` returns true, so the
browser never lands on a port that is not answering yet; if `is_ready()` times
out, the tray says so in a notification instead of opening a tab on a refused
connection.

Five details are copied from the user's existing stats tray, all five verified
in `Ants_Projects_Hub_Website/tray/ants-stats-tray.py` on 2026-08-02:

- **Long actions run on a `QThreadPool`**, never on the GUI thread. A refresh
  drives a rebuild that takes tens of seconds; doing it inline freezes the menu
  mid-click and makes Plasma offer to kill the application. That file's
  `run_async()` is the shape.
- **A module-level set keeps each runnable's Python wrapper alive** while
  `QThreadPool` owns the C++ side (`_jobs` in that file). Without it the wrapper
  can be collected while the job is still running, which is a crash rather than
  a misbehaviour, and it is invisible in a short test.
- **`app.setQuitOnLastWindowClosed(False)`**, or dismissing a notification ends
  the application and takes the server with it.
- **The icon, the tooltip and the menu wording all state the same thing**, so
  the state is never read off a 22-pixel icon alone.
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

**`open_on_start` is read here, because `tray.py` is the file that acts on
it.** LOTTO-0002 §4.7 owns the setting — its path, its key and its default of
**true** — and this document owns what the tray does with it: at startup, after
`start()` and once `is_ready()` returns true, the tray opens the page if the
setting is true and does not if it is false. **A missing, unreadable or
malformed `settings.json` falls back to the default rather than raising**, and
that rule belongs here rather than with the file format, because the
consequence is the tray's: a corrupt settings file must never be the reason no
icon appears. Without this paragraph the setting has a writer (LOTTO-0002's
settings panel) and no reader.

**Two SVG icons, `icons/tray-running.svg` and `icons/tray-stopped.svg`,
resolved relative to `tray.py`** — `os.path.dirname(os.path.abspath(__file__))`,
not the working directory, which under §4.5's autostart entry is not the
repository.

### 4.4 The headless contract

`serve.py` imports no Qt at any depth. The rule is stated here rather than in
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
at module scope and mints the token inside `start()`. INV-19 covers both
modules, because a Qt import in `supervise.py` breaks the headless case exactly
as one in `serve.py` does: `tools/verify_page.py` itself imports it.

### 4.5 One port, and the environment an autostarted tray inherits

`supervise.py` resolves the port once — `LOTTO_PORT`, default 4322 — passes it
to the child alongside `LOTTO_TOKEN`, and exposes `url` for the tray to open.
`serve.py` uses that same value both to bind and to build LOTTO-0014 §4.2's
`Host` allowlist. **A tray and a server disagreeing about the port fail as a 421
on every request** — the allowlist rejecting the very URL the tray just opened —
which is a confusing failure to debug and a trivial one to prevent by reading
the value once.

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
  whatever the other cases needed) and asserts that no module name matching
  `PySide|Qt` is in `sys.modules`, that the import returns rather than blocking,
  and that no child process was created. Everything that binds, builds or serves
  sits behind `if __name__ == "__main__":` (§4.4), which is what makes the
  import safe to perform at all — without it this case hangs instead of failing,
  and a hanging check reads as a broken test rather than a broken contract.
  **The check sees import-time depth only.** A Qt import performed lazily inside
  a function body is invisible to it, and that limit is stated rather than
  papered over: what the case actually forbids is a module-level import, which
  is the shape the failure takes in practice.
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
  fails if it never comes up**, then stops it and asserts the child has exited
  and that the port accepts a fresh bind.
  **The readiness wait is what stops the case being a tautology.** Without it, a
  `serve.py` that dies instantly on an import error satisfies both closing
  assertions — the process has certainly exited and the port is certainly free —
  so the case would pass against a server that never worked at all. It is the
  same trap `tools/verify_coverage.py` was rewritten to escape, and it is the
  likelier failure here than a genuine orphan.
  **The confirming bind retries for a bounded period** rather than asserting on
  one attempt: a socket the child held can sit in `TIME_WAIT`, so a single
  immediate bind can fail while nothing is holding the port in any sense the
  invariant means.
  The invariant is worded as the *supervisor's* contract, not the tray's,
  because that is what the case can drive: reaching the Qt shutdown path needs a
  `QApplication` and a display, and §11 records that as an unchecked gap rather
  than claiming this case covers it.
  The case **picks a free port itself** — bind a socket to port 0, read the
  number the kernel assigned, close it, and pass that concrete number as
  `LOTTO_PORT` — rather than running on 4322, where a developer with their own
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
  `serve.py` is unaffected, which is the point of INV-19.
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
  `wait()`. The user sees the quit take up to the timeout rather than the tray
  vanishing and the server surviving it.
- **The child starts but never answers.** `is_ready()` times out — a bad
  `LOTTO_PORT`, an import error in `serve.py`, a machine under enough load to
  miss the window. The tray reports it and leaves the icon in its stopped state
  rather than opening a browser tab on a refused connection. This is the case
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
  unaffected — the claim README.md makes about the project being standard
  library plus `dbus-python` stays true for everything except this one file.

## 7. Tests

Both of this spec's cases live in `tools/verify_page.py`, the script LOTTO-0002
§7 introduces — **one script for all three parts of the split**, joining
`tools/verify_privacy.py`, `tools/verify_sources.py`, `tools/verify_coverage.py`
and `tools/verify_pools.py`. Exit code is the signal, as with the other four.
One script rather than three because the ten cases share their fixtures, their
temporary-directory setup and their stub builder, and because CLAUDE.md's
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
  not use the stub-builder seam. `LOTTO_NO_BUILD` is what keeps it cheap: the
  child binds and serves without building, so the case costs a process spawn
  rather than 27 network requests against the operator's API.
- **`serve_is_headless` must run in a fresh interpreter**, not in the one
  running the suite. By the time the other nine cases have run, the suite's own
  process has imported whatever they needed — including `supervise`, which
  `no_orphan_server` drives directly — so asserting on `sys.modules` there would
  measure the test harness rather than the modules under test.

**Each case is observed failing before the invariant is accepted**, per
LOTTO-0002 §7, which owns that rule and the reasoning for it. The deliberate
breakages for this document's two cases: add `import PySide6.QtCore` to
`serve.py` and watch `serve_is_headless` fail, then do the same to
`supervise.py`; and drop the `kill()` fallback (or the `wait()`) and watch
`no_orphan_server` fail. A third is worth running because it is the one that
case was rewritten for — make `serve.py` exit immediately at startup and confirm
`no_orphan_server` fails on the readiness wait, rather than passing on closing
assertions a dead child satisfies trivially.

## 8. Alternatives considered (and rejected)

- **A systemd user unit driven by the tray**, as the user's stats tray does.
  Rejected 2026-08-02 for the install step: it turns "clone the repo and run the
  tray" into a unit file to write, a `systemctl --user daemon-reload` and an
  enable. Still available to anyone who wants it, precisely because INV-19 keeps
  `serve.py` Qt-free — the alternative is preserved rather than closed off.
- **The lifecycle inside `tray.py`, with no `supervise.py`.** Rejected: it makes
  INV-20's check need a `QApplication` and a display, in a script that runs
  headless beside four others — the third gap in §2. The module is small enough that the
  testability is the whole argument.
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
- **Network:** none of its own. The tray's Refresh item is one loopback POST
  that causes the server to make the 27 requests LOTTO-0002 §10 already counts;
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
| INV-19 `serve.py` is Qt-free | `tools/verify_page.py::serve_is_headless` |
| INV-20 no orphan server | `tools/verify_page.py::no_orphan_server` |
| §4.4 `supervise.py` Qt-free and spawning nothing on import | `tools/verify_page.py::serve_is_headless` — INV-19 covers both modules, each in a fresh interpreter |
| §4.1 `is_ready()` gating every browser open | `tools/verify_page.py::no_orphan_server` — the case fails if the child never answers, which is that same wait |
| §4.1 a new token per `start()` | **nothing** — a supervisor that reused one token across restarts would pass every case here; the stale-tab 403 it would suppress is a browser-side behaviour no exit-code script observes |
| §4.2 the reap also running on `aboutToQuit` | **nothing** — INV-20 drives `Supervisor.stop()` directly, because reaching the Qt shutdown signal needs a `QApplication` and a display, which is what §4.1 split the module to avoid. Code review only |
| §4.3 the four Qt details (thread pool, live wrapper set, quit-on-close, wording agreement) | **nothing** — each is a Qt runtime behaviour needing a display; the wrapper-lifetime one is a crash that a short run does not reproduce |
| §4.3 the state poll noticing a child that died on its own | **nothing mechanical** — driving it needs a tray; observable by starting the tray with the port already occupied |
| §4.3 the busy guard admitting one long action at a time | **nothing** — a second click needs a running tray and a display. The server's 409 (LOTTO-0014 §4.1) is the backstop; it is the tray's *reporting* of it that goes unchecked |
| §4.3 `tray.py` reading `open_on_start`, and its fallback on a corrupt file | **nothing mechanical** — needs a tray and a session. The fallback is what stops a bad settings file hiding the icon, so it is verified by writing a malformed `settings.json` and starting the tray once |
| §4.5 the port being read once and agreeing end to end | **nothing** — a disagreement surfaces as a 421 on every request, which is loud at run time and invisible to a check that supplies the port itself |
| §6 the tray exiting non-zero with no system tray | **nothing mechanical** — depends on the session's tray implementation; verified by running it under a session with no tray |

Twelve rows, eight `nothing`. (§4.2's environment channel for the token is not
tabulated here — LOTTO-0014 §11 owns that row, since the rule it states is the
token's, and a rule tabulated twice becomes two rules that disagree.)

That ratio is high, and it is honest rather than alarming: this part of the
split is the one needing a display and a desktop session, and its mechanically
checkable contracts — the headless imports and the reaped child — are exactly
the ones that fail silently. **Seven of the eight are loud at run time.** The
exception is the per-`start()` token: its breach is silent by construction,
because a supervisor reusing one token across restarts leaves a stale page
authorised against a server that never issued it one. That row is code review
only, and it is the gap worth knowing about.

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
| 1 | 2026-08-02 | 2 | 4 | 4 | 9 | 8 | All 27 verified findings fixed; 0 unverified, 0 deferred. Both lanes independently led on the same two CRITICALs, and both were about the one code block an implementer copies. **§4.2's sketch minted the token and called `Popen` at module scope**, contradicting §4.1's "minted per `start()`" and §4.4's "importing it must spawn nothing" — and encoding precisely the alternative §8 rejects; it is now a `Supervisor` class with the mint inside `start()`. **The same `Popen` set no `cwd`.** The spec had already identified the hazard — an autostart entry's working directory is not the repository — and closed only the half about the *script* path. Verified: `history.py::ARCHIVE` is `"archive_results.json"`, `backfill.py::CACHE` is `"archive_cache"` and `tickets.py::load()` defaults to `"lotto_sms_raw.txt"`, all cwd-relative, so an autostarted tray would spawn a server that finds no data and renders the empty state — this project's cardinal failure arriving through the one launch path this item adds, on a machine where running the same server by hand works. `cwd=HERE` added. **Two further CRITICALs, one per lane.** §11 credited `no_orphan_server` with catching a Qt import in `supervise.py`; measured (`env -u DISPLAY python3 -c "import PySide6.QtWidgets"` succeeds — only constructing a `QApplication` needs a display), so the row was false in the one table whose purpose is saying what is *not* checked. INV-19 now covers both modules and the row cites it. And `open_on_start` was orphaned across the split: LOTTO-0002 §4.7 states it is "read by **`tray.py`** at startup", while this document — which owns `tray.py` — never mentioned it, so an implementer reading only this spec ships a tray that ignores the setting the other spec promises. §4.3 now owns the reading and the corrupt-file fallback; §4.7 keeps the file. **One HIGH was a live tautology:** `no_orphan_server` asserted the child had exited and the port was free, both of which a `serve.py` that dies instantly on an import error satisfies — the case would have passed against a server that never worked. It now waits on a new `is_ready()` and fails if the child never answers. That split also fixed a real design gap neither lane framed as one: `Popen` returns before the child binds, so every browser open raced the bind. Also fixed: `token: str | None` in the surface block, a runtime `TypeError` before 3.10 against a floor both README.md:55 and CLAUDE.md:9 assert; §10 cited a busy guard §4.3 never stated (the prior art has one, the spec dropped it); §11's "The six are all loud at run time" was false of the per-`start()` token row, whose own text calls the breach silent; and §7's constraint sentence left "Two of them" with no referent. Doc grew 443 -> 580 lines, most of it §4.1's readiness contract and §6's three new failure modes. |
| 0-split | 2026-08-02 | — | — | — | — | — | **Provenance row — no reviewer was dispatched, and this is not a review loop.** Split out of `docs/specs/LOTTO-0002-local-web-page.md` on the seam that spec's §12 recommended and the user chose: this document takes §4.8, INV-19 and INV-20 — the tray, the supervisor and the headless contract — and LOTTO-0002 kept §4.1–§4.7 with INV-12–18 and INV-21. **A second cut the same day** moved that spec's §4.3–§4.4 and INV-12–14 and INV-21 again, into `docs/specs/LOTTO-0014-http-surface-and-security.md`, once the first cut proved to remove only 66 of the parent's 1,161 lines; this document was unaffected by it beyond cross-references. The parent had run three cold-eyes loops (83 verified findings fixed, 0 deferred) and **converged by cap rather than clean**, with two of the three loops producing more defects from their own fixes than from the draft. **Those loops confer nothing on this document**: they were run against 1,161 lines that no longer exist, so the gate starts again from loop 1 on these bytes. Content carried over was re-grounded rather than trusted — PySide6 6.11.0 and `QSystemTrayIcon.isSystemTrayAvailable` confirmed by import, the port claim re-measured against `ss -ltn` and a real bind, and the four Qt details in §4.3 read out of `Ants_Projects_Hub_Website/tray/ants-stats-tray.py` rather than recalled. Two of those four (the runnable-wrapper set and `setQuitOnLastWindowClosed(False)`) are new here — the parent named the prior art without carrying them. |
