# LOTTO-0019 — Report what a build is doing, and what it found

**Status:** spec draft (2026-08-05).
**Kind:** feature.
**Source:** ROADMAP LOTTO-0019 (in-session-2026-08-02).
**Also covers:** LOTTO-0012 (retry the results API), LOTTO-0020 (show build
progress). One document because all three change the same function
(`results.py::_post()`) and the same wire shape (`GET /status`); three
documents describing one JSON object would disagree on the first edit.
**Blocked by:** LOTTO-0018 — shipped 2026-08-02.
**Blocker for:** LOTTO-0028 (refresh on a schedule).

Layman: while the app is checking your tickets it says how many lookups it has
done instead of just "building", and when it finishes it tells you how many new
winning lines it found rather than a flat "Results refreshed."

## 1. Goal

A build stops being opaque at both ends. While it runs, `GET /status` reports
how many HTTP requests it has issued so far, and the opening page shows that
number climbing instead of a static notice. When it finishes, `/status` reports
whether it found anything the previous build did not, and the tray says so
instead of the fixed string `REFRESH_MESSAGE[REFRESH_DONE]`. Underneath both, a
transport failure no longer kills the build on its first occurrence.

## 2. Problem

Three defects on one path, verified against current source 2026-08-05.

1. **A single dropped connection aborts the whole build.**
   `results.py::_post()` calls `urllib.request.urlopen` once, inside a `with`,
   with no retry. Every API request in the project reaches the network through
   it — `results.py::draws()` and `results.py::divisions()` are its only
   callers — so one `URLError` ends `check.py`, every `tools/verify_*.py`, and
   the page's build alike. LOTTO-0012 records the measurement: four of seven
   build attempts failed with `URLError(SSL: UNEXPECTED_EOF_WHILE_READING)`
   while LOTTO-0002 was being written.

2. **The first build shows no progress.** `serve.py::make_server()` binds
   before `main()` runs the opening `refresh()` (LOTTO-0002 §4.2), so the page
   answers at once and then sits on the *building* notice in
   `page.py::render()` for the thirty-odd seconds that build takes.
   `page.py`'s poll re-reads `GET /status` every 2 s, and
   `serve.py::Handler.do_GET` answers it with `{"building", "built", "stale"}`
   — three fields, none of which changes during a build. The poll has nothing
   to show and the page has nothing to say.

3. **A finished refresh cannot say what it found.** `State.finish()` replaces
   `self.model` outright and keeps no record of what changed, so
   `Supervisor.refresh()` has only its four outcome constants to report and
   `REFRESH_MESSAGE[REFRESH_DONE]` is the fixed sentence `"Results
   refreshed."`. The project exists to surface a win before it is found by
   accident, and today the notification that a win might have arrived is
   indistinguishable from the notification that nothing changed.

Consequence 3 is the one that matters most and the one most easily made worse:
a summary that reports *nothing new* in the same words it would use for *no
comparison was possible* is this project's cardinal failure arriving through
the notification, which is exactly the shape LOTTO-0018 closed one step
earlier.

## 3. Scope decisions

**None of these were put to the user.** All five were taken in session on
2026-08-05 from what the ROADMAP bullets already constrain, and they are
recorded here because each is a preference between workable options rather than
a deduction — so the next reader argues with a decision rather than re-taking
it. The one most worth re-opening is the last.

- **The progress figure has a numerator and no denominator.** LOTTO-0020's
  bullet suggests "fetched N of M", and the M is not honest: `check.py`
  fetches lazily as it prices wins, so the total for *this* build is unknown
  until it ends. LOTTO-0002 §4.2's figure of 27 requests is a dated
  measurement against one dump, not a constant — and LOTTO-0006 would move it.
  A bare count is the largest true statement available.
- **The count is of HTTP attempts, not of draws fetched.** A retried request
  is a request the network really carried, and under LOTTO-0012 retries are
  the commonest reason a build is slow. Counting attempts is what makes the
  figure move when the build is stuck retrying, which is the case the figure
  exists for. It is named `requests` rather than `fetched` for the same
  reason: `fetched` would over-claim.
- **The comparison baseline lives in the server process only.** No file, no
  new on-disk state. A restart therefore loses it, and a win first seen by a
  process's opening build is not announced — see §6. Persisting it is
  LOTTO-0028's problem, because a baseline is only worth keeping across
  restarts once something refreshes without being asked.
