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
  **Premise falsified 2026-08-12 — do not build from the description
  above.** The 14 `Ref:VAS…` messages this item calls payouts are DEBITS.
  Their text is "Standard Bank: R<amount> paid from Acc. NNNN to
  VAS00000000000 LOTTO. Acl bal R<amount> <date>" — money leaving the
  account to buy a ticket, with the direction stated in the message. They
  are purchase receipts duplicating the ticket SMS, not the bank paying
  winnings, so they are not external ground truth and they confirm nothing
  about scoring. The word this item's measurement keyed on, "paid", appears
  in both wordings and does not distinguish them.

  **But the REASONING above survives, and an intermediate note in this same
  session wrongly said it did not.** That note claimed three conclusions fell
  with the premise and that the source was "test-bearing now, not blocked
  behind LOTTO-0006". It was written from two payout messages visible in a
  partially-loaded thread list, both of which happened to post-date
  2025-01-01. Against the full population that generalisation is wrong, and
  this item's original shape is right.

  **The real payout SMSes: 149 of them, measured against the phone
  2026-08-12** (LOTTO-0030 fixed the filter that had always excluded them).
  Wording is "The winnings of R<amount> for ticket ref: VAS00000000000 will
  be paid in your account within two business days." — no game name, which is
  exactly why the import never saw one. Every one of the 149 carries both an
  amount and a VAS reference; 122 distinct refs, spanning 2022-11-23 to
  2026-01-14, R3,870.60 total.

  **The split is 146 before the archive window and 3 inside it**, so this
  item's central claim holds with better evidence than it was filed on:
  - **Today it validates the uncheckable logic, as written.** 146 payouts
    land on tickets `scorable()` refuses to score. Had those been scored
    against the wrong draws, 146 real wins would have read R0.00. That is
    external confirmation of INV-6, and still the only such confirmation.
  - **3 are scoreable now** — a small immediate cross-check on the engine,
    which the item did not know it had.
  - **LOTTO-0006 remains the unlock, and is now quantified:** backfilling to
    2022 turns 149 messages into 149 known-correct answers to test scoring
    against, ticket in, amount out.

  What actually changes: the 14 `Ref:VAS…` debits are NOT the input, so
  "the dump holds 575 messages: 558 purchases and 17 others" describes the
  purchase corpus and nothing about payouts. `tools/verify_payouts.py` is
  still the right shape and the VAS reference is still the join. Merged with
  LOTTO-0029 (same work); sequence is LOTTO-0030 (done) → re-pull the dump
  over USB → LOTTO-0029/0010.

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

- ✅ **LOTTO-0003** Pick up new tickets automatically as the SMS arrives.
  Kind: implement. Source: user-request-2026-08-01.
  Layman: new tickets appear by themselves, without plugging the phone in.
  KDE Connect emits `conversationCreated` / `conversationUpdated` over D-Bus;
  subscribe rather than polling.
  Resolved (2026-08-13): `watch_sms.py` collects new lottery SMSes over
  KDE Connect with no cable, `supervise.SmsWatch` owns it as a second
  child of the tray, and the tray re-scores the page when the dump grows.
  Specced in docs/specs/LOTTO-0003-live-sms-watch.md (INV-32..INV-37);
  checked by tools/verify_watch.py, seven cases, all observed failing.
  The roadmap line above said to subscribe rather than poll, and that is
  half right in a way worth recording: `conversationCreated` fires only
  the first time the daemon learns of a conversation - 202 signals on a
  first run, ZERO on every run after, against the same 2,325
  conversations. A discovery built on it works once per daemon lifetime,
  and the first live run duly reported "0 new" against a phone holding
  951 matching messages. Discovery now reads activeConversations()
  directly and waits for it to stop GROWING; the signals carry live
  arrivals and history answers, which they do reliably.
  Live proof, cable unplugged: 2,325 threads read in 21s, one thread
  asked for history, two new payout SMSes written (07:03 and 07:04 that
  morning, both after the last cable pull). The 951 records already held
  were left byte-identical.
  Not done here: LOTTO-0028 (scheduled refresh) is less pressing now that
  an arrival triggers one, and two invariant halves are stated but
  unchecked (INV-37, and INV-36's tray notification) - see
  LOTTO-0003 §11 for why, and LOTTO-0007 for the deferred reconnect gap.

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
  Correction (2026-08-12): three claims above have gone stale and the bullet
  now contradicts the tree. LOTTO-0025 added `.github/workflows/ci.yml`, so
  "no `.github/` at all" is false, "this item adds the first of both" is now
  only about the packaging manifest, and "publishing from CI would add the
  first workflow to a repo that has none" describes a repo that no longer
  exists. The push-cadence warning at the end is spent for the same reason:
  the workflow landed and the repo is public, so the free-minutes point was
  already made. What survives unchanged is everything about the artifact —
  the platform-bound entry points (`find_lotto_sms.py` cannot cross to
  Windows), the requirement that the absent fetcher be NAMED in the UI, and
  the rule that the local check must RUN the built artifact from outside the
  repository rather than merely build it. Those are the parts to design to.

- ✅ **LOTTO-0016** Run the CI locally before pushing, from the same script CI runs.
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
  Resolved (2026-08-12): shipped by LOTTO-0025, verified against the tree
  rather than the record. `./local-CI.sh` holds the one list of checks and
  `.github/workflows/ci.yml` invokes it as `./local-CI.sh --ci` with no second
  copy of the steps — the structural property this bullet asked for. The
  script is `local-CI.sh`, not the `tools/ci.sh` proposed here; the name is
  the only thing that differs. The data split this bullet said to decide
  explicitly is decided and stated in the script header: three verifiers need
  the gitignored dump and archive, and `verify_privacy.py`'s degraded
  pattern-only mode is asserted against locally instead of trusted, so a
  skipped check cannot pass quietly.
  Two sub-asks did NOT ship and are recorded here rather than dropped.
  (a) There is no containerised `podman run --rm ubuntu:24.04` lane. The
  tool-drift risk it was aimed at did occur — ruff 0.15.11 here vs 0.16.1 on
  the runner, 71 errors against zero on identical bytes — and was closed by
  `ruff.toml` pinning the rule selection, which fixes the verdict rather than
  the image. The residual OS gap is narrow today: both lanes are Python 3.13.
  Worth reopening only if a divergence appears that a rule lock cannot fix.
  (b) "Print that the Windows half is uncovered" belongs to LOTTO-0015, which
  has not shipped. There is no Windows lane yet to disclaim.

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

- ✅ **LOTTO-0019** Tell the user they won, instead of waiting for them to come and look.
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
  Spec: `docs/specs/LOTTO-0019-build-reporting.md` — an umbrella covering this item, LOTTO-0012 and LOTTO-0020, because all three change `results.py::_post()` and `GET /status`'s body. Accepted 2026-08-05 after a 3-loop cold-eyes gate: 77 findings verified, 77 fixed, 5 dismissed, nothing deferred. Unblocked by LOTTO-0018. The scheduling half is split out as LOTTO-0028 — this item makes a refresh REPORT what it found; nothing yet makes one HAPPEN unasked.
  Resolved 2026-08-05: `GET /status` carries `found` (new winning lines and their total) and `supervise.refresh_message()` turns it into the tray's sentence. Three DONE states kept distinct — "nothing was compared" never reads as "compared, found nothing" — and the body is two integers, no ticket data (INV-29, INV-30). Also fixed the counter freezing under a live "Checking your tickets…" notice when an opening build fails. Spec `docs/specs/LOTTO-0019-build-reporting.md`; 17/17 verifier cases green, 30/30 breaks red. Scheduling stays open as LOTTO-0028.

- ✅ **LOTTO-0020** Show what the first build is actually doing instead of "building" for half a minute.
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
  Specced under `docs/specs/LOTTO-0019-build-reporting.md` (umbrella; see LOTTO-0019). Resolved 2026-08-05: the figure ships with NO denominator — `check.py` fetches lazily, so this build's total is unknowable until it ends, and this bullet's own warning about 27 being a dated measurement is what rules it out. It counts HTTP *attempts*, which is what makes it move during the retry storms LOTTO-0012 introduces.
  Resolved 2026-08-05: `GET /status` reports `requests` and the opening page interpolates it. No denominator — the bullet's own warning about 27 being a dated measurement is what ruled it out, and `check.py` fetches lazily so this build's total is unknowable until it ends. Counts ATTEMPTS, so it keeps moving through LOTTO-0012's retries. Holds INV-28; three breaks observed red, including `reset_on_worker_thread` for the window where a late reset would report the previous build's total.

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

  **Layman:** An external manager can now put the page on whatever port it likes, and start it without an icon appearing next to the clock.
  Kind: feature.
  Source: user-request-2026-08-03.

- 📋 [LOTTO-0028] **Refresh on a schedule, so a win is found without the user clicking anything.**
  Split out of LOTTO-0019 rather than folded into it. LOTTO-0019 makes a
  refresh REPORT what it found; nothing in the project makes a refresh
  HAPPEN on its own. `tray.py::refresh()` is wired to a menu action only —
  verified 2026-08-05: `tray.py` constructs no QTimer and `supervise.py`
  schedules nothing.
  So after LOTTO-0019 the summary is real but only ever reaches a user who
  was already opening the menu, which leaves most of the gap its own
  headline names ("instead of waiting for them to come and look").
  Two things to settle before building, neither guessable:
  (a) the cadence, set against draw times rather than a round number of
  hours — Daily Lotto draws nightly, Lotto and PowerBall twice a week, so
  a fixed 6-hourly poll is mostly wasted requests against a free public
  API;
  (b) what a scheduled refresh does when it FAILS, since nobody is
  watching it — LOTTO-0018's rule (a failure reported as a success is
  worse than a blank) is harder to honour for a notification the user did
  not ask for.
  LOTTO-0019's comparison baseline is the other constraint: it lives in
  the server process and is reset by a restart, so a scheduled refresh is
  also what would make that baseline long-lived enough to be worth having.
  **Layman:** The tray checks for new draws on its own, instead of only when you ask it to.
  Kind: feature.
  Source: in-session-2026-08-05 (split out while speccing LOTTO-0019).

