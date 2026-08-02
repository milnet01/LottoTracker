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

- 📋 **LOTTO-0002** Local web page showing tickets, results and claimable winnings.
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

- 📋 **LOTTO-0014** The local page's HTTP surface and security boundary.
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

- 📋 **LOTTO-0013** Tray icon and server supervisor for the local page.
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
  (a) an unscrapable payout page prices every archive-era win at R0.00
  instead of raising, unlike `paying_combinations()` which does raise —
  **do this one first: it is the project's cardinal rule ("no data must never
  read as did not win") violated by shipped code, on a money path, and every
  other item in this list is cosmetic beside it. R0.00 is indistinguishable
  from a real losing line in `check.py`'s output;**
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