- **The summary reaches the user through `supervise.py`, not `tray.py`.**
  LOTTO-0013 §4.6 put the refresh wording in `supervise.py` so a headless case
  can read it, and `tray.py::refresh()`'s comment records that the tray
  composes only the failure line. That division holds here: the tray gains no
  new sentence.
- **Progress is shown on the opening build's page only.** The refresh-in-flight
  page keeps today's behaviour. Taken 2026-08-05 to keep the change surgical;
  LOTTO-0020's own argument is about "the first thing a new user sees".

## 4. Design

### 4.1 One function, both halves — `results.py::_post()`

The retry and the counter go in the same place for the same reason `_post()`
already exists: it is the single funnel, so every caller gets both at once.

```python
ATTEMPTS = 3
BACKOFF = 1.0   # seconds; doubled per retry, so 1 s then 2 s

# Every HTTP attempt this module makes, for GET /status to read out
# (LOTTO-0019 §4.2). Reset by whoever starts a build, never by _post itself:
# a counter that reset itself would have no build to belong to.
requests_made = 0


def _post(path, body):
    global requests_made
    req = urllib.request.Request(
        API + path, json.dumps(body).encode(), HEADERS, method="POST"
    )
    for attempt in range(ATTEMPTS):
        requests_made += 1
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                payload = json.load(r)
            break
        except urllib.error.HTTPError:
            # The server answered. A retry gets the same answer, and a 404
            # retried three times is 3 s of nothing.
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == ATTEMPTS - 1:
                raise          # the ORIGINAL error, unwrapped
            time.sleep(BACKOFF * 2**attempt)
    if payload.get("code") != 0:
        raise RuntimeError(f"{path}: {payload.get('msg', payload)}")
    return payload["data"]
```

Three things this deliberately does not do:

- **No bare `except`, and no empty result on exhaustion.** The last failure
  re-raises the original exception. An empty draw list returned quietly is the
  "no data reads as no win" failure arriving through the network layer, and
  `check.py::paying_combinations()` already raises rather than returning `{}`
  for the same reason.
- **`HTTPError` is not retried.** It is a `URLError` subclass, so it must be
  caught first or the general arm swallows it. The retry is for transport
  failures — the measured one is an SSL EOF — not for answers.
- **`json.JSONDecodeError` is not retried.** A truncated body is a different
  failure and gets a different fix if it ever appears.

New module-level imports in `results.py`: `time`, `urllib.error`.

**The counter needs no lock.** `State.begin()` guarantees one build at a time
and `check.py` is single-threaded within it, so there is exactly one writer;
`GET /status` only ever reads. One writer and N readers of a small-int rebind
cannot lose an update or read a torn value in CPython. A second concurrent
build would break that argument, which is what `State.begin()` prevents.

### 4.2 What `GET /status` answers

`serve.py::Handler.do_GET` gains two keys. The three existing ones are
unchanged, so `page.py`'s poll and `Supervisor.refresh()`'s wait keep working
untouched.

```jsonc
{
  "building": false,      // unchanged
  "built": "2026-08-05T18:22:04",   // unchanged
  "stale": false,         // unchanged

  "requests": 27,         // HTTP attempts made by the build in flight, or by
                          // the last one to run. 0 before any build starts.

  "found": {              // what the LAST COMPLETED build found that its
    "new_wins": 2,        // predecessor did not. null when there was no
    "new_cents": 24000    // predecessor to compare against (§4.3) — never {}
  }                       // and never a zeroed object standing in for null.
}
```

`found` is `null` or an object with exactly those two integer keys. There is no
third shape. `new_cents` is the summed `amount_cents` of the new wins only, not
a running total, so it can be 0 while `new_wins` is 2 — a new winning line in a
division that pays nothing is still news.

`GET /status` carries no token (LOTTO-0014 §4.1). Adding a count and a rand
total to it widens nothing: `GET /` on the same origin already renders every
ticket, so `/status` remains strictly the smaller disclosure.

### 4.3 The comparison, and its three states

`State` gains one field and `finish()` gains the diff. Both stay under the
existing lock.

```python
def _win_key(w):
    """What makes two win records the same line. `line` is a board LABEL
    (tickets.py builds boards as (label, numbers, special)), so this key
    holds no drawn numbers."""
    return (w["ref"], w["plus_flag"], w["pool_id"], w["line"], w["date"])


def _compare(previous, current):
    """-> {"new_wins": int, "new_cents": int}, or None when there is nothing
    to compare against. The None is the contract, not a convenience:
    reporting a first build's every win as `new` would tell a user who just
    opened the app that they have won 46 times today."""
    if previous is None:
        return None
    was = {_win_key(w) for w in previous.get("wins", ())}
    fresh = [w for w in current.get("wins", ()) if _win_key(w) not in was]
    return {"new_wins": len(fresh),
            "new_cents": sum(w["amount_cents"] for w in fresh)}
```

