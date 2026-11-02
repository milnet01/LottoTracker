# ADR-0014 — Daily Lotto Plus is scored from the archive alone

**Status:** Accepted, 2026-11-02 (LOTTO-0085). Supersedes ADR-0011.
**Enforced by:** `tools/verify_pools.py`'s `archive-page divisions` probes, and
`tools/verify_sources.py`'s floor on `EXPECTED_EMPTY` pools.

## Context

ADR-0011 mapped `daily/1` to an empty pool because no source carried it.
`za.national-lottery.com` now lists it, under `/daily-lotto-plus`. Its first
listed draw is 2025-09-26 and its last is 2026-05-31, when the game ended. The
official feed has never carried it.

Measured 2026-11-02 against the bank's payout SMSes: every reference with a
Plus win agrees with the bank to the cent, and no Plus win falls on a reference
the bank paid nothing on. That is the evidence it is the game the tickets
bought. The pool's draws never equal plain Daily Lotto's on the same date, so
ADR-0011's ban on aliasing still stands.

## Decision

**`daily/1` is its own pool, with draws and prizes from the archive.**
`check.py::paying_combinations()` reads its divisions from the results page of
its newest draw, because no feed row exists to read them from.

**`history.py::ARCHIVE_ONLY` declares the pool.** A pool with no feed rows is
otherwise a renamed pool, and ADR-0010 requires that to raise.

**`backfill.py::YEARS_RAN` bounds the years it is fetched for.** The site
answers 404 for other years, and `build()` refuses a partial archive.

**A Plus entry older than the first listed draw stays uncheckable.** The site
holds no page for the dates before it. `history.py::scorable()` already gates
on the pool's first draw, so nothing is scored against a later draw. Whether
draws ran on those dates is unverified: `tickets.py` records a 2025-09-21 start.
