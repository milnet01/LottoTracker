#!/usr/bin/env python3
"""LOTTO-0001 INV-4: no real SMS content is tracked by git.

This repository is public and the SMS dump is not. Two leaks got past earlier,
one per review loop, and each taught a different lesson:

  loop 2  a real ticket reference pasted into README.md as sample output.
          The check then in force grepped for `Ref:VAS…`, but pasted program
          output drops the `Ref:` prefix, so it reported clean.
  loop 3  the spec's and tickets.py's "example" messages were verbatim real
          messages -- correct numbers, dates and amounts -- with only the
          reference scrubbed. A reference-only check cannot see that: a
          lottery ticket is identified by its draw and numbers, not just its
          reference.

So this compares tracked files against the dump itself rather than against a
pattern someone guessed. When the dump is absent (a fresh clone) the content
comparison cannot run; the pattern checks still do, and the exit code says
which mode ran.
"""

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMP = os.path.join(ROOT, "lotto_sms_raw.txt")

# Sample references must be obviously fake.
SENTINEL = "VAS00000000000"
REFERENCE = re.compile(r"\bVAS[0-9]{6,}")

# Shapes that carry ticket identity: played board lines, and purchase headers
# with their amount and game.
IDENTIFYING = (
    re.compile(r"A: (?:\d\d[ -]?)+"),
    re.compile(r"B: (?:\d\d[ -]?)+"),
    re.compile(r"Played R[\d.]+ [A-Za-z0-9 ]+"),
    re.compile(r"Date \d{2}/\d{2}/\d{4}"),
    re.compile(r"Date \d{2} [A-Z][a-z]{2} \d{4}"),
)


def tracked():
    out = subprocess.run(
        ["git", "-C", ROOT, "ls-files"], capture_output=True, text=True
    )
    return [f for f in out.stdout.split("\n") if f.strip()]


def main():
    leaks = 0
    dump = None
    if os.path.exists(DUMP):
        dump = open(DUMP, errors="replace").read()

    for rel in tracked():
        path = os.path.join(ROOT, rel)
        try:
            text = open(path, errors="replace").read()
        except (OSError, IsADirectoryError):
            continue

        for ref in set(REFERENCE.findall(text)):
            if ref != SENTINEL:
                print(f"  LEAK {rel}: ticket reference {ref}")
                leaks += 1

        if dump is None:
            continue
        for pattern in IDENTIFYING:
            for hit in set(pattern.findall(text)):
                if hit.strip() and hit.strip() in dump:
                    print(f"  LEAK {rel}: verbatim from the SMS dump: {hit.strip()!r}")
                    leaks += 1

    mode = "content+pattern" if dump is not None else "pattern only (no dump present)"
    print(f"{len(tracked())} tracked files, {leaks} leak(s) [{mode}]")
    return 0 if leaks == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