`State.finish(model)` sets `self.found = _compare(self.model, model)` **before**
rebinding `self.model`. `State.fail()` sets `self.found = None`: a build that
raised completed no comparison, and a summary left over from an earlier refresh
would outlive the build it describes.

Three states, and they must stay three:

| `found` | Means |
|---|---|
| `null` | nothing was compared — first build of this process, or the build failed |
| `{"new_wins": 0, …}` | compared, and nothing is new |
| `{"new_wins": n>0, …}` | compared, and *n* lines are new |

§4.5 owns the sentence each state produces; it is not restated here, because a
wording written in two places is two wordings.

The first two rows are the cardinal rule. "Nothing was compared" and "nothing
was found" are different facts and get different sentences; collapsing them
would let a build that could not compare read as a build that found nothing.

The `no_dump` model (LOTTO-0002 §4.1) carries no `wins` key at all. `_compare`
reads it through `.get("wins", ())`, so a dump appearing between two builds
compares an empty set against a real one and reports every win as new — which
is correct: they are all news to a page that had none.

### 4.4 What the page shows while building

`page.py::render()`'s building branch gains one element, and the poll fills it.
Pure-function boundary is preserved: `render()` reads `model["requests"]` for
the initial value and the poll updates it in place thereafter.

```html
<div class="notice"><strong>Checking your tickets…</strong> …
  <span id="progress">27 lookups so far.</span></div>
```

In `page.py::JS`, inside the existing `if(s.building)` arm:

```js
if(s.building){var p=document.getElementById("progress");
               if(p)p.textContent=s.requests+" lookups so far.";
               setTimeout(poll,2000);return}
```

"Lookups" rather than "requests" in user-facing text; the wire key stays
`requests`. No new poll, no new interval, no second request per tick — the
figure rides the poll `page.py` already makes, which is why this costs nothing.

### 4.5 What the tray says

`supervise.py` gains one function beside `REFRESH_MESSAGE`, and
`Supervisor.refresh()` records the summary it already fetched.

```python
def refresh_message(outcome, found=None):
    """The sentence for an outcome. Only REFRESH_DONE consults `found`, and a
    `found` of None leaves the sentence exactly as it was before LOTTO-0019 —
    which is what keeps "nothing compared" distinct from "nothing new"."""
    line = REFRESH_MESSAGE[outcome]
    if outcome != REFRESH_DONE or found is None:
        return line
    n, cents = found["new_wins"], found["new_cents"]
    if not n:
        return line + " No new wins."
    return (f"{line} {n} new winning line{'' if n == 1 else 's'}, "
            f"R{cents / 100:,.2f}.")
```

`Supervisor.refresh()` already polls `GET /status` until `building` is false;
it stores that final answer's `found` on `self.found` and keeps returning one
of the four outcome constants unchanged, so INV-23's total map still holds and
no caller's signature moves. `tray.py::refresh()`'s `finished()` swaps
`supervise.REFRESH_MESSAGE.get(msg, msg)` for
`supervise.refresh_message(msg, self.sup.found)`, and still composes only the
failure line.

The notification body is built from two integers. It names no ticket, no board,
no draw date and no division — the reasoning that keeps ticket data out of the
URL (LOTTO-0014 INV-21) applies with more force to a notification, which the
desktop may log and sync off the machine.

## 5. Invariants