- 📋 [LOTTO-0029] **A payout SMS would be a third results source, and the dump does not carry one today.**
  The user's point, and it is a good one: every ticket that paid out should
  have a message announcing it, and a message stating the amount beats a
  figure this project derives. It would be the only source authoritative
  about this user's own WINNINGS rather than about the draw — a cross-check
  on scoring, not merely another price feed, and it would price the archive
  era with no payout-page scrape at all.

  **Measured 2026-08-12 before filing, and the result is negative today.**
  `lotto_sms_raw.txt` holds 2,492 lines and contains ZERO case-insensitive
  matches for won, win, winner, winning, prize, congrat, claim, payout or
  credit. The one keyword present is "paid", 14 times, in a single uniform
  message shape — almost certainly the purchase wording, not a payout.

  **That is not proof the messages do not exist, and the distinction is the
  whole item.** `find_lotto_sms.py` filters on KEYWORDS (lotto, powerball,
  power ball, ithuba, sizekhaya, national lottery, nationallottery, jackpot)
  against body AND sender, then pulls FULL history for matching threads. So
  a payout arriving in the same thread as a ticket confirmation would
  already be in the dump, and its absence there is real evidence. A payout
  from a DIFFERENT sender whose text contains none of those eight words
  would never be fetched, and this project could not tell the two apart.

  **Cheap next step, before any parser is written:** `find_lotto_sms.py`
  already prints a "Senders seen" diagnostic. Run it and read the sender
  list, or widen KEYWORDS once and re-pull, to separate "no such message
  exists" from "the filter never looked". Only then is there anything to
  parse. Filed as investigate rather than implement for that reason — the
  parser is the easy half and it is downstream of a question nobody has put
  to the phone yet.

  **If the messages do exist, the design question is not how to parse
  them.** It is what happens when the SMS and the scored result disagree.
  This project's shape is that a wrong number is a bug in scoring or in a
  source, never a second opinion (CLAUDE.md: `serve.py` adds no third
  opinion) — so a payout SMS is either promoted to authoritative for its own
  ticket, or it becomes a verifier that makes a disagreement loud. Decide
  that before writing the parser.

  Not needed to close LOTTO-0023, which shipped 2026-08-12 having
  established that no archive-era division is unnameable.
  **Layman:** If the lottery texts you when you win, that text is proof of the amount — better than any figure this project works out for itself.
  Kind: investigate.
  Source: user-request-2026-08-12.
  Measured against the phone 2026-08-12, and the answer is the
  opposite of the filing: **the payout SMSes exist.** Standard Bank sends
  them, in the STDBANK thread, in one uniform shape — "Standard Bank: The
  winnings of R<amount> for ticket ref: VAS00000000000 will be paid in your
  account within two business days. T&C's apply. Query? 0860 123 000".
  They carry the VAS ticket reference, so the join key to a Ticket is
  already in the message; no fuzzy matching is needed.

  **Why the filing measured negative, and it is not a counting error.** The
  dump is built by the documented adb import, NOT by `find_lotto_sms.py`
  (which writes no file — LOTTO-0001 §4.1), and that import filtered
  `body LIKE '%lotto%' OR body LIKE '%powerball%'`. A payout SMS names no
  game; note "lotto" is not a substring of "lottery". So the dump was never
  capable of holding one, and "zero payout words in 2,492 lines" measured
  the game-naming subset of the corpus rather than the corpus. The bullet's
  own two hypotheses were the right pair, and the second one holds — at the
  import filter, which neither hypothesis had named. Fixed as LOTTO-0030.

  **The exact mechanism.** A purchase debit reads "R<amount> paid from Acc.
  NNNN to VAS00000000000 LOTTO" — it contains "LOTTO", so it clears the
  filter and lands in the dump. A payout reads "The winnings of R<amount>
  for ticket ref: VAS00000000000" — no game name anywhere, so it never
  crosses from the phone. That one word is the whole difference between the
  messages the dump has and the payouts it has never held.

  **Sender census, since a first pass here got it wrong.** That pass claimed
  all 575 dump messages were `address=STDBANK`, generalised from the file's
  first rows; the real split is 397 numeric senders and 178 STDBANK (in three
  spellings, one with a trailing space). Purchase SMSes arrive from rotating
  numeric addresses whose BODY says "Standard Bank:". There is no single
  sender to key a filter on, which is why the fix is on message content.

  **Reconciled with LOTTO-0010: its evidence is wrong, its reasoning is
  right.** That item (2026-08-02) reads the dump's 14 `Ref:VAS…` messages as
  payouts. They are debits — money leaving the account to BUY a ticket, the
  direction stated in the message text — so they are not external ground
  truth. But its conclusions hold against the REAL payouts, now that
  LOTTO-0030 can see them: 149 messages, 146 of which predate the archive
  window and therefore confirm `scorable()` rather than scoring, exactly as
  that item argues, plus 3 inside the window it did not know it had. An
  intermediate note in this session claimed the opposite — that the source
  was immediately test-bearing and LOTTO-0006 was not the unlock — on the
  strength of two messages seen in a partially-loaded thread list. Two
  samples are not a population; the retraction is recorded under LOTTO-0030.
  LOTTO-0010 and this item are one piece of work.

  Progress (2026-08-12): step 1 is done and the item survives it, upgraded
  from investigate-whether to design-how. The open design question in the
  body — authoritative vs verifier on disagreement — is untouched by this
  and is still what blocks a parser; with 149 payouts against 122 distinct
  refs, note that some tickets carry more than one payout, so the answer has
  to hold for a ticket paid across several draws or pools.
  The collection defect found on the way is LOTTO-0030 (shipped). **The
  remaining prerequisite is mechanical, not a decision: re-run the widened
  adb import over USB.** Until that happens `lotto_sms_raw.txt` holds the old
  575 records and no payouts, so there is nothing on disk to parse.
  Progress (2026-08-13): step 2 measured. The join WORKS and the
  reconciliation is worth building - it already found that scoring
  under-counts real money.
  Decision taken by the user 2026-08-13, and it settles what this item
  builds: when a payout SMS and the computed score disagree, the
  disagreement is FLAGGED LOUDLY - both figures shown - never resolved in
  the SMS's favour. A scoring bug that hides is the failure this project
  exists to prevent, and the measurement below is what that decision buys.
  Measured against the 953-record dump (368 payout messages parse, 224
  distinct refs, R8,312.70 paid lifetime):
  - ref is a clean join key: 561 tickets, 561 distinct refs, 223 of 224
    paid refs match a ticket. One paid ref has NO purchase SMS at all.
  - 77 refs carry more than one payout, so any design must sum per ref
    rather than expect one payment per ticket.
  - computed lifetime wins: R3,323.00 over 77 refs. Against the bank:
    60 refs agree exactly, 17 differ (15 of them computed LOW, by R315.50
    in total; 2 high by R11.40), and 147 refs were paid where the app
    found no win at all.
  - 142 of those 147 involve an entry nothing can score, so the silence is
    correct and is the uncheckable-is-not-a-loss rule working. FOUR are
    fully scorable and were still missed: R65.40, every one of them Lotto
    entered in all three tiers.
  - ZERO refs where the app claims a win the bank never paid. It errs
    downward only.
  Lead, not a conclusion: all four outright misses and 16 of the 17 amount
  disagreements are archive-era (pre-2026-06-01), which is exactly the era
  `tools/verify_sources.py` cannot cross-check because the official API
  does not reach back that far. The API era has only 7 paid refs (6 agree,
  1 differs), too few to clear it. Traced one miss fully - a 5-board
  single-draw ticket, paid R10.50 the morning after the draw - and no
  board reaches a paying division in ANY of its three pools, so either the
  stored archive numbers for that draw are wrong or the prize came from
  something this model does not represent. `paying_combinations()` was
  ruled out: the division table is complete and plain MATCH 2 correctly
  does not pay.
  Next step is therefore to check stored archive draw numbers for those
  four draws against an independent source, before building anything.
  Investigation (2026-08-13) into the four fully-scorable misses. Four
  causes ELIMINATED, each by a check that would have shown the defect:
  1. Not the division table. `paying_combinations()` returns all 8 Lotto
     divisions with the right labels, and plain MATCH 2 correctly does not
     pay - the traced ticket's best outcomes were MATCH 2 and MATCH
     1 + BONUS, which genuinely win nothing.
  2. Not a date offset in the archive. Scored the traced ticket against
     the two draws either side of its own: two chance hits appear (one
     BEFORE the purchase date, one AFTER the payout arrived, so neither
     can be the prize), and ~1 chance hit is expected across 75
     board-draw pairs at Lotto's P(match 3). No systematic shift.
  3. Not the archive parser or a corrupt store. Re-parsed the three
     cached year pages for the draw in question and compared against
     `archive_results.json`: all three tiers agree exactly, main numbers
     and bonus. The three tiers also carry distinct number sets, so no
     tier is duplicating another.
  4. Not the ticket parse. Every board in the dump carries exactly its
     game's pick count - 309 Lotto boards at 6, 312 PowerBall at 5, 130
     Daily at 5, zero exceptions across all 561 tickets. A dropped number
     would have made matches systematically low, which is what the
     under-counting looked like, and it is not happening.
  What remains: the traced ticket reaches no paying division in ANY of
  its three pools for the draw it was bought for, yet the bank paid the
  next morning. Either the results SOURCE is wrong for that draw (the
  project has one archive source and `tools/verify_sources.py` cannot
  cross-check it before 2026-06-01, which is exactly where all four
  misses sit), or a payout can arise from something this model does not
  represent. Distinguishing them needs an INDEPENDENT results source for
  those four archive-era draws - a second site, since the official API
  does not reach back. That is a new dependency and is the user's call;
  nothing further can be settled offline.
  Second source fetched (2026-08-13), and it CLEARS the archive rather
  than convicting it. The previous note named the archive era as the lead
  because nothing could cross-check it; that lead is now dead.
  Two archive-era draws were checked against sites the project does not
  scrape (`thesouthafrican.com`, `za.lottonumbers.com`; the archive is
  `za.national-lottery.com`). Both agree EXACTLY with
  `archive_results.json` - all three Lotto tiers, six main numbers and the
  bonus ball, on 2025-10-01 and 2025-09-24. The stored results are right.
  A wrong turn, recorded because the correction is the useful part: a
  range check over all 1,431 stored draws reported 133 Lotto draws
  carrying numbers of 53-58, which looked like archive corruption
  confined to the Ithuba era and ending exactly at the 2026-06-01
  handover. It is not corruption - the independent source shows the same
  values, and lottonumbers.com states 58 as the highest number drawn in
  that period. The premise "SA Lotto is 6/52" was the error, not the
  data. **Do not add a 1-52 range assertion anywhere**: it would fail on
  133 real draws.
  So five causes are now eliminated (division table, date offset, archive
  parser/store, ticket board parse, results data itself), plus a sixth
  checked here: no purchase SMS names more than one game, so a payout
  cannot be for a second game bought in the same transaction - all 561
  carry exactly one `Played R...` line.
  What that leaves is a conclusion about the DOMAIN, not the code: a
  payout SMS is not always attributable to a computed win. The traced
  ticket reaches no paying division against numbers now verified twice,
  and was paid R10.50 the next morning anyway. Consequences for the
  build, which are the point of this item:
  - an unexplained payout is its OWN category on the page, beside
    "app says won" and "bank paid" - never evidence that scoring is
    broken, and never silently dropped.
  - the 15 refs where the app computes LOW remain unexplained and are the
    better lead now, being a difference in AMOUNT on tickets that did win
    - a pricing question rather than a matching one.

