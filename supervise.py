"""Own the server child process: its token, its port, its life and its death.

Standard library only, and no Qt at any depth (LOTTO-0013 INV-19). That is the
whole reason this is a separate module from tray.py: putting the spawn-and-reap
contract in the tray would make INV-20's check need a QApplication and a running
display, inside a script that has to sit beside four headless tools/verify_*.py.
Splitting it out costs one small module and buys a testable lifecycle.

Importing this module spawns nothing and mints nothing. Module scope holds the
imports and HERE and no state.
"""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PORT = 4322
MIN_PORT, MAX_PORT = 1024, 65535

# ------------------------------------------------------------ refresh outcomes
#
# LOTTO-0013 §4.6. The four things Supervisor.refresh() can report, and the one
# sentence each. The wording lives HERE rather than in tray.py for the reason
# port_fallback does (§4.5): this module is Qt-free, so a headless case can read
# it. INV-23 asserts the map is total and that only REFRESH_DONE reads as
# success - the other three name what is NOT known, and a user who reads only
# the first few words must not take any of them for a finished refresh.

REFRESH_DONE = "done"
REFRESH_FAILED = "failed"
REFRESH_RUNNING = "running"
REFRESH_BUSY = "busy"

POST_TIMEOUT = 30.0  # the refresh POST's own ceiling. It is answered without
                     # touching the build, so waiting longer on it only delays
                     # saying the server is not answering (§4.6).

REFRESH_MESSAGE = {
    REFRESH_DONE: "Results refreshed.",
    # Not "the previous results": a FIRST build that failed leaves no model at
    # all, and this sentence has to be true of that page too (§4.6).
    REFRESH_FAILED: (
        "The refresh failed. The page still shows what it had before, "
        "and says so."
    ),
    REFRESH_RUNNING: "Still refreshing. The page shows the result when it finishes.",
    REFRESH_BUSY: (
        "A refresh is already running. The page shows the result when it finishes."
    ),
}


def refresh_message(outcome, found=None):
    """The sentence for an outcome. Only REFRESH_DONE consults `found`.

    LOTTO-0019 §4.5, INV-29/INV-30. Three distinct DONE sentences, and the
    first two are this project's cardinal rule: "nothing was compared" and
    "compared, found nothing" are different facts and must not collapse into
    one string.

    .get(), not [], for the reason tray.py::refresh() used to record at its own
    call site: this is composed inside a Qt slot, where a KeyError kills the
    tray mid-notification. That comment moved here with the lookup. INV-23
    asserts the map is total, so the fallback is unreachable; it exists so that
    if it ever were, the user sees a bare outcome word instead of nothing.

    `found` is subscripted rather than .get()-ed on purpose: it is built by
    serve.py::_compare() and crosses no process boundary, so a missing key is
    a defect in this project's own code, not untrusted input.

    The body is composed from the two integers and nothing else - no ticket
    reference, no board label, no draw date, no division name. A desktop
    notification may be logged and synced off the machine, so the reasoning
    that keeps ticket data out of the URL (LOTTO-0014 INV-21) applies here
    with more force.
    """
    line = REFRESH_MESSAGE.get(outcome, outcome)
    if outcome != REFRESH_DONE:
        return line
    if found is None:
        # DONE with nothing to compare means exactly one thing: the first
        # successful build in this process. A failed build sets `stale` and is
        # reported as REFRESH_FAILED, so it never reaches here.
        return line + " First check this session — nothing to compare against."
    n, cents = found["new_wins"], found["new_cents"]
    if not n:
        return line + " No new wins."
    # Duplicates page.py::_rands() on purpose: this module is the Qt-free
    # lifecycle the tray imports, and importing the renderer to format one
    # number would couple the notification path to the page.
    return (
        f"{line} {n} new winning line{'' if n == 1 else 's'}, "
        f"R{cents / 100:,.2f}."
    )


# --------------------------------------------------------------- settings I/O
#
# These live here rather than in serve.py because tray.py needs to READ them and
# may not import serve (LOTTO-0013 §4.1's one-way arrow), while serve.py owns
# WRITING them because POST /settings is a server route. One reader, three
# callers - the tray at startup, the model builder, and the settings route.
# LOTTO-0002 §4.7 owns the format: the paths, the key, the default and the
# fallback below.


