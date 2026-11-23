"""The Android app's one way into the tracker (LOTTO-0106 §4.2).

The phone's counterpart of lottotracker.py: the Kotlin in android/ calls the
functions here and nothing else, and nothing on the desktop imports this file.
Kotlin holds no decision; it moves inbox rows, strings and clicks between
Android and this module, the split tray.py keeps with supervise.py. So every
rule stays in Python, where the verifiers reach it headless.

Imports no Qt and no D-Bus: watch_sms is imported for its writer path and
filter only, never connect(). Kotlin calls every function off the main thread.
"""

import datetime
import secrets
import threading
import time

import clock
import paths
import serve
import supervise
import watch_sms

# Each fixed supervise notice that names a desktop thing, in its phone form
# (§4.5, INV-126). Every other string passes through unchanged.
PHONE_WORDING = {
    supervise.SMS_QUIET_NOTICE: (
        "No lottery SMS has reached this app for a while, so it cannot warn you "
        "about a ticket bought since then. Check that the app is still allowed "
        "to read SMS."
    ),
    supervise.WARN_STATE_NOTICE: (
        "Re-buy warnings are paused: the app could not save which tickets it has "
        "already warned you about. Closing and reopening the app will try again."
    ),
}

DAY_MS = 24 * 60 * 60 * 1000

# Seconds since the last build after which returning to the app on Wi-Fi
# rebuilds, per supervise.WIFI_REFRESH choice. None: every return. "off" is
# absent: never. Each build downloads results; on mobile data no return
# rebuilds (the user, 2026-11-23).
WIFI_INTERVAL_S = {
    "always": None,
    "hourly": 60 * 60,
    "daily": 24 * 60 * 60,
    "weekly": 7 * 24 * 60 * 60,
}

# The running server and its state, or None. Set by start_server() only.
_running = None
# time.monotonic() when the last build started, or None before the first.
_built_at = None


def phone(notice: str) -> str:
    """A notice in its phone form."""
    return PHONE_WORDING.get(notice, notice)


def import_messages(rows):
    """Append the inbox rows the dump lacks; -> how many were written (INV-129).

    `rows` holds (address, date_ms, body) per inbox row. Through
    watch_sms.append_new(), the dump's one writer path and wanted()'s one
    filter. The dump is named at the call, not by append_new()'s default, so
    a test can point it elsewhere. Kotlin calls this before start_server().
    """
    paths.ensure_data()
    # Plain Python values whatever the bridge handed over.
    clean = [(str(a), int(d), str(b)) for a, d, b in rows]
    return watch_sms.append_new(clean, watch_sms.DUMP)


def since_ms():
    """The oldest inbox date Kotlin need ask for: a day before the newest record.

    0 for an empty dump, so the first open reads the whole inbox. The day of
    overlap is absorbed by append_new()'s (date, body) key.
    """
    newest = watch_sms.high_water(watch_sms.DUMP)
    return max(0, newest - DAY_MS) if newest else 0


def start_server():
    """serve.main()'s steps on a fresh port, serving in a daemon thread.

    -> (port, token). Every route needs the token (§4.4, INV-122). An open is
    the desktop's restart, so it clears the re-buy pause (LOTTO-0034 §3 item 5),
    and it builds afresh.
    """
    global _running
    stop_server()
    supervise._warn_state_unsaved = False
    paths.ensure_data()
    port = supervise.free_port()
    token = secrets.token_urlsafe(32)
    server, state = serve.make_server(serve.build_model, token, port,
                                      token_on_every_route=True)
    # Bound before the build, as in serve.main(): the page answers at once.
    _rebuild(state)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _running = (server, state, port, token)
    return port, token


def _rebuild(state):
    """serve.refresh(), noting when it started; -> whether it started."""
    global _built_at
    started = serve.refresh(state, serve.build_model)
    if started:
        _built_at = time.monotonic()
    return started


def should_rebuild(written, metered, choice, built_at, now):
    """Whether returning to the app rebuilds (LOTTO-0106 §4.4, INV-130).

    Never on a metered network or with the choice "off". Otherwise on a new
    lottery SMS, or once the choice's interval has passed since the last build.
    """
    if metered or choice not in WIFI_INTERVAL_S:
        return False
    interval = WIFI_INTERVAL_S[choice]
    return (written > 0 or interval is None or built_at is None
            or now - built_at >= interval)


def resume(written, metered):
    """The app came back to the screen with its server still running.

    `written` is what import_messages() just wrote; `metered` is Android's
    word on the network. -> None when no server is running, so Kotlin calls
    start_server(); else (port, token, rebuilding). The page stays as it is:
    a rebuild runs in the background and the page's own poll() reloads it
    once the rebuild finishes.
    """
    if _running is None:
        return None
    _server, state, port, token = _running
    choice = supervise.read_settings()["wifi_refresh"]
    rebuilding = (should_rebuild(int(written), bool(metered), choice,
                                 _built_at, time.monotonic())
                  and _rebuild(state))
    return port, token, rebuilding


def stop_server():
    global _running
    if _running is None:
        return
    server = _running[0]
    _running = None
    server.shutdown()
    server.server_close()


def refresh():
    """The ⋮ menu's Refresh results. Returns at once; the page shows the result."""
    if _running is None:
        # Kotlin's menu is on the page, which the first open's server serves.
        return supervise.refresh_message(supervise.REFRESH_FAILED)
    started = _rebuild(_running[1])
    return supervise.refresh_message(
        supervise.REFRESH_RUNNING if started else supervise.REFRESH_BUSY)


def fetch_older():
    """The ⋮ menu's Fetch older results: waits for the download, then says how
    it went. On success the page re-scores, as the tray's does."""
    outcome = supervise.fetch_older()
    if outcome == supervise.FETCH_DONE and _running is not None:
        _rebuild(_running[1])
    return supervise.FETCH_MESSAGE[outcome]


def next_evening_ms():
    """Milliseconds until the next supervise.CHECK_AT, South African time (§4.6)."""
    now = clock.now()
    due = datetime.datetime.combine(now.date(), supervise.CHECK_AT)
    if due <= now:
        due += datetime.timedelta(days=1)
    return int((due - now).total_seconds() * 1000)


def evening(today_iso=None):
    """The evening job's notices, each in its phone form (§4.2, INV-126).

    Kotlin imports the inbox first. `today_iso` is for a test; Kotlin passes
    nothing, so today is clock.today() (ADR-0009).
    """
    today = (datetime.date.fromisoformat(today_iso) if today_iso
             else clock.today())
    notices = supervise.expiry_notices(today) + supervise.sms_quiet_notices(today)
    return [phone(n) for n in notices]