- ✅ [LOTTO-0030] **The import filter matched game names, so it excluded every payout SMS.**
  **Layman:** The command that copies lottery texts off the phone only looked for messages naming a game. The bank's "you won" texts don't name one, so 149 of them were skipped every time. Now they come across.
  Kind: fix.
  Source: in-session-2026-08-12.
  Shipped 2026-08-12 alongside LOTTO-0029 step 1.

  **The defect, in one line.** The documented adb import ran
  `--where "body LIKE '%lotto%' OR body LIKE '%powerball%'"`, and a payout SMS
  — "The winnings of R*amount* for ticket ref: VAS00000000000 will be paid in
  your account…" — names no game anywhere. Note also that `lotto` is not a
  substring of `lottery`. Every other message shape happens to name a game
  (`Played R… Lotto Plus 2`, `… to VAS… LOTTO`, `Your lotto transaction was
  unsuccessful`), which is why the gap survived: the filter looked complete
  because the messages it could see were complete.

  **Fix.** A third clause, `OR body LIKE '%VAS00%'`, in both copies of the
  command (`README.md`, `docs/specs/LOTTO-0001` §4.1). The VAS reference is
  common to all four shapes — every one of the dump's 575 records carries one,
  formatted `VAS00` + 9 digits — so it is simultaneously the widest and the
  most precise clause of the three, and it is already `Ticket.ref`, the join
  key scoring uses. `find_lotto_sms.py` gets `vas00` in `KEYWORDS` for the
  same reason: one `matches()` drives both thread discovery and the
  within-thread filter there, so the single addition lets an inspection run
  see a payout without dumping the rest of the inbox.

  **Measured after the change, against the phone:** the old list matched 386
  of 2,324 threads, the new one matches 560, and **149 of the additions are
  payout SMSes** — every one carrying both an amount and a VAS reference, 122
  distinct refs, spanning 2022-11-23 to 2026-01-14, R3,870.60 in total. That
  is the dataset LOTTO-0010 and LOTTO-0029 need, and it has never been in the
  dump.

  **Two claims this bullet made on 2026-08-12 were WITHDRAWN the same day, and
  the reason is worth keeping.** An early draft asserted (a) that thread
  discovery matched "0 of 25 threads", and (c) that `requestConversation()`
  no longer delivered history. Both were artifacts of reading
  `activeConversations()` too early: `requestAllConversationThreads()` fills
  the list ASYNCHRONOUSLY, and a 6-second wait returned a partially-loaded
  snapshot of 25 threads where the phone actually has 2,324. Re-measured at
  5, 10, 20 and 30 seconds the count is stable at 2,324 and the ORIGINAL
  eight-keyword list matches 386 — so discovery was never broken, and neither
  was the history pull. **The lesson for the next session: this D-Bus API has
  no completion signal, so any count taken from it is a lower bound until it
  stops moving.** Sample at two waits and compare before believing one.

  **A sampling-bias warning, from the same session.** Working off the
  partial list, two payout messages were visible and both happened to fall
  inside the archive window, which produced a confident and wrong conclusion
  that the payout source was immediately test-bearing. Against the full 149
  the split is 3 inside the window and 146 before it. Two samples agreeing is
  not evidence about a population.

  Privacy: payout SMSes carry the VAS reference and a rand amount, which per
  CLAUDE.md identify a ticket on their own. The sentinel VAS00000000000 is
  used in every example above, and `tools/verify_privacy.py` passes at full
  strength. Re-run it after the first widened import — this change widens
  what the dump holds, and so widens what a leak would expose.

  **Re-pulled over USB 2026-08-13, and the first pull found a false positive
  worth recording.** `VAS` is not a lottery namespace — it is Standard Bank's
  *value-added services* platform, and prepaid **electricity** rides on it with
  an identically formatted reference (`VAS` + 11 digits, prefix `00`, on every
  shape alike, so the reference cannot discriminate). The unrestricted `VAS00`
  clause pulled 993 records, 42 of them electricity: a `U: <n>kWh` purchase
  plus a token continuation reading "Enter tokens on SMS 1" that carries no
  `kWh` at all, which is why one exclusion would not have been enough. Two
  `NOT LIKE` clauses now bound it. **The pre-fix check missed this because it
  was run against the wrong population** — five marketing messages that
  happened to be to hand, rather than the phone's real corpus. A matcher is
  only tested by the population it will actually run against.

  **Final numbers:** 951 records (from 575), a strict superset — 0 of the
  original 575 missing — spanning 2022-11-09 to 2026-08-10, carrying **366
  payout SMSes**, far more than the 149 the KDE Connect probe suggested,
  because that probe could only ever see the newest message per thread.
  Deliberately KEPT: seven VAS messages naming neither a game nor a utility
  (`R… purchased for VAS…`, `R… deposited into Acc. … from VAS…`) — they may
  be lottery refunds, and if they are not, `parse()` returns `None` and they
  are inert. So the honest guarantee is "no message without a lottery-or-VAS
  marker crosses, and no known utility message crosses", NOT "only lottery
  messages cross"; LOTTO-0001 §4.1 now says exactly that, having previously
  claimed the stronger version.

  The re-pull immediately exposed a latent parser bug (LOTTO-0031) that no
  test could have caught while the dump was stale.

