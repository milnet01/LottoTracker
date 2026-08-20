# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **The page shows the numbers you chose beside the numbers that were drawn (LOTTO-0035)**
  Every winning line now renders your board and that draw's numbers side by
  side, and every ticket with draws still to come shows what you played. The
  special number — the PowerBall, or Lotto's bonus ball — is marked apart from
  the mains rather than reading as a sixth main number. Holds INV-48.

  The item was filed as "the cheapest on the list, a rendering change alone"
  and that was wrong: the model carried `len(t.boards)`, the count, never the
  numbers. Both halves needed `build_model()` work. The scoring engine now
  reports the numbers it matched, rather than a consumer re-deriving them.

  Writing the red test found a defect in the test rather than in the code, the
  second time `--break` has done that. The break for the absence rule first
  patched `page._balls` and the case stayed green, because `_boards_cell()`
  answers the empty case itself and never calls it — the assertion was being
  satisfied by a path the break did not touch.

- **The bank's own payout messages, checked against every win this app computed. (LOTTO-0029/0010)**
  369 payout SMSes were sitting unread in the dump. `check.py` now joins them
  to tickets on the VAS reference and reports, per reference, what the bank
  paid beside what this project computed. The bank has paid R8,332.70; this
  app computes R3,343.20, and the difference is now visible instead of absent.

  Where the two disagree the disagreement is FLAGGED, never resolved in the
  SMS's favour (your decision, 2026-08-13). Adopting the bank's figure would
  price the archive era for free and erase the 15 references where the app
  computes LOW - which are the evidence that something in pricing is wrong.

  Seven categories, decided in a fixed order because as an unordered set they
  overlap. 61 references agree exactly. 15 are computed low and 2 high. 142
  were paid where an entry nothing can score may be the reason - correct
  silence, not a defect. 1 was paid against a reference with no purchase SMS
  at all. And 4 are fully checkable, paid, and reach no paying division: the
  real leads, kept in their own category so they cannot be buried in the 142.
  Zero references where the app claims a win the bank never paid.

  `tools/verify_payouts.py` holds INV-40 to INV-47, and joins local-CI.sh's
  local-only lane - it needs both the dump and the archive, and the payouts
  are the one thing that must never reach a public runner. Eight cases, each
  observed failing under its own `--break`.

- **New tickets arrive with no cable — `watch_sms.py` listens over KDE Connect and appends to the dump. (LOTTO-0003)**
  The tray starts it, stops it and re-scores the page when the dump grows,
  so a ticket bought on the phone reaches the page by itself. adb keeps
  bulk history; the two paths share one filter, checked against SQLite
  (INV-32), and one dump reader, `tickets.py::rows()`.
  The subscribe-don't-poll plan was half wrong and the correction is the
  interesting part: `conversationCreated` fires only the first time the
  KDE Connect daemon learns of a conversation — 202 signals on a first
  run, zero on every later one, against the same 2,325 conversations — so
  the first build of this reported "0 new" against a phone holding 951
  matching messages. Discovery now reads `activeConversations()` and
  waits for it to stop growing. Seven cases in `tools/verify_watch.py`,
  all observed failing; none of them could have caught that defect, and
  the spec says so (§7).
  Live, with the cable unplugged: 2,325 threads read in 21 seconds, two
  new payout SMSes collected, the 951 existing records untouched.

- **The tray says what a refresh found, instead of a flat "Results refreshed."** (LOTTO-0019)
  `GET /status` gains `found` — how many winning lines the last completed
  build found that its predecessor did not, and their total — and
  `supervise.refresh_message()` turns it into a sentence: "2 new winning
  lines, R240.00."
  Three DONE states, and the first two are this project's cardinal rule in
  notification form: `found: null` (nothing was compared — the first check
  this session) must never read like `new_wins: 0` (compared, nothing new).
  The first build of a process compares against no predecessor and reports
  null rather than announcing every existing win as new.
  The body is composed from two integers and nothing else — no ticket
  reference, no board label, no draw date, no division — because a desktop
  notification may be logged and synced off the machine, which is the
  reasoning LOTTO-0014 INV-21 already applies to the URL.
  Holds INV-29 and INV-30. Scheduling is deliberately not here: LOTTO-0019
  makes a refresh REPORT what it found, and LOTTO-0028 is what would make one
  HAPPEN unasked.

