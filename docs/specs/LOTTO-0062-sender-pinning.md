<!-- ants-spec-format: 1 -->
# LOTTO-0062 — Flag a lottery SMS from a sender not seen before

**Status:** accepted (2026-10-15).
**Kind:** security.
**Source:** ROADMAP LOTTO-0062 (in-session-2026-09-02, found while building
LOTTO-0061's import filter). The scope decisions in §3 were taken with the
user on 2026-10-08.

**Pairs with:** LOTTO-0029 (payout reconciliation, whose rule that a
disagreement is never resolved in the SMS's favour is the real containment)
and LOTTO-0001 (the purchase parser).

*Layman: if a lottery text arrives from someone other than the bank, the app
keeps it but tells you, so a fake message cannot quietly add a ticket or a
win.*

## 1. Goal

After this ships, every purchase and payout the app reads carries the sender
it came from, checked against the senders the bank is known to use. One from
any other sender is still counted, and is listed on the page and in
`check.py`'s output as coming from a sender not seen before. Nothing is ever
dropped on sender grounds.

## 2. Problem

`tickets.py::parse()` and `tickets.py::parse_payout()` decide on the message
body alone. `tickets.py::rows()` returns the sender as the first element of
each triple, and both `tickets.py::load()` and `tickets.py::load_payouts()`
discard it (`for _address, date_ms, body in rows(raw)`).

1. **A forged payout inflates "the bank paid".** Anyone who can deliver an SMS
   to the phone can send text matching `tickets.PAYOUT`. `check.reconcile()`
   never resolves a disagreement in the message's favour, so a forgery is
   never adopted as money the app believes. It
   still adds noise to the figure sign 5 is judged by.
2. **A forged purchase adds a ticket never bought.** It is scored, priced into
   spend, and counted by the re-buy warning (LOTTO-0034).
3. **Nothing shows either.** The page and the terminal give no sign of where
   a message came from.

**What the dump holds.** Measured 2026-10-15 against the live dump, over the
records that parse as a purchase or a payout:

```bash
python3 - <<'EOF'
import re, collections, tickets, clock
norm = lambda a: re.sub(r"[^A-Z0-9]", "", a.upper())
c = collections.Counter()
for a, ms, b in tickets.rows(open("lotto_sms_raw.txt", errors="replace").read()):
    if tickets.parse(b, clock.from_ms(ms)) or tickets.parse_payout(b):
        n = norm(a)
        c["digits/len%d/%s" % (len(n), n[:5]) if n.isdigit() else "name/len%d" % len(n)] += 1
print(sorted(c.items()))
EOF
```

- **Since 2024-09-06** records come from an alphanumeric sender ID. Its
  three spellings in the dump differ only by a trailing space or newline, and
  all collapse to the one token `STDBANK` once uppercased with every
  non-alphanumeric character removed.
- **Up to 2025-02-26** records came from numeric senders: a different number
  almost every message, every one sixteen digits after the `+`, all sharing
  the prefix `27839`. An exact-number allowlist could never have worked for
  that era.

**An SMS sender ID is not an authentication boundary.** Whoever can deliver a
message to the phone can usually set the sender to any name. This item makes a
forgery visible; it does not make one impossible.

## 3. Scope decisions (agreed with the user)

- **Kept and flagged, never dropped** — the user, 2026-10-08. A bank renaming
  its sender must not silently stop imports, which is the failure this project
  cares most about.
- **Both message kinds are checked**, purchases and payouts — the user,
  2026-10-08. A forged purchase adds a ticket never bought.
- **Flagged on the page and in `check.py`'s output, never in a desktop
  notification** — from the 2026-10-08 plan, under `CLAUDE.md` § Privacy: a
  notification may be logged and synced off the machine.
- **The legacy numeric rule is closed at a date** — the author's call,
  confirmed by the user 2026-10-15. A
  number matching the legacy pattern received on or after
  `LEGACY_UNTIL` is flagged. The era ended 2025-02-26; leaving it open would
  accept any forger who picks a sixteen-digit `+27839` number.
- **A new name is added by hand** to `KNOWN_SENDERS`, once the user has seen
  it flagged and judged it the bank's. Nothing learns senders by itself: a
  forger's first message would teach the app to trust the forger.

## 4. Design

### 4.1 The rule, in `tickets.py`

```python
# Read off the dump on 2026-10-15 (LOTTO-0062 §2). A new name the bank starts
# using is added here by hand, after the page has flagged it.
KNOWN_SENDERS = frozenset({"STDBANK"})
LEGACY_PREFIX = "27839"          # the numeric era's shared prefix
LEGACY_DIGITS = 16               # every numeric sender's length, after "+"
LEGACY_UNTIL = datetime(2025, 3, 1)   # naive SAST; exclusive

def normalise_sender(address: str) -> str:
    """Uppercase, every non-alphanumeric character removed."""

def sender_known(address: str, received: datetime) -> bool:
    """True when the normalised address is in KNOWN_SENDERS, or is
    LEGACY_DIGITS digits starting LEGACY_PREFIX and `received` is before
    LEGACY_UNTIL. False otherwise, including for an empty address."""
```

`received` is the dump row's timestamp through `clock.from_ms()`, the same
value `load()` passes to `parse()` as `bought`. The phone sets it on receipt,
so a sender cannot choose it.

### 4.2 Carrying it

`Ticket` and `Payout` each gain two attributes, set to `None` by their
constructors: `sender` (the normalised address) and `sender_known`.
`tickets.load()` and `tickets.load_payouts()` set both on every record they
return, from the row's address and timestamp. `None` therefore means a record
built outside `load()` — a fixture — and never "known".

The record is returned whatever `sender_known` says. Neither loader filters on
it, and neither does `parse()` or `parse_payout()`, which never see the
address.

### 4.3 Listing the unknown ones, in `check.py`

```python
def unknown_senders(tickets, payouts) -> list[dict]:
    """Every record whose sender_known is False, oldest first:
    {"kind": "purchase" | "payout", "received": "YYYY-MM-DD",
     "ref": str, "sender": str}. Pure; reads no file."""
```

A record with `sender_known is None` is not listed. `check.py`'s `__main__`
prints, when the list is non-empty and before the wins:

```
FROM A SENDER NOT SEEN BEFORE - still counted below. If it is the bank,
add the name to tickets.KNOWN_SENDERS; if not, treat the record as forged.
  2026-10-14  payout    VAS00000000000  from SOMEONEELSE
```

`ref` and `sender` go through `terminal_safe()`, as every other third-party
string printed there does. An empty list prints nothing.

### 4.4 The page

`serve.build_model()` calls `tickets.load_payouts(DUMP)` and adds
`"unknown_senders": check.unknown_senders(all_tickets, payouts)` to the model.
`page.py` gains `_senders_section(model)`, rendered in the full body directly
after `_notice(model)`. When the list is non-empty it renders a notice headed
*From a sender not seen before*, one row per record (date, kind, reference,
sender, each through `_e()`), and the sentence *These are still counted on
this page. If one is the bank, it has a new sender name; if not, the message
was not from the bank.* When the list is empty, or the key is absent, it
renders the empty string.

`page.py` stays pure: the section reads only the model.

### 4.5 What does not change

- **The admission filter.** `watch_sms.py::INCLUDE` and LOTTO-0001 §4.1's adb
  clause still admit on wording. The sender check is at read time, so a
  message from a new sender is in the dump and can be flagged.
- **`check.reconcile()`.** A payout from an unknown sender is reconciled like
  any other. LOTTO-0029 INV-43 is the containment.
- **Every desktop notification.** `supervise.new_ticket_notice()` takes `(running, busy)` and
  LOTTO-0003 INV-37 holds its wording; the re-buy notice's content is
  LOTTO-0034 INV-54's.

## 5. Invariants

The trust boundary is the SMS sender, which the sender controls. The defences
this design must preserve are LOTTO-0029 INV-43 (a disagreement is never
resolved in the SMS's favour) and `CLAUDE.md` § Privacy's rule that a desktop
notification carries no ticket data.

- **INV-72** — `tickets.normalise_sender()` uppercases and removes every
  non-alphanumeric character, so `"StdBank "`, `"STDBANK\n"` and `"stdbank"`
  all return `"STDBANK"`, and `"+27839…"` returns the digits alone.
  *Test:* `tools/verify_senders.py`, case `spellings_collapse`; break
  `normalise_case_only`, which uppercases without stripping.
  *Breaks when:* the normalisation keeps a trailing space or newline, which
  splits the current sender into the three spellings the dump holds and flags
  two of them.

- **INV-73** — `tickets.sender_known()` returns `True` for exactly two shapes:
  a normalised address in `KNOWN_SENDERS`, and `LEGACY_DIGITS` digits starting
  `LEGACY_PREFIX` received before `LEGACY_UNTIL`. The fixtures are passed
  already normalised — digits with no `+` — so the case reads the rule and not
  the normalisation INV-72 owns. Each isolates one condition: the known name (`True`); another name (`False`); an empty
  address (`False`); a legacy number on 2025-02-28 (`True`); the same number on
  2025-03-01 (`False`); a fifteen-digit number with the prefix before the
  cutoff (`False`); a sixteen-digit number with another prefix before the
  cutoff (`False`); a sixteen-character address starting `27839` and holding a
  letter, before the cutoff (`False`).
  *Test:* `tools/verify_senders.py`, case `accept_rule_is_exact`; breaks
  `legacy_any_date` (drops the date condition) and `prefix_only` (drops the
  length condition).
  *Breaks when:* any one condition is dropped — each fixture fails only the
  condition it isolates.

- **INV-74** — A sender never drops a record. `tickets.load()` and
  `tickets.load_payouts()` return one record for every row `parse()` or
  `parse_payout()` accepts, whatever its sender, and every record they return
  carries a `bool` `sender_known`.
  *Test:* `tools/verify_senders.py`, case `unknown_is_kept`: a temporary dump
  holding one purchase and one payout, each from an unknown sender, loads as
  one ticket and one payout, each with `sender_known is False`. Break
  `drop_unknown`, which filters the loaders on `sender_known`.
  *Breaks when:* a loader filters on the sender, which turns a bank renaming
  its sender into imports silently stopping.

- **INV-75** — A record from an unknown sender is shown on both surfaces.
  `check.unknown_senders()` lists it; `page._senders_section()` renders its
  date, kind, reference and sender; `check.py`'s `__main__` prints it. An
  empty list renders and prints nothing.
  *Test:* `tools/verify_senders.py`, case `unknown_is_shown`: the pure
  function over a fixture, the page section over a hand-authored model, and
  the empty case for both. Break `section_silent`, which makes
  `_senders_section()` return the empty string.
  *Breaks when:* a surface omits the list, or renders a heading for an empty
  one — the second reads as an alarm with nothing behind it.

- **INV-76** — *Withdrawn 2026-10-15, before it was built.* It asserted that
  every record in the live dump comes from a known sender. `tools/verify_payouts.py`
  prints the counts it takes from real data rather than asserting them, and one
  forged SMS would have blocked every push for good. The census prints the
  count instead (§7).
  *Test:* none — withdrawn.
  *Breaks when:* not applicable.

## 6. Failure modes

- **The bank changes its sender name.** Every new record is flagged and still
  counted. The page says so. The user adds
  the name to `KNOWN_SENDERS`.
- **A forger uses the bank's own name.** Not caught; §2 says why it cannot be.
  LOTTO-0029 INV-43 still holds the payout side.
- **A forged purchase.** Flagged, and still counted by the re-buy warning
  (LOTTO-0034), which may then warn about a ticket never bought. The flag is
  on the page, not in the warning, by the notification rule.
- **The address field is empty or malformed.** `rows()` reads it as
  `([^,]*)`, so the worst case is an empty string, which `sender_known()`
  returns `False` for. The record is kept and flagged.
- **A comma in a sender name.** `watch_sms.py::format_row()` replaces it with
  a space, which `normalise_sender()` then removes, so the name still matches.
  An adb-imported record whose address holds a comma does not match `rows()`
  at all and is dropped before any sender check; that is existing behaviour,
  unchanged here. Not seen in the dump.

## 7. Tests

One new verifier, `tools/verify_senders.py`, on the CI lane: it reads no dump,
building a temporary one for `unknown_is_kept`. It follows
`tools/verify_payouts.py`'s shape — named cases, the exit code as the signal,
`--break <name>` and `--list`. This item is greenfield, so each case is
observed red under its own break rather than against pre-fix code.
`tools/verify_payouts.py`'s census, on the local lane, also prints how many
records in the live dump come from an unknown sender, and asserts nothing about
that count.

| Case | File | Locks |
|------|------|-------|
| `spellings_collapse` | `tools/verify_senders.py` | INV-72 |
| `accept_rule_is_exact` | `tools/verify_senders.py` | INV-73 |
| `unknown_is_kept` | `tools/verify_senders.py` | INV-74 |
| `unknown_is_shown` | `tools/verify_senders.py` | INV-75 |
| `unknown_sender_never_pays` | `tools/verify_senders.py` | LOTTO-0001 INV-77 |

`unknown_is_shown` checks `check.py`'s `__main__` output only through
`unknown_senders()`, which it prints; the print loop itself is not executed.

## 8. Alternatives considered (and rejected)

- **Drop a message from an unknown sender.** Rejected by the user: a bank
  renaming its sender would stop every import with no signal.
- **An allowlist of exact numbers for the legacy era.** Cannot work: the era
  used a different number almost every message (§2).
- **Learn senders automatically** — trust a name after its first message.
  Rejected: the forger's first message is the one that must be flagged.
- **Show the flag in a desktop notification.** Rejected under `CLAUDE.md` §
  Privacy; a notification may leave the machine.
- **Leave the legacy rule open-ended.** Rejected (§3): the era is over, and an
  open rule accepts any sixteen-digit `+27839` number forever.

## 9. Out of scope

- Authenticating the bank's messages. Not possible over SMS (§2).
- Excluding flagged purchases from the re-buy warning or flagged payouts from
  reconciliation — deferred; not yet queued. The user's decision keeps them
  counted. A flagged payout never marks a win paid: LOTTO-0001 INV-77 (the
  user, 2026-10-15).

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-72 | `tools/verify_senders.py::spellings_collapse` |
| INV-73 | `tools/verify_senders.py::accept_rule_is_exact` |
| INV-74 | `tools/verify_senders.py::unknown_is_kept` |
| INV-75 | `tools/verify_senders.py::unknown_is_shown` |
| INV-76 | withdrawn; the count is printed by `tools/verify_payouts.py`, not asserted |
| No notification carries a sender (§4.5) | **Partial:** LOTTO-0003 INV-37 and LOTTO-0034 INV-54 check the wording of today's notices; nothing stops a new notice being given a record |
| `check.py`'s `__main__` print loop (§4.3) | **nothing** — no verifier runs `check.py` as a script |

## 11. Cross-doc impact

- `CLAUDE.md` § Privacy — none; the notification rule already covers this.
- `.claude/rules/verifiers.md` — add `tools/verify_senders.py` to the
  catalogue and the CI lane; `local-CI.sh` runs it and its header's lane list
  names it.
- `.claude/rules/architecture.md` — the `tickets.py` note gains the sender
  check, and that it filters nothing.
- `LOTTO-0002` §4.1 — the model gains `unknown_senders`; §4.5 gains the
  section.
- `LOTTO-0029` — none; reconciliation is unchanged.
- `CHANGELOG.md` — a Security entry citing LOTTO-0062.

## 12. Cold-eyes loop log

Rows live in `../reviews/LOTTO-0062-sender-pinning-loop-log.md`.
