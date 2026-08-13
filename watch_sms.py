#!/usr/bin/env python3
"""Append new lottery SMSes to the dump as they arrive over Wi-Fi (LOTTO-0003).

The second writer of `lotto_sms_raw.txt`, and the one that removes the USB
cable. adb still owns BULK HISTORY and still runs on demand (LOTTO-0001 §4.1);
this path owns NEW messages, which is the half a cable cannot do while it is
unplugged. Both write one file, so both must agree on what belongs in it -
see FILTER below, and INV-32.

    python3 watch_sms.py          # catch up, then listen until killed
    python3 watch_sms.py --once   # catch up, wait for quiet, then exit. It must
                                  # wait: requestConversation()'s answers arrive
                                  # as signals, so exiting straight after asking
                                  # would write none of the history it asked for

Everything above "the phone" is importable WITHOUT `dbus-python`, so
tools/verify_watch.py can drive the filter, the format and the de-duplication
with synthetic messages on a machine with no phone and no KDE Connect. The
D-Bus import is inside connect() for exactly that reason.

Nothing here prints a message body. A body is real personal data (CLAUDE.md
§Privacy) and this process's stdout is inherited from the tray, which on an
autostarted session is the desktop's log.
"""

import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DUMP = os.path.join(HERE, "lotto_sms_raw.txt")
THREADS = os.path.join(HERE, "sms_threads.json")

# ------------------------------------------------------------------- the filter
#
# The adb WHERE clause of LOTTO-0001 §4.1, re-expressed in Python. The two
# collection paths append to ONE file, so a message this accepts that adb's SQL
# would reject - or the reverse - makes the dump's contents depend on which path
# happened to collect it, which is the same class of defect as LOTTO-0030 (a
# filter that silently excluded 366 payouts). INV-32 asserts the two agree.
#
# Body only, and lower-cased: adb matches `body LIKE`, never the address, and
# SQLite's LIKE is case-insensitive across ASCII. `find_lotto_sms.py` uses a
# WIDER list and also matches addresses - deliberately, because it only prints
# (§4.1). Do not unify them: that one is inspection, this one is the pipeline.
INCLUDE = ("lotto", "powerball", "vas00")
EXCLUDE = ("kwh", "enter tokens")

# A body-shaped header would split one record into two, the second carrying a
# forged date. No message has ever contained one (measured across all 951
# records on 2026-08-13) - the guard is here because an SMS body is outside
# data, the cost is one substitution, and the failure it prevents is a wrong
# ticket rather than a crash.
_HEADER = re.compile(r"^(Row: \d+ address=)", re.M)


def wanted(body):
    """True if this message belongs in the dump. INV-32."""
    low = body.lower()
    return any(k in low for k in INCLUDE) and not any(k in low for k in EXCLUDE)


def format_row(index, address, date_ms, body):
    """One record in adb's `content query` format. INV-33.

    The address is stripped of commas and newlines because `tickets.rows()`
    reads the address as everything up to the first comma: one comma there
    would swallow the `date=` field and the record would be dropped whole.
    """
    address = str(address).replace(",", " ").replace("\n", " ").strip()
    body = _HEADER.sub(r" \1", str(body).strip())
    return f"Row: {index} address={address}, date={int(date_ms)}, body={body}\n"


def append_new(messages, path=DUMP):
    """Append the wanted messages the dump does not already carry.

    Returns how many were written. De-duplication is on (date, body): the
    catch-up pass re-reads history the dump already holds every single run, so
    this is the normal path and not an edge case. Measured 2026-08-13: the
    key is unique across all 951 records, and adb's own re-pull relies on the
    same pair. INV-34.
    """
    try:
        raw = open(path, errors="replace").read()
    except FileNotFoundError:
        raw = ""
    import tickets  # here, not at module scope: a missing dump must not stop

    seen = {(date_ms, body) for _a, date_ms, body in tickets.rows(raw)}
    index = max((int(m.group(1)) for m in re.finditer(
        r"^Row: (\d+) address=", raw, flags=re.M)), default=-1) + 1

    out = []
    for address, date_ms, body in messages:
        row = format_row(index + len(out), address, date_ms, body)
        # Read the record back through the dump's own reader before accepting
        # it: what is de-duplicated is then exactly what will later be scored,
        # and a record the reader cannot see (a negative date, say) is dropped
        # here rather than written and silently ignored forever.
        parsed = tickets.rows(row)
        if not parsed:
            continue
        _a, key_date, key_body = parsed[0]
        if not wanted(key_body) or (key_date, key_body) in seen:
            continue
        seen.add((key_date, key_body))
        out.append(row)

    if out:
        # One append, opened and closed around it. serve.py may read the dump
        # at any moment (its rebuild is on a timer the user can also click),
        # and a partial record is a record tickets.rows() drops silently.
        with open(path, "a") as fh:
            fh.write("".join(out))
    return len(out)


