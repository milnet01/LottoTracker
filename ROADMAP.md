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
  instead of raising, unlike `paying_combinations()` which does raise;
  (b) `backfill.py::parse_page()` raises `KeyError` on an abbreviated month
  in a href rather than skipping the row;
  (c) INV-5's grep sees only a double-quoted `"MATCH <digit>` literal — it
  cannot see the label grammar in `api_label()`/`site_label()`, so a
  feed-side rename of `MATCH n` would drop every win silently;
  (d) Multiplay expansion is Lotto-only; a >6-number PowerBall or Daily
  board would silently collapse to one line (no such ticket exists today);
  (e) §8's "~30 lookups a month" is not recomputed from §10's request model.

- 💭 **LOTTO-0006** Backfill results earlier than 2025-01-01.
  Kind: enhancement. Source: in-session-2026-08-01.
  Layman: check really old tickets too.
  Low value: prizes expire after 365 days, so these can no longer be claimed.
  Note the 2025-01-01 floor is a configured default in
  `backfill.build(years=(2025, 2026))`, not a limit of the archive itself.
