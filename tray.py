#!/usr/bin/env python3
"""Tray icon for the local lottery page (LOTTO-0013).

The menu and the icon and nothing else. Everything about the server's lifetime
lives in supervise.py, which is Qt-free so INV-20 can drive it from a headless
exit-code script.

    python3 tray.py
    LWSM_MANAGED=1 python3 tray.py   # no icon; the server, logged to stdout

Four details are copied from the user's existing stats tray
(Ants_Projects_Hub_Website/tray/ants-stats-tray.py), and each is load-bearing
rather than stylistic - see the comments at their sites.
"""

import datetime
import os
import webbrowser

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

import supervise
import watch_sms  # for the dump's path only; nothing here imports dbus

HERE = os.path.dirname(os.path.abspath(__file__))
ICON_RUNNING = os.path.join(HERE, "icons", "tray-running.svg")
ICON_STOPPED = os.path.join(HERE, "icons", "tray-stopped.svg")
POLL_MS = 5000  # bounds how long the icon can claim a dead server is running


def managed():
    """True when a process manager started us and owns the presentation.

    A hint about whether an ICON is wanted. It is unauthenticated, trivially
    forged, inherited by every child process and readable out of
    /proc/<pid>/environ, so **no authorisation may hang off it** - not the
    token, not the Host allowlist, not a POST check, not the port.

    It does decide process lifetime, and that is not an exception: with no menu
    there is no Quit and no aboutToQuit, so the managed path REMOVES the ability
    to stop the server rather than granting anything (LOTTO-0013 §4.7). A branch
    that takes a capability away needs only to be correct; a branch that lets
    something through on the strength of a forgeable string is the one this
    docstring forbids.

    Only "1" counts: absent, empty or anything else is the unchanged path.
    """
    return os.environ.get("LWSM_MANAGED") == "1"


def run_headless(sup=None):
    """Start the server, log to stdout, and wait - no icon, and no stop path.

    Everything the tray does *to* the server hangs off the menu, and the one
    menu item this file is warned about is "Quit (stops the server)". Under a
    manager that stop is the wrong answer twice over: the manager owns the
    process tree it started, and a reap it did not ask for looks to it like the
    service dying. So this path never calls sup.stop() - not on a failed
    readiness poll, not on the way out. wait() only collects the child's exit
    status; it does not end it.

    open_on_start is not honoured here either: a run with no icon has no desktop
    session to open a browser into.
    """
    sup = supervise.Supervisor() if sup is None else sup
    if sup.port_fallback:
        print(sup.port_fallback, flush=True)
    sup.start()
    print(f"managed: no tray icon. serving on {sup.url}", flush=True)
    # Reported, not acted on. A server that is slow to answer is still the
    # manager's to restart, and the only alternative here would be to stop it.
    if not sup.is_ready():
        print("the server has not answered yet; still waiting", flush=True)
    return sup.child.wait()


# ------------------------------------------------------------ background jobs
#
# A refresh drives a rebuild that takes tens of seconds, and is_ready() blocks
# for up to ten. Either on the GUI thread freezes the menu mid-click and makes
# Plasma offer to kill us.


class _JobSignals(QObject):
    done = Signal(bool, str)


