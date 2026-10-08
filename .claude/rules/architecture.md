---
paths:
  - "**/*.py"
---

# Architecture — what each file owns

The detail behind the diagram in `CLAUDE.md` § Architecture. This file
loads by itself when a session reads a `.py` file with the native Read
tool; an Ants-verb read does not load it.

## Per-file notes

- **`watch_sms.py`** is the cable-free collector (LOTTO-0003). It reads the
  phone's conversation list at start — polling it until it stops growing, which
  is the completion signal D-Bus does not give — then lives on `conversationUpdated`
  signals. **`conversationCreated` fires only the first time the KDE Connect
  daemon learns of a conversation** — measured 202 signals on a first run and
  **zero** on every later one against the same 2,325 conversations — so nothing
  may build discovery on it; that mistake shipped a watcher that reported "0
  new" against a phone holding 951 matching messages. Its filter is
  LOTTO-0001 §4.1's adb `WHERE` clause re-expressed, and `verify_watch.py`
  checks the two against SQLite. `find_lotto_sms.py` is a different tool with a
  deliberately wider list: it prints, this writes. Do not merge them.
  **A KDE Connect restart breaks it in HALF, and the half that survives is the
  one you would expect to lose** — measured 2026-08-15, the second D-Bus
  assumption this project got wrong by recall rather than by measuring. The
  held proxy dies (`ServiceUnknown`, because dbus-python pins a well-known name
  to the unique connection it resolved at `get_object()` time), while the
  signal match rule survives untouched (it carries an interface and a member
  and no sender). So the watcher does not go deaf — it goes **mute**, and since
  steady state makes no call to the phone, the loss is invisible until a
  catch-up that never ran is noticed. **And nothing brings the daemon back:**
  the watcher must reach for it, because the bus name is D-Bus *activatable* and
  the act of reaching starts it. `RETRY_EVERY` is 60s, not 2s, so it cannot
  resurrect a daemon the user stopped on purpose. LOTTO-0003 §4.8.
- **`tickets.py`** holds the bank's *parsing*, and reads **two** message kinds.
  It is not the only bank-specific file: `watch_sms.py::INCLUDE` and
  LOTTO-0001 §4.1's adb `WHERE` clause hold the bank's *admission filter*, and
  `INCLUDE` carries the reference prefix `vas00`. **A bank wording change
  touches both**, and INV-32 asserts the two filters agree — fixing the parser
  alone leaves a message the parser handles correctly and never receives, which
  is exactly how LOTTO-0030 excluded 366 payouts. `rows()` is the dump
  format's one reader, and both writers depend on that staying true — a second
  reader that drifts would duplicate every record it failed to recognise.
  `parse_payout()` reads the bank's statement of a prize it paid; it and
  `parse()` are disjoint by construction and **must stay so**. A purchase debit
  reads "R… paid from Acc. … to VAS… LOTTO" — money *leaving* the account, and
  it names a game. A payout names none, which is the one word that kept every
  payout out of the dump until LOTTO-0030 widened the import filter. Widening
  `PAYOUT` toward "paid" counts the 14 debits as winnings, so lifetime "paid"
  grows by what the user *spent* (LOTTO-0029 INV-40).
  `parse()` handles two SMS eras; `GAME_MAP` translates an SMS game name to the one `(game, plus_flag,
  pool_id)` it names, and `entered_pools()` derives the *full* set of pools
  from the ticket price, which is what scoring actually iterates
  (`Ticket.pools`).
- **`results.py` / `backfill.py`** are two results sources with different
  shapes; **`history.py`** normalises both into one draw record
  `{date, main, special, issue, source}` and is the only place that merges them.
  `issue` (the draw number) exists only for API draws — that asymmetry is why
  `check.py::amount()` has two pricing paths.
- **`check.py`** scores and prices. Prize divisions are read from the live
  source, never hardcoded (INV-5).
- **The port is `$PORT`, else `$LOTTO_PORT`, else 4322** — the same precedence in
  `serve.py::resolve_port()` and `supervise.py::_port_or_default()`, so there is
  one knob whichever way the page is started. `$PORT` is the name an external
  process manager already sets, which is why it wins. Unset and empty mean "no
  preference" and fall through.
  **On a bad value the two deliberately diverge, and must not be "unified"** —
  each says so at its own site. `serve.py` is machine-facing and **exits**
  naming the variable and the value: a manager that asked for port 80 and got
  4322 has been lied to. The tray is human-facing and **falls back to 4322 with
  a notification**, because a tray that exits just vanishes, and a typo in a
  shell profile must never be indistinguishable from the app being broken. That
  is safe only because a manager range-checks before it sets and launches
  `serve.py` directly, so the fallback can never mislead one (LOTTO-0013 §4.5).