- **INV-27** — `results.py::_post()` makes up to `ATTEMPTS` attempts when the
  transport fails, sleeping `BACKOFF * 2**n` between them, and re-raises the
  original exception unchanged when the last attempt fails. An `HTTPError` is
  never retried.
  *Test:* `tools/verify_page.py::post_retries_transport_failure`; breaks
  `no_retry` and `retry_http_error`.
  *Breaks when:* a `URLError` raised by the first `urlopen` aborts the caller
  (today's behaviour); or a 404 costs three attempts, which turns one wrong
  path into three seconds of nothing and three counted requests.

- **INV-28** — `results.requests_made` counts every HTTP attempt `_post()`
  makes, is reset to 0 by the code that starts a build before its first
  request, and is what `GET /status` reports as `requests`.
  *Test:* `tools/verify_page.py::build_progress_is_visible`; breaks
  `no_counter_reset` and `count_per_call`.
  *Breaks when:* the reset happens after the build rather than before, so the
  second build in a process opens at the first one's total; or `_post()`
  increments once per call instead of once per attempt, so the figure freezes
  during exactly the retry storm it exists to narrate.

- **INV-29** — `GET /status`'s `found` is `null` unless a completed build had a
  predecessor model to compare against, and an object with `new_wins: 0` when
  it had one and nothing was new. No code path renders those two as the same
  sentence.
  *Test:* `tools/verify_page.py::no_comparison_is_not_no_wins`; breaks
  `found_on_first_build` and `null_found_reads_as_zero`.
  *Breaks when:* the first build of a process compares against an empty model
  and reports every existing win as new; or `refresh_message()` maps `None` and
  `{"new_wins": 0}` to one string, making "could not compare" indistinguishable
  from "compared, found nothing".

- **INV-30** — The refresh notification body contains a count and a rand total
  and nothing else: no ticket reference, no board label, no draw date, no
  division name.
  *Test:* `tools/verify_page.py::notification_carries_no_ticket_data`; break
  `summary_names_a_ticket`.
  *Breaks when:* `refresh_message()` is built from a win record's `ref`,
  `line`, `date` or `matched` rather than from the two integers — for instance
  a well-meant "your PowerBall line B won on 2026-07-04".

## 6. Failure modes

- **The API is down for the whole build.** All three attempts fail on the first
  request; the original `URLError` propagates; `State.fail()` sets `stale`,
  clears `found`, and leaves the model untouched (INV-18). The page shows the
  stale notice, the tray reports `REFRESH_FAILED`. `requests` is left at
  whatever was counted, which is honest — the requests were made.
- **The server restarts.** `found` starts `None`, so the first build after a
  restart announces nothing even if it genuinely found a new win. The page
  still shows it, which is the mitigation; the notification does not. This is
  the price of holding no on-disk state, it is the reason LOTTO-0028 exists,
  and it must not be papered over by having the first build report its whole
  win list as new — that is INV-29's breaking input.
- **Two builds race.** They cannot: `State.begin()` returns `False` and the
  route answers 409. If that guard were ever removed, the unlocked counter in
  §4.1 would lose increments — which is why the argument for skipping the lock
  is written down beside it rather than assumed.
- **A retry succeeds after the page has given up.** It has not: the page polls
  until `building` goes false, and `Supervisor.refresh()`'s deadline reports
  `REFRESH_RUNNING` rather than a failure. Retries lengthen the wait; they do
  not change which outcome is reported.
- **A win disappears between builds.** `_compare` reports only additions, so a
  win present before and absent now is invisible to the notification. That is
  the correct silence for a *new wins* summary, and the page's own figures
  still move. Nothing in the project can currently retract a win — draws are
  immutable — so this is a guard against a future source, not a live case.

## 7. Tests

Four new cases in `tools/verify_page.py`, joining the thirteen already there,
under the same three constraints its docstring states (no network, no real
data, recompute rather than import the judgement). Its header count and
CLAUDE.md's "twenty-two breaks" both move.

| Case | Invariant | Seam |
|---|---|---|
| `post_retries_transport_failure` | INV-27 | `results.urllib.request.urlopen` replaced with a stub that raises `URLError` a fixed number of times, then returns a canned payload. No socket. |
| `build_progress_is_visible` | INV-28 | Same stub, counted; a builder driven twice through `serve.refresh()` + `wait_idle(5)`, reading `GET /status` between. |
| `no_comparison_is_not_no_wins` | INV-29 | `serve.make_server()` with a builder returning a scripted sequence of models; asserts `found` is `null` after build 1 and an object after build 2, and that `supervise.refresh_message()` returns different strings for `None` and `{"new_wins": 0}`. |
| `notification_carries_no_ticket_data` | INV-30 | `supervise.refresh_message(REFRESH_DONE, found)` called directly; asserts the sentinel `VAS00000000000` and a fixture board label appear nowhere in the result. |

Each case must be **observed failing** under its named `--break` before it is
believed, per the project's own rule: these are greenfield, so there is no
pre-fix code to red-test against. Seven new breaks: `no_retry`,
`retry_http_error`, `no_counter_reset`, `count_per_call`,
`found_on_first_build`, `null_found_reads_as_zero`, `summary_names_a_ticket`
— seven, taking the total from twenty-two to twenty-nine.

`build_progress_is_visible` must call `serve.State.wait_idle(5)` before
asserting, like every other refreshing case: `refresh()` starts a daemon thread
and returns at once, so an assertion made straight after it races a build that
may not have begun (LOTTO-0002 §4.2).

## 8. Alternatives considered (and rejected)

- **Carry the summary in `POST /refresh`'s response body instead of on
  `/status`.** Rejected: the POST is answered 202 *before* the build starts
  (LOTTO-0013 §4.6), so its body cannot describe a build that has not run. This
  is the same reasoning LOTTO-0018 already settled.
- **Show "fetched N of 27".** Rejected under §3: 27 is a measurement, not a
  constant, and a denominator that is wrong is worse than none — a bar that
  reaches 100% and keeps working is a stalled counter reading as completion.
- **Diff the win totals rather than the win set.** Rejected: two wins of equal
  value, one replacing another, would net to zero and announce nothing. Set
  difference on `_win_key` costs one pass over ~50 records.
- **Retry in each caller rather than in `_post()`.** Rejected for the reason
  LOTTO-0012 gives: one function serves `draws()`, `divisions()` and therefore
  every script, and per-caller retries would be four copies that drift.
- **Persist the comparison baseline to disk.** Rejected for now: it is new
  on-disk state whose only reader is a notification, and it is worth nothing
  until something refreshes unattended. Tracked by LOTTO-0028.

## 9. Out of scope

- Refreshing on a schedule, so the summary reaches a user who is not already
  opening the tray menu — tracked by LOTTO-0028.
- A progress figure on the refresh-in-flight page (as opposed to the opening
  build's page) — §3; no follow-up filed, it is a deliberate limit rather than
  a gap.
- Retrying 5xx answers, and any change to `_post()`'s 20 s per-attempt timeout
  — LOTTO-0012 names the transport failure it was filed for and this stays
  inside that.

## 10. Resource cost

One `int` in `results.py` and one `dict` of two `int`s in `State`. The
comparison holds a set of tuples the size of the previous model's win list —
bounded by the win count, itself bounded by the ticket dump, and discarded when
`_compare` returns. No count is asserted here on purpose: the win list grows
with the dump, so a figure measured today would be a ceiling nobody re-measures. No new file, no new on-disk state, no new external
dependency, no new build target, no new thread and no new HTTP request: the
progress figure rides the poll `page.py` already makes and the summary rides
the poll `Supervisor.refresh()` already makes.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-27 | `tools/verify_page.py::post_retries_transport_failure` |
| INV-28 | `tools/verify_page.py::build_progress_is_visible` |
| INV-29 | `tools/verify_page.py::no_comparison_is_not_no_wins` |
| INV-30 | `tools/verify_page.py::notification_carries_no_ticket_data` |
| §4.1 the counter is safe without a lock (one writer) | **nothing** — the argument rests on `State.begin()`, which is checked, but no case asserts that only one thread writes the counter |
| §4.2 `found` never takes a third shape (neither `{}` nor a zeroed object standing in for `null`) | **nothing** — INV-29's case asserts `null` against an object, so a malformed third shape would reach a cold reader and no further |
| §4.4 the page's progress element is updated by the poll | **nothing** — `tools/verify_page.py` renders `page.render()` as a string and never executes its JavaScript; tracked by LOTTO-0007 |
| §4.5 the tray composes only the failure line | `tools/verify_page.py::refresh_reports_the_build` (existing, INV-23) |

Eight rows, **three** with a bolded `nothing`. Two of them (§4.1, §4.4) are the
same standing limit — nothing here executes browser JavaScript or counts
threads. The third (§4.2) is narrower and closable: a shape assertion on
`/status`'s body would catch it, and it is not written because no third shape
has ever been produced. None of the three is a gap this item can close on its
own.

## 12. Cross-doc impact

- `CLAUDE.md` — the `--break` count (twenty-two → twenty-nine), and the
  `verify_page.py` line naming which invariants it covers.
- `tools/verify_page.py` — its docstring's case count (thirteen → seventeen)
  and the invariant range in its first line.
- `docs/specs/LOTTO-0002-local-web-page.md` — §4.2 describes `State` and
  `refresh()`; `finish()` and `fail()` gain `found`, so its `State` sketch
  needs the field.
- `docs/specs/LOTTO-0013-tray-and-supervisor.md` — §4.6 describes
  `Supervisor.refresh()` and `REFRESH_MESSAGE`; `refresh_message()` joins them.
  INV-23 is unchanged: the outcome map stays total and only `REFRESH_DONE`
  reads as success.
- `docs/specs/LOTTO-0014-http-surface-and-security.md` — §4.1 lists `GET
  /status`'s response body.
- `CHANGELOG.md` and `ROADMAP.md` — three bullets flipped, one entry each.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