class _Job(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = _JobSignals()

    def run(self):
        try:
            self.signals.done.emit(True, self.fn() or "")
        except Exception as err:  # noqa: BLE001 - any failure becomes a notification
            self.signals.done.emit(False, str(err))


_jobs = set()  # QThreadPool owns the C++ side; this keeps the Python wrapper alive


def run_async(fn, on_done):
    job = _Job(fn)
    _jobs.add(job)
    job.signals.done.connect(lambda ok, msg: (_jobs.discard(job), on_done(ok, msg)))
    QThreadPool.globalInstance().start(job)


# -------------------------------------------------------------------- the tray


def dump_size():
    """Bytes in the SMS dump, or 0. LOTTO-0003's growth signal."""
    try:
        return os.path.getsize(watch_sms.DUMP)
    except OSError:
        return 0


class LottoTray(QSystemTrayIcon):
    def __init__(self, sup, watch=None):
        super().__init__()
        self.sup = sup
        self.watch = watch
        self.running_icon = QIcon(ICON_RUNNING)
        self.stopped_icon = QIcon(ICON_STOPPED)
        self.busy = False  # one long action at a time
        # The baseline for "has a new ticket arrived?". Taken before the
        # watcher is started, so the first thing it appends is noticed.
        self.dump_size = dump_size()
        # The day the re-buy check last ran (LOTTO-0034 §4.6). None so the
        # first sync() after startup always checks.
        self.expiry_checked_on = None

        menu = QMenu()
        self.act_open = menu.addAction("Open page", self.open_page)
        self.act_refresh = menu.addAction("Refresh results now", self.refresh)
        menu.addSeparator()
        self.act_toggle = menu.addAction("Stop server", self.toggle)
        menu.addSeparator()
        menu.addAction("Quit (stops the server)", self.quit)
        self.setContextMenu(menu)

        self.activated.connect(
            lambda reason: self.open_page()
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.sync)
        self.timer.start(POLL_MS)

    # Icon, tooltip and menu wording all say the same thing, so state is never
    # read off a 22-pixel icon alone.
    def sync(self):
        if self.busy:
            return
        on = self.sup.is_running()
        self.setIcon(self.running_icon if on else self.stopped_icon)
        self.setToolTip(
            f"Lotto Tracker — running on {self.sup.url}"
            if on
            else "Lotto Tracker — server stopped"
        )
        self.act_toggle.setText("Stop server" if on else "Start server")
        # Disabled while stopped rather than implicitly starting the server:
        # asking to see a page is not asking to start something.
        self.act_refresh.setEnabled(on)
        self.act_open.setEnabled(on)
        self.check_new_tickets()
        self.check_expiring_tickets()

    def check_new_tickets(self):
        """Notice what the watcher appended, say so, and score it (LOTTO-0003).

        Size rather than a parse: `watch_sms.py` only ever appends, so a file
        that grew holds records that were not there before, and comparing two
        integers every five seconds costs nothing. A SHRUNK file is an adb
        re-pull rewriting the dump, which is not new arrivals - it re-baselines
        silently rather than announcing a win that may not exist.

        The refresh is what makes the cable unnecessary in the way the user
        actually meant it: a ticket that reaches the file but not the page has
        not arrived as far as anyone can see. INV-37.
        """
        size = dump_size()
        if size <= self.dump_size:
            self.dump_size = size
            return
        self.dump_size = size
        # Never "refreshing" when nothing is, and never naming a menu item this
        # state has disabled: supervise.new_ticket_notice() owns both, so the
        # wording is checkable without a Qt object (LOTTO-0007 (k)).
        running = self.sup.is_running()
        self.note(supervise.new_ticket_notice(running, self.busy))
        if running and not self.busy:
            self.refresh()

    def check_expiring_tickets(self):
        """Say once a day which tickets are nearly finished (LOTTO-0034 §4.6).

        No new timer: sync() already runs at POLL_MS, and comparing one date is
        free where recomputing 561 tickets every five seconds would not be. The
        date guard also handles the two cases a 24-hour timer gets wrong -
        midnight rollover while the tray is running, and resume from suspend -
        because it keys on the date changing rather than on elapsed time.

        Every decision belongs to supervise.expiry_notices() - which tickets
        qualify, what the notice says, and the state file that makes it once.
        This supplies today and displays strings, and holds nothing else. That
        split is what makes INV-52 to INV-56 reachable from a headless script.
        """
        today = datetime.date.today()
        if today == self.expiry_checked_on:
            return
        self.expiry_checked_on = today
        for body in supervise.expiry_notices(today):
            self.note(body)

    def note(self, body, bad=False):
        """A desktop notification. `bad=True` for anything that FAILED.

        Every notice used to carry the green tick, including "Refresh
        failed", "The server is not answering" and the watcher-stopped
        notice - a failure wearing the success glyph. The icon is what a
        screen reader and a high-contrast theme key off, and this is the
        tray's only unprompted surface.
        """
        icon = (QSystemTrayIcon.MessageIcon.Critical if bad
                else QSystemTrayIcon.MessageIcon.Information)
        self.showMessage("Lotto Tracker", body, icon, 5000)

    def _begin(self, action, doing):
        self.busy = True
        self.setToolTip(f"Lotto Tracker — {doing}…")
        action.setEnabled(False)

    def _end(self, action, label):
        self.busy = False
        action.setText(label)
        self.sync()

    def open_page(self):
        if self.busy or not self.sup.is_running():
            return
        self._begin(self.act_open, "starting")

        def finished(ok, msg):
            self._end(self.act_open, "Open page")
            if not ok:
                self.note(f"The server is not answering: {msg}", bad=True)
            elif not webbrowser.open(self.sup.url):
                self.note(
                    f"Could not open a browser. The page is at {self.sup.url}",
                    bad=True,
                )

        def go():
            if not self.sup.is_ready():
                raise RuntimeError("timed out waiting for the server")

        run_async(go, finished)

    def refresh(self):
        if self.busy:
            return
        self._begin(self.act_refresh, "refreshing")
        self.act_refresh.setText("Refreshing…")

        def finished(ok, msg):
            self._end(self.act_refresh, "Refresh results now")
            # `msg` is one of supervise's four outcomes when ok, and an
            # exception's text when not. The tray composes only the failure
            # line - the one path that has no outcome because nothing was
            # determined about the build (LOTTO-0013 §4.6, INV-23).
            # refresh_message() replaces the bare map lookup (LOTTO-0019 §4.5):
            # a DONE refresh now says what it found. The .get()-not-[] guard
            # that used to be explained here moved into that function with the
            # lookup itself.
            if ok:
                self.note(supervise.refresh_message(msg, self.sup.found))
            else:
                self.note(f"Refresh failed: {msg}", bad=True)

        run_async(self.sup.refresh, finished)

    def toggle(self):
        if self.busy:
            return
        if self.sup.is_running():
            # Synchronous, like quit(): see quit() for why.
            self.sup.stop()
            self.sync()
            self.note("Server stopped.")
            return
        self._begin(self.act_toggle, "starting")

        def finished(ok, msg):
            self._end(self.act_toggle, "Stop server")
            if ok:
                self.note("Server started.")
            else:
                self.note(f"Could not start it: {msg}", bad=True)

        def go():
            self.sup.start()
            if not self.sup.is_ready():
                raise RuntimeError("started but never answered")

        run_async(go, finished)

    def quit(self):
        # SYNCHRONOUS, and this is the one place the off-the-GUI-thread rule is
        # deliberately broken. Dispatched to the thread pool, this returns
        # immediately, the event loop ends and the process exits before wait()
        # completes - orphaning the child that holds the port, which is exactly
        # what INV-20 forbids. A freeze of up to the stop() timeout is the cost.
        self.sup.stop()
        if self.watch is not None:
            self.watch.stop()
        QApplication.instance().quit()


def main():
    # Before any Qt object exists: a managed run must not need a display, and
    # must not reach the menu that can stop the server (INV-25).
    if managed():
        return run_headless()

    app = QApplication([])
    app.setApplicationName("Lotto Tracker")
    app.setQuitOnLastWindowClosed(False)  # dismissing a notification must not quit

    # Before anything is spawned: starting the server and then exiting non-zero
    # would orphan a live child holding the port.
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Lotto Tracker", "This desktop has no system tray.")
        return 1

    sup = supervise.Supervisor()
    watch = supervise.SmsWatch()
    tray = LottoTray(sup, watch)
    tray.show()
    # A NOTIFICATION, never a print. supervise.py falls back on an unusable
    # $PORT or $LOTTO_PORT rather than exiting (its docstring says why), and a
    # fallback nobody sees is the silent substitution that policy exists to
    # avoid - an autostarted tray has no terminal for a print to land in. After
    # show(), because showMessage() needs a visible icon to hang off.
    if sup.port_fallback:
        tray.note(sup.port_fallback)

    sup.start()
    # Started after the tray exists so a failure can be NOTIFIED rather than
    # printed (LOTTO-0003). Without this child no new ticket ever reaches the
    # dump, and the page would go on rendering an increasingly old set of
    # tickets with nothing anywhere saying collection had stopped.
    watch.start()

    # Connected HERE, immediately after the children exist, and not further
    # down. A session logout never clicks Quit, and that is the commonest way
    # an orphan would be created - but it is not the only one. tray.sync()
    # below reaches supervise.expiry_notices(), whose write path §4.5 states
    # is unguarded, and expiry.DISPLAY_NAME[t.game] is an unguarded subscript
    # §4.7 records as checked by nothing. An unwritable $XDG_CONFIG_HOME, a
    # read-only home or a game missing from that table therefore raises
    # BEFORE app.exec(), and with these connected later the server child
    # spawned two lines up was orphaned holding the port - INV-20, by a route
    # neither spec's failure-mode list predicts. Connecting first costs
    # nothing and closes the whole window.
    app.aboutToQuit.connect(sup.stop)
    app.aboutToQuit.connect(watch.stop)

    tray.sync()

    # died_early() waits up to three seconds for the child to fall over on its
    # own imports (dbus-python absent, KDE Connect not running), and three
    # seconds on the GUI thread is a frozen menu.
    def watcher_checked(ok, msg):
        if not ok or msg == "died":
            tray.note("New tickets will NOT arrive on their own — the SMS "
                      "watcher stopped. Import over the cable meanwhile.",
                      bad=True)

    run_async(lambda: "died" if watch.died_early() else "", watcher_checked)


    # open_on_start is read here because tray.py is the file that acts on it.
    # A missing, unreadable or malformed settings.json falls back to the default
    # rather than raising: a corrupt settings file must never be the reason no
    # icon appears (supervise.read_settings does that; LOTTO-0002 §4.7 owns the
    # format). The open waits on is_ready(), off the GUI thread, so the browser
    # never lands on a port that is not answering yet.
    if supervise.read_settings()["open_on_start"]:
        tray.open_page()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