def read_threads(path=THREADS):
    """Thread ids that have ever carried a lottery message. INV-35."""
    try:
        got = json.load(open(path))
        return {int(t) for t in got} if isinstance(got, list) else set()
    except (OSError, ValueError, TypeError):
        # Never a reason to exit - the rule supervise.read_settings() follows.
        # But the cost is NOT just a slower run, and saying so here was wrong:
        # with no remembered set, pull_targets() keeps only threads matching
        # NOW, so a ticket sitting under a newer non-matching message is
        # neither asked for nor visible in the snapshot - and it does not heal,
        # because consume() re-adds a thread only on a message that matches.
        # Those are reachable over the cable until the thread matches again.
        # LOTTO-0003 §4.5.
        return set()


def write_threads(ids, path=THREADS):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(sorted(int(i) for i in ids), fh)
    os.replace(tmp, path)


# --------------------------------------------------------------------- the phone
#
# KDE Connect's ConversationMessage struct, in its own field order:
#   0 event, 1 body, 2 addresses, 3 date(ms), 4 type, 5 read,
#   6 threadID, 7 uID, 8 subID, 9 attachments
BODY, ADDRS, DATE, THREAD = 1, 2, 3, 6

QUIET = 8.0     # seconds of silence that count as "the phone has finished"
CATCHUP_CAP = 1200.0   # ceiling on the whole catch-up, in case it never quiets


def decode(msg):
    """One ConversationMessage -> (address, date_ms, body, thread_id).

    Only the FIRST address: a record has one `address=` field, and a group
    thread's second address would have to be joined with a separator the
    format has no room for.
    """
    addresses = [str(a[0]) for a in msg[ADDRS]]
    return (
        addresses[0] if addresses else "",
        int(msg[DATE]),
        str(msg[BODY]),
        int(msg[THREAD]),
    )


def connect():
    """The KDE Connect conversations interface for the first paired device."""
    import find_lotto_sms  # imports dbus; one device-discovery implementation

    return find_lotto_sms.conversations_iface()


def pull_targets(snapshot, known, high_water):
    """Which threads to ask for history, given the newest message in each.

    `snapshot` is (date_ms, thread_id, matched) per thread, from
    activeConversations(). `high_water` is the newest date the dump already
    holds. A thread earns a history request when it has MOVED since the dump
    was last written - its newest message is newer than anything we have - and
    it is either lottery-shaped now or has been before.

    That bound is the whole point. 543 of the phone's 2,325 threads match the
    filter (measured 2026-08-13, the bank sends from many shortcodes), so
    asking all of them for 200 messages each would be a hundred thousand
    messages on every start. Asking only the threads that moved is usually
    asking for nothing at all.

    The `known` half is not redundant with `matched`: a bank thread whose
    newest message is now an ordinary balance notice does not match, and its
    lottery message underneath would be unreachable without it.

    An EMPTY or absent dump has no high-water mark (high_water() returns 0), so
    every matching thread is asked - and that is deliberate, not an escaped
    edge case. A first run has no other way to rebuild history over Wi-Fi, and
    a bound applied there would make the cable mandatory for the one case with
    no alternative. The bound is a steady-state economy. INV-35.
    """
    return {
        thread
        for date_ms, thread, matched in snapshot
        if date_ms > high_water and (matched or thread in known)
    }


def high_water(path=DUMP):
    """The newest message date the dump holds, or 0 for an empty one."""
    import tickets

    try:
        raw = open(path, errors="replace").read()
    except FileNotFoundError:
        return 0
    return max((date_ms for _a, date_ms, _b in tickets.rows(raw)), default=0)


