# LOTTO-0001 — cold-eyes loop 7 run state (2026-08-03)

**Status: CLOSED.** All 19 distinct findings (both lanes, merged) were verified
against current files, all 19 verified true, all 19 fixed, 0 dismissed.

The permanent record is **§13 of
`docs/specs/LOTTO-0001-lottery-ticket-tracker.md`**, loop 7's row — it carries
the grades, the CRITICAL, the two code-side fixes and the reasoning. This file
existed only so the lane spend would survive a session window; it did, and it
has nothing left to say that §13 does not say better.

Two things worth carrying forward rather than re-deriving:

- **The fork is settled.** INV-26's runtime raise is marked *pending* in §4.4,
  §5, §6 and §11 rather than step 2 being landed first, because three of loop
  7's own findings were the contract holes step 2 must build against. The
  markers come off with step 2.
- **Loop 8 must run cold** — un-briefed, per the re-brief rule. Do not hand it
  this file or §13's row. An issue not raised again is the proof the fix held.
