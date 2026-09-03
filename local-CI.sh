#!/usr/bin/env bash
#
# local-CI.sh - the pre-push gate. Run this before every `git push`.
#
#   ./local-CI.sh            full gate: the CI lane plus the four checks a
#                            runner cannot do (see below). This is the one to
#                            run before pushing.
#   ./local-CI.sh --ci       the CI lane ONLY. This is what
#                            .github/workflows/ci.yml invokes, so the runner
#                            and this machine execute the same lines rather
#                            than two lists that agree today and drift later.
#   ./local-CI.sh --force    run even when the push is documentation only.
#
# WHY THERE ARE TWO LANES, AND WHY THEY CANNOT BE ONE
#
# Six of the nine verifiers read data that is deliberately not in the repo:
# lotto_sms_raw.txt is real SMS content and archive_results.json/archive_cache/
# are a scraped archive that is large and not ours to redistribute (.gitignore
# says both). A fresh clone - which is exactly what a runner gets - therefore
# fails verify_sources, verify_coverage, verify_pools, verify_payouts,
# verify_expiry and verify_periods on missing input, and no amount of YAML fixes
# without publishing the private data. The remaining three - verify_page,
# verify_watch and verify_privacy - are the CI lane.
#
# This paragraph said "three of the five" until 2026-08-20, and had said it
# since before verify_payouts.py existed. It was found by the review-contract
# gate on CLAUDE.md, in all three of its loops, and matters more than a stale
# count usually would: CLAUDE.md points the reader HERE as the authoritative
# statement of the asymmetry, so someone adding a fifth data-dependent verifier
# would have reasoned from a comment that was already wrong. verify_expiry.py
# (LOTTO-0034) is that fifth verifier, added 2026-08-22, and the counts above
# were moved with it. verify_periods.py (LOTTO-0036) is the sixth, added
# 2026-08-27, and the counts above were moved with it again.
#
# The privacy check is the one that matters most. tools/verify_privacy.py compares tracked
# files against the dump's actual text; with no dump it falls back to pattern
# checks alone and says so ("pattern only (no dump present)"). That mode still
# exits 0. So a green runner does NOT mean "no leak" - it means the strong half
# of the check never ran. This script asserts the strong half locally, because
# here the dump IS present and a degraded run means something is wrong.
#
# Hence: the runner gets the checks it can honestly perform, this machine gets
# all of them, and the overlap is one shared implementation rather than a copy.
# (The project already learned this the expensive way - serve.py once imported
# read_settings() and redefined it twenty lines down; two identical readers are
# indistinguishable from one until somebody edits one of them.)

set -uo pipefail
cd "$(dirname "$0")" || exit 2

CI_ONLY=0
FORCE=0
for a in "$@"; do
    case "$a" in
        --ci)    CI_ONLY=1 ;;
        --force) FORCE=1 ;;
        -h|--help)
            sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "local-CI.sh: unknown option: $a" >&2; exit 2 ;;
    esac
done

