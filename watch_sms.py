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

import fcntl
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


def lock_path(path=DUMP):
    """The sidecar file whose flock serialises writers of `path`. INV-38.

    A SIDECAR rather than the dump itself, and that is not a style choice.
    Locking the dump means opening it, and opening it in append mode CREATES
    it - while `serve.py::build()` keys its "no messages have been imported"
    notice on the dump's EXISTENCE, never its emptiness. A lock that created
    an empty dump would replace that notice with an empty results table, which
    is "no data" reading as "did not win": the one failure this project exists
    to prevent (CLAUDE.md, LOTTO-0009 INV-26).
    """
    return path + ".lock"


def append_new(messages, path=DUMP):
    """Append the wanted messages the dump does not already carry.

    Returns how many were written. De-duplication is on (date, body): the
    catch-up pass re-reads history the dump already holds every single run, so
    this is the normal path and not an edge case. Measured 2026-08-13: the
    key is unique across all 951 records, and adb's own re-pull relies on the
    same pair. INV-34.

    The read and the append are ONE critical section, held under an exclusive
    flock on the sidecar. De-duplication is against the file's contents at
    READ time, so without the lock two watchers that both read before either
    wrote would both append the same message - and their row indices would
    collide too, since each takes max(existing) + 1. The case is reachable
    rather than theoretical: `supervise.SmsWatch.start()` guards only against
    its own second spawn, and `python3 watch_sms.py` is a documented hand
    invocation. INV-38.
    """
    with open(lock_path(path), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            raw = open(path, errors="replace").read()
        except FileNotFoundError:
            raw = ""
        import tickets  # here, not at module scope: a missing dump must not
        # stop this module being imported by a verifier with no project state.

        seen = {(date_ms, body) for _a, date_ms, body in tickets.rows(raw)}
        index = max((int(m.group(1)) for m in re.finditer(
            r"^Row: (\d+) address=", raw, flags=re.M)), default=-1) + 1

        out = []
        for address, date_ms, body in messages:
            row = format_row(index + len(out), address, date_ms, body)
            # Read the record back through the dump's own reader before
            # accepting it: what is de-duplicated is then exactly what will
            # later be scored, and a record the reader cannot see (a negative
            # date, say) is dropped here rather than written and silently
            # ignored forever.
            parsed = tickets.rows(row)
            if not parsed:
                continue
            _a, key_date, key_body = parsed[0]
            if not wanted(key_body) or (key_date, key_body) in seen:
                continue
            seen.add((key_date, key_body))
            out.append(row)

        if out:
            # One append, opened and closed around it. serve.py may read the
            # dump at any moment (its rebuild is on a timer the user can also
            # click), and a partial record is a record tickets.rows() drops
            # silently.
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

# The daemon's well-known bus name, watched so a restart can be recovered from
# rather than survived by half (INV-39).
KDECONNECT = "org.kde.kdeconnect"

QUIET = 8.0     # seconds of silence that count as "the phone has finished"
CATCHUP_CAP = 1200.0   # ceiling on the whole catch-up, in case it never quiets
RETRY_EVERY = 60.0     # how often to reach for KDE Connect once it has gone
RETRY_GRACE = 5.0      # and how long to leave it alone straight after it went


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


def daemon_change(name, old_owner, new_owner):
    """One NameOwnerChanged, read as what it means here: "back", "gone", None.

    Measured 2026-08-15 by killing kdeconnectd under a running watcher, and
    the result SPLITS - which is why this is not "the watcher goes deaf":

      * the held conversations proxy DIES. Every later call on it raises
        `ServiceUnknown: The name is not activatable`, because dbus-python
        resolves a well-known name to a unique connection at get_object()
        time and stays pinned to it.
      * the signal match rule SURVIVES. It carries an interface and a member
        and no sender, so it matches whoever emits next: 69 signals from the
        restarted daemon reached a receiver registered before the restart.

    So live arrivals keep landing, and what is lost is everything that CALLS
    the phone - the catch-up and the history requests. Steady state makes no
    such call, which is exactly why the loss was silent: it shows up only as a
    backlog that never arrives. INV-39.
    """
    if str(name) != KDECONNECT:
        return None
    return "back" if str(new_owner) else "gone"


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
        self.last_signal = time.monotonic()

    def handle(self, msg):
        """Signal handler for conversationCreated and conversationUpdated."""
        self.last_signal = time.monotonic()
        self.consume(msg)

    def accept(self, decoded):
        """Filter one decoded message and remember its thread. No dump I/O.

        Splitting the filter from the WRITE is what lets snapshot() batch: the
        caller decides when to persist, and the thread set is updated here but
        deliberately not saved, for the same reason.
        """
        address, date_ms, body, thread = decoded
        if not wanted(body):
            return None
        self.threads.add(thread)
        return (address, date_ms, body)

    def record(self, batch, grew):
        """Persist what accept() collected: ONE append, one thread-state write.

        `grew` says whether the thread set changed, so an unchanged set is not
        rewritten. This is LOTTO-0007 (j)'s fix in one line: `append_new()`
        re-reads and re-parses the whole 210 KB dump on every call, so calling
        it once per accepted message made a catch-up ~543 reads (~114 MB)
        against this phone instead of one. LOTTO-0003 §10.

        Nothing is written until the batch is complete, which also means a
        watcher killed mid-snapshot leaves the thread state claiming no
        knowledge of threads whose messages were never appended. The next run
        redoes the snapshot, which is idempotent, so that is the safe half.
        """
        if grew:
            write_threads(self.threads, self.threads_path)
        if not batch:
            return 0
        n = append_new(batch, self.path)
        self.written += n
        if n:
            # The count, never the message (see the module docstring).
            print(f"+{n} new lottery SMS (total this run: {self.written})",
                  flush=True)
        return n

    def consume(self, msg):
        """Take one message from a SIGNAL and write it straight away.

        The signal path carries one message, so there is nothing to batch and
        delaying it would only postpone the tray's notice. The snapshot path
        is the one that batches - see snapshot().
        """
        try:
            decoded = decode(msg)
        except (IndexError, TypeError, ValueError):
            return  # a struct we do not recognise is not a reason to die
        before = len(self.threads)
        got = self.accept(decoded)
        self.record([got] if got else [], len(self.threads) != before)

    def idle_for(self):
        return time.monotonic() - self.last_signal

    def snapshot(self, conv):
        """Read activeConversations(), consume it, and describe what moved.

        Returns (thread_count, [(date_ms, thread, matched), ...]) - the second
        being what pull_targets() needs. Consuming here is what collects a new
        ticket in the ordinary case: a purchase SMS is the newest message in
        its thread, so the snapshot alone carries it and no history request is
        needed at all.

        ONE append for the whole snapshot rather than one per message, which
        is what record() exists for (LOTTO-0003 §10).
        """
        rows, batch = [], []
        before = len(self.threads)
        for msg in conv.activeConversations():
            try:
                decoded = decode(msg)
            except (IndexError, TypeError, ValueError):
                continue
            _address, date_ms, body, thread = decoded
            rows.append((date_ms, thread, wanted(body)))
            got = self.accept(decoded)
            if got:
                batch.append(got)
        self.record(batch, len(self.threads) != before)
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

    # A daemon that is not ready is NOT a watcher that cannot run, and the two
    # were the same thing until 2026-08-15. `connect()` needs KDE Connect's
    # DEVICE object, which appears only once the phone re-pairs - so starting
    # the tray at login, before the phone is back, killed the watcher outright
    # and the user got one notification and no collector. That is transient and
    # belongs in the retry loop below. An ImportError is the other thing
    # entirely - dbus-python or KDE Connect is absent and nothing will ever
    # work - and it is re-raised so main() still names the cable (INV-36).
    try:
        conv = connect()
    except ImportError:
        raise
    except (Exception, SystemExit) as err:  # noqa: BLE001 - transient
        conv = None
        print(f"KDE Connect is not answering yet ({err.__class__.__name__}) - "
              "waiting for it.", flush=True)

    state = {"phase": "discovering" if conv else "waiting", "count": -1,
             "still": 0, "retry_at": 0.0, "conv": conv,
             # None means "not currently waiting"; tick() starts the clock.
             "waiting_since": None}

    bus = dbus.SessionBus()
    for signal in ("conversationCreated", "conversationUpdated"):
        bus.add_signal_receiver(
            watch.handle,
            signal_name=signal,
            dbus_interface="org.kde.kdeconnect.device.conversations",
        )

    def begin_catchup():
        """Start - or RESTART - the discover-then-catch-up cycle.

        Everything the cycle is bounded by is re-read here rather than closed
        over once, and that is what makes it re-runnable after a reconnect:
        the high-water mark has moved (the watcher wrote while the daemon was
        up), the known-thread set has grown, and `pulled` has to forget what
        it asked the now-dead proxy for or the replacement asks for nothing.
        """
        state["conv"].requestAllConversationThreads()
        state["phase"] = "discovering"
        state["count"] = -1
        state["still"] = 0
        state["started"] = time.monotonic()
        state["water"] = high_water(path)
        state["known"] = set(watch.threads)
        watch.pulled.clear()

    def owner_changed(name, old_owner, new_owner):
        """KDE Connect stopped or came back (INV-39, LOTTO-0007 (l))."""
        change = daemon_change(name, old_owner, new_owner)
        if change == "gone":
            state["phase"] = "waiting"
            state["retry_at"] = time.monotonic() + RETRY_GRACE
            print("KDE Connect stopped - no new tickets will be collected "
                  "until it is back.", flush=True)
        elif change == "back":
            # Not a reconnect on its own - the proxy is still the dead one.
            # It only says the next attempt need not wait out the interval.
            state["phase"] = "waiting"
            state["retry_at"] = 0.0

    bus.add_signal_receiver(
        owner_changed,
        signal_name="NameOwnerChanged",
        dbus_interface="org.freedesktop.DBus",
        arg0=KDECONNECT,
    )

    loop = GLib.MainLoop()
    if conv:
        begin_catchup()

    def tick():
        """Two seconds at a time: reconnect, fill, catch up, then idle."""
        if state["phase"] == "waiting":
            # One state, not two: "the daemon went away" and "the daemon came
            # back" both mean "try to connect again", and NameOwnerChanged is
            # only what makes the next attempt immediate.
            # The waiting clock is started HERE rather than at each of the
            # three places that set the phase, so a fourth one cannot forget.
            if state["waiting_since"] is None:
                state["waiting_since"] = time.monotonic()
            # --once is a CATCH-UP, so waiting forever is not one of its
            # outcomes. Without this ceiling the RuntimeError at the end of
            # run() is unreachable - every path through this branch returns
            # True before the loop.quit() that would let the run end - so
            # `--once` against an absent daemon hung silently and
            # indefinitely, which is neither of the two answers §4.8 allows
            # it. Same cap as the catch-up's own.
            if (once and time.monotonic() - state["waiting_since"]
                    > CATCHUP_CAP):
                loop.quit()
                return False
            if time.monotonic() < state["retry_at"]:
                return True
            try:
                state["conv"] = connect()
                begin_catchup()
            except (Exception, SystemExit):  # noqa: BLE001 - means "not yet"
                # Reaching for it is also what BRINGS IT BACK: the bus name is
                # D-Bus activatable, so the attempt starts the daemon. Measured
                # 2026-08-15 - NOTHING else did. A watcher that only listened
                # for it to return sat here indefinitely, which is the same
                # silence this handler exists to end. Slowly, though: the same
                # call every two seconds would resurrect a daemon the user
                # stopped on purpose. Its DEVICE object also appears only once
                # the phone re-pairs, so an early failure is the normal case
                # rather than the answer.
                state["retry_at"] = time.monotonic() + RETRY_EVERY
                return True
            state["waiting_since"] = None
            print("KDE Connect is back - catching up on what it missed.",
                  flush=True)
        if state["phase"] == "discovering":
            # The completion measure: the snapshot has stopped GROWING. A cold
            # daemon fills it over ~12 minutes; a warm one is already complete,
            # and both end here without a guessed sleep. The snapshot is read
            # for its length only until it settles - consuming a half-filled
            # list would be harmless but pointless.
            try:
                count = len(state["conv"].activeConversations())
                state["still"] = (state["still"] + 1
                                  if count == state["count"] else 0)
                state["count"] = count
                if (state["still"] * 2 >= QUIET
                        or time.monotonic() - state["started"] > CATCHUP_CAP):
                    seen, rows = watch.snapshot(state["conv"])
                    asked = watch.pull_history(
                        state["conv"],
                        pull_targets(rows, state["known"], state["water"]))
                    print(f"catch-up: {seen} threads, {asked} asked for "
                          f"history, {watch.written} written", flush=True)
                    state["phase"] = "catching-up"
                    watch.last_signal = time.monotonic()
            except dbus.DBusException:
                # The daemon went away mid-discovery. NameOwnerChanged will
                # bring us back; what matters here is returning True, because
                # GLib REMOVES a timeout source whose callback raised - an
                # escaping exception would stop the watcher permanently, which
                # is a worse version of the defect this handler exists to fix.
                state["phase"] = "waiting"
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
    if once and state["phase"] == "waiting":
        # --once is a catch-up, so ending it still waiting means the catch-up
        # did not happen. Exiting 0 here would be the project's cardinal
        # failure by the shortest road: nothing collected, reported as fine.
        raise RuntimeError("KDE Connect never answered, so nothing was "
                           "caught up. Import over the cable meanwhile.")
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
