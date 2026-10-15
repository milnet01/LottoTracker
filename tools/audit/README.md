# Audit config

`check-code` reads `audit-config.json` here (its third probe path), so a run
uses this project's tools and settings instead of the global defaults
(LOTTO-0056, the user's decision of 2026-09-28).

- **The tools** are the ones this project already runs: the Python linters
  and type checkers, each reading its own settings file at the repository
  root (`ruff.toml`, `pyrightconfig.json`, `mypy.ini`, `.yamllint`,
  `_typos.toml`), `shellcheck` on the gate and hook scripts, and
  `actionlint` and `zizmor` on the CI workflow.
- **`scope.txt`** lists paths no tool should scan. Each is untracked.
- **No suppressions file yet.** `close-findings` writes one when a finding
  is judged a false positive; `.ants_review_falsepos.jsonl` is the existing
  record.

`./local-CI.sh` runs most of the same tools before every push; this file is
for a deliberate `check-code` sweep.
