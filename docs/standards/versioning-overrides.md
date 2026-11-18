# Versioning — this project's deltas

Overrides `~/.claude/standards/versioning.md` § 4 (Zero-dot-x) for this
project only.

## Every 0.x release raises the MINOR number

Releases go 0.1.0, 0.2.0, 0.3.0 and on, then 1.0.0. A release before 1.0.0
never takes a PATCH step, whatever it contains. The user set this on
2026-11-18: a run of 0.1.x releases followed by 1.0.0 reads as a jump.

Nothing checks it. `cut-release` takes the version it is given, so whoever
names the version applies this rule.

## What makes it 1.0.0

The page looks professional and production-ready: LOTTO-0100 and LOTTO-0101
are shipped. The roadmap item LOTTO-0060 holds the scope and its history.