- **The building page says how many lookups it has done, instead of nothing for half a minute** (LOTTO-0020)
  `GET /status` gains `requests` — every HTTP attempt the build has made —
  and the opening page's notice interpolates it and the poll keeps it moving.
  No denominator: `check.py` fetches lazily, so this build's total is unknown
  until it ends, and LOTTO-0002's 27 is a dated measurement rather than a
  constant. It counts *attempts*, which is what makes it move during the
  retry storms LOTTO-0012 introduces.
  The counter resets in `serve.py::refresh()` before the worker thread
  starts, not on it: `begin()` has already set `building`, so a later reset
  leaves a window where `/status` reports the previous build's total for a
  build in flight. Holds INV-28, with three breaks observed red.

- **A pre-push gate, and a CI workflow that runs the same script.** (LOTTO-0025)
  `./local-CI.sh` runs before every push (wire it up with `git config
  core.hooksPath .githooks`); `.github/workflows/ci.yml` invokes
  `./local-CI.sh --ci`, so there is one list of checks rather than two
  copies to drift apart. **The two lanes are deliberately unequal.**
  Three verifiers need the SMS dump and the scraped archive, and neither
  may reach a public runner — in a fresh clone `verify_sources`,
  `verify_coverage` and `verify_pools` exit 1, while `verify_privacy.py`
  *passes* on a weaker pattern-only fallback. A green tick on GitHub is
  therefore worth less than a green `./local-CI.sh`, so the script
  asserts locally that the privacy check ran in `content+pattern` mode
  instead of trusting its exit code — an exit code read as "no leak"
  when the strong half never ran is this project's cardinal failure in
  CI clothing. Documentation-only pushes skip the gate, and the
  workflow's `paths-ignore` mirrors that. Every branch red-tested in a
  dump-less clone, not assumed.

- **The tray resolves the port the same way the server does.** (LOTTO-0024)
  `supervise.py` reads `$PORT`, then `$LOTTO_PORT`, then 4322 — one knob
  whichever way the page is started, so a shell that exports `$PORT` moves
  a hand-started tray too. Only the behaviour on a *bad* value diverges,
  deliberately and with the reasoning stated at both sites: `serve.py` is
  machine-facing and exits, the tray is human-facing and falls back to
  4322 with a notification, because a tray that exits just vanishes. That
  is safe because a manager range-checks before it sets and launches
  `serve.py` directly, so the fallback can never mislead one.

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

### Changed

- **Catching up reads the message file once instead of once per message** (LOTTO-0007)
  543 messages took 543 full re-reads of the file (~114 MB) on every start;
  they now take one.

- **The SMS import now excludes prepaid-electricity messages** (LOTTO-0030)
  The widened `VAS00` clause turned out to catch more than lottery: VAS is
  the bank's value-added services platform, and prepaid electricity carries
  an identically formatted reference. Added `AND body NOT LIKE '%kWh%' AND
  body NOT LIKE '%Enter tokens%'` — two clauses, because the token
  continuation SMS carries no `kWh`. First re-pull over USB: 951 records
  (from 575), a strict superset, including 366 payout SMSes. `LOTTO-0001`
  §4.1 no longer claims "only lottery messages ever cross to the PC", which
  was never quite true and is now measurably not.

### Security

