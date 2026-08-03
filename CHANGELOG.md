# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`LWSM_MANAGED=1` runs the tray with no icon, logging to stdout.** (LOTTO-0024)
  For processes an external manager starts, where a tray icon is redundant.
  No headless path can stop the server — the menu it skips contains "Quit
  (stops the server)", and the manager owns the tree it started. Any other
  value, or none, is the unchanged tray. The variable is a presentation
  hint with no security value; nothing is granted or relaxed on it.
  LOTTO-0013 §4.7, INV-25.

- **The bound port comes from `$PORT`, then `$LOTTO_PORT`, then 4322.** (LOTTO-0024)
  `$PORT` is the name an external process manager already sets, so it wins;
  the `$LOTTO_PORT` path is unchanged. `supervise.py` pins both variables
  in the child so a session's own `$PORT` cannot send the server to a port
  the tray is not watching. LOTTO-0002 INV-24.

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

- **A non-numeric port variable died with a traceback instead of a message.** (LOTTO-0024)
  `LOTTO_PORT=abc python3 serve.py` raised an unhandled `ValueError` from a
  bare `int()`. Both variables now exit non-zero naming the variable and
  the value they rejected, and an out-of-range port is rejected before the
  bind rather than as a confusing "permission denied". Never a silent
  fallback: a caller that asked for port 80 and got 4322 has been lied to.

- **The tray waits for the build before reporting a refresh, and reports a failure as a failure (INV-23)** (LOTTO-0018)
  `POST /refresh` answers 202 = accepted, not finished — `serve.py::refresh()`
  starts a daemon thread and returns — and `tray.py` treated that as
  completion, so the icon said "Results refreshed." milliseconds into a
  thirty-second build, and said the same when the build raised. New
  `supervise.Supervisor.refresh()` POSTs, then polls `GET /status` (the signal
  the page already uses) on the page's own 2 s cadence until `building` clears,
  and returns one of four outcomes: done, failed, still running at the 300 s
  budget, or already running (the 409, which surfaced as
  `Refresh failed: HTTP Error 409: Conflict`). Only the first reads as success.
  The wording lives in Qt-free `supervise.REFRESH_MESSAGE` so a headless case
  can assert it. LOTTO-0013 §4.6, three cold-eyes loops, 43 verified findings
  fixed; `tools/verify_page.py::refresh_reports_the_build` and its three
  breaks (`notify_on_202`, `stale_is_success`, `success_wording`).

- **The cold-eyes gate INV-22 was owed, run to acceptance in two loops** (LOTTO-0022)
  LOTTO-0001 §13 loops 5 and 6. 23 verified findings fixed, 2 dismissed,
  1 filed as LOTTO-0023. §6 still described the pre-INV-22 behaviour, so
  the failure-modes section licensed the R0.00 default the invariant
  forbids; and INV-5's recorded test was red against correct code, its
  glob sweeping the `tools/` doubles — one of which is INV-22's own probe,
  so the obvious repair would have deleted a guard on the money path.
  §4.4 now carries `check()`'s win-record shape, which no document stated
  although `serve.py` spreads it into the page model.

- **A win whose prize cannot be read now raises instead of pricing at R0.00 (INV-22)** (LOTTO-0007)
  `check.py::amount()` is called only after a combination has matched a paying
  division, so every call prices a line already known to have won — there is no
  "did not win" answer for it to give. It nevertheless fell back to `0.0` when
  the archive payout page could not be parsed, or when neither the exact nor
  the plain division label appeared in the table, putting a figure on the page
  and in the terminal that is indistinguishable from a real losing line. That
  is this project's cardinal failure on the money path itself, and
  `paying_combinations()` already raised for the identical reason.
  Both branches now raise with a diagnostic naming the pool, the draw and the
  label. A division the source *does* carry and states as zero still returns
  `0.0` — that is an answer, not a gap, and the guard asserts both directions.
  Measured before the change: 86 wins, 69 archive-era, **0 priced at R0.00**,
  all 67 archive draws parsing. Figures after are identical (R2,651.60 total,
  62 claimable lines) — this closes a latent hole rather than repricing
  anything. `tools/verify_pools.py` gains four blind-lookup probes; red-tested
  by reverting the archive branch, which mispriced 2 and exited 1.

- **One settings reader, not two that agree today** (LOTTO-0013)
  `serve.py` imported `read_settings()` from `supervise` and then redefined
  it twenty lines below, so the local copy won and the file shipped with two
  readers of the same settings file. Both bodies were identical, so nothing
  misbehaved and all five checks were green over it — which is the shape of
  the defect rather than a mitigation: agreeing duplicates are
  indistinguishable from one reader until somebody edits one, and the
  divergence then surfaces as the settings panel and the tray disagreeing
  about `open_on_start`. The duplicate is gone; `serve.py` imports the reader
  and defines only `write_settings()`. No behaviour change.

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
