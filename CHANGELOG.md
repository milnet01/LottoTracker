# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **A local web page for tickets, results and claimable winnings** (LOTTO-0002)
  `serve.py` builds the model and serves it; `page.py` renders it and is a pure
  function, so the whole page can be rendered in a test with no socket and no
  results file. The page leads with what is claimable and its expiry, then what
  is outstanding, then every entry, then spend against winnings.
  The honesty rules are structural rather than prose: an entry nothing can score
  carries `won_cents: None` and renders as "not checkable" with its reason,
  never as a blank, a dash or a zero — and `draws_covered` is `None` for the
  same entries, because "0 draws checked" on a 2019 ticket is the same failure
  one column left. An empty page is correct only when it names why: the dump is
  missing, the first build failed, or `LOTTO_NO_BUILD` is set.
  Spend is compared against winnings over the checkable entries of resolved
  tickets only, both sides scoped identically; lifetime spend is a separate,
  labelled line and the two are never subtracted. Comparing them would put a
  false loss of R25,592.90 on the page.

- **Tray icon and server supervisor** (LOTTO-0013)
  `tray.py` is PySide6 and nothing else; `supervise.py` owns the token, the port
  and the child process and imports no Qt, which is what makes the
  spawn-and-reap lifecycle checkable from a headless script rather than needing
  a display. Quitting reaps the server synchronously — dispatched to a thread
  pool it would return before `wait()` completed and orphan the child holding
  the port. The child is spawned with an explicit `cwd`, without which an
  autostarted tray starts a server that finds none of the data files and shows
  an empty page.

### Security

- **The local page's HTTP surface and security boundary** (LOTTO-0014)
  Four routes and nothing else. An exact, lowercased `Host` allowlist answering
  421 otherwise — a `127.0.0.1` bind stops the network but not the user's own
  browser being aimed at the port by a hostile page, which is CVE-2026-46611
  (Glances) exactly. A per-run token in an `X-Lotto-Token` header on both write
  routes, compared with `secrets.compare_digest`, reaching the tray through the
  child's environment rather than argv, which `ps` exposes. `X-Frame-Options:
  DENY` and `frame-ancestors 'none'` on every response including the 421s,
  without which the token guards a forged request but not a real one clicked
  through an invisible overlay. No `Access-Control-Allow-*` header ever, on any
  route. Nothing request-derived reaches a response header or a written file:
  header values come from a fixed table, the access log is silenced because it
  writes the request line to stderr, and the `Server` header is overridden
  because the default names both the server and the interpreter version.
  Bounded body reads (4 KiB, then 413) and a socket timeout, because reading
  exactly `Content-Length` bytes hangs just as completely when a client declares
  4000 and sends 1.

- **`tools/verify_page.py` — ten cases, INV-12 to INV-21** (LOTTO-0002/0013/0014)
  Joins the four existing checks; exit code is the signal. It needs no network
  and no real data: every case runs with both `$HOME` and `$XDG_CONFIG_HOME`
  redirected and tickets built from the `VAS00000000000` sentinel.
  Every case was observed **failing** before its invariant was accepted. These
  items are greenfield, so there was no pre-fix code to red-test against; the
  script carries a `--break <name>` flag that applies one deliberate defect and
  asserts the named case goes red. Thirteen breaks, all thirteen red.
  One of them caught a defect in a *case* rather than in the code, which is the
  whole argument for the practice: rendering an unscorable entry's amount as an
  em-dash did **not** turn INV-15 red, because the assertion compared raw markup
  (so `&mdash;` never equalled `—`) and had explicitly excluded the empty string
  from its forbidden set. Both are exactly the renderings the cardinal rule
  forbids, and the check could not see either. Fixed, then re-verified red.

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
