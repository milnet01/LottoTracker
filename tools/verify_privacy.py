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
comparison cannot run and only the pattern checks do.

**The exit code does NOT say which mode ran** -- it reports leaks, and nothing
else. A caller that needs the strong mode asks for it with `--require-content`,
which fails when the dump is absent. local-CI.sh's local lane passes it; the
public CI lane does not, because a public runner never has the dump. The
docstring claimed the opposite until 2026-09-02, which is the one place a
maintainer would look to learn whether a green tick means anything.

Three things here exist because a run that checks NOTHING must not look like a
clean one -- the failure this file is least able to afford:

  * `tracked()` fails on a git that did not run, and on an empty file list.
  * every IDENTIFYING pattern must still match the dump, or it has stopped
    working and the content half is silently inert.
  * a tracked file that cannot be read is named and counted, never skipped.
"""

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMP = os.path.join(ROOT, "lotto_sms_raw.txt")

# Sample references must be obviously fake. Case-insensitive: a reference
# written lowercase in prose is still a reference, and both earlier leaks got
# past because of formatting rather than because the shape was wrong.
SENTINEL = "VAS00000000000"
REFERENCE = re.compile(r"\bVAS[0-9]{6,}", re.I)

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
    """Every path git tracks. Raises rather than returning an empty list.

    The return code is checked and an empty list is a failure. Without both, a
    git that cannot run returns empty stdout, the scan reads no file at all,
    and this prints "0 tracked files, 0 leak(s) [content+pattern]" and exits 0
    -- the one gate between real SMS content and a public repository reporting
    success having checked nothing. Worse, the mode string still reads
    content+pattern, so local-CI.sh's own full-strength assertion, which greps
    for exactly that, passes too: both guards defeated by one failure.
    Reproduced 2026-09-02 with a `git` that exits 127.
    """
    out = subprocess.run(
        ["git", "-C", ROOT, "ls-files"], capture_output=True, text=True
    )
    if out.returncode != 0:
        raise RuntimeError(
            f"git ls-files failed (rc={out.returncode}): "
            f"{out.stderr.strip()[:200]}"
        )
    files = [f for f in out.stdout.split("\n") if f.strip()]
    if not files:
        raise RuntimeError(
            "git tracks no files under this root, so nothing would be checked"
        )
    return files


def dead_patterns(dump):
    """IDENTIFYING patterns that no longer match the dump at all.

    The positive control. The dump is real SMS traffic, so every shape here is
    present in it by construction -- one that matches nothing has stopped
    working, and a broken pattern leaves the content half detecting nothing
    while the run stays green and reads exactly like a clean one.
    """
    return [p.pattern for p in IDENTIFYING if not p.search(dump)]


def main(argv=()):
    require_content = "--require-content" in argv

    dump = None
    if os.path.exists(DUMP):
        with open(DUMP, encoding="utf-8", errors="replace") as fh:
            dump = fh.read()
    if dump is None and require_content:
        print("  NO DUMP: lotto_sms_raw.txt is absent, so the content "
              "comparison cannot run and --require-content was asked for.")
        return 1

    files = tracked()
    problems = 0

    if dump is not None:
        for pattern in dead_patterns(dump):
            print(f"  DEAD PATTERN {pattern!r} matches nothing in the dump - "
                  f"the content check it carries is inert")
            problems += 1

    leaks = 0
    unreadable = []
    for rel in files:
        path = os.path.join(ROOT, rel)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except IsADirectoryError:
            # A submodule: git tracks the gitlink, not files under it.
            continue
        except OSError as exc:
            # Named and counted, never skipped silently. A tracked file that
            # will not open is one whose leak would be reported as absent
            # while the summary still counted it as checked.
            unreadable.append(f"{rel} ({type(exc).__name__})")
            continue

        for ref in set(REFERENCE.findall(text)):
            if ref.upper() != SENTINEL:
                print(f"  LEAK {rel}: ticket reference {ref}")
                leaks += 1

        if dump is None:
            continue
        for pattern in IDENTIFYING:
            for hit in set(pattern.findall(text)):
                if hit.strip() and hit.strip() in dump:
                    print(f"  LEAK {rel}: verbatim from the SMS dump: {hit.strip()!r}")
                    leaks += 1

    for u in unreadable:
        print(f"  UNREADABLE {u}")
    problems += len(unreadable)

    mode = "content+pattern" if dump is not None else "pattern only (no dump present)"
    print(f"{len(files)} tracked files, {leaks} leak(s) [{mode}]"
          + (f", {problems} problem(s)" if problems else ""))
    return 0 if leaks == 0 and problems == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