- ✅ [LOTTO-0031] **The SMS wording adopted the rebrand names and GAME_MAP did not, so those tickets vanished.**
  Found the moment the widened import brought fresh messages in, which is
  the point of LOTTO-0030 and a good argument for re-pulling more often.

  **The defect.** `tickets.py::GAME_MAP` translates the game name an SMS
  prints into `(game, plus_flag, pool_id)`. `parse()` returns `None` for a
  name the map does not hold, and `load()` drops a `None` silently. The June
  2026 rebrand renamed Lotto Plus 2 to **Lotto 5 Max** and PowerBall Plus to
  **XTRA**; three of the project's four name tables were updated at the time
  — `PAYOUT_SLUG` (backfill.py), `POOL_NAMES` (history.py) and the README's
  game list — and `GAME_MAP` was not, because until now no SMS had used the
  new wording. The first one arrived **2026-08-08**: a R200.00 ten-draw
  two-board `LOTTO 5 MAX` ticket, which parsed to `None` and was therefore
  never scored, never counted and never shown. A silently-dropped ticket is
  the failure class this project was built after hitting.

  **Fix.** Two aliases, `"lotto 5 max"` and `"powerball xtra"`, carrying the
  same values as the pre-rebrand names they replace. Aliases rather than
  replacements: the old wording is all over the archive era and must keep
  parsing. `entered_pools()` still derives the real pool set from the price
  (INV-8/INV-9), so the map's `plus_flag`/`pool_id` remain the fallback they
  always were — what the map is load-bearing for is the BASE GAME, which
  drives board parsing and scoring, and both aliases keep it.

  **Before:** `PARSE GAP: 561 purchase SMSes, 560 parsed` / 1 with wrong draw
  coverage — `tools/verify_coverage.py` red.
  **After:** 561 tickets, 1,238 entries, 0 with wrong draw coverage.
  `./local-CI.sh` 9 checks PASS. Both symptoms were the one ticket.

  **Worth carrying: the verifier caught this, and nothing else would have.**
  No test failed before the re-pull because no message in the old dump used
  the new wording — the bug was latent in the code and only a data refresh
  could expose it. INV-6's coverage check is what turned a silent drop into a
  red build. It also means the *next* wording change will be silent again
  until someone re-pulls, which is an argument for LOTTO-0003 (automatic
  ingest) beyond convenience: a stale dump hides parser rot.
  **Layman:** A ticket bought on 8 August was quietly ignored, because the bank's text now calls the game "Lotto 5 Max" and the code only knew the old name. Fixed, and the ticket is now scored.
  Kind: fix.
  Source: in-session-2026-08-13 (surfaced by LOTTO-0030's first re-pull).

## Hardening

- ✅ [LOTTO-0025] **A pre-push gate, and the CI that mirrors it.**
  `./local-CI.sh` runs before every push; `.github/workflows/ci.yml` runs the
  same script with `--ci` on GitHub. One list of checks, in one file, so the
  runner and this machine cannot drift apart.

  **The two lanes are deliberately unequal, and the inequality is the point.**
  Three verifiers need `lotto_sms_raw.txt` and the scraped archive, and neither
  may reach a public runner — measured in a fresh clone: `verify_sources`,
  `verify_coverage` and `verify_pools` all exit 1 on missing input. Worse,
  `verify_privacy.py` *passes* there, because without the dump it falls back to
  pattern-only checks and still exits 0. A green tick on GitHub therefore means
  less than a green `./local-CI.sh`, and pretending otherwise would be this
  project's cardinal failure wearing a CI badge: absence of a finding read as
  absence of a leak. So `local-CI.sh` asserts the privacy check ran in
  `content+pattern` mode rather than trusting its exit code, and both the
  script header and the workflow say which checks a runner cannot perform.

  The CI lane is `ruff`, a `compileall` syntax pass, `verify_page.py` (no
  network, sentinel data, needs PySide6 plus four system libraries) and
  `verify_privacy.py` in its weaker mode. A documentation-only push — every
  changed file `.md` — skips the gate, and `paths-ignore` mirrors that on the
  runner so the two agree about what needs no gating.

  Red-tested rather than assumed: the full gate run in a dump-less clone goes
  red on all four data-dependent checks including the degraded-privacy
  assertion; `--ci` in the same clone goes green; a docs-only commit skips; a
  docs+code commit does not; and `--force` overrides the skip.

  **The first real run went red, and the cause was this item's own blind
  spot.** One shared script guarantees one *list of checks*; it does not
  guarantee one *set of tools*. `ruff` was unpinned, so the runner installed
  0.16.1 against 0.15.11 here — and 0.16 widened its default rule set to
  include SIM, EXE, RUF, FURB, DTZ, PLW, B, PIE and I. 71 errors there, zero
  here, on identical bytes. The fix is `ruff.toml` stating the selection the
  project was actually written against (`E4`, `E7`, `E9`, `F` — ruff's
  pre-0.16 default), verified clean under both versions, so the verdict no
  longer depends on which release `pip` resolves. The version pair is now
  printed in the gate's header so a future divergence is visible rather than
  latent. Deliberately *not* fixed by adopting the new defaults: all 71 are
  style opinions on working code, and closing them is a real change that
  deserves its own diff rather than arriving as a side effect of a linter
  release.

  Left open deliberately: `ruff.toml` locks the *rules*, but the two machines
  still run different ruff *builds* (0.15.11 here, whatever `pip` resolves
  there). Pinning the version would satisfy "identical" more literally at the
  cost of a pin that rots; the rule lock is what makes the verdict identical,
  and the version pair printed in the gate header is what makes any residual
  difference visible. Revisit if a release ever diverges *within* the selected
  rule families.
  **Layman:** One command now checks everything before your work leaves the machine, and GitHub runs the half it is allowed to see.
  Kind: chore.
  Source: user-request-2026-08-03.

- 📋 **LOTTO-0004** Automated guard that no SMS content can be committed.
  Kind: security. Source: in-session-2026-08-01.
  Layman: make it impossible to accidentally publish your messages.
  `tools/verify_privacy.py` now does the checking, but someone must remember
  to run it. A pre-commit hook would make it structural.
  **Partly advanced by LOTTO-0025 (2026-08-03), which does not close this.**
  The `.githooks/pre-push` gate runs `verify_privacy.py` automatically before
  every push, so "someone must remember" is no longer true at the push
  boundary. It is still true at the *commit* boundary, which is what this item
  asks for: content committed and then inspected locally has already been
  written to history, and a pre-push gate that a `--no-verify` skips is a
  seatbelt rather than a lock. Keep this item open for the pre-commit half.
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

- ✅ **LOTTO-0012** Retry the results API instead of dying on its first refusal.
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
  Specced under `docs/specs/LOTTO-0019-build-reporting.md` (umbrella; see LOTTO-0019), as INV-27. Bounded to 3 attempts with 1 s/2 s backoff, re-raising the ORIGINAL exception on exhaustion. `HTTPError` is never retried — the server answered. `socket.timeout` is caught explicitly because it is only an alias of `TimeoutError` from Python 3.10 and this project pins 3.8+.
  Resolved 2026-08-05: `results.py::_post()` retries a transport failure up to 3 attempts with 1 s/2 s backoff and re-raises the ORIGINAL exception on exhaustion. `HTTPError` is caught first and never retried — the server answered. Holds INV-27; `tools/verify_page.py::post_retries_transport_failure` checks it, with `no_retry` and `retry_http_error` observed red.

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
  feed-side rename of `MATCH n` would drop every win silently.
  **Superseded 2026-08-03 by LOTTO-0026, which owns the runtime half** —
  this bullet describes a blind spot in a *check*, and the same grammar has
  a matching hole in the *code* that is the more serious of the two. Close
  them together; do not fix the grep alone and read (c) as done;
  (d) Multiplay expansion is Lotto-only; a >6-number PowerBall or Daily
  board would silently collapse to one line (no such ticket exists today);
  (e) §8's "~30 lookups a month" is not recomputed from §10's request model.
  Progress (2026-08-12): one more rough edge for the tail, found while
  closing LOTTO-0017 and deliberately not fixed there.
  (f) `docs/specs/LOTTO-0013-tray-and-supervisor.md` line 9 says
  `verify_page.py` "runs **thirteen and twenty-two today**". It runs
  **seventeen cases and thirty-one breaks**. The sentence is inside a dated
  parenthetical about the LOTTO-0024 amendment ("...today, after the LOTTO-0024
  amendment below"), so it was true when written on 2026-08-03 and went stale
  when LOTTO-0019 added eight breaks and LOTTO-0017 a ninth. Left alone on
  purpose: rewriting the number in place would back-date a record of what that
  amendment did, which is the thing the loop log exists to preserve. The fix, if
  taken, is to re-date the clause rather than edit the figures — e.g. state the
  2026-08-03 numbers in the past tense and give the current ones separately.
  Cheap, and worth doing next time that file is open for another reason.
  Progress (2026-08-12): a second documentation edge, surfaced while measuring
  LOTTO-0029 and deliberately not fixed there.
  (g) `docs/specs/LOTTO-0014` §351–353 carries an invariant-ownership map that
  omits **INV-22** and **INV-26**. It was already stale before 2026-08-12, and
  LOTTO-0023 adding **INV-31** makes it staler — three missing rows now. Unlike
  (f) this is not a dated record and rewriting it would destroy nothing, so the
  only reason it is deferred is cost: LOTTO-0014 is an authoring edit away from
  re-arming its own `review-contract` gate, and a three-row map fix is not worth
  a full cold-read loop on its own. Fold it into the next change that opens
  LOTTO-0014 for another reason, and let the one gate cover both.
  Progress (2026-08-13): a third, found while writing LOTTO-0030/0031's entries.
  (h) `CHANGELOG.md`'s `[Unreleased]` section is **out of Keep-a-Changelog
  order and carries two `### Security` headings**. Current order is Added,
  Changed, Security, Fixed, Security; canonical is Added, Changed, Deprecated,
  Removed, Fixed, Security. Pre-existing — the duplicate predates 2026-08-13
  and neither heading was created by this session's entries (`changelog_log`
  created only `### Changed`, and placed it correctly). Deferred rather than
  fixed because the two fixes differ in kind: reordering is mechanical and
  `changelog_log op:"normalize"` does it in one call, but MERGING the duplicate
  `### Security` blocks is an editorial judgement about which entries belong
  together, and doing the first without the second leaves the file still
  malformed while looking tidied. Do both in one pass, or neither.
  Progress (2026-08-13): four more, all from LOTTO-0003's review gate.
  Each is CODE rather than prose, which is why the gate surfaced them
  instead of fixing them, and each is stated in the spec at the section
  named. None is a regression: (i) and (k) shipped with the item, (j) is a
  cost, (l) predates it.
  (i) `watch_sms.py::append_new()` reads the dump then appends with no
  lock, so two concurrently running watchers can both append the same
  message, with colliding row indices. Reachable: `SmsWatch.start()`
  guards only its own second spawn, and `python3 watch_sms.py` is a
  documented hand invocation. A lockfile or abstract socket is the fix.
  LOTTO-0003 §6.
  (j) `Watch.snapshot()` calls `append_new()` per message, so a catch-up
  re-reads and re-parses the whole 210 KB dump once per accepted message -
  543 times on this phone, ~114 MB inside the measured 21 seconds.
  Batching the snapshot into one `append_new()` makes it one read. The
  per-message shape exists because the same function serves the signal
  path, where one message is all there is. LOTTO-0003 §10.
  (k) When the server is stopped, the new-ticket notification says to use
  "Refresh results now" - but `tray.py::sync()` DISABLES that menu item
  while the server is stopped, so the instruction points at something the
  user cannot click. Found by a review lane reading past the document into
  the code. The wording or the enablement has to give. LOTTO-0003 §4.7.
  (l) `watch_sms.py` holds its D-Bus proxy from start-up, so if KDE
  Connect restarts the watcher stays alive and stops hearing anything,
  silently - quitting and reopening the tray is the only fix today. Filed
  here rather than left only in LOTTO-0003 §9, which is where it was
  recorded as out of scope.
  Progress (2026-08-15): (i), (j), (k) and (l) are DONE - the four code
  items LOTTO-0003's review gate surfaced. (b) to (h) remain open.
  (i) `append_new()` now holds an exclusive flock spanning the read AND the
  append, so the critical section is the whole of what de-duplication
  depends on. A single-instance guard was the other candidate and is
  weaker: it makes a second watcher REFUSE to run, where this makes it
  CORRECT. The lock is a SIDECAR file, and that is load-bearing rather
  than tidy - locking the dump means opening the dump, an open in append
  mode CREATES it, and `serve.py::build()` keys its "nothing has been
  imported" notice on the dump's EXISTENCE, so a lock on the dump would
  have turned that notice into an empty results table. Measured with the
  lock removed: 105 of 120 row indices collided, three runs out of three.
  (j) `snapshot()` now batches into ONE `append_new()`. Measured after the
  change: 543 messages produce 1 call and all 543 are still written; it
  was 543 calls and ~114 MB re-read on every start.
  (k) The wording gave, not the enablement. The stopped-server notice now
  names "Start server", which that state leaves enabled and which does
  score the ticket. The decision moved into
  `supervise.new_ticket_notice()` so it is checkable without a
  QSystemTrayIcon - INV-37 was recorded as unchecked for exactly that
  reason, and now has a case.
  (l) WAS FILED WRONG, and the correction is the useful half. Measured
  2026-08-15 by killing kdeconnectd under a running watcher: the held
  proxy DIES (`ServiceUnknown`) while the signal match rule SURVIVES (69
  signals still arrived), because the rule carries an interface and a
  member and no sender. So the watcher never went deaf - it went MUTE.
  Live arrivals kept landing and only the calls failed, which is exactly
  why nobody would notice. Second correction: NOTHING brings the daemon
  back. The watcher has to reach for it, the bus name being D-Bus
  activatable, every 60s rather than 2s so it cannot resurrect a daemon
  the user stopped on purpose. A third defect surfaced while testing and
  is fixed with it: a daemon merely not READY YET killed the watcher at
  start-up, which is the normal case at login when the tray starts before
  the phone re-pairs. Observed end to end: catch-up, kill, "stopped",
  self re-activation, "back", second full catch-up (2328 threads).
  New invariants INV-38 and INV-39; `tools/verify_watch.py` goes 7 cases
  to 11, each red-tested. Spec amended at LOTTO-0003 4.7, 4.8 (new), 5,
  6, 7, 9, 10, 11.

- ✅ **LOTTO-0026** A feed-side rename of `MATCH n` scores every line as a loss.
  Kind: fix. Source: in-session-2026-08-03; approach approved by the user
  before the CI work interrupted it.
  Layman: if the lottery site renames its prize categories, every win would
  quietly turn into "you didn't win" — with no error anywhere.

  **This is the cardinal rule broken by shipped code on a money path**, and
  the direct sibling of LOTTO-0007(a): the same failure, one function
  earlier. `check.py::check()` decides a line won by
  `label = api_label(...)` then `if label not in pays: continue`. `pays`
  comes from `paying_combinations()`, which raises when a pool has no recent
  draw — but *not* when the division table parses into labels that simply do
  not match. Rename `MATCH 3` to anything else upstream and `pays` is full
  of valid keys, every lookup misses, every line `continue`s, and the run
  reports zero wins with no diagnostic. **INV-22 cannot reach this**:
  `amount()` runs only after a match, so the 2026-08-02 guard never fires —
  there is nothing to price because nothing was recognised as a win.
  LOTTO-0001 §11 already carries the row (`§4.4 label grammar | **nothing**`).

  **Revised 2026-08-03: the failure arrived before the guard did.** Reading
  the grammar off the live feed to write step 1 found the API had already
  moved — or had never been read correctly — and 53 PowerBall wins were being
  scored as losses. LOTTO-0027 fixed the labels and shipped the check; this
  item still owns the **runtime** half, because a check that runs when someone
  runs it does not stop the next rename from being silent in between. Two
  things changed here as a result:
  the rule is now **reachability, not conformance** — the approved
  "raise when *no* label conforms to `MATCH n`" would have sat quiet through
  LOTTO-0027, since the plain labels conformed and only the PowerBall-qualified
  ones moved (user decision, 2026-08-03); and step 1's §11 row 547 is already
  written, so what remains for the spec is INV-26 itself and its §6 failure
  mode.

  Agreed approach, in this order:
  1. Amend `docs/specs/LOTTO-0001-lottery-ticket-tracker.md` — a new
     invariant for the grammar check, its §6 failure mode, and the §11 rows
     (542 for INV-5, 547 for the label grammar). Gate with `/cold-eyes`
     before implementing, per the cold-eyes-then-implement ordering.
  2. Implement the guard in `paying_combinations()`, mirroring its existing
     raise: a division table carrying a division **no label this project can
     build will ever equal** means the grammar moved — raise rather than
     return a dict with a hole in it. Reuse `tools/verify_pools.py`'s reach
     rule rather than writing a second one, and mind its direction (LOTTO-0001
     §4.4). Red-test first; LOTTO-0027's `+ PB` labels are a real red state to
     test against rather than a contrived one.
  3. ~~Widen INV-5's grep so it can see the f-string grammar in
     `api_label()`/`site_label()`.~~ **Revised 2026-08-03: there is no
     widening that works, and the spec now says so instead.** The labels are
     built with f-strings, so any pattern broad enough to see the grammar
     fires on the correct code that constructs it — a check that is red on a
     healthy tree is worse than the blind spot it replaces. LOTTO-0007(c)
     therefore closes against **INV-26**, which detects a rename by reading
     the feed rather than by reading the source, and INV-5's §11 row records
     both the limit and where the cover actually comes from. INV-5 keeps its
     production-only glob and its original job: catching an inlined division
     table.

  **Do not "fix" this by returning `{}` or a default** — that is the exact
  failure the guard exists to prevent, and `paying_combinations()`'s
  docstring already says so for the no-draw case.
  Progress (2026-08-03): **step 1 done.** LOTTO-0001 §5 carries **INV-26**
  (reachability, with its direction and why conformance is not a substitute),
  §6 carries the matching failure mode, and §11's INV-5 and label-grammar rows
  are rewritten. Step 3 was revised rather than done, above. The document goes
  to `/cold-eyes` before step 2 touches `paying_combinations()`, per the
  cold-eyes-then-implement ordering.
  **Loop 7 is closed** (2026-08-03). All 19 distinct findings across its two
  lanes were verified against current files; all 19 were true, all 19 are
  fixed, 0 dismissed. The record is LOTTO-0001 §13's loop-7 row, and
  `docs/reviews/LOTTO-0001-cold-eyes-loop7.md` is now a pointer at it rather
  than a findings list.
  **The fork both lanes raised is settled, the way the default said.**
  INV-26's runtime raise is marked *pending* in §4.4, §5, §6 and §11 rather
  than step 2 being landed first — because three of loop 7's own findings are
  precisely the contract holes step 2 must build against: the `(hits,
  special)` domain, whether the raise aborts the run or fails one pool, and
  whether "publishes for a pool" means the pool's history or its newest draw.
  Landing step 2 first would have built from the gaps the gate had just found.
  **The pending markers come off with step 2, which is all this item still
  owes.**
  Two of the fixes landed in code rather than prose, both in
  `tools/verify_pools.py`: INV-26's reach check gained the anti-vacuity floor
  INV-3 and INV-6 both carry — zero live pools, or any live pool whose
  division table is empty, now fail, where before both states printed
  `0 unreachable` and passed (red-tested on both branches) — and the comment
  justifying the check's direction carried the wrong counter-example verbatim
  (`MATCH 6` for Daily Lotto, which the domain caps at five and so never
  builds; the real buildable-but-unpublished daily labels are `MATCH 0` and
  `MATCH 1`). `./local-CI.sh` 9 checks PASS.
  **The gate is closed: converged by cap at three loops (7, 8, 9).**
  51 distinct findings across the three loops (19 + 14 + 18), 50 verified,
  50 fixed, 1 dismissed on evidence, **0 deferred** — there is no findings tail to fold
  in. Each loop's row in LOTTO-0001 §13 carries the detail.
  Loop 9's two structural results are the ones that outlive this item.
  **§4.3 never stated `history.py::POOL_NAMES`**, the table `all_draws()`
  filters the API response on — and two of its seven strings are June-2026
  rebrand names (`LOTTO 5 MAX`, `PowerBall XTRA`), so an implementer
  rebuilding `history.py` from the spec would get zero API draws for `lotto/2`
  and `powerball/1` with no error at all. It is now stated. That it surfaced
  only at loop 3, after two cold reads had passed over it, is the evidence
  behind the second result: **the document is 831 lines and should be split.**
  Recommended, not done — the call is the user's, and LOTTO-0001 is the
  project's root contract, so the split needs its own item.
  A third thing worth carrying: §7's path-resolution paragraph produced a
  finding in **all three loops** (a false exception, then the hazard written
  backwards, then the wrong scripts). It is now a four-row table. Prose that
  fails three independent cold reads is a shape problem, not a wording one.
  Resolved (2026-08-04): **step 2 landed, and the item is closed.**
  `check.py::paying_combinations()` now builds its division table, subtracts
  `check.py::buildable_labels()` from it, and raises on anything left over —
  the same abort as the no-recent-draw raise beside it, for the same reason.
  The domain lives in `buildable_labels()` bounded by `check.py::MAINS` and by
  which games `match()` can report a special hit for, exactly as INV-26 states.
  `tools/verify_pools.py` keeps its own transcription of that domain rather
  than importing the new function — the same reason its price table is
  transcribed — so a domain widened by mistake still fails the sweep, and its
  live-pool loop now catches the raise and reports it instead of aborting
  mid-sweep. Three probes drive the raise itself: the `+ PB` state that
  actually shipped, the daily-domain bound, and the converse that a feed
  publishing a subset of the buildable labels must **not** raise.
  Red-tested both ways (LOTTO-0001 §7): guard disabled → 2 probes `NO RAISE`,
  exit 1; direction reversed to set equality → `FALSE RAISE` plus 6 unreachable
  divisions across three live pools, exit 1. The pending markers are off §4.4,
  §5, §6 and §11, and §7 now records the red test. `./local-CI.sh` PASS,
  `python3 check.py` unchanged at R2,731.60 claimable.

- ✅ **LOTTO-0027** The API's PowerBall division labels never matched, so 53 wins read as losses.
  Kind: fix. Source: in-session-2026-08-03, found while writing LOTTO-0026's
  spec amendment — the grammar was read off the live feed rather than out of
  the document, and the document was wrong.
  Layman: every PowerBall prize that needed the PowerBall number itself was
  reported as "did not win". The tool was asking for a prize category spelled
  a way the lottery does not spell it.
  `check.py::api_label()` built `MATCH 5 + PB`, and `MATCH 0 + PB` for a line
  matching only the PowerBall. The feed publishes `MATCH 5 + POWERBALL`, and
  names the PowerBall-only division `MATCH POWERBALL` — no digit, no `+`.
  `check()`'s pay gate is `if api_label(...) not in pays: continue`, so every
  such line continued past as a loss, with no error anywhere and no figure on
  the page distinguishing it from a real miss.
  **This is LOTTO-0026's failure, already arrived** — and the guard approved
  for that item would not have caught it: the plain `MATCH n` labels still
  conformed to the grammar, and only the PowerBall-qualified ones had moved.
  That is why LOTTO-0026's rule became *reachability* rather than conformance,
  decided with the user 2026-08-03.
  Measured on the current dump: **86 → 139 wins**, lifetime R2,650.60 →
  R3,213.30, claimable 62 lines / R2,417.90 → 92 lines / R2,730.40. Nothing
  was repriced — 53 wins that were there all along are now reported. The
  archive branch needed no change: `site_label()` already built the payout
  table's own `0 + PowerBall` grammar, so these lines priced correctly the
  moment the gate stopped dropping them.
  Red-tested first, per the project's rule that a case is observed failing
  before it is trusted: the new division-label reach case in
  `tools/verify_pools.py` reported 12 unreachable divisions across the two
  PowerBall pools and exited 1 against the shipped labels, 0 after the fix.
  Its direction is load-bearing and stated at the site — every *feed* division
  must be buildable, never the converse, since `api_label()` legitimately
  builds `MATCH 6` for Daily Lotto and `MATCH 0` for a line that hit nothing.
  Noted, not chased: the pre-fix lifetime measured R2,650.60 today against the
  R2,651.60 recorded on 2026-08-02, one win R1.00 apart. `results.py` holds
  divisions in memory only, so API prize amounts are re-read every run and are
  not frozen the way the archive cache is; an operator-side revision fits, and
  it predates this change either way.
  LOTTO-0001 §4.4's grammar table had the wrong API column and is corrected
  from the live feed; §7 and §11 follow.
  Left alone deliberately: `docs/specs/LOTTO-0002-local-web-page.md` §7's
  worked example and its figure table are a dated snapshot of one run
  (R2,651.60 lifetime, 86 wins) and now understate by these 53 wins. They
  illustrate what the page displays rather than stating a contract, so they
  are refreshed the next time that document is gated rather than edited here
  — an edit would owe it a cold-eyes loop of its own for no design benefit.

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

- ✅ **LOTTO-0017** INV-19 says "no Qt" but cannot see a PyQt import.
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
  Resolved 2026-08-12: the probe predicate gained a third arm —
  `re.fullmatch(r'Qt|PyQt\d*', top_level)` — so a `PyQt6.QtCore` import in
  `serve.py` or `supervise.py` now fails INV-19's case instead of passing it.
  Observed failing first, per the project's rule: `--break pyqt_import` appends
  a real `import PyQt6.QtCore` and the case reported PASS before the widening,
  red after. PyQt6 measured at 6.10.2 on this machine, so the breach was live.
  Two bullet claims did not survive checking and are corrected here: the break
  count went from **thirty to thirty-one**, not thirteen to fourteen (LOTTO-0019
  had added eight since this was written), and CLAUDE.md was already correct at
  thirty. LOTTO-0013 §5 and §11 updated in the same change; the §11 row now
  names both red-tests instead of naming the gap.

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

- ✅ [LOTTO-0023] **A win in a retired prize division is dropped silently, with no count.**
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
  Costed 2026-08-12 while picking the next item, and NOT built — the note
  is here so the next session does not redo the analysis. The bullet says the
  extra per-draw lookup is "already memoised per draw"; it is not memoised in a
  way that helps. `check.py::check()` drops a line at `if label not in pays`,
  and separating a retired-division win from a loss means consulting **that
  draw's own** division set. Every non-winning line reaches that branch, and a
  losing label ("MATCH 1") is absent from both sets, so the lookup cannot be
  bounded to near-wins — `buildable_labels(game) - set(pays)` contains every
  losing label too. So the honest implementation fetches one division table per
  (pool, draw) actually scored: `divisions()` for API draws, and
  `backfill.payouts()` — a page scrape per draw DATE — for archive ones. Daily
  Lotto alone draws nightly since 2025-01-01, so that is several hundred new
  payout-page fetches on a cold cache, against today's zero (the table is
  fetched only when a line has already won).
  That does not kill the item, but it makes the scope question in the bullet a
  real design decision with a fetch budget attached, not a "count is probably
  the whole fix" tidy-up. Two ways out worth weighing first: confine the check
  to archive-era draws (the handover is the only division-structure break known
  to exist, and LOTTO-0026 already raises on a mid-API-era grammar move), or
  compare division SETS per pool-era once rather than per line. Either wants
  deciding before code.
  Resolved (2026-08-12) as INV-31, after the user chose "flag it, don't
  price it" over scoring such wins. `check.py::retired_divisions()` compares
  each pool's archive-era division structure against the current set,
  `retired_report()` names any gap, and `tools/verify_pools.py` sweeps every
  live pool with three probes.
  **The costing note above was right that a per-line answer is unaffordable,
  and wrong about what the question is.** It is structural, not per-line:
  what moves at a handover is a pool's division set, so the last archive
  draw before the break samples the era that ended — six payout pages, one
  per live pool, cached thereafter, against the several hundred a per-(pool,
  draw) lookup needed. That reframing is what made the item buildable
  without a scope decision about fetch budget.
  **The finding that matters: there is no retired division.** All six live
  pools compare clean. The premise LOTTO-0023 was filed on — "if one exists,
  nothing says so" — held, but no instance existed, and now something says
  so. That is why the report is pool-level: with no gap there are no dropped
  lines to count, and counting them is the follow-up worth building once
  there is something to count.
  **A near-miss worth recording, because it nearly shipped backwards.**
  Lotto archive pages spell Division 8 as `2 + Bonus` on some draws and a
  bare `2` on others, and all three Lotto pools sample a bare-`2` page. Read
  as a distinct "Match 2" division, the check reports a retired division on
  every Lotto pool and flags every match-2-without-bonus line in the archive
  era as a possible win — a loss reading as a win, the cardinal failure
  inverted. Settled from the pages themselves rather than by reasoning: both
  shapes state "eight prize divisions" in prose and carry exactly eight
  rows, so it is one division inconsistently labelled. `amount()` already
  leaned on that equivalence from the other direction, though its comment
  described it as a structural difference rather than a labelling one.
  Both failure directions were observed red before the case was believed: a
  detector stubbed to return nothing misses both gap probes, and the
  ambiguity rule deleted reports a false gap on all three Lotto pools.
  `./local-CI.sh` PASS on both lanes.
  **Gate owed:** LOTTO-0001 gained INV-31 and a rewritten §11 row, which is
  an authoring edit under global rule 14, so `review-contract` on that spec
  has not yet run.
  **Still owed, and now larger — updated 2026-08-13.** The user was asked and
  chose to defer it again, on the standing argument that the document is past
  the size a cold read covers (its own loop-9 log says so). Since then §4.1 has
  been substantially rewritten twice by LOTTO-0030: the adb `WHERE` clause and
  its two `NOT LIKE` exclusions, the VAS-is-not-lottery reasoning, the
  asynchronous-`activeConversations()` warning, and — the part that most wants
  a cold read — a **weakened guarantee**, where "only lottery messages ever
  cross to the PC" became the narrower claim the filter can actually make.
  A downgraded guarantee is exactly the kind of change a gate exists to catch,
  so whoever runs it should start there. The split argument is unchanged and
  still the user's call.
