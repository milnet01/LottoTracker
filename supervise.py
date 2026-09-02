"""Own the server child process: its token, its port, its life and its death.

No Qt at any depth (LOTTO-0013 INV-19), and otherwise the standard library
plus `expiry` and `tickets` - the two project imports LOTTO-0034 §4.7 adds, so
that the re-buy warning's selection and wording sit where a headless script can
reach them. `expiry` itself imports nothing from the project (INV-50). That is
the whole reason this is a separate module from tray.py: putting the spawn-and-reap
contract in the tray would make INV-20's check need a QApplication and a running
display, inside a script that has to sit beside four headless tools/verify_*.py.
Splitting it out costs one small module and buys a testable lifecycle.

Importing this module spawns nothing and mints nothing. Module scope holds the
imports and HERE and no state.
"""

import datetime
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import expiry
from tickets import load as load_tickets

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


def new_ticket_notice(running, busy):
    """What the tray says when the dump grew. LOTTO-0003 §4.7, INV-37.

    Here rather than in tray.py for refresh_message()'s reason: the wording is
    a decision, the tray is the only place a decision cannot be checked without
    constructing a QSystemTrayIcon, and LOTTO-0003 §11 records INV-37 as
    stated-but-unchecked because of exactly that. Moving the decision out makes
    it checkable from a headless script; the tray keeps only the call.

    Every branch has to name an action the user can actually take, which is
    what the stopped-server branch got wrong (LOTTO-0007 (k)): it said to use
    *Refresh results now*, and `tray.sync()` DISABLES that item while the
    server is stopped - deliberately, because asking to see a page is not
    asking to start something (LOTTO-0013). So the item it names had to give,
    not the enablement. *Start server* IS enabled in that state, and starting
    the server builds the model, so it does score the new ticket.

    The busy branch is unreachable through `sync()`, which returns early while
    busy (§4.7). It is kept as a guard against a second caller, and it claims
    only what is true of any caller: the next refresh will pick the ticket up.

    No ticket data in any branch, for refresh_message()'s reason - a desktop
    notification may be logged and synced off the machine.
    """
    if not running:
        return ("A new lottery SMS arrived. "
                "Use “Start server” to score it.")
    if busy:
        return ("A new lottery SMS arrived. "
                "It will be scored on the next refresh.")
    return "A new lottery SMS arrived — refreshing the page."


# ------------------------------------------------------------ re-buy warnings
#
# LOTTO-0034. The project's primary job: tickets are bought ten draws at a time,
# and the app has to say when one is nearly finished so the next one gets
# bought. Here rather than in tray.py for new_ticket_notice()'s reason - the
# wording, the selection and the state file are all decisions, and a decision
# inside tray.py cannot be checked without constructing a QSystemTrayIcon.

WARN_AT = 2       # draws left, at or below which a ticket is warned about (§3.1)
PRUNE_DAYS = 90   # how long a warned ticket's record is kept (INV-55)

UNKNOWN_GAME_NOTICE = (
    "A ticket names a lottery game this app does not recognise, so it cannot "
    "say when that ticket runs out. The draw calendar needs updating."
)


# Explicit, not %a/%b - see expiry_notice().
_DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def expiry_notice(game_name, final_draw, draws_left):
    """One ticket's re-buy warning, as a string. LOTTO-0034 §4.7, INV-54.

    The game name, the final draw date and the number of draws left, and NO
    other field of the ticket: not the reference, the board numbers, the cost,
    the prize or the purchase date. That bound is the whole of §3.3's exception
    to new_ticket_notice()'s "no ticket data in any branch" rule - the user was
    shown the trade and chose usefulness, because with two tickets running a
    notice that will not name the game cannot say what to go and buy. A desktop
    notification may be logged and synced off the machine, so the exception is
    bounded here rather than widened at the call site.

    The date is formatted by hand rather than with %-d: the zero-padded %d
    reads as a serial number in a sentence, and %-d is glibc-only. The day and
    month names come from the tables below rather than %a and %b, which go
    through LC_TIME - and Qt calls setlocale() when QApplication is built, so
    those two words would arrive in the desktop's language inside an otherwise
    English sentence.
    """
    return (
        f"Your {game_name} ticket has {draws_left} "
        f"draw{'' if draws_left == 1 else 's'} left — last draw "
        f"{_DAY_NAMES[final_draw.weekday()]} {final_draw.day} "
        f"{_MONTH_NAMES[final_draw.month - 1]}. "
        "Time to buy the next one."
    )