- ****A PyQt import into the server could pass the "no Qt" check** (LOTTO-0017)**
  INV-19 says `serve.py` and `supervise.py` pull in no Qt at all — that is what
  keeps the page servable with no desktop. Its check looked for the name
  `PySide`, or a top-level package spelled exactly `Qt`, and `PyQt6.QtCore` is
  neither: an import of it passed a check whose invariant reads "no Qt". PyQt6
  is installed on this machine (6.10.2), so the wrong binding was one habit away.
  The predicate now carries a third arm, `Qt|PyQt\d*` on the top-level package.
  Observed failing before it was fixed, as the project requires: the new
  `--break pyqt_import` appends a real `import PyQt6.QtCore` to `serve.py`, and
  the case reported PASS before the widening and FAIL after. Thirty-one breaks
  now, all red; 17/17 cases green.

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

- **The watcher no longer dies when the phone link is merely not ready yet** (LOTTO-0007)
  Starting the tray at login, before the phone has re-paired, used to kill
  the collector outright. It now waits and retries.

- **The new-ticket notice no longer points at a menu item you cannot click** (LOTTO-0007)
  With the server stopped it said to use “Refresh results now”, which the
  tray greys out in that very state. It now says “Start server”.

- **Two watchers appending at once can no longer lose a message or repeat a row** (LOTTO-0007)
  The read and the append are now one locked step. Measured without the
  lock: 105 of 120 row numbers collided.

- **A KDE Connect restart no longer silently stops new tickets being caught up** (LOTTO-0007)
  Killing the phone-link daemon used to leave the watcher alive but unable
  to ask the phone for anything, and nothing said so. It now notices, brings
  the daemon back itself, and re-runs the catch-up.

- **A ticket naming the rebranded game was silently never scored** (LOTTO-0031)
  `tickets.py::GAME_MAP` had no entry for the June-2026 rebrand names, so
  the first SMS to use one — a R200.00 ten-draw two-board `LOTTO 5 MAX`
  ticket bought 2026-08-08 — parsed to `None` and was dropped without a
  word. Three sibling tables (`PAYOUT_SLUG`, `POOL_NAMES`, the README game
  list) were updated at the rebrand; this one was missed because no message
  had used the new wording until now. Added `lotto 5 max` and `powerball
  xtra` as aliases, keeping the old names for the archive era. Coverage went
  from a red `PARSE GAP: 561 purchase SMSes, 560 parsed` to 561 tickets /
  1,238 entries / 0 with wrong draw coverage.