def config_home():
    return os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )


def autostart_path():
    return os.path.join(config_home(), "autostart", "lotto-tracker-tray.desktop")


def settings_path():
    return os.path.join(config_home(), "lotto-tracker", "settings.json")


def read_settings():
    """The two settings as currently stored.

    A missing, unreadable or malformed settings.json yields the default rather
    than raising. All three readers share that rule, because each fails
    differently otherwise - the tray never appears, the build dies, or a toggle
    500s - and all three would be caused by one corrupt file that should simply
    have been ignored.
    """
    open_on_start = True
    try:
        with open(settings_path()) as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("open_on_start"), bool):
            open_on_start = data["open_on_start"]
    except (OSError, ValueError):
        pass
    return {
        "autostart": os.path.exists(autostart_path()),
        "open_on_start": open_on_start,
    }


def _port_or_default(port):
    """$PORT, then $LOTTO_PORT, then 4322 - and a bad value FALLS BACK, saying so.

    Same precedence as serve.py::resolve_port(), deliberately: one predictable
    knob across the project, so a tool setting $PORT does not also have to learn
    this project's own variable name.

    **The behaviour on a bad value diverges from serve.py's, and that divergence
    is deliberate. Do not "unify" these two functions.**

      * `serve.py` is MACHINE-facing. An external process manager must never be
        silently handed a port other than the one it asked for, so an unusable
        value is fatal there.
      * this is HUMAN-facing. A tray that exits just vanishes - no window, no
        terminal, no icon - so a typo in a shell profile would look exactly like
        the application being broken. It falls back and says so instead, the
        same rule read_settings() follows for a corrupt settings.json.

    That asymmetry is safe rather than merely tolerable, because the fallback
    cannot deceive a manager: a manager range-checks a port before it sets it,
    and it launches `serve.py` directly - so the unusable case is unreachable on
    the managed path, and the path where it IS reachable is the one with a human
    reading the notification. Below 1024 a non-root tray cannot bind, so
    accepting it only defers the failure to a confusing "port in use".

    Returns (port, fallback_message_or_None). The message names whichever source
    was bad, and tray.py raises it as a NOTIFICATION - never a print, which an
    autostarted tray has no terminal to carry (LOTTO-0013 §4.5).
    """
    if port is not None:
        source, raw = "port", port
    else:
        source, raw = next(
            ((n, os.environ[n]) for n in ("PORT", "LOTTO_PORT") if os.environ.get(n)),
            ("PORT", None),
        )
    if raw in (None, ""):
        return DEFAULT_PORT, None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_PORT, f"{source}={raw!r} is not a number; using {DEFAULT_PORT}"
    if not MIN_PORT <= n <= MAX_PORT:
        return DEFAULT_PORT, (
            f"{source}={n} is outside {MIN_PORT}-{MAX_PORT}; using {DEFAULT_PORT}"
        )
    return n, None


