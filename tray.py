#!/usr/bin/env python3
"""Tray icon for the local lottery page (LOTTO-0013).

The menu and the icon and nothing else. Everything about the server's lifetime
lives in supervise.py, which is Qt-free so INV-20 can drive it from a headless
exit-code script.

    python3 tray.py

Four details are copied from the user's existing stats tray
(Ants_Projects_Hub_Website/tray/ants-stats-tray.py), and each is load-bearing
rather than stylistic - see the comments at their sites.
"""

import os
import webbrowser

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

import supervise

HERE = os.path.dirname(os.path.abspath(__file__))
ICON_RUNNING = os.path.join(HERE, "icons", "tray-running.svg")
ICON_STOPPED = os.path.join(HERE, "icons", "tray-stopped.svg")
POLL_MS = 5000  # bounds how long the icon can claim a dead server is running


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


class LottoTray(QSystemTrayIcon):
    def __init__(self, sup):
        super().__init__()
        self.sup = sup
        self.running_icon = QIcon(ICON_RUNNING)
        self.stopped_icon = QIcon(ICON_STOPPED)
        self.busy = False  # one long action at a time

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

    def note(self, body):
        self.showMessage("Lotto Tracker", body, self.running_icon, 5000)

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
                self.note(f"The server is not answering: {msg}")
            elif not webbrowser.open(self.sup.url):
                self.note(f"Could not open a browser. The page is at {self.sup.url}")

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
            # .get() rather than [], because a KeyError raised here is inside a
            # Qt slot. INV-23 asserts the map is total, so the fallback is
            # unreachable; it exists so that if it ever were, the user sees a
            # bare outcome word rather than the tray dying mid-notification.
            self.note(
                supervise.REFRESH_MESSAGE.get(msg, msg)
                if ok
                else f"Refresh failed: {msg}"
            )

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
            self.note("Server started." if ok else f"Could not start it: {msg}")

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
        QApplication.instance().quit()


def main():
    app = QApplication([])
    app.setApplicationName("Lotto Tracker")
    app.setQuitOnLastWindowClosed(False)  # dismissing a notification must not quit

    # Before anything is spawned: starting the server and then exiting non-zero
    # would orphan a live child holding the port.
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Lotto Tracker", "This desktop has no system tray.")
        return 1

    sup = supervise.Supervisor()
    tray = LottoTray(sup)
    tray.show()
    if sup.port_fallback:
        tray.note(sup.port_fallback)

    sup.start()
    tray.sync()

    # A session logout never clicks Quit, and that is the commonest way an
    # orphan would be created.
    app.aboutToQuit.connect(sup.stop)

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
