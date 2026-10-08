#!/usr/bin/env python3
"""LOTTO-0004: a commit carrying SMS content is refused at the commit, not
only at the push.

    python3 tools/verify_hooks.py
    python3 tools/verify_hooks.py --list
    python3 tools/verify_hooks.py --break hook_skips_check  # must FAIL

Both cases build a throwaway git repository, so neither needs the SMS dump,
the scraped archive or this clone's history. That is why this runs in
local-CI.sh's CI lane.

PRIVACY. The leak planted is an INVENTED reference assembled at run time, so
this file holds no reference-shaped string for verify_privacy.py to report,
and nothing here prints it.
"""

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import verify_privacy  # noqa: E402

# Invented, and assembled so that this source holds no reference-shaped string.
FAKE_REF = "VAS" + "1" * 11

ACTIVE_CASE = None  # set by main(); a break fires only in its own case


def need(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _clean_env():
    """The environment minus git's own variables.

    local-CI.sh runs this from inside a hook, and a hook may export GIT_DIR or
    GIT_INDEX_FILE. Inherited, they point every git call below at THIS clone
    rather than at the scratch repository.
    """
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def git(root, *args):
    return subprocess.run(
        ["git", "-C", root, "-c", "user.name=verify",
         "-c", "user.email=verify@example.invalid",
         "-c", "commit.gpgsign=false", *args],
        capture_output=True, text=True, env=_clean_env(),
    )


def scratch_repo(tmp):
    """A repository holding this clone's checker and pre-commit hook."""
    need(git(tmp, "init", "-q").returncode == 0, "git init failed")
    os.makedirs(os.path.join(tmp, "tools"))
    shutil.copy2(os.path.join(HERE, "verify_privacy.py"),
                 os.path.join(tmp, "tools", "verify_privacy.py"))
    os.makedirs(os.path.join(tmp, ".githooks"))
    shutil.copy2(os.path.join(REPO, ".githooks", "pre-commit"),
                 os.path.join(tmp, ".githooks", "pre-commit"))
    git(tmp, "config", "core.hooksPath", ".githooks")


def write(tmp, name, text):
    with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
        fh.write(text)


def staged_copy_is_read():
    """--staged reads the index, which is what a commit records.

    The leak is staged and then edited out of the working copy without
    re-staging: the working copy is clean, the commit would not be.
    """
    with tempfile.TemporaryDirectory() as tmp:
        need(git(tmp, "init", "-q").returncode == 0, "git init failed")
        write(tmp, "notes.md", f"sample {FAKE_REF}\n")
        git(tmp, "add", "notes.md")
        write(tmp, "notes.md", "sample clean\n")

        saved = verify_privacy.ROOT, verify_privacy.DUMP
        verify_privacy.ROOT = tmp
        verify_privacy.DUMP = os.path.join(tmp, "no-dump-here.txt")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                working = verify_privacy.main([])
                staged = verify_privacy.main(["--staged"])
        finally:
            verify_privacy.ROOT, verify_privacy.DUMP = saved

    need(working == 0, "the working copy is clean, yet the default run failed "
         "- the scenario is not the one this case is about")
    need(staged == 1, "a leak in the index passed --staged")
    return "working copy clean (exit 0); staged leak refused (exit 1)"


def hook_refuses_commit():
    """A real `git commit` of a staged leak is refused by the hook, and a
    clean commit is not."""
    with tempfile.TemporaryDirectory() as tmp:
        scratch_repo(tmp)
        if ACTIVE_CASE == BREAKS.get(BROKEN):
            write(tmp, os.path.join(".githooks", "pre-commit"),
                  "#!/bin/sh\nexit 0\n")

        write(tmp, "notes.md", f"sample {FAKE_REF}\n")
        git(tmp, "add", "notes.md")
        refused = git(tmp, "commit", "-q", "-m", "leak")
        need(refused.returncode != 0, "a commit carrying a reference went through")
        need(git(tmp, "rev-parse", "--verify", "-q", "HEAD").returncode != 0,
             "the hook failed but a commit was still recorded")

        write(tmp, "notes.md", "sample clean\n")
        git(tmp, "add", "notes.md")
        clean = git(tmp, "commit", "-q", "-m", "clean")
        need(clean.returncode == 0,
             "a clean commit was refused - the hook refuses everything: "
             + (clean.stdout + clean.stderr).strip()[-200:])
    return "leak refused, clean commit recorded"


CASES = [
    ("staged_copy_is_read", "LOTTO-0004", staged_copy_is_read),
    ("hook_refuses_commit", "LOTTO-0004", hook_refuses_commit),
]

# Each break must make exactly the named case fail.
BREAKS = {
    "staged_reads_working_copy": "staged_copy_is_read",
    "hook_skips_check": "hook_refuses_commit",
}

BROKEN = None


def _apply_break(name):
    """Scoped to the case the break names, as in verify_periods.py."""
    if name == "staged_reads_working_copy":
        real = verify_privacy.read_text

        def patched(rel, staged):
            if ACTIVE_CASE != BREAKS[name]:
                return real(rel, staged)
            return real(rel, False)

        verify_privacy.read_text = patched
    # hook_skips_check is applied inside its case, to the scratch repo's copy.


def main(argv):
    if "--list" in argv:
        for name, inv, _ in CASES:
            print(f"{inv}  {name}")
        print("\nbreaks:")
        for b, case in sorted(BREAKS.items()):
            print(f"  --break {b:30} -> {case} must FAIL")
        return 0

    global ACTIVE_CASE, BROKEN
    for i, a in enumerate(argv):
        if a == "--break":
            BROKEN = argv[i + 1]
            if BROKEN not in BREAKS:
                print(f"unknown break {BROKEN!r}; --list shows them")
                return 2
            _apply_break(BROKEN)
            print(f"BREAK {BROKEN}: {BREAKS[BROKEN]} must FAIL\n")

    failed = []
    for name, inv, fn in CASES:
        ACTIVE_CASE = name
        try:
            detail = fn()
            print(f"  {inv}  {name:24} PASS  {detail}")
        except AssertionError as e:
            failed.append(name)
            print(f"  {inv}  {name:24} FAIL  {e}")

    print()
    if BROKEN:
        want = BREAKS[BROKEN]
        if failed == [want]:
            print(f"RED-TEST OK: {want} failed under --break {BROKEN}")
            return 0
        if want in failed:
            others = [f for f in failed if f != want]
            print(f"RED-TEST TOO COARSE: {BROKEN} also reddened {others}")
            return 1
        print(f"RED-TEST FAILED: {want} still passes under --break {BROKEN}")
        return 1
    if failed:
        print(f"{len(failed)} of {len(CASES)} FAILED: {', '.join(failed)}")
        return 1
    print(f"all {len(CASES)} cases pass")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