class Supervisor:
    """Owns the token, the port and the child process. No Qt anywhere."""

    def __init__(self, port=None):
        self.port, self.port_fallback = _port_or_default(port)
        self.url = f"http://127.0.0.1:{self.port}"
        self.token = None
        self.child = None
        # What the last refresh THIS Supervisor waited out found (LOTTO-0019
        # §4.5). Initialised here rather than on first use: refresh() returns
        # REFRESH_BUSY on a 409 WITHOUT polling, so a first-ever refused
        # refresh would otherwise reach an attribute that was never assigned -
        # and an AttributeError inside a Qt slot is the failure refresh_message's
        # .get() guards against one line further on. Only DONE consults it.
        self.found = None

    # -- lifecycle -----------------------------------------------------------

    def start(self):
        """Spawn the child. No-op if one is already running."""
        if self.is_running():
            return
        # Per start(), not per process: a Stop then Start is a new run and gets
        # a new token, so a tab left open across the restart is told to reload
        # rather than staying silently authorised.
        self.token = secrets.token_urlsafe(32)
        self.child = subprocess.Popen(
            [sys.executable, os.path.join(HERE, "serve.py")],
            # Not optional. The server's data paths are relative to the working
            # directory - history.ARCHIVE, backfill.CACHE, tickets.load()'s
            # default - and an autostart session's cwd is not the repository, so
            # without this the child finds no data and renders an empty page.
            cwd=HERE,
            env={
                **os.environ,
                "LOTTO_TOKEN": self.token,
                # BOTH port variables, both set to the port this object already
                # decided on. serve.py::resolve_port() reads $PORT first, and a
                # $PORT inherited from the session would otherwise send the
                # child somewhere the tray is not looking - which is the 421 on
                # every request that §4.5 exists to prevent.
                "LOTTO_PORT": str(self.port),
                "PORT": str(self.port),
            },
        )

    def is_running(self):
        return self.child is not None and self.child.poll() is None

    def is_ready(self, timeout=10.0):
        """True once the child is ANSWERING, not merely alive.

        Popen returns before the child has bound anything, so is_running() is
        true during a window in which the port refuses connections. Any HTTP
        status counts as an answer, including a 421: the question is whether
        something is listening.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.is_running():
                return False
            try:
                urllib.request.urlopen(self.url + "/status", timeout=1)
                return True
            except urllib.error.HTTPError:
                return True
            except (urllib.error.URLError, OSError):
                time.sleep(0.1)
        return False

    def stop(self, timeout=5.0):
        """terminate(), then kill() after the timeout, then wait().

        terminate() alone is not enough: the server may be mid-build inside a
        non-interruptible fetch, and a child ignoring SIGTERM while blocked in a
        socket read keeps the port. The wait() is what actually reaps it, and it
        is what INV-20 observes - `child` is deliberately left set afterwards so
        the case can inspect returncode.
        """
        self.token = None
        if self.child is None:
            return
        if self.child.poll() is None:
            self.child.terminate()
            try:
                self.child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait(timeout=timeout)
        else:
            self.child.wait(timeout=timeout)

    # -- talking to it -------------------------------------------------------

    def post(self, path, timeout=300.0):
        """POST to the child carrying the token. Raises on anything but 2xx.

        The long default is deliberate: a rebuild is 27 requests against a
        third-party API that failed four of seven attempts when measured. A
        timeout is still required, because without one a single hung POST wedges
        the tray's one-job-at-a-time guard permanently.
        """
        if not self.token:
            raise RuntimeError("the server is not running")
        req = urllib.request.Request(
            self.url + path, method="POST", headers={"X-Lotto-Token": self.token}
        )
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.read().decode()

    def status(self, timeout=5.0):
        """GET /status, parsed. No token - it is a GET (LOTTO-0014 §4.1).

        is_ready() deliberately does NOT use this, and must not be refactored
        onto it: readiness counts ANY HTTP status as an answer, including the
        421 and 500 this raises on, so the obvious dedup would make a server
        that answers 421 look like one that is not listening (§4.1).
        """
        with urllib.request.urlopen(self.url + "/status", timeout=timeout) as res:
            return json.loads(res.read().decode())

    def refresh(self, timeout=300.0, interval=2.0):
        """POST /refresh, then WAIT for the build. Returns one of the four
        outcomes above (LOTTO-0013 §4.6, INV-23).

        202 means ACCEPTED, not finished: serve.py::refresh() starts a daemon
        thread and returns, so reporting on the POST's return says "Results
        refreshed." milliseconds into a thirty-second build - and says it just
        as readily when the build then raises, which four of seven measured
        attempts did. The completion is observable from outside the process
        because State.begin() sets `building` before the POST is answered and
        State.fail() sets `stale` without touching the model (INV-18), so this
        is a wait on a signal that already exists, not a second opinion.

        `timeout` is ONE deadline over the whole call, never one for the POST
        and another for the poll.
        """
        deadline = time.monotonic() + timeout
        try:
            self.post("/refresh", timeout=min(POST_TIMEOUT, timeout))
        except urllib.error.HTTPError as err:
            # 409 alone: a refresh declined because one is already running is
            # not a failure, and the build it names is not this call's - so it
            # is reported at once and nothing is polled. Everything else (403,
            # 500, a timeout) still raises and is still reported as a failure.
            if err.code == 409:
                return REFRESH_BUSY
            raise
        while True:
            # Clamped to what is left, which is what keeps `timeout` one
            # deadline. A poll with nothing left simply fails, and the check
            # below then reports it as still running.
            left = deadline - time.monotonic()
            try:
                answer = self.status(timeout=max(0.0, min(5.0, left)))
            except (urllib.error.URLError, OSError, ValueError):
                # One dropped response, or one malformed body, is not evidence
                # that a thirty-second build failed. Only a child of OURS that
                # has died ends the wait early (§4.6 case 1); a Supervisor that
                # spawned nothing cannot ask, and keeps polling (case 3).
                if self.child is not None and not self.is_running():
                    raise RuntimeError("the server stopped while refreshing")
            else:
                if not answer.get("building"):
                    # The build is over, so this poll's answer is the one that
                    # describes it (LOTTO-0019 §4.5). BUSY and RUNNING never
                    # reach here, so neither disturbs `found`.
                    self.found = answer.get("found")
                    return REFRESH_FAILED if answer.get("stale") else REFRESH_DONE
            # The deadline is tested AFTER a poll attempt, never before, so this
            # is never returned about a build nothing tried to look at.
            if time.monotonic() >= deadline:
                return REFRESH_RUNNING
            time.sleep(min(interval, max(0.0, deadline - time.monotonic())))


class SmsWatch:
    """Own the SMS-watcher child: `watch_sms.py`, and its death (LOTTO-0003).

    The same spawn-and-reap contract as Supervisor, deliberately in the same
    Qt-free module so the lifecycle stays checkable from a headless script -
    but with no token and no port, because this child talks to the phone over
    D-Bus and never to us. It is a SECOND child of the tray, not a second
    server.

    A failure to start is not fatal and must not be silent: without it new
    tickets simply stop arriving, which on the page is indistinguishable from
    not winning - the failure this project exists to prevent. `died_early()`
    is what lets the tray say so (INV-36).
    """

    def __init__(self, command=None):
        # The command is injectable for the same reason run_headless() takes a
        # supervisor: INV-36's case has to drive spawn-and-reap without running
        # the real watcher, which would talk to the phone and APPEND TO THE
        # REAL DUMP. A verifier with a side effect on live data is not one.
        self.command = command or [sys.executable, os.path.join(HERE, "watch_sms.py")]
        self.child = None

    def start(self):
        """Spawn the watcher. No-op if one is already running."""
        if self.is_running():
            return
        self.child = subprocess.Popen(
            self.command,
            # For the reason Supervisor.start() gives: the dump, and the thread
            # state beside it, are resolved relative to the working directory,
            # and an autostarted session's cwd is not the repository.
            cwd=HERE,
        )

    def is_running(self):
        return self.child is not None and self.child.poll() is None

    def died_early(self, timeout=3.0):
        """True if the child is already gone - the "dbus-python is missing" case.

        A short wait, not a poll of the exit code alone: Popen returns before
        the child has reached its own imports, so an immediate poll() reports a
        healthy process that is about to exit(1). Returns False while it lives,
        which is the answer for every healthy run.
        """
        if self.child is None:
            return True
        try:
            self.child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return False
        return True

    def stop(self, timeout=5.0):
        """terminate(), then kill() after the timeout, then wait().

        Same shape as Supervisor.stop() and for the same reason: the watcher
        sits in a GLib main loop and may be mid-write to the dump, and a child
        that ignores SIGTERM would outlive the tray holding a D-Bus name.
        """
        if self.child is None:
            return
        if self.child.poll() is None:
            self.child.terminate()
            try:
                self.child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait(timeout=timeout)
        else:
            self.child.wait(timeout=timeout)


def free_port():
    """A concrete free port, for callers that must not collide with 4322.

    Not LOTTO_PORT=0: serve.py builds its Host allowlist from the same value, so
    port 0 would produce {"127.0.0.1:0", "localhost:0"} and 421 everything, and
    nothing reports a kernel-assigned port back to the parent.
    """
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()