# --- documentation-only pushes run the privacy check and skip the rest -----
# The unit is the commits that are about to be pushed, not the working tree.
# $GATE_RANGES is set by .githooks/pre-push from git's own stdin protocol and
# names exactly the refs being pushed; without it (a hand run) we fall back to
# the current branch's upstream, which answers a DIFFERENT question and is why
# the hook passes the ranges in. No upstream and no ranges means we cannot
# tell, so we run everything.
#
# A documentation-only push is NOT unchecked. verify_privacy.py's subject is
# prose - CLAUDE.md says never paste real message content into code, DOCS or
# commit messages, and records two leaks that got past weaker checks, one per
# review loop. Skipping it on exactly the push class it was written for left
# INV-4 unenforced, and ci.yml's paths-ignore closed the same hole on the
# runner, so a docs-only push ran no privacy check anywhere. It needs only the
# dump and git ls-files, and is the cheapest of the nine.
if [ "$CI_ONLY" -eq 0 ] && [ "$FORCE" -eq 0 ]; then
    changed=""
    if [ -n "${GATE_RANGES:-}" ]; then
        for range in $GATE_RANGES; do
            changed="$changed"$'\n'"$(git diff --name-only "$range" 2>/dev/null)"
        done
        changed=$(printf '%s\n' "$changed" | grep -v '^$' | sort -u)
    elif upstream=$(git rev-parse --abbrev-ref '@{upstream}' 2>/dev/null); then
        changed=$(git diff --name-only "$upstream"..HEAD 2>/dev/null)
    fi
    if [ -n "$changed" ] && ! printf '%s\n' "$changed" | grep -qv '\.md$'; then
        echo "local-CI: documentation only ($(printf '%s\n' "$changed" | wc -l) file(s), all .md)."
        echo "          Running the privacy check anyway - prose is its subject."
        out=$(python3 tools/verify_privacy.py --require-content 2>&1); rc=$?
        printf '  %-32s %s\n' "verify_privacy.py" \
            "$([ "$rc" -eq 0 ] && echo PASS || echo "FAIL (rc=$rc)")"
        if [ "$rc" -ne 0 ]; then
            printf '%s\n' "$out" | tail -20 | sed 's/^/       | /'
            echo "local-CI: FAIL"
            exit 1
        fi
        if ! printf '%s' "$out" | grep -q 'content+pattern'; then
            printf '  %-32s FAIL\n' "privacy ran at full strength"
            printf '       | %s\n' "verify_privacy.py degraded to pattern-only - lotto_sms_raw.txt is missing, so the content comparison never ran."
            echo "local-CI: FAIL"
            exit 1
        fi
        printf '  %-32s PASS\n' "privacy ran at full strength"
        echo "local-CI: documentation only - rest of the gate skipped."
        echo "          Run with --force to gate anyway."
        exit 0
    fi
fi

FAILED=()
LAST_OUT=""
LAST_LABEL=""

run() {  # run <label> <command...>
    local label="$1"; shift
    printf '  %-32s ' "$label"
    local out rc
    out=$("$@" 2>&1); rc=$?
    LAST_OUT="$out"
    LAST_LABEL="$label"
    if [ "$rc" -eq 0 ]; then
        echo "PASS"
    else
        echo "FAIL (rc=$rc)"
        if [ "$CI_ONLY" -eq 1 ] && [ "$label" = "verify_privacy.py" ]; then
            # NEVER on a public runner. This check reports WHAT it matched,
            # and what it matches is real SMS content - so printing its output
            # into a public Actions log publishes the leak it has just caught.
            printf '       | output withheld on the CI lane: it quotes what it matched.\n'
            printf '       | Run ./local-CI.sh locally to read it.\n'
        else
            printf '%s\n' "$out" | tail -20 | sed 's/^/       | /'
        fi
        FAILED+=("$label")
    fi
    return 0
}

fail() {  # fail <label> <reason>
    printf '  %-32s FAIL\n' "$1"
    printf '       | %s\n' "$2"
    FAILED+=("$1")
}

# --- the CI lane -----------------------------------------------------------
# Everything here runs identically on a runner and on this machine.
#
# The versions are printed because the first local-vs-runner comparison
# disagreed on exactly this: ruff 0.15.11 here against 0.16.1 there, whose
# wider default rule set reported 71 errors that no one had opted into.
# ruff.toml pins the RULES so the verdict no longer depends on the release,
# and this line makes the remaining difference visible rather than latent.
echo "local-CI: CI lane   [$(ruff --version 2>/dev/null || echo 'ruff MISSING'), $(python3 -V 2>&1)]"
run "ruff check"        ruff check .
run "syntax (compileall)" python3 -m compileall -q .
run "verify_page.py"    python3 tools/verify_page.py
# In the CI lane on purpose: LOTTO-0003's checks need no phone, no KDE Connect
# and no dump. Its one dump-dependent case says so and carries on when there is
# none, which is why it is honest to run it where there never is one.
run "verify_watch.py"   python3 tools/verify_watch.py
# --require-content ONLY on the local lane. It makes verify_privacy.py exit
# non-zero when the dump is absent, which is the strong mode this machine can
# always run; a public runner never has the dump, so asking there would fail
# every CI run. This is the verifier's OWN guard - the grep below is the
# second, independent one, and lane 2 of the 2026-09-02 test audit showed a
# single failure could defeat the grep alone.
if [ "$CI_ONLY" -eq 0 ]; then
    run "verify_privacy.py" python3 tools/verify_privacy.py --require-content