- **`serve.py::period_buckets()`** owns the per-period figures (LOTTO-0036).
  It is a **pure function taking its two data sources as arguments**, which is
  the only reason INV-57 to INV-60 are checkable at all: **no case in
  `tools/verify_page.py` invokes `build_model()` for an assertion** — its model
  is `fixture_model()`, a hand-authored dict, and `render_pure()` installs an
  `all_draws` double that *raises*. The cases that spawn `serve.py` set
  `LOTTO_NO_BUILD` and drive `/status` or `/settings`, never `/refresh` —
  **`LOTTO_NO_BUILD` gates only the OPENING build**, so a refresh in that child
  would start a real one against live data and the operator's API. So a
  builder-side defect cannot be seen there, and that file's own docstrings say
  so. Do not move these cases into it. Money belongs to the
  period of the **draw**, never of the purchase (the user's call, 2026-08-27),
  and the key set is built from the spend side so a win can never conjure a
  bucket with no spend.
- **`serve.py`** is `check.py`'s second consumer and adds no third opinion: a
  wrong number on the page is a bug in its rendering or in LOTTO-0001/0009,
  never a separate calculation. It does **all** the I/O; **`page.py`** is a pure
  function from a model dict to one HTML string, which is what lets the whole
  page be rendered in a test with no socket and no `archive_results.json`.
- **`supervise.py`** owns the server child — its token, its port, its reaping —
  and is Qt-free so that lifecycle is checkable from a headless script.
  It also owns **reading** the two settings (`config_home()`, `autostart_path()`,
  `settings_path()`, `read_settings()`), because `tray.py` needs them and may
  not import `serve`; **`serve.py` imports them from here** and owns only the
  *writing*, behind `POST /settings`'s lock. One reader, three callers — do not
  add a second, however local it looks: two readers that agree today pass every
  check and diverge later (LOTTO-0013 §4.1).
  It also owns the **re-buy warning** (LOTTO-0034): `expiry_notice()` for the
  wording, `expiry_notices()` for the selection and the state file, and
  `expiry_state_path()` beside the two settings paths. `tray.py` supplies
  today's date and displays strings and holds no decision, which is the only
  reason INV-52 to INV-56 are reachable from a headless script.
  **`expiry_warned.json` has exactly ONE writer, `expiry_notices()`** — putting
  warn-state into `settings.json` would give that file a second writer that is
  not the server, which is the arrangement the one-reader rule above exists to
  prevent. The record is written **before** the notice is emitted, which is the
  opposite direction to every read rule here and is deliberate: a crash then
  costs a missed notice rather than a repeated one, and *say it once* is a user
  decision. Do not harmonise the two.
  It also owns `new_ticket_notice()`, for the same reason `refresh_message()`
  lives here: **a wording decision inside `tray.py` cannot be checked without
  constructing a `QSystemTrayIcon`**, and the project has no Qt-constructing
  test. Every branch must name a menu item that state leaves *enabled* — the
  one that did not sent the user to a greyed-out *Refresh results now*
  (LOTTO-0003 §4.7).
  **`tray.py`** is the only file that imports PySide6, and the only file that
  reads `LWSM_MANAGED` — `=1` means a process manager started it, so it runs
  with no icon and, above all, no path that stops the server (INV-25). It is a
  presentation hint with no security value; nothing else may hang off it.
- **`tools/verify_*.py`** import the modules directly via a `sys.path` insert.

## Load-bearing decisions — do not "simplify" these

- **An entry nothing can score is *uncheckable*, not a loss.** `history.py::scorable()`
  gates it out and `check.py::uncheckable_report()` reports the two reasons
  separately (predates all draw data / pool no source publishes). Silently
  scoring such an entry against the wrong draws is the bug this project was
  built after hitting. **The unit is the entry**: a ticket checkable in one
  pool and not another is *partly* uncheckable, still scored on the rest, and
  must never be counted as wholly excluded (INV-11).
- **A ticket is entered in every tier its price paid for**, base game first,
  because a PLUS game cannot be bought alone (INV-8). The tiers come from the
  price in whole cents, not from the printed name, which states only the top
  tier and since 2026-06-01 states none (INV-9). A price matching no tier is
  reported, never guessed at (INV-7) — `tickets.py::TIER_PRICES` is hardcoded
  because no feed publishes it, so `tools/verify_pools.py` is the only thing
  that makes a price change loud.
- **The PowerBall is the final number on a board line in both eras**, marked
  with `-` only in the new format. Treating it as a main number scores every
  PowerBall ticket one match high and never matches the PB (INV-1).
- **A Lotto board with >6 numbers is Multiplay** and expands to one line per
  6-number combination, each winning independently (INV-2). Currently
  Lotto-only — see LOTTO-0007(d).
- **The bank's payout SMS never replaces a computed figure.** `check.py::reconcile()`
  joins the bank's own record to tickets on the `VAS` reference and reports both
  figures side by side; a disagreement is flagged, never resolved in the SMS's
  favour (user decision 2026-08-13, LOTTO-0029 INV-43). Adopting it would price
  the archive era for free — and erase the 15 references where the app computes
  LOW, which are the evidence that something in pricing is wrong. Three things
  not to "simplify": the unit is the **reference**, not the payment (77 of 225
  are paid more than once); money is compared in **whole cents**, never float
  rands; and the seven categories are decided in a fixed **order**, because as
  an unordered set they overlap — a reference with no purchase SMS has no
  entries, so "every entry is scorable" is vacuously true of it and it would
  match `unexplained` as well as `no_ticket`.
- **`computed_cents` is three-valued and the three must not converge** — the
  cardinal rule again, one layer below the page. `None` is *not checkable*
  (nothing could be scored), `0` is *checked, total prize zero*, and a positive
  integer is the summed prize. So `computed_cents` never answers "did it win?";
  `first_win` does. A reference that is only **partly** scorable carries an
  integer, never `None`, or LOTTO-0009 INV-11 is breached from the other side.
- **A dump with no parsable payout reports that, and emits no category census.**
  If the bank changes its wording, `parse_payout()` matches nothing and every
  scored reference would otherwise satisfy `unpaid` — announcing prizes nobody
  was ever paid. The guard is in `reconcile()` itself, not only in the report,
  so the page cannot render the fictions either (INV-47). Same class as
  LOTTO-0031, where a rebranded game name parsed to `None` and a ticket was
  silently never scored.
- **The re-buy warning reads the CALENDAR, never the results.** `expiry.py`
  imports nothing of the project's and touches no file (INV-50), because a
  ticket's last draw is fixed at purchase — the ndraws-th calendar draw on or
  after its start — so the warning is right with the server stopped and the
  machine offline. `draws_left` (calendar: has it *happened*) and
  `draws_remaining` (results: has it been *scored*) are different quantities
  that coincide only while results are current, which is exactly when the
  warning does not need help. **Do not unify them** — same cardinal rule as
  `_money_cell()`, one layer out. Both boundaries are pinned and moving either
  shifts every date by one: `start` is inclusive, and a draw falling *today*
  has not yet happened. `DRAW_DAYS` is hardcoded like `TIER_PRICES` and rots
  the same way, so INV-49 checks it against
  observed history in **both** directions — a one-directional check passes a
  *removed* draw day forever.
- **Every date is South African time, read through `clock.py`** (LOTTO-0066,
  INV-64): a fixed UTC+2, because SAST has no daylight saving, returned naive
  because `HANDOVER` and every draw date are naive. **Never call
  `date.today()`, `datetime.now()` or `fromtimestamp()` directly** — each
  reads the machine's own zone, which put a draw on the wrong day on any
  machine not set to SAST. `expiry.py` still takes `today` from its caller
  (INV-50); the caller gets it from `clock.today()`.
- **`paying_combinations()` raises** rather than returning `{}` when a pool has
  no recent draw. An empty set would score the whole pool as losses with no
  diagnostic.
- **`daily/1` (Daily Lotto Plus) is deliberately mapped to a pool no source
  carries**, so those 11 *entries* read as uncheckable while the same tickets'
  `daily/0` entries score normally — they are the project's only partly
  uncheckable tickets. Aliasing them onto plain Daily Lotto would score them
  against a different game. `tools/verify_sources.py` exempts it via
  `EXPECTED_EMPTY`.
- **Source-agreement comparison is set-based**: the archive sorts numbers
  ascending, the API preserves drawn order.
- **Site slugs renamed at the June 2026 rebrand** (Lotto Plus 2 → Lotto 5 Max,
  PowerBall Plus → XTRA) and the archive rewrote its *old* links to match, so
  `PAYOUT_SLUG` uses current names for historic draws.
