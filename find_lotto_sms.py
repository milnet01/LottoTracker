#!/usr/bin/env python3
"""Find lottery-related SMS threads via KDE Connect, without dumping the inbox.

activeConversations() returns only the newest message per thread, so this
filters those down to lottery senders first and pulls full history for the
matching threads only. Everything else is never read.

ConversationMessage struct order comes from KDE Connect's own definition:
  0 event, 1 body, 2 addresses, 3 date(ms), 4 type, 5 read,
  6 threadID, 7 uID, 8 subID, 9 attachments
"""

import sys
import time
from datetime import datetime

import dbus

from tickets import terminal_safe

# A cold KDE Connect daemon fills its conversation list over minutes. Both
# waits below poll until the list STOPS GROWING rather than sleeping on a fixed
# guess, which is watch_sms.py's own measured answer to the same problem: on a
# slow link a fixed sleep prints a confident negative from an incomplete read.
QUIET_POLLS = 6      # consecutive unchanged reads that count as settled
POLL_EVERY = 1.0     # seconds between reads
SETTLE_CAP = 90.0    # seconds before giving up and using what there is

KEYWORDS = (
    "lotto",
    "powerball",
    "power ball",
    "ithuba",
    "sizekhaya",
    "national lottery",
    "nationallottery",
    "jackpot",
    # A payout SMS names no game at all — "The winnings of R<amount> for
    # ticket ref: VAS00000000000 will be paid in your account…" — so every
    # keyword above misses it, and note "lotto" is not a substring of
    # "lottery". The VAS reference is the one term spanning purchases,
    # debits, failed transactions and payouts alike. LOTTO-0030.
    #
    # It is wider than lottery, though: VAS is the bank's value-added
    # services platform, so prepaid electricity carries the same reference
    # format. The adb import excludes those by shape (see LOTTO-0001 §4.1);
    # this path is inspection only and does not, so an inspection run will
    # show utility messages too. That is noise on the terminal, not data in
    # the pipeline — `find_lotto_sms.py` writes no file.
    "vas00",
)

BODY, ADDRS, DATE, THREAD = 1, 2, 3, 6


def device_ids(bus):
    """Paired AND reachable device ids, newest KDE Connect API first.

    Asked of the daemon rather than read off the devices node. Introspecting
    that node lists every REMEMBERED device - paired or not, present or not -
    so taking the first of them could bind the watcher, which imports this
    module as its one device-discovery path, to a phone last seen months ago,
    while watch_sms.py's own docstring says "the first paired device".

    The introspection fallback is kept for a daemon too old to answer, and it
    says so on stderr rather than quietly being the weaker thing again.
    """
    try:
        daemon = dbus.Interface(
            bus.get_object("org.kde.kdeconnect", "/modules/kdeconnect"),
            "org.kde.kdeconnect.daemon",
        )
        return [str(i) for i in daemon.devices(True, True)]
    except dbus.DBusException as err:
        print(f"kdeconnect daemon.devices() unavailable ({err.get_dbus_name()});"
              " falling back to listing every remembered device, paired or"
              " not.", file=sys.stderr)
    node = bus.get_object("org.kde.kdeconnect", "/modules/kdeconnect/devices")
    devices = dbus.Interface(
        node, "org.freedesktop.DBus.Introspectable"
    ).Introspect()
    return [
        line.split('"')[1]
        for line in devices.splitlines()
        if "<node name=" in line
    ]


def conversations_iface():
    bus = dbus.SessionBus()
    ids = device_ids(bus)
    if not ids:
        # RuntimeError, NOT sys.exit. This function is not script-local:
        # watch_sms.py::connect() imports it as its one device-discovery
        # implementation, and the watcher's whole retry design rests on a
        # failure here being catchable. sys.exit raises SystemExit, which
        # derives from BaseException, so `except Exception` does not see it -
        # the no-device case is exactly LOTTO-0003 §4.8's normal login case,
        # and it was killing the watcher outright past both of its guards
        # (INV-36 and INV-39, breached in one line). main() below turns this
        # into the same message for a human at a terminal.
        raise RuntimeError(
            "No KDE Connect device found — is the phone paired and awake?"
        )
    obj = bus.get_object(
        "org.kde.kdeconnect", f"/modules/kdeconnect/devices/{ids[0]}"
    )
    return dbus.Interface(obj, "org.kde.kdeconnect.device.conversations")


def matches(msg):
    haystack = (str(msg[BODY]) + " " + " ".join(str(a[0]) for a in msg[ADDRS])).lower()
    return any(k in haystack for k in KEYWORDS)


def settled_conversations(conv):
    """activeConversations() once the list has stopped growing."""
    count, still, started = -1, 0, time.monotonic()
    while time.monotonic() - started < SETTLE_CAP:
        got = conv.activeConversations()
        still = still + 1 if len(got) == count else 0
        count = len(got)
        if still >= QUIET_POLLS:
            return got
        time.sleep(POLL_EVERY)
    print(f"the conversation list was still growing after {SETTLE_CAP:.0f}s;"
          " showing what has arrived so far.", file=sys.stderr)
    return conv.activeConversations()


def show(msg):
    # Both the body and the sender are attacker-controlled and go straight to a
    # terminal, so both go through terminal_safe(): a UCS-2 message carrying an
    # escape drives the emulator rather than being read (CWE-150).
    # watch_sms.py's header says "Nothing here prints a message body"; this is
    # the one path in the project that does, on purpose.
    when = datetime.fromtimestamp(int(msg[DATE]) / 1000).strftime("%Y-%m-%d %H:%M")
    sender = terminal_safe(", ".join(str(a[0]) for a in msg[ADDRS]))
    print(f"\n[{when}] from {sender}  (thread {int(msg[THREAD])})")
    print(f"  {terminal_safe(msg[BODY])}")


def main():
    conv = conversations_iface()
    conv.requestAllConversationThreads()
    threads = settled_conversations(conv)
    print(f"{len(threads)} threads on the phone.")

    hits = [m for m in threads if matches(m)]
    if not hits:
        print("\nNo lottery-looking threads in the newest message of each thread.")
        print("Senders seen (newest message only, bodies not shown):")
        for m in threads:
            print("  " + terminal_safe(", ".join(str(a[0]) for a in m[ADDRS])))
        return

    print(f"{len(hits)} lottery-looking thread(s). Pulling their history:")
    for m in hits:
        conv.requestConversation(int(m[THREAD]), 0, 200)

    seen = set()
    for m in settled_conversations(conv):
        if matches(m) and (key := (int(m[THREAD]), int(m[DATE]))) not in seen:
            seen.add(key)
            show(m)


if __name__ == "__main__":
    # The sys.exit that used to live in conversations_iface() belongs here,
    # where the caller really is a shell.
    try:
        main()
    except RuntimeError as err:
        sys.exit(str(err))
