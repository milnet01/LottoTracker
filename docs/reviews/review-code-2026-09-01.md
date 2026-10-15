# review-code sweep of 2026-09-01 — record

**Written 2026-10-15, from surviving evidence. This is NOT a contemporaneous
record.** The sweep left no record file (LOTTO-0059). Everything below is read
from the ROADMAP items the sweep filed and the commits that closed them. Where
that evidence does not support a figure, this file says so instead of
reconstructing one.

## Sources

- **LOTTO-0050** and its commit `12db7b8` (2026-09-01): the sweep's own
  summary, and the closure of every CRITICAL and HIGH.
- **LOTTO-0040 to LOTTO-0049**: one item per lane, each holding that lane's
  MEDIUM and LOW tail and, once closed, how each was resolved.
- The commits that closed them: `7fd8323`, `ad81a4f`, `2d055a3`, `68281de`,
  `e45dba8` (`git log --oneline --grep='LOTTO-004[0-9]'`).
- **`.ants_review_falsepos.jsonl` holds nothing from this sweep.** Every entry
  is `review_kind: "audit"` — `check-code` runs of 2026-08-31 and 2026-09-01 —
  and none names one of this sweep's lanes.

## What the sweep was

Ten lanes, one subsystem each, over production code, each briefed against its
own contracts. LOTTO-0050 states the size as 4,322 lines and the yield as
"about 130 findings"; nothing on disk records how either was measured. It also
states that all ten lanes re-read `CLAUDE.md` from disk and found the injected
copy identical.

**Totals stated by LOTTO-0050:** 3 CRITICAL and 15 HIGH, all fixed in
`12db7b8`. Two MEDIUMs were calibrated up to HIGH against this project's
partially sighted user and fixed with them: both settings switches had an empty
accessible name, and every tray notification carried the success icon.

## Per lane

The CRITICAL and HIGH figures are read from each lane item's opening sentence.
Summed across lanes they give LOTTO-0050's 3 and 15. "Dismissed" lists only
what an item body records; see § What is not known.

| Lane | Item | CRITICAL | HIGH | Tail closed in | Dismissed, as recorded |
|---|---|---|---|---|---|
| sms-parsing | LOTTO-0040 | 0 | 1 — the uncaught `ValueError` family | `7fd8323` | the dump being read twice per run |
| results-sources | LOTTO-0041 | 0 | 3 — retry arms, atomic writes, `parse_page` shape validation | `ad81a4f` | none |
| scoring-and-pricing | LOTTO-0042 | 0 | 0 | `2d055a3` | none |
| build-and-periods | LOTTO-0043 | 0 | 0 | `68281de` | two clock reads across a build |
| page-renderer | LOTTO-0044 | 1 — three empty states rendering R0.00 | 3 — the poll (two) and the pool filter; the switch labels were calibrated up | `68281de` | en-US money grouping; one cited figure (12.75px) corrected |
| http-security | LOTTO-0045 | 1 — request smuggling past the Host allowlist | 2 — the inert timeout, the 501 path | `68281de` | none; one contract question settled by the user 2026-09-02 |
| supervisor-lifecycle | LOTTO-0046 | 0 | 1 — the state file truncated in place | `68281de` | none |
| sms-watcher | LOTTO-0047 | 1 — `SystemExit` escaping both guards | 1 — `--once` hanging forever | `e45dba8` | none |
| tray-calendar-tools | LOTTO-0048 | 0 | 2 — `sys.exit` in a library function, the orphan window at startup; the notification icons were calibrated up | `e45dba8` | the tray's done-signal thread, refuted by measurement |
| shell-gate | LOTTO-0049 | 0 | 2 — the docs-only push skipping the privacy check, the pre-push hook discarding git's ref protocol | `e45dba8` | the empty-array expansion under `set -u` on bash 3.2 |

Two items state their own tail size: LOTTO-0041 *"All eight findings fixed"*
and LOTTO-0042 *"All seven findings fixed"*. The others say every finding was
fixed, documented or dismissed without giving a number. Their bullets group
several LOW findings in one line, so counting bullets would not give one.

Items the tail moved elsewhere rather than closing: the forged-record boundary
in `rows()` became LOTTO-0061, the timezone question LOTTO-0066, library use at
the version floor LOTTO-0065, and two document defects LOTTO-0053 and
LOTTO-0054.

## What is not known

- **Findings per lane.** Only the total, "about 130", survives. No per-lane
  count was recorded.
- **Verified against raw.** Nothing records how many findings each lane
  returned before verification, or how many verification dismissed. The
  dismissals above were all made later, while closing the filed tail.
- **Whether "about 130" counts before or after verification.** LOTTO-0050
  does not say.
- **Lane spend and brief contents.** Not recorded.

## Why this file exists

Without it, the sweep's claims about itself — every lane item opens by saying
its CRITICAL and HIGH findings were closed — were checkable only against
LOTTO-0050 and git, both written by the session that ran the sweep. This file
cannot repair that: it is written from those same sources. What it adds is one
place that states what survives and what does not. Every `review-code` sweep
from now on leaves its own record here (`CLAUDE.md` § Working conventions).
