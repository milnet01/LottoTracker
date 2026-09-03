# Test-audit baseline and break sweep — 2026-09-02/03

Recorded by the `review-tests` run whose lane reports sit beside this
file. Both are cited by the LOTTO-0067..0075 resolution notes.

## Baseline: every verifier, standalone, before any fix
```
verify_coverage.py         rc=0     11.2s
verify_expiry.py           rc=0      3.5s
verify_page.py             rc=0      7.6s
verify_payouts.py          rc=0     35.5s
verify_periods.py          rc=0     37.6s
verify_pools.py            rc=0     17.7s
verify_privacy.py          rc=0      4.8s
verify_sources.py          rc=0     16.2s
verify_watch.py            rc=0      4.2s
```

## Break sweep, after the fixes: 56 breaks, every one exact
```
breaks run: 56
non-OK: none
```

## The five too-coarse breaks the tightened verdict first surfaced
```
verify_expiry    exclusive_start                  rc=1   RED-TEST TOO COARSE: exclusive_start also reddened ['notice_names_nothing_else', 'draws_left_today_boundary']
verify_expiry    never_records                    rc=1   RED-TEST TOO COARSE: never_records also reddened ['state_file_is_pruned']
verify_expiry    swallow_unknown_game             rc=1   RED-TEST TOO COARSE: swallow_unknown_game also reddened ['notice_names_nothing_else']
verify_expiry    unlisted_draw_day                rc=1   RED-TEST TOO COARSE: unlisted_draw_day also reddened ['calendar_matches_real_draws']
verify_payouts   compare_in_rands                 rc=1   RED-TEST TOO COARSE: compare_in_rands also reddened ['unscored_is_not_unexplained']
```