def _read_warned(path):
    """The state file's records, or none of them.

    A missing, unreadable or malformed file yields an empty list rather than
    raising - read_settings()'s rule, for read_settings()'s reason. The cost is
    a REPEATED notice rather than a lost one, which is the right way round for
    a file the user may delete.
    """
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict) or not isinstance(data.get("warned"), list):
        return []

    def usable(r):
        if not (isinstance(r, dict) and isinstance(r.get("ref"), str)
                and isinstance(r.get("final"), str)):
            return False
        try:
            datetime.date.fromisoformat(r["final"])
        except ValueError:
            # `final` is compared LEXICALLY against an ISO cutoff, so a value
            # that is not a date is never older than it and is never pruned -
            # and its `ref` then stays in the warned set for good, silencing
            # the one notice this project exists to give (INV-55, INV-56).
            return False
        return True

    return [r for r in data["warned"] if usable(r)]


def write_atomic(path, text, mode=None):
    """Write text via a temp file in the same directory, then rename.

    open(path, "w") truncates BEFORE the write, so an interrupted write leaves
    a short file that reads as a complete one. serve.py writes the autostart
    .desktop entry through this, where the stakes are highest: presence IS the
    state, so a truncated entry reads as "autostart on" and autostarts nothing.

    _write_warned() below stays separate rather than calling this. It also
    fsyncs and chmods, and LOTTO-0034 s4.5 chose its crash direction on
    purpose; folding the two would put that argument in a helper shared with
    callers that do not make it.
    """
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    if mode is not None:
        os.chmod(tmp, mode)
    os.replace(tmp, path)


def _write_warned(path, records):
    """The state file's one writer (LOTTO-0034 §4.5).

    Temp file then rename, and 0600. open(path, "w") empties the file BEFORE
    json.dump runs, so a failure between the two destroyed every record rather
    than one - which inverts the crash direction §4.5 chose on purpose. That
    section accepts a crash costing a MISSED notice; losing the history costs
    the opposite, re-warning every live ticket and breaching §3.2's "say it
    once", which is a user decision rather than an implementation detail. It
    also gives §6's full-disk case a bound: the tray dies, but the record of
    what has already been said survives.

    Owner-only, because the records carry VAS references and CLAUDE.md's
    privacy rule treats a reference as identifying on its own; XDG asks for
    0700 on a directory this code creates.
    """
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, mode=0o700, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as fh:
        json.dump({"warned": records}, fh)
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _qualifies(draws_left, ref, warned):
    """§4.4's test: is this ticket owed a re-buy notice right now?

    Both halves matter. The upper bound is the user's decision (§3.1); the
    LOWER bound is what stops a first run against a dump of 561 mostly-finished
    tickets firing hundreds of notices, and it is what makes INV-52 true - an
    expired ticket is never warned about however recently it expired, because
    "two draws remain" would then be false.
    """
    return 0 < draws_left <= WARN_AT and ref not in warned


def expiry_notices(today, tickets=None, state_path=None):
    """Every notice owed right now, and the state write that makes it once.

    LOTTO-0034 §4.7; INV-52, INV-53, INV-55, INV-56.

    This owns loading, selection and the state file; tray.py owns none of them
    and holds no decision, which is what makes those four invariants reachable
    from a headless script. `tickets` and `state_path` are injectable so a
    verifier can supply constructed tickets and a temporary file.

    A ticket qualifies when BOTH hold: 0 < draws_left <= WARN_AT, and its
    reference is not already recorded. The LOWER bound is not decoration - it
    is what stops a first run against a dump of 561 mostly-finished tickets
    firing hundreds of notices, and an expired ticket must never be warned
    about however recently it expired, because "two draws remain" would then be
    false (INV-52).

    The unit is the TICKET, not the entry: a Lotto ticket is entered in up to
    three pools sharing one start and one ndraws, so all three expire together
    and warning per entry would say the same thing three times. Ticket.ref is
    the key - measured 2026-08-22, 561 tickets carry 561 distinct references.

    The record is written BEFORE the notices are returned, not after. A crash
    between the two then costs a missed notice rather than a repeated one,
    which is the OPPOSITE direction to _read_warned()'s rule and is deliberate:
    "say it once" is a user decision, so a duplicate contradicts the contract
    directly, while a missed notice is a cost the spec already accepts. Do not
    harmonise the two.
    """
    if tickets is None:
        # tickets.load() opens the dump directly and RAISES on a missing one,
        # so the catch is here rather than left to the caller: this runs inside
        # the tray's timer slot, where an exception kills the tray.
        try:
            tickets = load_tickets()
        except (OSError, ValueError):
            tickets = []
    path = state_path or expiry_state_path()

    # Pruned on every write, keyed on the ticket's own final draw rather than
    # on the write date, so the file cannot grow without bound (INV-55).
    cutoff = (today - datetime.timedelta(days=PRUNE_DAYS)).isoformat()
    # Read ONCE. The write test at the end compared against a SECOND call, so
    # a record the reader had dropped was absent from both sides and never
    # triggered the rewrite that would clear it from disk. Such a record is
    # still left there: it is invisible to every reader, and spotting it here
    # would need a second reader of this file, which s4.5 forbids.
    on_disk = _read_warned(path)
    records = [r for r in on_disk if r["final"] >= cutoff]
    warned = {r["ref"] for r in records}

    notices, unknown = [], False
    for t in tickets:
        try:
            left = expiry.draws_left(t.game, t.start, t.ndraws, today)
        except (KeyError, ValueError):
            # LOTTO-0031's failure class: a rebrand makes every new ticket
            # unknown at once. Loud, but ONCE per call however many tickets
            # carry it - one per ticket would be a burst of hundreds.
            unknown = True
            continue
        if not _qualifies(left, t.ref, warned):
            continue
        final = expiry.final_draw_date(t.game, t.start, t.ndraws)
        warned.add(t.ref)
        records.append({"ref": t.ref, "final": final.isoformat()})
        notices.append(
            expiry_notice(expiry.DISPLAY_NAME[t.game], final, left)
        )

    if records != on_disk:
        _write_warned(path, records)

    if unknown:
        # Deliberately NOT recorded, so it recurs every day until the table is
        # updated. Mechanically it cannot be: §4.5's record needs a `final` and
        # final_draw_date() raises for exactly these games. And it should not
        # be - this reports a DEFECT rather than nudging a re-buy, and "say it
        # once" is a decision about re-buy notices. Going quiet about a game
        # the app cannot score is LOTTO-0031 exactly (INV-53, INV-56).
        notices.append(UNKNOWN_GAME_NOTICE)
    return notices


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


