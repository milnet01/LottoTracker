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

# --- documentation-only pushes skip the gate -------------------------------
# The unit is the commits that are about to be pushed, not the working tree.
# No upstream (a fresh branch) means we cannot tell, so we run.
if [ "$CI_ONLY" -eq 0 ] && [ "$FORCE" -eq 0 ]; then
    if upstream=$(git rev-parse --abbrev-ref '@{upstream}' 2>/dev/null); then
        changed=$(git diff --name-only "$upstream"..HEAD 2>/dev/null)
        if [ -n "$changed" ] && ! printf '%s\n' "$changed" | grep -qv '\.md$'; then
            echo "local-CI: documentation only ($(printf '%s\n' "$changed" | wc -l) file(s), all .md) - gate skipped."
            echo "          Run with --force to gate anyway."
            exit 0
        fi
    fi
fi

FAILED=()
LAST_OUT=""

run() {  # run <label> <command...>
    local label="$1"; shift
    printf '  %-32s ' "$label"
    local out rc
    out=$("$@" 2>&1); rc=$?
    LAST_OUT="$out"
    if [ "$rc" -eq 0 ]; then
        echo "PASS"
    else
        echo "FAIL (rc=$rc)"
        printf '%s\n' "$out" | tail -20 | sed 's/^/       | /'
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
run "verify_privacy.py" python3 tools/verify_privacy.py
PRIVACY_OUT="$LAST_OUT"

# --- the local-only lane ---------------------------------------------------
if [ "$CI_ONLY" -eq 0 ]; then
    echo "local-CI: local-only lane (needs the SMS dump and the scraped archive)"

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
