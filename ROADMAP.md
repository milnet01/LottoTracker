# ROADMAP — LottoTracker

Status keys: 📋 planned · 🚧 in progress · ✅ shipped · 💭 considered

## Core

- ✅ **LOTTO-0001** Parse Standard Bank ticket SMSes and score them against real draws.
  Kind: implement. Source: user-request-2026-08-01.
  Layman: the PC reads your lottery texts and tells you whether any won.
  Spec: `docs/specs/LOTTO-0001-lottery-ticket-tracker.md`.
  Covers both SMS eras, both results sources, Multiplay expansion and prize
  pricing. 558 tickets parsed, 121 checkable (426 predate all draw data, 11
  are in a pool no source publishes); R700.10 found still claimable.
  Superseded 2026-08-01 by LOTTO-0009, which counts in entries rather than
  tickets: 1,233 entries, 259 checkable, R2,423.00 still claimable. Its §4.2,
  §4.4 and INV-6 are amended accordingly.

- ✅ **LOTTO-0002** Local web page showing tickets, results and claimable winnings.
  Kind: implement. Source: user-request-2026-08-01.
  Layman: a page in your browser instead of a wall of terminal text.
  Spec: `docs/specs/LOTTO-0002-local-web-page.md`. Unblocked 2026-08-01 —
  LOTTO-0009 shipped, so the page will render 1,233 entries rather than 558.
  Chosen by the user over a desktop app or CLI. Should show live tickets with
  draws remaining, wins with their expiry dates, and a claimable total.
  A local server bound to 127.0.0.1, driven by a PySide6 tray icon that starts
  and stops it and re-opens the page — pattern copied from the user's existing
  `Ants_Projects_Hub_Website/serve.mjs` + `tray/ants-stats-tray.py`, which is
  reused as a shape, not as code (that repo is public and deploys to Pages).
  Decisions taken with the user 2026-08-01, not to be re-litigated:
  - Long-running local server, not a statically generated file.
  - The tray icon is **required**, not optional — it is how the server is
    started, stopped and the page re-opened. PySide6 (already installed, and
    what the user's stats tray uses). `serve.py` must not import PySide6, so
    the server still runs headless under systemd.
  - No database. Tickets are re-parsed from `lotto_sms_raw.txt` each run;
    results stay in the existing `archive_results.json` / `archive_cache/`.
    `sqlite3` only if prizes ever need marking as claimed — a separate item.
  - Spend is compared against winnings over the **checkable** entries only;
    total lifetime spend is shown separately and labelled.
  Security constraints for the spec (researched 2026-08-01):
  - Bind `127.0.0.1` and validate the `Host` header against an exact allowlist
    (`127.0.0.1:PORT`, `localhost:PORT`), rejecting anything else with 421.
    A localhost bind stops the network, not the user's own browser being aimed
    at the port by a hostile page — CVE-2026-46611 (Glances) is this exact
    pattern. `Origin` is not a substitute: a top-level navigation carries none.
  - Subclass `BaseHTTPRequestHandler` and render HTML in memory; serving files
    via `SimpleHTTPRequestHandler` reintroduces the whole path-traversal class.
  - `ThreadingHTTPServer` (browsers pre-open sockets and hang a single-threaded
    server). `Cache-Control: no-store`. Generic `<title>`, no ticket data in
    the URL — browsers send URLs and titles to sync and search suggestions.
  - Never pass request-derived data to `send_header()` (no CRLF validation).
  Spec written and gated 2026-08-02: 3 cold-eyes loops, 2 lanes each, 83 findings
  verified and fixed, 0 deferred. Holds INV-12 to INV-21. Three further
  decisions taken with the user that day: the tray spawns `serve.py` as a child
  rather than driving a systemd unit (no install step); the start-at-login
  toggle lives in a settings panel **on the page**, which is what gives the
  server its one write endpoint and therefore its token; and settings render as
  sliding switches over a real checkbox.
  Two design holes the review closed, both of which an implementer would have
  patched by weakening security: the tray's Refresh button is a `POST /refresh`
  and had no way to obtain the token (now `LOTTO_TOKEN` in the child's
  environment), and there was no anti-framing header, so a hostile page could
  iframe the port — the `Host` allowlist passes, the framed page holds the
  token, and the user clicks the autostart switch through an overlay.
  Converged by cap, not clean — two of the three loops produced more defects
  from their own fixes than from the draft, which is the size signal, and §12
  recommended a split before implementation.
  **Split twice on 2026-08-02, on the user's decision.** The first cut took the
  tray and supervisor out to LOTTO-0013 along the seam §12 named, and moved only
  66 of 1,161 lines — the tray was never the weight. The second cut took the
  HTTP surface and security boundary out to LOTTO-0014, along a seam of
  *subject* rather than invariant count: web-security rules on one side, the
  lottery-data honesty rules on the other, which need different expertise to
  review. The three pre-split cold-eyes loops were archived to
  `docs/specs/LOTTO-0002-pre-split-review-log.md`; they confer no review credit
  on any part, and each part re-enters the gate at loop 1 on its own bytes.
  This item now holds **INV-15 to INV-18** and 875 lines: the model, the build
  lifecycle, what the page shows, spend against winnings, and the settings
  panel. Sections were deliberately not renumbered — §4.3 and §4.4 remain as
  pointers, because LOTTO-0011 and sibling specs cite §4.5 and §4.7 by number.
  Resolved (2026-08-02): shipped. `serve.py`, `page.py`, `supervise.py`,
  `tray.py`, `icons/` and `tools/verify_page.py`. Every one of the ten cases was
  observed FAILING against a deliberate break before its invariant was accepted
  — thirteen breaks, all red — and one of them found a defect in a *case* rather
  than in the code: an em-dash for an unscorable amount did not turn INV-15 red,
  because the assertion compared raw markup and excluded the empty string from
  its own forbidden set. Both are renderings the cardinal rule forbids.
  End to end against the real dump, reproducing the specs' figures
  independently: 974 of 1,233 entries uncheckable, R10,603.50 spent on checkable
  entries against R2,651.60 won, R28,244.50 lifetime, 62 claimable lines.
  Two contract gaps surfaced by building rather than by reading: `tray.py` needs
  to read `open_on_start` but may not import `serve.py`, so the settings reader
  moved to `supervise.py`; and `make_server()` does not build, which two cases
  had assumed. All five checks green.
  Folded back (2026-08-02): both gaps are now in the contracts rather than only
  in commit messages — §4.2 and §7 here, §4.1 in LOTTO-0013 — each with a §13
  row marked as originating in implementation. Re-gated with two further
  cold-eyes loops per spec: 65 verified findings fixed, 2 dismissed, 0 deferred.
  Loop 1's CRITICAL was the amendment's own collateral, and both LOTTO-0002
  lanes found it independently: §4.1 still denied the `serve.py → supervise.py`
  import the settings move had just created, which would have told the next
  implementer to rebuild the duplicate reader. Loop 2 found that §4.6's worked
  snippet — the only runnable statement of the compared-spend figure — omitted
  `t.resolved`, the clause INV-16 exists to protect; it reproduces the same
  R10,603.50 today only because no ticket is unresolved.
  **A real code defect came out of writing the amendment, not out of review:**
  `serve.py` imported `read_settings()` from `supervise` and redefined it twenty
  lines below, so the shipped file held the two readers the amendment claimed it
  had collapsed into one. Identical bodies, all five checks green over it —
  which is the shape of the failure, not a mitigation. Deleted; LOTTO-0013 §11
  now records that nothing mechanical catches it, and CLAUDE.md's architecture
  diagram carries the edge so a future session does not recreate it.
  Gate stopped at two re-gate loops by user decision rather than at the 3-loop
  cap: CRITICALs 1 → 0, nothing verified outstanding. One code gap found in
  passing is filed as LOTTO-0017.

- ✅ **LOTTO-0014** The local page's HTTP surface and security boundary.
  Kind: security. Source: split from LOTTO-0002 on 2026-08-02 (second cut).
  Layman: the rules that stop a website you happen to be visiting from reading
  your lottery tickets off the page running on your own machine.
  Spec: `docs/specs/LOTTO-0014-http-surface-and-security.md`. Holds INV-12,
  INV-13, INV-14 and INV-21.
  Four routes and nothing else; an exact `Host` allowlist answering 421
  otherwise (CVE-2026-46611, Glances, is this design without that check, and it
  was exploited by DNS rebinding); a per-run token in an `X-Lotto-Token` header
  on both write routes, with `Origin` checked in addition and never instead;
  `X-Frame-Options: DENY` plus `frame-ancestors 'none'`, without which the token
  guards a forged request but not a real one clicked through an invisible
  overlay; no `Access-Control-Allow-*` header ever; and nothing request-derived
  reaching a response header or a written file.
  Ships with LOTTO-0002 and LOTTO-0013 in one change; the three share
  `tools/verify_page.py`.

- ✅ **LOTTO-0013** Tray icon and server supervisor for the local page.
  Kind: implement. Source: split from LOTTO-0002 on 2026-08-02 (first cut, per
  that spec's §12).
  Layman: the icon next to the clock that starts the page, opens it, refreshes
  it and shuts it down again — and the guarantee that nothing is left running
  behind it.
  Spec: `docs/specs/LOTTO-0013-tray-and-supervisor.md`. Holds INV-19 and INV-20.
  `supervise.py` is Qt-free and owns the token, the port and the child process,
  which is what makes the spawn-and-reap lifecycle checkable from a headless
  exit-code script instead of needing a `QApplication` and a display. `tray.py`
  is PySide6 and nothing else. The token reaches the tray through the child's
  environment — not argv, which `ps` exposes — closing the gap that would
  otherwise be resolved by exempting `POST /refresh` from the token check.
  Two Qt details carried from the user's existing stats tray that the parent
  spec named the prior art for but never wrote down: a module-level set keeping
  each `QRunnable`'s Python wrapper alive while `QThreadPool` owns the C++ side,
  and `setQuitOnLastWindowClosed(False)` so dismissing a notification does not
  end the application and take the server with it.

- ✅ **LOTTO-0009** Score every pool a ticket was entered in, not just the top tier.
  Kind: fix. Source: in-session-2026-08-01 (found while sizing LOTTO-0008).
  Layman: you paid for three lottery draws and we were only checking one of them.
  Spec: `docs/specs/LOTTO-0009-entered-pools.md` (umbrella, covers LOTTO-0008).
  Blocks LOTTO-0002 — the page would otherwise display known-low totals.
  PLUS games cannot be bought alone: the operator's rules require the base game
  and run a separate draw with its own prize pool for each tier
  (LOTTO/PLUS 1/PLUS 2 Rules 21Sep25 §1.5, §1.16, §1.17). `tickets.py::GAME_MAP`
  maps an SMS to one pool, so a `Lotto Plus 2` ticket is scored against
  `lotto/2` alone and its `lotto/0` and `lotto/1` entries are never checked.
  449 of 558 tickets are entered in more than one pool (444 name a PLUS tier,
  5 more are priced as one); before this fix 558 of 1,233 paid entries were
  scored (45%).
  The printed game name is unreliable — the suffix is sometimes omitted, and
  Standard Bank dropped it entirely after the 2026-06-01 handover — so the
  entered tiers are derived from the ticket price, which resolves 558/558
  exactly once the handover price change is applied. Name is a cross-check.
  Also rescues the 11 `Daily Lotto Plus` tickets now reported as uncheckable:
  no source carries `daily/1`, but their base `daily/0` entry is checkable.
  Cold-eyes 2026-08-01: 3 loops, 2 lanes each, 51 findings verified and fixed,
  0 deferred; spec accepted. Converged by cap — collateral outnumbered draft
  defects for two loops running, so §4 is a split candidate before any further
  editing.
  Resolved (2026-08-01): implemented. The entered tiers come from the ticket
  price in whole cents — 1,233 of 1,233 entries derived, 0 unresolved, and the
  5 tickets whose printed name disagrees with their price are reported rather
  than silently reinterpreted. `scorable()`, `covered()` and `amount()` take
  the entry's pool; the uncheckable report moved out of `__main__` into
  `check.py::uncheckable_report()`, counts entries, and splits tickets into
  wholly and partly uncheckable so the 11 Daily Lotto Plus tickets are scored
  on `daily/0` instead of written off. New `tools/verify_pools.py` (INV-7,
  INV-11) recomputes the price table independently; `tools/verify_coverage.py`
  re-based on entries. All five invariants red-tested per spec §7.
  **30 new winning lines worth R1,790.40, of which R1,722.90 is still
  claimable** — claimable total R700.10 → R2,423.00. No previously reported
  win changed pool or disappeared.
  Cold-eyes after implementation: 2 further loops (5 total), 29 verified
  findings fixed, 0 deferred. Loop 4 found a real implementation gap both
  lanes agreed on — the spec cited `verify_pools.py --era-audit` and the flag
  did not exist, so the era guard was fixed rather than the claim deleted.
  Loop 5 converged and stopped on the collateral trigger: 6 of its 9 findings
  were loop 4's own fixes. §4 remains the split candidate before any further
  editing. LOTTO-0001 was retrofitted in the same pass (its own loop 4, 17
  findings) — its unit is now the entry.

- 📋 **LOTTO-0010** Read the payout SMSes and reconcile them against computed wins.
  Kind: implement. Source: user-correction-2026-08-02.
  Layman: the bank already told you what it paid you — check our maths against it.
  The dump holds 575 messages: 558 ticket purchases and 17 others.
  `tickets.py::parse()` returns `None` for all 17, so they are read and
  discarded on every run. **14 of them carry a `Ref:VAS…` that matches a ticket
  we already parse**, which is the join — the same reference `Ticket.ref`
  already holds, so no new parsing key is needed. The remaining 3 are a
  different message shape and are not payouts.
  They are the only *external* ground truth this project has; every existing
  check verifies the code against itself or against the two results sources.
  **Measured 2026-08-02, and the result is not what it looks like:** all 14 paid
  tickets are from 2023, which predates the earliest draw data (2025-01-01), so
  every one is `scorable() == False` and we compute no win for any of them.
  Overlap with the 46 tickets we *do* report wins for is exactly zero.
  That makes this item worth doing for a different reason than expected:
  - **Today it validates the uncheckable logic, not the scoring.** The bank paid
    out on 14 tickets this project deliberately refuses to score. Had they been
    scored against the wrong draws — the bug this project was built after
    hitting — 14 real wins would have been reported as R0.00. That is external
    confirmation of INV-6 and of `history.py::scorable()`, and it is the only
    such confirmation available.
  - **It becomes a scoring check the moment LOTTO-0006 lands.** Backfill results
    to 2023 and these 14 stop being unscorable, at which point they are 14
    known-correct answers to test the whole engine against — ticket in, amount
    out, compared to what the bank actually paid.
  Build it as `tools/verify_payouts.py` beside the other four, exit-code style.
  Feeds LOTTO-0011; upgrades LOTTO-0006 from low-value to test-bearing.

- 📋 **LOTTO-0011** Stop saying "still claimable" — the bank pays automatically.
  Kind: fix. Source: user-correction-2026-08-02.
  Layman: the wording implies you have to go and collect money that is already
  in your account.
  `check.py` prints `STILL CLAIMABLE:` and computes `expired` from
  `CLAIM_DAYS = 365`; README.md and `docs/specs/LOTTO-0002-local-web-page.md`
  §4.5 carry the same framing, and LOTTO-0002's whole first page section is
  called "Claimable now". The user is paid the winnings directly, so the figure
  is money **already received**, not money outstanding — the current wording
  invites a trip to a lottery office for a prize that was banked months ago.
  Two things to settle before rewording, neither of which should be guessed:
  (a) whether a threshold exists above which a South African prize must still be
  claimed in person, in which case expiry stays meaningful for that band only;
  (b) what the 365-day expiry then means for the rest — likely informational,
  not actionable. LOTTO-0010's payout messages are the evidence for both.
  Do not simply delete the expiry logic: an unpaid large prize is exactly the
  case where a deadline would matter, and that is the case this project exists
  to catch.

- 📋 **LOTTO-0003** Pick up new tickets automatically as the SMS arrives.
  Kind: implement. Source: user-request-2026-08-01.
  Layman: new tickets appear by themselves, without plugging the phone in.
  KDE Connect emits `conversationCreated` / `conversationUpdated` over D-Bus;
  subscribe rather than polling.

- ✅ **LOTTO-0008** Record what each ticket cost, so prizes can be compared against spend.
  Kind: implement. Source: user-request-2026-08-01.
  Layman: show what you paid for a ticket next to what it won.
  Spec: `docs/specs/LOTTO-0009-entered-pools.md` (umbrella, covers this id).
  Every ticket SMS carries `Played R<amount>`; `tickets.py::parse()` matches it
  and discards it. Capturing it into `Ticket` is the whole change.
  Specified with LOTTO-0009 rather than alone: the price is also the signal for
  which pools a ticket was entered in, so one contract governs both readings.
  Feeds LOTTO-0002's spend-vs-prize display. The comparison must be drawn only
  over checkable entries: cost is known for all 1,233, winnings only where
  results exist, so a lifetime total would convert 974 unknowns into losses.
  Resolved (2026-08-01): shipped inside LOTTO-0009. `Ticket.cost` is the total
  rands the SMS charged for the whole ticket — every board, draw and tier
  (INV-10) — and the same price is what derives the entered pools. The display
  itself is LOTTO-0002; the checkable-entries-only rule is spec §4.7.

- 📋 **LOTTO-0015** Ship a Linux AppImage and a Windows executable, both build-tested locally first.
  Kind: package. Source: user-request-2026-08-02.
  Layman: One file you can double-click, instead of needing Python and PySide6 installed.
  Verified 2026-08-02: the project has no packaging manifest and no `.github/`
  at all, so this item adds the first of both.
  **Two entry points are platform-bound and one of them cannot cross.**
  `tray.py` needs PySide6, which bundles fine on both targets;
  `find_lotto_sms.py` needs `dbus-python` and KDE Connect, which is Linux-only.
  So a Windows build ships the page and the scoring but not the way tickets get
  in, and the decision to take before building is where its `lotto_sms_raw.txt`
  comes from. Whatever the answer, the absent fetcher must be *named* in the UI
  — an SMS import that silently does nothing renders an empty page, which is
  this project's cardinal failure ("no data" reading as "did not win") arriving
  through the packaging.
  **The local scripts must RUN the artifact, not just build it.** A bundler
  resolving imports proves nothing about the files this project opens at run
  time: `icons/`, `archive_results.json`, `archive_cache/` and the dump are all
  resolved relative to the process, and LOTTO-0013 §4.2 already had to fix that
  class once with `cwd=HERE` for the autostarted tray. A frozen build relocates
  every one of those paths, so the check is: build, run the artifact from a
  directory that is not the repository, and confirm the page renders real
  figures rather than the empty state.
  Publishing from CI would add the first workflow to a repo that has none. The
  repo is public, so runner minutes are free, but say so when it lands — the
  project's push cadence currently assumes no workflows exist.

- 📋 **LOTTO-0016** Run the CI locally before pushing, from the same script CI runs.
  Kind: chore. Source: user-request-2026-08-02.
  Layman: Catch the breakage on your own machine instead of finding it on GitHub.
  Pairs with LOTTO-0015, which adds the first workflow this repo has ever had.
  **"Exactly replicates" is only achievable one way, and it is not by writing
  the steps twice.** Two files listing the same commands drift on the first
  edit, and the drift is invisible until CI fails on something the local run
  passed. So the steps live in ONE script — `tools/ci.sh` — which the workflow
  invokes as its single build step and which a developer runs by hand. Then
  "replicates" is structural rather than maintained.
  **Where the parity genuinely stops, and it must be said rather than implied:**
  the runner's OS and image are not reproducible locally. `tools/ci.sh` on this
  openSUSE box is not `ubuntu-24.04`, and nothing local reaches a Windows runner
  at all — so LOTTO-0015's Windows executable has its first real build in CI no
  matter what this item does. `podman run --rm ubuntu:24.04` closes the Linux
  half of that gap and is worth doing; the Windows half stays open, and the
  script should print that it is open rather than exiting 0 and reading as full
  coverage.
  The five `tools/verify_*.py` are the natural core of the run, but note that
  three of them need `lotto_sms_raw.txt` and `archive_results.json`, which are
  gitignored real data — so CI can run a subset the local script cannot, and
  vice versa. Decide that split explicitly; a check skipped for missing data
  must say so, not pass quietly.

- ✅ **LOTTO-0018** The tray says "Results refreshed." before the refresh has happened, and even when it fails.
  Kind: fix. Source: in-session-2026-08-02.
  Layman: The icon tells you it is done about a second in, while it is still working — and it says the same thing when the update actually failed.
  Verified 2026-08-02 by reading the path end to end.
  `serve.py::refresh()` starts a daemon thread and returns `True` at once, so
  `POST /refresh` answers **202 = accepted**, not *finished*. `tray.py::refresh()`
  treats the 202 as success and calls `note("Results refreshed.")` — roughly a
  second in, while the 27 requests behind it still have thirty-odd seconds to
  run. If that build then raises (four of seven attempts failed when LOTTO-0002
  was measured — see LOTTO-0012), the user has already been told it succeeded and
  is never told otherwise.
  **This is the cardinal rule in notification form**: a failure reported as a
  success is worse than a blank, because it actively stops the user looking.
  The page half is already honest — it polls `GET /status` and shows the stale
  notice on failure (INV-18) — so the defect is that the tray does not use the
  same signal it already has. Fix shape: after a 202, poll `/status` the way the
  page does and notify on the *transition*, reporting failure as failure.
  Pairs with LOTTO-0019, which is what the notification should say once it fires
  at the right time; do this one first, since a well-worded lie is still a lie.
  Resolved 2026-08-02. The wait lives in `supervise.Supervisor.refresh()`,
  which is Qt-free so `tools/verify_page.py` can drive it headlessly: POST,
  then poll `GET /status` every 2 s — the page's own cadence — until
  `building` clears, then report one of four outcomes. Only *done* reads as
  success. *Failed*, *still running* (the 300 s budget expired) and *already
  running* (the 409, which used to reach the user as `Refresh failed: HTTP
  Error 409: Conflict`) each name what is **not** known instead. The four
  sentences live in `supervise.REFRESH_MESSAGE` rather than in `tray.py`,
  following the precedent `port_fallback` set, and that is what lets a
  headless case assert that only one of them reads as success.
  Contract is LOTTO-0013 §4.6 and INV-23, written **before** implementation
  and gated over three cold-eyes loops (§13 loops 6, 7 and 8): 43 verified
  findings fixed, 0 deferred, no CRITICAL after the first loop, converged at
  the cap with nothing outstanding. Two of those loops caught this project's
  cardinal rule inside the fix for it — `REFRESH_FAILED` first promised "the
  previous results" on the path where a first build failed and there is no
  previous model, and §4.3's new composes-no-message rule would have silenced
  the raise path entirely.
  Checked by `tools/verify_page.py::refresh_reports_the_build`, with three
  breaks observed red: `notify_on_202` (the shipped defect itself),
  `stale_is_success` (a patient lie is still a lie) and `success_wording`.
  This unblocks LOTTO-0019.

- 📋 **LOTTO-0019** Tell the user they won, instead of waiting for them to come and look.
  Kind: feature. Source: in-session-2026-08-02.
  Layman: The icon pops up "2 new winning lines, R240" — the whole point of the app, delivered without you opening anything.
  The project exists to surface a win before it is discovered by accident, and
  today it still waits to be asked: the tray's only notification is the generic
  `note("Results refreshed.")` in `tray.py::refresh()`, and finding out what
  changed means opening the page and reading it.
  `POST /refresh` currently answers with an **empty body** (`self._send(202)`),
  so the tray has nothing to report even if it wanted to. Two ways to close
  that, and the choice is a real one:
    (a) the refresh response — or a new field on `GET /status` — carries a small
        summary of the completed build (new winning lines, their total);
    (b) the tray diffs nothing and simply links to the page.
  (a) is the feature; (b) is not worth building.
  **Two constraints, both already established, and both easy to breach here.**
  A desktop notification is *outside* the security boundary that LOTTO-0014
  draws around the page, so it must carry no ticket reference and no line
  numbers — a count and a total only; the same reasoning that keeps ticket data
  out of the URL (INV-21) applies to a notification body, which the desktop may
  log and sync. And "no new wins" must never render the same as "the build
  failed" or "nothing could be checked" — LOTTO-0018 owns the timing half of
  that, and this item must not undo it by summarising a build that did not
  finish.
  Blocked in practice on LOTTO-0018: a summary that arrives at the wrong moment
  is a more convincing wrong answer than the generic string it replaces.

- 📋 **LOTTO-0020** Show what the first build is actually doing instead of "building" for half a minute.
  Kind: enhancement. Source: in-session-2026-08-02.
  Layman: A page that says "checking draw 9 of 27" instead of sitting there looking broken for thirty seconds.
  `serve.py` binds before it builds (LOTTO-0002 §4.2), so the first page answers
  immediately and then says *building* for the thirty-odd seconds the 27
  requests take. `GET /status` returns `{building, built, stale}` — enough to
  know that work is happening, nothing about how much is left — and the page's
  poll runs every 2 s with nothing new to show each time. A progress figure is
  the difference between a page that looks busy and one that looks broken,
  and this is the first thing a new user sees.
  The count already exists in the design: LOTTO-0002 §4.2 measures the build at
  **27 requests** and INV-17 counts them, so the denominator is known and
  asserted rather than guessed. `results.py::_post()` is the single funnel every
  API request passes through (which is also why LOTTO-0012 fixes retries there
  once for every caller), so a counter belongs in it, read out on `/status`.
  `backfill.py` caches to `archive_cache/` on disk and mostly makes no requests
  at all, so the figure is honest only if it counts what is actually fetched.
  **The denominator moves and must not be presented as fixed**: 27 is a dated
  measurement against today's dump, and LOTTO-0006 would change it. Show
  "fetched N" over a total only where the total is known for *this* build, and
  never let a stalled counter read as completion — the same rule that stops a
  blank cell reading as R0.00.
  Small, self-contained, and touches no scoring. Worth doing alongside
  LOTTO-0012, whose retries make the wait longer and therefore worth narrating.

- 📋 **LOTTO-0021** Extend the page's filter beyond game, reusing the pattern already there.
  Kind: enhancement. Source: in-session-2026-08-02.
  Layman: Narrow 1,233 rows down to the year, or to just the ones that could be checked — not only by which game.
  **Not a new feature — an extension, and the existing one sets the pattern.**
  `page.py` already ships a client-side `#gamefilter` that shows and hides
  `#entries tbody tr` by `data-game`, and its comment already records the rule
  that makes it safe: *"It must not add a query parameter, a fragment or a
  history entry: all three put ticket data where the browser syncs it
  (INV-21)."* Any new filter obeys the same rule or it breaks a shipped
  security invariant.
  Worth adding, in rough order of use: by **year**, since 1,233 entries span
  2022 to now and the interesting ones are recent; and by **checkable state**,
  which is the split the whole project is built around.
  **The second one carries the trap.** A filter that hides uncheckable entries
  makes the page assert a smaller, tidier reality — 259 checkable entries of
  1,233 — and a user who forgets a filter is active reads the remainder as the
  whole truth. That is the cardinal rule arriving through the UI rather than
  through the data: filtering must never make "not checkable" *disappear*
  silently. Whatever is hidden gets a visible, persistent count of what the
  filter is holding back, and the default state stays unfiltered.
  Free-text search over ticket references is deliberately **excluded**: a
  reference identifies a real ticket, and putting one in a search box invites it
  into the places INV-21 exists to keep it out of.

- ✅ [LOTTO-0024] **The server takes its port from $PORT, and the tray runs without an icon under a process manager.**
  Two knobs, both read at startup, and one live bug fixed on the way.

  `serve.py::resolve_port()` — `$PORT`, then `$LOTTO_PORT`, then 4322.
  `$PORT` is the name a process manager already sets, so it wins; the
  `$LOTTO_PORT` path is what it was. A value that is *set* and cannot be
  a port (non-empty, and either non-numeric or outside 1024-65535) now exits non-zero naming
  the variable and the value, for BOTH variables — the bug being that
  `LOTTO_PORT=abc python3 serve.py` died with an unhandled `ValueError`
  traceback. Never a silent fallback: a manager that asked for port 80
  and got 4322 has been told nothing (LOTTO-0002 INV-24, §6).

  `supervise.py` resolves the same two variables in the same order (one
  Cold-eyes (2026-08-03): three loops on each of LOTTO-0002 and
  LOTTO-0013, converged at the 3-loop cap. 56 verified findings fixed
  across both, 1 dismissed on evidence, 1 deferred. CRITICAL 1 -> 1 -> 0
  and HIGH 4 -> 3 -> 2 on LOTTO-0002; the same shape on LOTTO-0013. Loop 2
  found the two halves failing to compose — a managed tray ignored $PORT —
  which the user resolved by having the tray share the server's
  precedence. Deferred tail: tray.py's module docstring says "Four details
  are copied from the user's existing stats tray" where LOTTO-0013 §4.3
  lists six and §11 says "four of the six"; pre-existing, code-side, one
  word, and not this run's to edit under a docs gate.
knob whichever way the page is started) and diverges only on a BAD
value, where it falls back to 4322 with a notification rather than
exiting — a tray that exits just vanishes, and that is safe because a
manager range-checks before it sets and launches serve.py directly. It
pins both variables in the child, both
  to the port it already chose. Without that, a session exporting its own
  `$PORT` would send the child somewhere the tray is not watching — the
  421-on-every-request failure LOTTO-0013 §4.5 exists to prevent.

  `tray.py::managed()` — `LWSM_MANAGED=1` runs it with no tray icon,
  logging to stdout and waiting on the child. Anything else is the
  unchanged path, icon included. No headless path calls `stop()`: the
  menu it skips contains "Quit (stops the server)", and a manager that
  started the process owns the tree. The variable is a presentation hint
  with no security value — unauthenticated, forgeable, inherited, and
  readable from a process's environ — so nothing else hangs off it
  (LOTTO-0013 §4.7, INV-25).

  Two cases added to `tools/verify_page.py`, `port_from_environment` and
  `tray_headless_when_managed`, with four breaks; all thirteen cases and
  the other four verifiers green.
  **Layman:** An external manager can now put the page on whatever port it likes, and start it without an icon appearing next to the clock.
  Kind: feature.
  Source: user-request-2026-08-03.

## Hardening

- 📋 **LOTTO-0004** Automated guard that no SMS content can be committed.
  Kind: security. Source: in-session-2026-08-01.
  Layman: make it impossible to accidentally publish your messages.
  `tools/verify_privacy.py` now does the checking, but someone must remember
  to run it. A pre-commit hook would make it structural.
  **A second, separate gap found 2026-08-02, and the hook does not close it.**
  `verify_privacy.py` compares tracked files against the dump's *text*, so it
  catches content that was copied. It cannot catch content that merely
  *identifies*: LOTTO-0002's spec drafts twice stated facts that pin a single
  real ticket while quoting nothing from it — a purchase week plus draw count
  over a two-ticket population, and one win's exact amount with a derivable
  draw date. Both passed the checker cleanly; both were caught by a human-style
  read in review.
  So the hook is worth building and must not be mistaken for completeness. Note
  it in the README as "catches copied content, not inferred identity", and keep
  the reviewer's eye on aggregates in any prose that quotes figures.

- 📋 **LOTTO-0012** Retry the results API instead of dying on its first refusal.
  Kind: fix. Source: in-session-2026-08-02.
  Layman: the lottery website drops connections a lot; try again instead of
  giving up.
  `results.py::_post()` calls `urlopen` once with no retry. Measured while
  writing LOTTO-0002's spec: **four of seven** build attempts failed with
  `URLError(SSL: UNEXPECTED_EOF_WHILE_READING)`, and each failure aborts the
  whole run — `check.py`, `tools/verify_*.py` and (once it exists) the page's
  refresh alike, since all of them reach the API through this one function.
  A bounded retry with backoff in `_post()` fixes every caller at once, which is
  the reason to put it there rather than in each script.
  Bound it: 3 attempts, exponential backoff, and re-raise the original error on
  exhaustion. Never a bare `except: pass` — a silently empty result set is the
  "no data reads as no win" failure this project exists to prevent, arriving
  through the network layer.
  LOTTO-0002 §6 and INV-18 already specify the page's behaviour when this fails,
  so that item does not block on this one; this reduces how often it happens.

- 💭 **LOTTO-0005** Support other banks' ticket SMS formats.
  Kind: feature. Source: user-request-2026-08-01.
  Layman: let people at other banks use this too.
  Only `tickets.py::parse()` is bank-specific. Needs a sample message per
  bank; see the "Adding your bank" section of README.md.

- 📋 **LOTTO-0007** Close the cold-eyes deferred tail.
  Kind: review-fix. Source: cold-eyes-2026-08-01 loop 3.
  Layman: a short list of known rough edges, written down so they are not
  rediscovered by another expensive review.
  Verified but unfixed at the loop cap; each has a §11 row in
  `docs/specs/LOTTO-0001-lottery-ticket-tracker.md`:
  (a) ✅ **fixed 2026-08-02.** An unscrapable payout page priced every
  archive-era win at R0.00 instead of raising, unlike `paying_combinations()`
  which does raise — the project's cardinal rule violated by shipped code on a
  money path, and by then visible on the page as well as in the terminal.
  `check.py::amount()` runs only after a combination matched a paying
  division, so it has no "did not win" answer to give: both its branches now
  raise when the price cannot be looked up, while a division the source states
  as R0.00 still returns 0.0. Holds **INV-22** (LOTTO-0001 §5), checked by four
  blind-lookup probes in `tools/verify_pools.py` and red-tested by reverting
  the archive branch (2 mispriced, exit 1). Measured before the change: 86
  wins, 69 archive-era, 0 at R0.00, all 67 archive draws parsing — so the
  figures are unchanged (R2,651.60, 62 claimable lines) and this closed a
  latent hole rather than repricing anything. What remains unchecked is
  narrower: a page that parses into a *wrong* table;
  (b) `backfill.py::parse_page()` raises `KeyError` on an abbreviated month
  in a href rather than skipping the row;
  (c) INV-5's grep sees only a double-quoted `"MATCH <digit>` literal — it
  cannot see the label grammar in `api_label()`/`site_label()`, so a
  feed-side rename of `MATCH n` would drop every win silently;
  (d) Multiplay expansion is Lotto-only; a >6-number PowerBall or Daily
  board would silently collapse to one line (no such ticket exists today);
  (e) §8's "~30 lookups a month" is not recomputed from §10's request model.

- 📋 **LOTTO-0006** Backfill results earlier than 2025-01-01.
  Kind: enhancement. Source: in-session-2026-08-01; re-valued 2026-08-02.
  Layman: check really old tickets too — and it would prove the maths is right.
  The 2025-01-01 floor is a configured default in
  `backfill.build(years=(2025, 2026))`, not a limit of the archive itself.
  **Promoted from 💭 to 📋 on 2026-08-02.** Both reasons it was parked have gone:
  it was "low value" because prizes expire after 365 days and could no longer be
  claimed, but the bank pays winnings out automatically (LOTTO-0011), so an old
  win is money already received rather than money forfeited — and reporting it
  correctly still matters.
  The stronger reason is that it now comes with a **test oracle**. LOTTO-0010
  found 14 payout messages, all for 2023 tickets, all currently unscorable.
  Backfilling to 2023 converts them into 14 tickets whose correct answer is
  already known from the bank's own record — the only end-to-end check of
  parsing, pool derivation, matching and pricing this project can have.
  Do LOTTO-0010 first: without the reconciliation script the oracle is unread.

- 📋 **LOTTO-0017** INV-19 says "no Qt" but cannot see a PyQt import.
  Kind: fix. Source: cold-eyes-2026-08-02 (LOTTO-0013 re-gate, loop 4).
  Layman: A safety check has a blind spot: it would miss one of the two ways of importing the graphics library.
  `tools/verify_page.py::serve_is_headless` collects the child interpreter's
  `sys.modules` and flags a name containing `PySide`, or a module whose
  top-level package is exactly `Qt`. `PyQt6.QtCore` is neither — so an import
  of it in `serve.py` or `supervise.py` passes a case whose invariant reads
  "pulls in no Qt or PySide6 module".
  Not theoretical: measured 2026-08-02, **PyQt6 is importable on this machine**
  (`~/.local/lib/python3.13/site-packages/PyQt6/`), so the breach is reachable
  today by anyone reaching for the wrong binding out of habit.
  The fix is one arm on the predicate — also flag a top-level package matching
  `^PyQt\d*$`. Do it under the project's own rule that a case must be observed
  failing first: add a `--break pyqt_import` alongside the existing
  `qt_import`, confirm `serve_is_headless` goes red, then widen the predicate
  and confirm it goes green. That takes the break count from thirteen to
  fourteen; CLAUDE.md and LOTTO-0013 §7 both state it and must move together.
  Documented meanwhile in LOTTO-0013's INV-19 clause, which names the gap
  rather than papering over it — so this item closes a stated gap, not a
  silent one.

- ✅ **LOTTO-0022** LOTTO-0001 owes a cold-eyes loop for INV-22.
  Kind: doc. Source: in-session-2026-08-02 (LOTTO-0007a).
  Layman: A safety review that is due on the spec we just changed, so it does not quietly go unread.
  LOTTO-0007(a) added **INV-22** to
  `docs/specs/LOTTO-0001-lottery-ticket-tracker.md` §5 and rewrote two §11
  rows. The amendment has not been through the gate: it was written, checked
  against the code and red-tested, but no independent reader has seen it.
  Small and self-contained — one invariant, its test clause and two table rows
  — so one loop should settle it, the same shape as the LOTTO-0002 and
  LOTTO-0013 re-gates on 2026-08-02.
  Filed rather than run because that session had just stopped a gate by
  decision, and spending four more reviewers without asking would have been
  the wrong call. It is recorded here so the obligation outlives the
  transcript: the fix is shipped and checked, what is outstanding is the cold
  read of the contract describing it.
  Worth folding in with LOTTO-0001's next amendment rather than running alone,
  if one is coming soon.
  Resolved 2026-08-02: two loops, recorded as LOTTO-0001 §13 loops 5 and 6.
  23 verified findings fixed, 2 dismissed on evidence, 1 filed as LOTTO-0023,
  1 surfaced code-side. Accepted at two loops, not stopped by the cap.
  "One loop should settle it" was wrong, and the reason is worth keeping: the
  amendment itself was sound, but it had left **§6 still describing the
  pre-INV-22 behaviour** — so the failure-modes section an implementer reads
  for the unhappy path licensed exactly the R0.00 default INV-22 forbids. The
  contradiction sat five sections from the new invariant, which is the distance
  the author cannot see and a cold reader can. Second: **INV-5's recorded test
  was red against correct code**, because its glob swept the `tools/` doubles
  and one of those doubles is INV-22's own probe — so the obvious repair
  deletes a guard on the cardinal money rule. Both were found independently by
  both lanes. Loop 6 found no CRITICAL, confirming the fixes held.

- 📋 [LOTTO-0023] **A win in a retired prize division is dropped silently, with no count.**
  Found by a cold-eyes lane on LOTTO-0001 during the LOTTO-0022 gate, and
  verified against the code.

  `check.py::check()` tests every line's label against
  `paying_combinations()`, which reads the division set from the pool's
  **newest** draw. A pre-handover division with no current equivalent
  therefore fails the gate and the line is dropped before `amount()` runs.
  LOTTO-0001 §4.4 has always called that "a known limit, not an oversight",
  and §11's label-grammar row reads `nothing`.

  The cardinal rule in its *omission* form: the win leaves no row, no count
  and no diagnostic, and reads exactly like a losing line. INV-22 closed the
  same shape on the money path one step later (an unpriceable win raises);
  this is the step before it, where the line never reaches pricing at all.

  **It is not unreportable by construction**, which is why this is filed
  rather than accepted. The gate uses the newest draw's division set; the
  draw being scored carries its **own** set (`results.py::divisions()` for
  API draws, the payout page for archive draws), and a label absent from the
  current set but present in that draw's own set is a retired-division win
  rather than a loss. The two cases are separable with one extra lookup,
  already memoised per draw.

  Scope decision needed before building: report a count beside the
  uncheckable report (cheap, honest, no repricing), or score and price such
  lines (changes the totals, and the prize is almost certainly past the
  365-day claim window anyway — every archive draw predates 2026-06-01). The
  count is probably the whole fix.

  Not a regression and not urgent: no such line is known to exist. What is
  known is that if one does, nothing says so.
  **Layman:** If an old ticket won in a prize category the lottery no longer runs, it vanishes from the report instead of being flagged — it looks exactly like a losing line.
  Kind: fix.
  Source: cold-eyes-2026-08-02 (LOTTO-0022 loop 6).
