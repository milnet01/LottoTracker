<!-- ants-spec-format: 1 -->
# LOTTO-0104 — Let the user accept a win the bank has not fully paid

**Status:** shipped 1.0.0 (2026-11-18).
**Kind:** feature.
**Source:** ROADMAP LOTTO-0104 (user-request-2026-11-18, made while reviewing
the LOTTO-0100 mock-up). The scope decisions in §3 were taken with the user on
2026-11-18.

**Pairs with:** LOTTO-0002 (the page, whose INV-70 decides what *Not yet paid*
lists), LOTTO-0014 (the HTTP surface, which this spec widens by one route) and
LOTTO-0029 (reconciliation, whose rule that the bank's figure never replaces
the app's is untouched).

*Layman: a prize the bank paid short, or never paid, can be marked as accepted,
and the app stops flagging it.*

## 1. Goal

After this ships, every win under *Not yet paid* carries an **Accept** button.
Pressing it moves the win to a new section, *Accepted by you*, stamped
*Accepted*, with an **Undo** button that moves it back. An accepted win no
longer counts in the Overview's "waiting on the bank" figure. The choice
survives a refresh, a restart and a new build. Nothing else on the page
changes: the bank's record, the spend and winnings totals, and every figure
the app worked out stay exactly as they are.

## 2. Problem

`page.py::_waiting()` lists every unexpired win whose `payment` is not
`paid` — `unpaid`, `partly paid` and `unknown` — under *Not yet paid*, and
`page.py::_glance_wins()` counts the same list on the Overview. A win stays
there until it is paid or its claim date passes, `check.CLAIM_DAYS` after the
draw (`check.py::claim_deadline()`).

Some of those wins will never be paid, and the user knows it: a small
prize the bank settled short, or one they chose not to chase. Today the page
keeps flagging it for a year, and the count on the Overview never falls to
what the user still cares about. The user, 2026-11-18: "I should be able to
accept draws where the app says the bank hasn't fully paid me and thus it
doesn't need to be highlighted anymore."

## 3. Scope decisions (agreed with the user)

Shown as a mock-up of the Wins tab and agreed by the user on 2026-11-18:

1. **Accepting moves a win, never removes it.** Accepted wins sit in their own
   foldable section, *Accepted by you*, under *Paid by the bank*, stamped
   *Accepted*, each with **Undo**. Hiding them entirely was offered and
   declined: nothing could then show or undo what was accepted.
2. **An accepted win leaves the Overview's "waiting on the bank" count.**
3. **The bank's record keeps the bank's figure.** Accepting is the user's
   choice not to chase a win. It is never the app deciding the win was paid.
4. **It ships with the redesign, before 1.0** (LOTTO-0100, LOTTO-0101).
5. **A reload keeps the open tab; a fresh visit opens on the Overview.**
   Asked after the review surfaced that a reload after Accept lands on the
   Overview; the user chose this over moving the row with no reload, and
   over leaving it. It helps every reload, a Refresh's included.

Decided by this spec, not the user:

6. **Any win under *Not yet paid* can be accepted**, `unknown` payment
   included. That section is where the button sits, and an unknown payment is
   the same choice not to chase.
7. **A fifth route, `POST /accept`**, rather than a wider `POST /settings`
   (§8).

## 4. Design

### 4.1 What names a win

A win is one board line of one ticket, in one pool, in one draw:
`check.py::check()` appends one record per board per draw it pays. Its key is
the six fields that record carries for that:

```
ref, game, plus_flag, pool_id, line, date
```

All six are already in every win in the model (`serve.py::build_model()`
copies `check.py`'s records whole). The key holds no amount, so a price
correction (LOTTO-0001 INV-90's estimates) does not orphan an acceptance.

### 4.2 The store

`accepted.json`, at `paths.ACCEPTED` in `paths.DATA`, holding one object:

```json
{"version": 1, "accepted": [{"ref": "…", "game": "…", "plus_flag": 0,
  "pool_id": 0, "line": "A", "date": "YYYY-MM-DD"}]}
```

- **One writer**: `serve.py`, behind `POST /accept`, under a lock held across
  the read, the change and the write, for LOTTO-0014 §4.1's reason for
  `POST /settings`. Written through `supervise.write_atomic()`, a temporary
  file renamed over the old one, so a crash leaves the old file or the new,
  never half of either.
- **One reader**: `serve.py`, on every `GET /`. An acceptance takes effect at
  the next page load, with no rebuild, as `serve.running_view()` does.
- **It holds ticket references**, so it is personal data. In a source
  checkout `paths.DATA` is the repository root, so **`.gitignore` names
  `accepted.json*`**, beside `lotto_sms_raw.txt`. The `*` covers the
  temporary file `write_atomic()` leaves beside the store when a write fails.
- **`serve.py` reads it through a module alias, `ACCEPTED = paths.ACCEPTED`**,
  looked up at each call, as `serve.DUMP` is. `verify_page.py`'s
  `temp_home()` gains a line pointing that alias into its temporary
  directory, so a case
  calling it gets its own store: in a source checkout `paths.DATA` is the
  repository, and the real store would otherwise be written.
- **An entry whose win is gone is kept.** A win can leave the model for a
  build and come back; dropping its acceptance on the way would flag it again.
- **Unreadable or malformed means empty**, and the page says so (§6). That is
  the safe direction: a lost store flags wins again, it never hides one.

### 4.3 The route

`POST /accept` takes `{"win": <key>, "accepted": bool}`, where `<key>` is an
object holding exactly §4.1's six fields, the shape of a store entry.

- It follows every rule LOTTO-0014 sets for `POST /settings`: the `Host`
  allowlist, the run token, the bounded body read with its 4 KiB cap and its
  timeout, and a fixed response header set.
- `accepted: true` is allowed only for a win the current model lists under
  *Not yet paid* with the store applied, so a win already accepted is 409
  and the store holds each key once. `accepted: false` is allowed only for a win in the store.
  Anything else is **409**, and nothing is written. A body that is not that
  shape is **400**.
- The entry written is the matched model win's own six fields, never the
  posted values, and Undo removes the store's own entry. So no
  request-derived string is written (LOTTO-0014 INV-14).
- It returns **200** and `{"accepted": <count>}`, the number of entries now in
  the store. A count, never ticket data, for the reason `GET /status` carries
  only counts.
- The page reloads after a 200. A reload keeps the folds (LOTTO-0002 INV-115)
  and the open tab, and touches no URL (LOTTO-0014 INV-21). The tab is kept in
  `sessionStorage` under `lotto-tab`, holding a tab id the script checks
  against the tabs that exist. `sessionStorage` belongs to one browser tab, so
  a fresh visit, such as the tray opening the page, still starts on the
  Overview (LOTTO-0002 INV-93).

### 4.4 The page

At `GET /`, `serve.py` gives the view a copy of each win, with
`accepted: true` where its key is in the store; the stored model is never
changed. It sets `accepted_unreadable: true` when the file exists but cannot
be read; an absent file is an empty store. `page.py` stays pure and reads
only those two keys:

- `_waiting()` leaves out accepted wins, so *Not yet paid* and the Overview
  count both drop them. Where *Not yet paid* is empty and *Accepted by you*
  is not, both empty states read "No win is waiting on the bank that you have not
  accepted." LOTTO-0002 §4.5's sentence would be false there.
- A new fold, *Accepted by you* (`fold-accepted`), lists accepted wins that are
  unexpired and not paid, with the same cells as *Not yet paid*, a stamp
  reading *accepted*, and **Undo**. No row is marked for a near deadline. It renders only when it has a row.
- Each *Not yet paid* row gains **Accept**. Both buttons are real `<button>`
  elements and post through the page's existing `post()`. Each carries its
  win's key as JSON in one `data-win` attribute, which the script posts
  unchanged.
- A win the bank later pays is shown under *Paid by the bank* only. Its store
  entry stays and is unused.

## 5. Invariants

- **INV-116** — Accepting a win moves it from *Not yet paid* to *Accepted by
  you*, and removes it from the Overview's waiting count. Undo moves it back.
  No other figure on the page changes: *Bank's record*, the spend and
  winnings totals, and each win's amount render identically with the win
  accepted or not. With every waiting win accepted, both empty states say
  so (§4.4).
  *Test:* `tools/verify_page.py`, case `accepting_moves_a_win`. It renders one
  fixture model twice through `render_pure()`, once with a win flagged
  `accepted`, and compares the two pages with the *Not yet paid*, *Accepted
  by you* and Overview *Prizes* folds cut out: the rest must be byte-equal.
  The fixture's accepted win is `unpaid`, so only the accepted flag can move
  it. Break `accept_hides_bank_row`, which drops the accepted win's ticket
  from *Bank's record*. A second render, whose only waiting win is accepted,
  must carry §4.4's empty-state sentence twice. Case `accept_route_guards`
  checks the server's half: after the accept's 200, `GET /` lists the win
  under *Accepted by you* and not under *Not yet paid*, and after the undo
  the reverse.
  *Breaks when:* acceptance is applied by filtering the wins list before the
  model is rendered, which takes the win out of every section at once.
- **INV-117** — A paid win is never shown as accepted, and an expired win is in
  neither *Not yet paid* nor *Accepted by you*.
  *Test:* case `accepting_moves_a_win`, the same fixture with a second win
  `paid` and flagged `accepted`, and a third expired and flagged `accepted`.
  *Breaks when:* *Accepted by you* lists every flagged win.
- **INV-118** — `POST /accept` writes only a key naming a current win:
  accepting needs a win under *Not yet paid*, undoing needs a key in the store.
  Any other request is 409 or 400 and leaves the store's bytes unchanged. The
  route meets every rule LOTTO-0014 sets for `POST /settings`.
  *Test:* `tools/verify_page.py`, case `accept_route_guards`, over
  `serve_on()` with a stub builder serving a fixture model: an accept and an
  undo of a real win are 200; an accept of a paid win, an accept of a key
  matching no win, a second accept of the same win, an undo of a key not in
  the store and a body missing
  `accepted` are each refused with the store unchanged; and the request
  without the token is 403. The route joins the lists in LOTTO-0014's
  `host_allowlist`, `token_required` and `no_reflected_headers` cases. Break
  `accept_any_key`, which skips the current-win check.
  *Breaks when:* the route trusts the posted key, so any string reaches the
  store and is shown back on the page.
- **INV-119** — The store has one writer, lives at `paths.ACCEPTED`, holds win keys
  and nothing else, and is gitignored. An unreadable store reads as empty and
  the page says the accepted wins could not be read.
  *Test:* case `accept_route_guards` reads the file after the 200s and asserts
  its keys are exactly `version` and `accepted`, and each entry's exactly the
  six of §4.1; it then writes `{` into the file and asserts the next
  `GET /` lists the win under *Not yet paid* and carries the sentence.
  INV-120's grep holds the one writer to `serve.py`.
  `tools/verify_paths.py` asserts `paths.ACCEPTED` resolves under `paths.DATA`,
  and `git check-ignore -q` exits 0 for `accepted.json` and for
  `accepted.json.1.tmp`, one path per call. Break `store_unread_hides`,
  which reads an unreadable store as "accept everything".
  *Breaks when:* a corrupt file raises and the page fails, or reads as
  "accept everything".
- **INV-120** — No notification, log line or `GET /status` field carries
  anything from the store. Acceptance is shown on the page and nowhere else.
  *Test:* case `accept_route_guards` asserts `GET /status` is the same before
  and after an accept. Only the store's two owners name it:
  `grep -lE 'accepted\.json|\.ACCEPTED\b|^ACCEPTED =' *.py` → `paths.py` and
  `serve.py`; a module reaching the store through `serve.ACCEPTED` fails it.
  *Breaks when:* the tray learns to count accepted wins.

## 6. Failure modes

- **The store is unreadable** — malformed JSON, a wrong shape, a permission
  error. It reads as empty, every win is flagged again, and *Not yet paid*
  says: "Your accepted wins could not be read, so they show here again." The
  file is not rewritten until the next accept, so a hand-repaired file is not
  overwritten by a stale page.
- **Two pages accept at once.** The lock serialises them; each sees the
  other's write.
- **A write fails after validation.** 500, the store is unchanged (the
  rename never happened), and the page shows "Could not save that." in the
  bar.
- **Two wins share a key.** Not seen: a ticket's board lines carry distinct
  labels in the bank's SMS. Unmeasured over the real dump. If it happens, one
  press accepts both and both show under *Accepted by you* with Undo, so
  nothing is hidden.
- **A page from an earlier session posts.** 403, as for `POST /settings`, and
  the bar says to reload.

## 7. Tests

All in `tools/verify_page.py`, on fixture models; none needs the dump or the
network.

| Case | Invariants |
|---|---|
| `accepting_moves_a_win` | INV-116, INV-117 |
| `accept_route_guards` | INV-116, INV-118, INV-119, INV-120 |

Plus `/accept` added to the route lists of LOTTO-0014's `host_allowlist`,
`token_required` and `no_reflected_headers` cases, `temp_home()` pointing
`serve.ACCEPTED` into its temporary directory (§4.2), and one assertion in
`tools/verify_paths.py`.

## 8. Alternatives considered (and rejected)

- **Widen `POST /settings` with an `accepted` key.** Rejected: `settings.json`
  is the tray's file, read by `supervise.read_settings()`, and win keys have no
  business there. It would also break `POST /settings`'s rule that a body is
  those two booleans and nothing else.
- **Keep acceptances in the browser's `localStorage`.** Rejected: the choice
  would live in one browser and vanish with its data, and LOTTO-0002 INV-63
  forbids ticket data in browser storage.
- **Key a win by its amount or division.** Rejected: an estimated Daily Lotto
  prize changes when its results page is out, and the acceptance would be
  orphaned.

## 9. Out of scope

- `check.py`'s terminal output, which keeps listing every win as it does.
- *Bank's record*, which keeps every row and both figures (§3 item 3).
- Accepting from the tray.
- Accepting several wins at once.

## 10. What checks this

| Rule | Checked by |
|---|---|
| INV-116 accepting moves one win, and no other figure | `verify_page.py::accepting_moves_a_win`, break `accept_hides_bank_row`; `verify_page.py::accept_route_guards` |
| INV-117 paid and expired wins are never shown as accepted | `verify_page.py::accepting_moves_a_win` |
| INV-118 the route writes only a current win's key | `verify_page.py::accept_route_guards`, break `accept_any_key` |
| INV-119 one writer, keys only, gitignored, unreadable reads as empty | `verify_page.py::accept_route_guards`, break `store_unread_hides`; `verify_paths.py`; `git check-ignore` |
| INV-120 nothing outside the page carries the store | `verify_page.py::accept_route_guards`; the `grep` over `*.py` |
| INV-120's log-line clause | **nothing** — neither §7 case reads a log |
| §4.2 the write is a rename, so a crash leaves a whole file | **nothing** — a crash between write and rename cannot be arranged in the suite |
| §4.3 the page reloads after a 200 and keeps its folds and tab | **Partial:** `verify_page.py::tabs_never_hide_a_warning` reads the script's one `sessionStorage` write and its tab-id check; what a reload does is browser-side and no case runs it |
| §6 two wins sharing a key | **nothing** — unmeasured over the real dump |

## 11. Cross-doc impact

- **LOTTO-0002** — INV-89's "tabs store nothing" becomes "a tab is kept in
  `sessionStorage` for a reload, and nothing else is stored", with its case
  reading that one write; INV-115's case counts `localStorage` writes only;
  INV-70 gains "and not accepted"; §4.5 lists *Accepted by
  you* after *Paid by the bank*, and its empty state gains §4.4's accepted
  form; §4.1's script jobs gain the accept and undo
  POSTs; INV-115's fold list gains `fold-accepted`.
- **LOTTO-0014** — §4.1's four routes become five, with `POST /accept`'s row
  and its response's header set; §4.1's lock paragraph covers both routes;
  INV-14 says `POST /accept` writes only values copied from the model.
- **`.gitignore`** — names `accepted.json*`.
- **`.claude/rules/architecture.md`** — `serve.py` owns the store's one reader
  and one writer.
- **README** — *Wins* gains one sentence on Accept and Undo.

## 12. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 1 | 2026-11-18 | 2, cold, via `neutral-lane`; every lane held every question | — | — | — | — | **Q1 1 · Q2 4 · Q3 3 · Q4 2 (verified 10, fixed 9, surfaced 1; dismissed 2).** Two came from building the packet and were fixed before dispatch: the test cases would have written the checkout's real store, since `paths.DATA` is the repository and `temp_home()` does not move it (now a `serve.ACCEPTED` alias that `temp_home()` points away); and §4.1 cited INV-90 to LOTTO-0002, which is LOTTO-0001's. Both lanes found: `.gitignore` must name `accepted.json*`, because `write_atomic()` leaves a temporary file beside the store on a failed write; LOTTO-0014 INV-14 forbids writing request-derived strings, so the entry is now copied from the model win; no case checked that `serve.py` sets the flag at `GET /`, so `accept_route_guards` now reads the page after an accept and an undo; and with every waiting win accepted, LOTTO-0002 §4.5's empty state would be false, so it gains an accepted form. One lane each: `<key>`'s wire shape is now pinned to a store entry's; INV-120's log-line clause gets a §10 "nothing" row; the 1b fix's "the test cases" became `temp_home()`, so LOTTO-0014's cases are covered too. **Surfaced to the user, not fixed:** a reload after Accept lands on the Overview tab, because LOTTO-0002 INV-89 says tabs store nothing. Dismissed: reusing `serve._win_key`'s five fields (§4.1 pins six and INV-119's test asserts six); a positive control for `/accept` in `host_allowlist` (INV-12's "answered normally" already covers it). Three open questions resolved clean: a missing store is not in §6's unreadable list; `plus_flag` is an integer (`tickets.GAME_MAP`); §6 already says the next accept rewrites a corrupt store. |
| 2 | 2026-11-18 | 2, cold, via `neutral-lane`; identical brief, packet rebuilt from disk; every lane held every question | — | — | — | — | **Q1 0 · Q2 4 · Q3 3 · Q4 1 (verified 8, fixed 8; dismissed 0).** Both lanes found: `page.py` was to read only the `accepted` flag yet say the store could not be read, so the view now carries `accepted_unreadable`, set when the file exists but cannot be read (an absent file is an empty store, which settles one lane's fresh-install case); and "allowed only for a win … under *Not yet paid*" was judged on a model with no flag, so a second accept would duplicate the entry, now 409 with a case row. One lane each: the flag was to be added to the shared model, which `do_GET`'s shallow copy would have mutated, now a copy per win; the key's path into the script is pinned to one `data-win` JSON attribute; *Accepted by you* rows carry no near-deadline marking, as the user asked; the earlier-session 403 message goes to the bar, since `msg()` writes the hidden Settings tab (LOTTO-0002 INV-89); §7 now lists the `temp_home()` change; INV-120's grep widens to catch a module reaching the store through `serve.ACCEPTED`. Four open questions resolved clean. **Cap reached (2 for a spec); the run ships.** **A calm cap**: 1 of the final loop's 8 verified findings landed on text this run wrote (the `temp_home()` sentence). The second share is not reported: the document is new, so every finding is inside the span that armed the gate. This loop's 8 fixes are read by no lane; implementation is their reader. One finding stays surfaced to the user (loop 1: a reload after Accept lands on the Overview tab). |
| 2-amend | 2026-11-18 | — | — | — | — | — | **Amendment row — no reviewer was dispatched, and this is not a review loop.** The question loop 1 surfaced was put to the user, who chose that a reload keeps the open tab and a fresh visit opens on the Overview (§3 item 5). §4.3, §10 and §11 changed with it; §3's own two calls renumbered to 6 and 7, and only item 3 is cited. Implementation is this text's reader. |