- **The SMS import filter matched game names, so it excluded every payout SMS** (LOTTO-0030)
  The documented adb import filtered `body LIKE '%lotto%' OR body LIKE
  '%powerball%'`, and a payout SMS ("The winnings of R<amount> for ticket
  ref: VAS00000000000 will be paid in your account…") names no game — note
  also that `lotto` is not a substring of `lottery`. Every other message
  shape happens to name one, so the filter looked complete. Added a third
  clause, `OR body LIKE '%VAS00%'`, to both copies of the command
  (`README.md`, `docs/specs/LOTTO-0001` §4.1), and `vas00` to
  `find_lotto_sms.py::KEYWORDS`, where one `matches()` drives both thread
  discovery and the within-thread filter. Measured against the phone: the
  old list matched 386 of 2,324 threads, the new one matches 560, and 149
  of the additions are payout SMSes — each carrying an amount and a VAS
  reference, 122 distinct refs, 2022-11-23 to 2026-01-14. Re-running the
  import needs the USB cable, so the dump on disk is unchanged for now.

- **A division the archive era paid and the current set cannot name is now reported, not dropped** (LOTTO-0023)
  `check()` gates every line against the division set of the pool's NEWEST
  draw, so a division retired at the June 2026 handover took all of its
  winners with it, before `amount()` could refuse — INV-22's omission form,
  one step earlier. `check.py::retired_divisions()` now compares each pool's
  archive-era division structure against the current set and reports any
  gap; `tools/verify_pools.py` sweeps it with three probes (INV-31).
  Per pool and one sampled payout page, not per line: every LOSING line
  reaches the same branch, so a per-line answer meant a page scrape per
  (pool, draw) scored — several hundred fetches to settle a structural
  question that six answer.
  Measured while building it: there is no retired division. All six live
  pools compare clean. The bare `2` bottom row on some Lotto archive pages
  is Division 8 spelled differently — both page shapes state "eight prize
  divisions" and carry exactly eight rows — and reading it as a distinct
  division would have reported a false gap on all three Lotto pools and
  flagged every match-2-without-bonus line in the archive era as a possible
  win, which is the cardinal failure inverted.

- **A failed opening build no longer leaves a live-looking counter under "Checking your tickets…"** (LOTTO-0019)
  A browser open since the bind never re-renders, so the poll's `stale` arm
  now blanks the progress span as well as showing the failure line. Without
  it the new counter would freeze mid-count under a notice that still reads
  as in flight — the cardinal rule arriving through the one element this
  change added.

- **The results API is retried instead of dying on its first refusal** (LOTTO-0012)
  `results.py::_post()` now makes up to three attempts with 1 s/2 s backoff
  and re-raises the ORIGINAL exception on exhaustion. Four of seven measured
  builds died on an SSL EOF, and one failure aborted the whole run — this is
  the single funnel every caller reaches the network through, so bounding it
  here fixes `check.py`, the page's build and the fetching verifiers at once.
  An `HTTPError` is never retried: the server answered, and a retry gets the
  same answer. `socket.timeout` is caught explicitly because it is only an
  alias of `TimeoutError` from Python 3.10 and this project pins 3.8+.
  Holds INV-27, checked by `tools/verify_page.py::post_retries_transport_failure`
  with breaks `no_retry` and `retry_http_error` observed red.

- **A feed-side division rename no longer scores every win in that division as a loss** (LOTTO-0026)
  `check.py::check()` decides a line won by joining `api_label()`'s string
  against the division table `paying_combinations()` read from the feed. A
  division this project cannot name is therefore a hole that scores exactly
  its own winners as losers while every other division goes on looking
  healthy — which is what happened on 2026-08-03, when the feed's
  `MATCH 5 + PowerBall` met a built `MATCH 5 + PB` and 53 wins read as
  losses (LOTTO-0027).
  `paying_combinations()` now subtracts the new `check.py::buildable_labels()`
  from the table it just built and raises on anything left over, aborting the
  run like the no-recent-draw raise beside it: a grammar that moved for one
  pool has almost certainly moved for its siblings, and a run that pressed on
  would report a partial win list indistinguishable from a complete one. The
  domain is bounded by `check.py::MAINS` and by which games `match()` can
  report a special hit for at all, and the rule is one-way — every division
  the feed publishes must be buildable, never the converse, since Daily Lotto
  publishes nothing for the `MATCH 0` and `MATCH 1` that `api_label()` still
  builds.
  `tools/verify_pools.py` gains three probes driving the raise (the `+ PB`
  state that shipped, the daily-domain bound, and the converse that a subset
  must not raise) and keeps its own transcription of the domain rather than
  importing the new function, so a domain widened by mistake still fails the
  sweep. Red-tested both ways: guard disabled → 2 probes `NO RAISE`, exit 1;
  direction reversed to set equality → `FALSE RAISE` plus six unreachable
  divisions across three live pools, exit 1. Scoring is unchanged on live
  data (R2,731.60 claimable, as before).
  Completes LOTTO-0026 step 2; INV-26's pending markers come off LOTTO-0001
  §4.4, §5, §6 and §11, and §7 records the red test.

- **Cold-eyes loop 7 on LOTTO-0001: 19 findings verified, 19 fixed, and the reach check no longer passes vacuously** (LOTTO-0026)
  All 19 distinct findings across the loop's two lanes were verified
  against current files and every one was true, so none was dropped. The
  CRITICAL, found by both lanes: INV-26 described `paying_combinations()`
  raising on an unreachable division in the present tense, when that is
  LOTTO-0026's own step 2 and is not built — so a reader would have closed
  step 2 believing the guard already shipped. The raise is now marked
  pending in §4.4, §5, §6 and §11 rather than step 2 being landed first,
  because three further findings were the contract holes step 2 must build
  against.
  Two fixes landed in `tools/verify_pools.py`. INV-26's division-label
  reach check had no anti-vacuity floor where INV-3 and INV-6 both carry
  one: its pool set is derived from the tickets an archive reaches, and
  every division in an *empty* division set is trivially reachable, so a
  feed returning no divisions at all would have printed `0 unreachable` and
  exited 0. It now fails on zero live pools and on any live pool with an
  empty division table, red-tested on both branches. The comment justifying
  the check's direction also carried a counter-example that cannot happen —
  `MATCH 6` for Daily Lotto, which the domain caps at five matches and
  therefore never builds.
  Prose fixes of substance: `division` is documented as coming from the
  win's own draw and always comes from the pool's newest API draw, so an
  archive-era win carries a current division name (69 of the 86 wins
  measured before LOTTO-0027 were archive-era); `amount()`'s archive
  plain-tier fallback was described as a bottom-tier repair when it applies
  to any match count on both games; §5's invariant-ownership map was wrong
  about four ranges and never named LOTTO-0014 at all; and §7 claimed
  `verify_coverage.py` resolves its inputs relative to its own file, where
  its tickets come from the working directory like every other script.

- **Every PowerBall win needing the PowerBall itself was scored as a loss.** (LOTTO-0027)
  `check.py::api_label()` built `MATCH 5 + PB`, and `MATCH 0 + PB` for a
  line matching only the PowerBall. The API publishes `MATCH 5 +
  POWERBALL`, and names the PowerBall-only division `MATCH POWERBALL` —
  no digit and no `+`. `check()`'s pay gate is `if api_label(...) not in
  pays: continue`, so those lines continued past as losses with no error
  anywhere and nothing on the page to tell them from a real miss: the
  project's cardinal rule broken by shipped code on the money path, one
  function earlier than the LOTTO-0007(a) hole it resembles. Found while
  reading the grammar off the live feed to write LOTTO-0026's spec
  amendment, rather than trusting the table LOTTO-0001 §4.4 already
  carried — which was itself wrong on both PowerBall rows and is now
  transcribed from the feed. On the current dump: **86 → 139 wins**,
  lifetime R2,650.60 → R3,213.30, claimable 62 lines / R2,417.90 → 92
  lines / R2,730.40. Nothing was repriced; 53 wins that were always
  there are now reported, and the archive branch needed no change
  because `site_label()` already built the payout table's own `0 +
  PowerBall` grammar. `tools/verify_pools.py` gained the case that
  catches it: every division the live feed publishes must be reachable
  by a label `api_label()` can build — directional on purpose, since the
  converse is false (`MATCH 6` for Daily Lotto, `MATCH 0` for a line
  that hit nothing). Red-tested against the shipped labels first: 12
  unreachable divisions across the two PowerBall pools, exit 1. This is
  the failure LOTTO-0026 was filed against, arriving before its guard
  did; that item keeps the runtime half, with its rule changed from
  grammar conformance to reachability — conformance would have sat quiet
  through this one, because only the PowerBall-qualified labels moved.

- **The lint rule set is stated in `ruff.toml` instead of inherited from whichever ruff is installed.** (LOTTO-0025)
  Found by the new CI on its first run, which is the whole point of it.
  `ruff` was unpinned, so the runner resolved 0.16.1 against 0.15.11
  locally, and 0.16 widened its default rule set to include SIM, EXE,
  RUF, FURB, DTZ, PLW, B, PIE and I. Identical bytes, 71 errors there,
  zero here — one shared script guarantees one list of checks, not one
  set of tools. `ruff.toml` now states the selection every module here
  was written against (`E4`, `E7`, `E9`, `F`, ruff's pre-0.16 default),
  verified clean under both 0.15.11 and 0.16.1, so a linter release can
  no longer change the verdict. The gate header prints the ruff and
  Python versions so the next divergence is visible rather than latent.
  The 71 findings were not adopted: they are style opinions on working
  code and deserve their own diff, not arrival as a side effect of
  `pip install`.

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