class Watch:
    """Listen, filter, append. No Qt and no HTTP - it talks to the phone only.

    Two ways in, because KDE Connect gives two and neither is sufficient alone:

      * activeConversations() - a SNAPSHOT of the newest message per thread,
        which is what discovery has to read. `conversationCreated` cannot serve
        that purpose: measured 2026-08-13, it fires only the first time the
        daemon learns of a conversation, so a first run saw 202 signals in 60s
        and every later run saw ZERO while the same list held 2,325 entries.
        A discovery built on it works once per daemon lifetime and then
        silently finds nothing, which is how the first live run here reported
        "0 new" against a phone holding 951 matching messages.
      * the signals - `conversationUpdated` fires for genuinely new messages
        AND for every message delivered in answer to requestConversation()
        (measured: 25 for one thread), so one handler serves live arrivals and
        history alike.

    The completion problem §4.1 warns about is still real and is answered by
    watching the snapshot STOP GROWING rather than by sleeping on it: a cold
    daemon fills the list over ~12 minutes, a warm one is complete on the first
    read, and neither case needs a guessed wait.
    """

    def __init__(self, path=DUMP, threads_path=THREADS):
        self.path = path
        self.threads_path = threads_path
        self.threads = read_threads(threads_path)
        self.pulled = set()
        self.written = 0
        self.seen_signals = 0
        self.last_signal = time.monotonic()

    def handle(self, msg):
        """Signal handler for conversationCreated and conversationUpdated."""
        self.seen_signals += 1
        self.last_signal = time.monotonic()
        self.consume(msg)

    def consume(self, msg):
        """Take one message, wherever it came from: a signal or the snapshot."""
        try:
            address, date_ms, body, thread = decode(msg)
        except (IndexError, TypeError, ValueError):
            return  # a struct we do not recognise is not a reason to die
        if not wanted(body):
            return
        if thread not in self.threads:
            self.threads.add(thread)
            write_threads(self.threads, self.threads_path)
        n = append_new([(address, date_ms, body)], self.path)
        self.written += n
        if n:
            # The count, never the message (see the module docstring).
            print(f"+{n} new lottery SMS (total this run: {self.written})",
                  flush=True)

    def idle_for(self):
        return time.monotonic() - self.last_signal

    def snapshot(self, conv):
        """Read activeConversations(), consume it, and describe what moved.

        Returns (thread_count, [(date_ms, thread, matched), ...]) - the second
        being what pull_targets() needs. Consuming here is what collects a new
        ticket in the ordinary case: a purchase SMS is the newest message in
        its thread, so the snapshot alone carries it and no history request is
        needed at all.
        """
        rows = []
        for msg in conv.activeConversations():
            try:
                _address, date_ms, body, thread = decode(msg)
            except (IndexError, TypeError, ValueError):
                continue
            rows.append((date_ms, thread, wanted(body)))
            self.consume(msg)
        return len(rows), rows

    def pull_history(self, conv, ids):
        """Ask for the recent history of the threads that have moved.

        New messages arrive live while we run; the ones that arrived while we
        did not are reachable two ways. The snapshot above carries each
        thread's NEWEST message, which is the whole story for a thread that
        received one lottery SMS. This closes the rest: a thread that received
        two, or one whose latest message is now an ordinary bank notice sitting
        on top of a ticket. pull_targets() decides which, and bounds it.
        """
        asked = sorted(ids - self.pulled)
        for thread in asked:
            self.pulled.add(thread)
            conv.requestConversation(thread, 0, 200)
        return len(asked)


def run(once=False, path=DUMP, threads_path=THREADS):
    """Catch up, then listen. Returns the number of messages written."""
    import dbus
    import dbus.mainloop.glib
    from gi.repository import GLib

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    watch = Watch(path, threads_path)
    conv = connect()

    bus = dbus.SessionBus()
    for signal in ("conversationCreated", "conversationUpdated"):
        bus.add_signal_receiver(
            watch.handle,
            signal_name=signal,
            dbus_interface="org.kde.kdeconnect.device.conversations",
        )

    loop = GLib.MainLoop()
    started = time.monotonic()
    water = high_water(path)
    known = set(watch.threads)
    conv.requestAllConversationThreads()
    state = {"phase": "discovering", "count": -1, "still": 0}

    def tick():
        """Two seconds at a time: fill, then catch up, then idle."""
        if state["phase"] == "discovering":
            # The completion measure: the snapshot has stopped GROWING. A cold
            # daemon fills it over ~12 minutes; a warm one is already complete,
            # and both end here without a guessed sleep. The snapshot is read
            # for its length only until it settles - consuming a half-filled
            # list would be harmless but pointless.
            count = len(conv.activeConversations())
            state["still"] = state["still"] + 1 if count == state["count"] else 0
            state["count"] = count
            if state["still"] * 2 >= QUIET or time.monotonic() - started > CATCHUP_CAP:
                seen, rows = watch.snapshot(conv)
                asked = watch.pull_history(conv, pull_targets(rows, known, water))
                print(f"catch-up: {seen} threads, {asked} asked for history, "
                      f"{watch.written} written", flush=True)
                state["phase"] = "catching-up"
                watch.last_signal = time.monotonic()
            return True
        if once and watch.idle_for() >= QUIET:
            loop.quit()
            return False
        return True

    GLib.timeout_add_seconds(2, tick)
    if not once:
        print("listening for new lottery SMSes over KDE Connect "
              f"(known threads: {len(watch.threads)})", flush=True)
    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    return watch.written


def main():
    once = "--once" in sys.argv[1:]
    try:
        written = run(once=once)
    except ImportError as err:
        # dbus-python or the GLib bindings are absent. Say which, and say what
        # it costs: this is the difference between "no new tickets" and "no new
        # tickets are being COLLECTED", and the two must never look alike.
        sys.exit(f"cannot watch for new tickets: {err}. "
                 "Tickets will only arrive when you import over the cable.")
    except Exception as err:  # noqa: BLE001 - the caller is a tray, not a shell
        sys.exit(f"the SMS watcher stopped: {err}")
    if once:
        print(f"{written} new lottery SMS(es) written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
