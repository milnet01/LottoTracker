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


def conversations_iface():
    bus = dbus.SessionBus()
    daemon = bus.get_object("org.kde.kdeconnect", "/modules/kdeconnect/devices")
    devices = dbus.Interface(
        daemon, "org.freedesktop.DBus.Introspectable"
    ).Introspect()
    ids = [
        line.split('"')[1]
        for line in devices.splitlines()
        if "<node name=" in line
    ]
    if not ids:
        sys.exit("No KDE Connect device found — is the phone paired and awake?")
    obj = bus.get_object(
        "org.kde.kdeconnect", f"/modules/kdeconnect/devices/{ids[0]}"
    )
    return dbus.Interface(obj, "org.kde.kdeconnect.device.conversations")


def matches(msg):
    haystack = (str(msg[BODY]) + " " + " ".join(str(a[0]) for a in msg[ADDRS])).lower()
    return any(k in haystack for k in KEYWORDS)


def show(msg):
    when = datetime.fromtimestamp(int(msg[DATE]) / 1000).strftime("%Y-%m-%d %H:%M")
    sender = ", ".join(str(a[0]) for a in msg[ADDRS])
    print(f"\n[{when}] from {sender}  (thread {int(msg[THREAD])})")
    print(f"  {msg[BODY]}")


def main():
    conv = conversations_iface()
    conv.requestAllConversationThreads()
    time.sleep(6)

    threads = conv.activeConversations()
    print(f"{len(threads)} threads on the phone.")

    hits = [m for m in threads if matches(m)]
    if not hits:
        print("\nNo lottery-looking threads in the newest message of each thread.")
        print("Senders seen (newest message only, bodies not shown):")
        for m in threads:
            print("  " + ", ".join(str(a[0]) for a in m[ADDRS]))
        return

    print(f"{len(hits)} lottery-looking thread(s). Pulling their history:")
    for m in hits:
        conv.requestConversation(int(m[THREAD]), 0, 200)
    time.sleep(8)

    seen = set()
    for m in conv.activeConversations():
        if matches(m) and (key := (int(m[THREAD]), int(m[DATE]))) not in seen:
            seen.add(key)
            show(m)


if __name__ == "__main__":
    main()
