# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Read lottery ticket SMSes off an Android phone** (LOTTO-0001)
  Two routes: `adb` over USB for bulk history, filtering on the device so only
  lottery messages are copied; and KDE Connect over Wi-Fi via
  `find_lotto_sms.py` for new tickets.
- **Parse Standard Bank ticket confirmations from both SMS eras** (LOTTO-0001)
  The bank changed its wording when Sizekhaya replaced Ithuba as licence
  holder on 2026-06-01. `tickets.py` reads both. 558 tickets parsed from
  messages dating back to 2022-11-09.
- **Fetch draw results from the operator's own public feed** (LOTTO-0001)
  `results.py` calls the endpoints the official results page itself uses. No
  API key, no registration, no cost.
- **Backfill results from before the operator handover** (LOTTO-0001)
  The official feed starts at 2026-06-01. `backfill.py` scrapes earlier draws
  and per-draw payout tables, cached so re-runs are free.
- **Score every ticket and price each win** (LOTTO-0001)
  `check.py` reports what is still claimable and when each prize expires,
  reading prize divisions from the source rather than hardcoding them. A
  ticket that nothing can score — one predating all draw data, or in a pool no
  source publishes — is reported as uncheckable, never scored against another
  game's draws and never counted as a loss.
- **Three contract checks** (LOTTO-0001)
  `tools/verify_sources.py` confirms the two results sources agree wherever
  they overlap; `tools/verify_coverage.py` confirms every ticket is scored
  over the right draws and that none were silently dropped in parsing;
  `tools/verify_privacy.py` confirms no real message content is tracked,
  comparing against the dump itself rather than a pattern.

- **Record what each ticket cost** (LOTTO-0008)
  `Ticket.cost` is the total the SMS charged for the whole ticket — every
  board, every draw, every tier. The same figure is what derives the entered
  pools, which is why the two were specified together.
- **A fourth contract check** (LOTTO-0009)
  `tools/verify_pools.py` asserts that every ticket's price resolves to real
  tiers and that a ticket checkable in one pool is never reported as wholly
  uncheckable. It transcribes the price table independently rather than
  importing the derivation it is testing.

### Fixed

- **Score every draw a ticket was entered in, not just the top one**
  (LOTTO-0009)
  A "plus" game cannot be bought alone: the operator requires the base game
  and runs a separate draw with its own prize pool for each tier, so a Lotto
  Plus 2 ticket is three entries with three prize pools. Only the top tier was
  being scored, so 675 of 1,233 paid entries — 55% — were never checked at
  all. Which tiers were bought is now derived from the ticket price in whole
  cents, because the printed game name states only the highest and, after the
  2026-06-01 handover, stops stating even that. All 1,233 entries resolve;
  a price matching no tier is reported, never guessed at.
  **This found 30 further winning lines worth R1,790.40, of which R1,722.90 is
  still claimable.** The claimable total moves R700.10 → R2,423.00. No
  previously reported win changed or disappeared.
- **Report what cannot be checked per entry, not per ticket** (LOTTO-0009)
  A ticket can now be checkable in one pool and not another — all 11
  `Daily Lotto Plus` tickets are, since no source publishes that pool while
  their base Daily Lotto entry scores normally. `check.py` counts uncheckable
  entries and splits the tickets behind them into wholly and partly
  uncheckable, so a ticket with one dead pool is still scored on the rest
  instead of being written off. The rule that no-data must never read as a
  loss now holds at the level the data actually varies.

### Security

- **Exclude all SMS content from version control** (LOTTO-0001)
  The repository is public. `.gitignore` covers the message dump and results
  cache; INV-4 asserts nothing matching them is ever tracked.
