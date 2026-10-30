# Code review sweep — 2026-10-28

Single-lane, budget-limited sweep over the Python modules (bugs, performance,
readability), done in one session. Each fix is its own commit on the PR branch.

## Found and fixed

| Where | What | Verified by |
|---|---|---|
| `tickets.py::load()`, `load_payouts()` | Dump read with the locale encoding while `watch_sms.py` writes UTF-8: any non-ASCII byte mis-decodes on a non-UTF-8 locale | `verify_senders.py`, `verify_watch.py` |
| `supervise.py` (three JSON opens), `watch_sms.py::read_threads()`, `tools/verify_coverage.py` | Same missing `encoding`; `read_threads()` also leaked its file handle | `verify_watch.py`, `verify_expiry.py` |
| `results.py` `__main__` | Smoke test joined `winNumList` unguarded: `TypeError` on a listed-but-undrawn draw (`null`) or integer numbers. `history.all_draws()` already guards both | ruff; read |
| `page.py::_wins_section()` | "(1 days)" beside a claim deadline; now uses `_count()` | `verify_page.py` |
| `check.py::match()` | Intersection built twice per branch with a throwaway set; now counted once | `verify_boards.py` |
| `check.py::uncheckable_report()` | `scorable()` asked up to four times per entry; now once | `verify_boards.py` |

## Looked at and dismissed

- `serve.py::refresh()` does not clear `check._retired`: dismissed, `build_model()` never calls `retired_divisions()`.
- ruff B023 in `tools/verify_pools.py`: the lambdas are called inside the same loop iteration, so late binding cannot bite.
- ruff B033 in `tools/verify_watch.py`: the duplicate `2424` is the deduplication under test.
- The remaining widened-ruff findings (SIM/UP/PERF style) are style opinions on working code; `ruff.toml` says widening the rule set is its own decision.

## Not covered

`verify_page.py`'s `tray_headless_when_managed` fails in this container only
because PySide6 is absent (it fails identically on the base). The local-lane
verifiers need `lotto_sms_raw.txt` / the archive and were not run here.
