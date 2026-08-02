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
    """A bad $LOTTO_PORT falls back; it never raises.

    A ValueError out of the constructor means no icon appears at all, which is
    the same outcome refused for a corrupt settings.json. Below 1024 a non-root
    tray cannot bind, so accepting it only defers the failure to a confusing
    "port in use". Returns (port, fallback_message_or_None).
    """
    raw = port if port is not None else os.environ.get("LOTTO_PORT")
    if raw in (None, ""):
        return DEFAULT_PORT, None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_PORT, f"LOTTO_PORT={raw!r} is not a number; using {DEFAULT_PORT}"
    if not MIN_PORT <= n <= MAX_PORT:
        return DEFAULT_PORT, (
            f"LOTTO_PORT={n} is outside {MIN_PORT}-{MAX_PORT}; using {DEFAULT_PORT}"
        )
    return n, None


class Supervisor:
    """Owns the token, the port and the child process. No Qt anywhere."""

    def __init__(self, port=None):
        self.port, self.port_fallback = _port_or_default(port)
        self.url = f"http://127.0.0.1:{self.port}"
        self.token = None
        self.child = None

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
                "LOTTO_PORT": str(self.port),
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