else
    run "verify_privacy.py" python3 tools/verify_privacy.py
fi
PRIVACY_OUT="$LAST_OUT"
# LAST_OUT belongs to whichever run() ran last, so this capture depended on
# textual adjacency alone: insert a check between the two lines and the
# full-strength assertion below silently grades the wrong command. The
# adjacency is still what makes it right - this is what SAYS SO when it stops
# being true.
if [ "$LAST_LABEL" != "verify_privacy.py" ]; then
    fail "privacy output captured" \
         "PRIVACY_OUT holds the output of '$LAST_LABEL', not verify_privacy.py - a check was inserted between the run and the capture."
fi

# --- the local-only lane ---------------------------------------------------
if [ "$CI_ONLY" -eq 0 ]; then
    echo "local-CI: local-only lane (needs the SMS dump and the scraped archive)"

    # The gate is only a gate if it is ON the push, and git does not track
    # hooks - core.hooksPath is local config, set once per clone. Nothing
    # asserted it, so a clone that skipped that one command had an entirely
    # inert push gate with no signal at all: every push went straight out, and
    # a green verdict here said nothing about it.
    if [ "$(git config --get core.hooksPath 2>/dev/null)" = ".githooks" ]; then
        printf '  %-32s PASS\n' "push hook wired"
    else
        fail "push hook wired" \
             "core.hooksPath is not .githooks, so .githooks/pre-push never runs and this gate is not on the push. Fix, once per clone: git config core.hooksPath .githooks"
    fi

    # The privacy check above is only worth its exit code in content+pattern
    # mode. Locally the dump is present, so "pattern only" is a broken gate
    # reporting success - precisely the "no data reads as no finding" shape
    # this project forbids everywhere else.
    if printf '%s' "$PRIVACY_OUT" | grep -q 'content+pattern'; then
        printf '  %-32s PASS\n' "privacy ran at full strength"
    else
        fail "privacy ran at full strength" \
             "verify_privacy.py degraded to pattern-only - lotto_sms_raw.txt is missing, so the content comparison never ran."
    fi

    run "verify_sources.py"  python3 tools/verify_sources.py
    run "verify_coverage.py" python3 tools/verify_coverage.py
    run "verify_pools.py"    python3 tools/verify_pools.py
    # Needs the dump AND the archive: periods_reconcile recomputes every
    # bucket from TIER_PRICES and history.covered() over the real tickets
    # (LOTTO-0036 INV-57). Its other three cases are synthetic, but the file
    # fails as a whole without its inputs rather than reporting a weaker pass.
    run "verify_periods.py"  python3 tools/verify_periods.py
    # Needs the dump AND the archive: it reconciles the bank's own payout
    # SMSes against every computed win (LOTTO-0029). A public runner has
    # neither, and the payouts are the one thing that must never reach one.
    run "verify_payouts.py"  python3 tools/verify_payouts.py
    # Three of its eight cases need real data and not the same data: the merged
    # draw record for the calendar, and the dump of 561 mostly-finished tickets
    # for the case that proves an expired ticket is never warned about. It has
    # no weak mode on purpose (LOTTO-0034 §7).
    run "verify_expiry.py"   python3 tools/verify_expiry.py
else
    echo "local-CI: --ci, so the six data-dependent verifiers and the"
    echo "          full-strength privacy assertion are NOT run. A green"
    echo "          result here is weaker than a green ./local-CI.sh."
fi

# --- verdict ---------------------------------------------------------------
echo
if [ "${#FAILED[@]}" -eq 0 ]; then
    echo "local-CI: PASS"
    exit 0
fi
echo "local-CI: FAIL - ${#FAILED[@]} check(s): ${FAILED[*]}"
exit 1
