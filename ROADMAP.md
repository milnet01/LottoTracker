# ROADMAP — LottoTracker

Status keys: 📋 planned · 🚧 in progress · ✅ shipped · 💭 considered

## Core

- ✅ **LOTTO-0001** Parse Standard Bank ticket SMSes and score them against real draws.
  Kind: implement. Source: user-request-2026-08-01.
  Layman: the PC reads your lottery texts and tells you whether any won.
  Spec: `docs/specs/LOTTO-0001-lottery-ticket-tracker.md`.
  Covers both SMS eras, both results sources, Multiplay expansion and prize
  pricing. 558 tickets parsed, 132 checkable (the rest predate all draw
  data); R800.20 found still claimable.

- 📋 **LOTTO-0002** Local web page showing tickets, results and claimable winnings.
  Kind: implement. Source: user-request-2026-08-01.
  Layman: a page in your browser instead of a wall of terminal text.
  Chosen by the user over a desktop app or CLI. Should show live tickets with
  draws remaining, wins with their expiry dates, and a claimable total.

- 📋 **LOTTO-0003** Pick up new tickets automatically as the SMS arrives.
  Kind: implement. Source: user-request-2026-08-01.
  Layman: new tickets appear by themselves, without plugging the phone in.
  KDE Connect emits `conversationCreated` / `conversationUpdated` over D-Bus;
  subscribe rather than polling.

## Hardening

- 📋 **LOTTO-0004** Automated guard that no SMS content can be committed.
  Kind: security. Source: in-session-2026-08-01.
  Layman: make it impossible to accidentally publish your messages.
  INV-4 is currently checked only by a command someone must remember to run.
  A pre-commit hook would make it structural.

- 💭 **LOTTO-0005** Support other banks' ticket SMS formats.
  Kind: feature. Source: user-request-2026-08-01.
  Layman: let people at other banks use this too.
  Only `tickets.py::parse()` is bank-specific. Needs a sample message per
  bank; see the "Adding your bank" section of README.md.

- 💭 **LOTTO-0006** Backfill results earlier than 2025-01-01.
  Kind: enhancement. Source: in-session-2026-08-01.
  Layman: check really old tickets too.
  Low value: prizes expire after 365 days, so these can no longer be claimed.
  Would only serve historical curiosity.