def expiry_state_path():
    """Which tickets have already had their re-buy warning (LOTTO-0034 §4.5).

    Beside settings.json and resolved the same way, but a SEPARATE file, and
    that is deliberate. settings.json is read here and written only by
    serve.py::write_settings() behind its lock, because POST /settings is a
    server route (LOTTO-0013 §4.1). Putting warn-state in it would give it a
    second writer that is not the server - the exact arrangement that rule
    exists to prevent. This file has one writer, expiry_notices(), which only
    the tray process calls.
    """
    return os.path.join(config_home(), "lotto-tracker", "expiry_warned.json")


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
        token = secrets.token_urlsafe(32)
        try:
            child = subprocess.Popen(
                [sys.executable, os.path.join(HERE, "serve.py")],
                # Not optional. tickets.load()'s default dump path is relative
                # to the working directory, and an autostart session's cwd is
                # not the repository, so without this the child finds no
                # messages and renders an empty page. history.ARCHIVE and
                # backfill.CACHE were on the same list until LOTTO-0041
                # anchored them to __file__.
                cwd=HERE,
                env={
                    **os.environ,
                    "LOTTO_TOKEN": token,
                    # BOTH port variables, both set to the port this object
                    # already decided on. serve.py::resolve_port() reads $PORT
                    # first, and a $PORT inherited from the session would send the
                    # child somewhere the tray is not looking - which is the
                    # 421 on every request that §4.5 exists to prevent.
                    "LOTTO_PORT": str(self.port),
                    "PORT": str(self.port),
                },
            )
        except OSError:
            # A failed spawn must leave NOTHING behind. Minting into
            # self.token first left a token set beside no child, so post()'s
            # `if not self.token` guard passed and sent the token to whatever
            # holds the port - and refresh() polled its full 300-second
            # deadline, holding the tray's one-job flag, over a build that was
            # never started.
            self.token, self.child = None, None
            raise
        # Both, and only once the spawn has actually returned a child.
        self.token, self.child = token, child

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
            # Only a child of OURS that has died ends this early. A Supervisor
            # that spawned nothing - s4.1 and s4.6 case 3, the managed run
            # where something else started serve.py - has no child to be dead,
            # and a bare `not self.is_running()` returned False for a server
            # answering perfectly. refresh() already guards it this way; two
            # methods of one class disagreed about the same shape.
            if self.child is not None and not self.is_running():
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
        # A child of OURS that has died means the port may now belong to
        # something else, and this request carries the token. Same shape as
        # is_ready() and refresh(): a Supervisor that spawned nothing has no
        # child to test and is not covered by this.
        if self.child is not None and not self.is_running():
            raise RuntimeError("the server stopped")
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
        # Raised by stop() before it terminates, so died_early() can tell a
        # watcher that was stopped from one that fell over at startup.
        self._stopped = False

    def start(self):
        """Spawn the watcher. No-op if one is already running."""
        if self.is_running():
            return
        self._stopped = False
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
        # A watcher the user STOPPED did not die at startup. stop() raises this
        # flag before it terminates, so a wait that returns because of a stop
        # is not reported as the "dbus-python is missing" case.
        return not self._stopped

    def stop(self, timeout=5.0):
        """terminate(), then kill() after the timeout, then wait().

        Same shape as Supervisor.stop() and for the same reason: the watcher
        sits in a GLib main loop and may be mid-write to the dump, and a child
        that ignores SIGTERM would outlive the tray holding a D-Bus name.
        """
        # Before the terminate(), not after: died_early() may already be inside
        # its wait() on another thread, and it reads this flag once the wait
        # returns to decide whether the exit was a death or a stop.
        self._stopped = True
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
