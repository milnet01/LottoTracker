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
how many HTTP attempts it has made so far, and the opening page shows that
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
# (LOTTO-0019 §4.2). Reset by serve.py::refresh()'s work(), beside the three
# memo clears and before build_model_fn() is called — never by _post itself,
# because a counter that reset itself would have no build to belong to.
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
        except (urllib.error.URLError, socket.timeout, TimeoutError):
            # socket.timeout explicitly: it is only an ALIAS of TimeoutError
            # from Python 3.10, and CLAUDE.md and README.md both pin this
            # project at 3.8+. Without it the retry silently skips the
            # commonest slow-network case on the stated floor.
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

New module-level imports in `results.py`: `socket`, `time`, `urllib.error`.

**Worst case, because this adds latency to a path that already has a
deadline.** Three attempts at the existing 20 s timeout plus 1 s and 2 s of
backoff is **63 s for one request that never succeeds**, against 20 s today.
`Supervisor.refresh()`'s 300 s deadline is unchanged, so a build in which even
five requests exhaust their retries now reports `REFRESH_RUNNING` where it
would previously have reported a failure — a different answer, not a wrong one
(§6). Two consequences that must land in the same change: `POST_TIMEOUT` stays
30 s, because the POST is answered without touching the build; and
`page.py::render()`'s building notice currently reads *"about half a minute"*,
which a retrying build falsifies — §4.4 rewords it.

**The count is of the results API only.** `backfill.py` fetches the archive and
caches to `archive_cache/` on disk, so it makes no request on most builds and
does not pass through `_post()`. LOTTO-0020's bullet raises this directly, and
the answer is that a counter reporting *only* what it can actually see is the
honest one: the figure is labelled as lookups the build made, never as the
build's total work.

**The counter needs no lock.** `State.begin()` guarantees one build at a time
and `check.py` is single-threaded within it, so there is exactly one writer;
`GET /status` only ever reads. One writer and N readers of a small-int rebind
cannot lose an update or read a torn value in CPython. A second concurrent
build would break that argument, which is what `State.begin()` prevents.

### 4.2 What `GET /status` answers

`serve.py::Handler.do_GET` gains two keys. The three existing ones keep their
names, types and meanings, so the wire contract is backward-compatible:
`Supervisor.refresh()`'s wait needs no change, and `page.py`'s poll changes only
to *use* the new key (§4.4), never because the old ones moved.

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

**Both keys are read the same way in `do_GET`, and BOTH branches need them —
this is the wiring, not a detail.** `do_GET` today unpacks `state.get()` and
serves either the `/status` JSON or the rendered page from the same values, so
the two new keys are gathered once, above the branch:

```python
model, building, built, stale, error, found = state.get()   # 6-tuple now
requests = results.requests_made
if path == "/status":
    body = json.dumps({"building": building, "built": built, "stale": stale,
                       "requests": requests, "found": found}).encode()
    ...
view = dict(model or {})
view.update({"built": built, "stale": stale, "error": error,
             "building": building, "requests": requests})   # <- the HTML view too
```

Three things follow, and the third is the one an implementer would otherwise
get wrong:

- **`State.get()` returns a six-tuple**, ending in `found`. It is the only
  locked accessor, so anything reading `state.found` directly would be reading
  outside the lock §4.3 promises. LOTTO-0002 §4.2 sketches the five-tuple and
  moves with this (§12).
- **`serve.py` imports `results` at module scope** to read the counter. It
  currently imports it lazily inside `refresh()`'s `work()`; `results.py` pulls
  in only `json`, `socket`, `time` and `urllib`, so this costs nothing and
  breaks no invariant — LOTTO-0013 INV-19 forbids Qt, not stdlib.
- **`requests` goes into the HTML view, not just the `/status` body.** The
  opening-build page is rendered when `model is None`, so a `requests` key
  living only in the model could never reach it — the one page this feature
  exists for. §4.4's renderer reads it off the view with `.get()`, matching how
  `page.py` reads every other key.

`GET /status` carries no token (LOTTO-0014 §4.1). Adding a count and a rand
total to it widens nothing: `GET /` on the same origin already renders every
ticket, so `/status` remains strictly the smaller disclosure.

### 4.3 The comparison, and its three states

`State` gains one field, `get()` returns it, and `finish()` computes the diff.
All three stay under the existing lock. Both functions below are module-level in
**`serve.py`**, beside `State`.

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
would outlive the build it describes. `State.begin()` leaves `found` alone, so
one `/status` response can carry a `requests` figure for the build *in flight*
beside a `found` for the *last completed* one. That is deliberate and safe:
nothing consults `found` while `building` is true — the page reloads instead,
and `Supervisor.refresh()` polls until `building` goes false before reading it.

Three states, and they must stay three:

| `found` | Means |
|---|---|
| `null` | nothing was compared — the first successful build in this process, or the build failed |
| `{"new_wins": 0, …}` | compared, and nothing is new |
| `{"new_wins": n>0, …}` | compared, and *n* lines are new |

The two reasons for `null` are distinguishable at the point of use even though
the value is one: a failed build sets `stale`, so it is reported as
`REFRESH_FAILED` and `found` is never consulted. `REFRESH_DONE` with `found`
null therefore means exactly one thing — the first successful build in this
server process — which is what lets §4.5 give it a sentence that says so.

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
Pure-function boundary is preserved: `render()` reads `model.get("requests", 0)`
— `.get()`, like every other key it reads, so a fixture written without the key
renders `0` rather than raising — and the poll updates the element thereafter.
§4.2 is what puts `requests` on the view `render()` receives.

The notice's existing *"about half a minute"* wording goes with it: under
LOTTO-0012 a retrying build can take considerably longer, and a fixed estimate
the build routinely overshoots is its own small version of a page that looks
broken.

```html
<div class="notice"><strong>Checking your tickets…</strong> This takes about
  half a minute on the first run, longer if the operator's site is dropping
  connections. Nothing below is a result yet.
  <span id="progress">0 lookups so far.</span></div>
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
    """The sentence for an outcome. Only REFRESH_DONE consults `found`.

    .get(), not [], carrying forward the reason tray.py's own call site
    records: this is composed inside a Qt slot, and a KeyError there kills
    the tray mid-notification. INV-23 asserts the map is total, so the
    fallback is unreachable; it exists so that if it ever were, the user
    sees a bare outcome word instead of nothing at all.
    """
    line = REFRESH_MESSAGE.get(outcome, outcome)
    if outcome != REFRESH_DONE:
        return line
    if found is None:
        # DONE with nothing to compare means exactly one thing (§4.3). Saying
        # so beats "Results refreshed." on its own, which leaves the user to
        # read silence about new wins as an absence of them.
        return line + " First check this session — nothing to compare against."
    n, cents = found["new_wins"], found["new_cents"]
    if not n:
        return line + " No new wins."
    return (f"{line} {n} new winning line{'' if n == 1 else 's'}, "
            f"R{cents / 100:,.2f}.")
```

The rand formatting duplicates `page.py::_rands()` on purpose: `supervise.py`
is the Qt-free lifecycle module the tray imports, and having it import the
renderer to format one number would couple the notification path to the page.
One `f`-string is the cheaper duplication.

`Supervisor.refresh()` already polls `GET /status` until `building` is false;
it stores that final answer's `found` on `self.found` and keeps returning one
of the four outcome constants unchanged, so INV-23's total map still holds and
no caller's signature moves. Two details the implementer needs and would
otherwise have to infer: **`Supervisor.__init__` sets `self.found = None`**, and
**`REFRESH_BUSY` and `REFRESH_RUNNING` leave it untouched** — `refresh()`
returns `REFRESH_BUSY` on a 409 without polling at all, so a first-ever refresh
that is refused would otherwise reach an attribute that was never assigned, and
`AttributeError` inside a Qt slot is the same failure the `.get()` above guards
against. Neither outcome consults it.

`tray.py::refresh()`'s `finished()` swaps
`supervise.REFRESH_MESSAGE.get(msg, msg)` for
`supervise.refresh_message(msg, self.sup.found)`, and still composes only the
failure line.

The notification body is built from two integers. It names no ticket, no board,
no draw date and no division — the reasoning that keeps ticket data out of the
URL (LOTTO-0014 INV-21) applies with more force to a notification, which the
desktop may log and sync off the machine.

## 5. Invariants

Numbering continues from INV-26, the highest allocated in this project
(`docs/specs/LOTTO-0001-lottery-ticket-tracker.md`) — ids are project-global
here, not per-spec.

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
  makes, is reset to 0 by `serve.py::refresh()`'s `work()` before the builder
  runs, and is what `GET /status` reports as `requests` and `page.py` renders on
  the building page.
  *Test:* `tools/verify_page.py::build_progress_is_visible`; breaks
  `no_counter_reset` and `count_per_call`.
  *Breaks when:* the reset is omitted, so the second build in a process opens
  at the first one's total and every figure after it is cumulative; or `_post()`
  increments once per call instead of once per attempt, so the figure freezes
  during exactly the retry storm it exists to narrate.

- **INV-29** — `GET /status`'s `found` is `null` unless a completed build had a
  predecessor model to compare against, and an object with `new_wins: 0` when
  it had one and nothing was new. `refresh_message()` returns three mutually
  distinct sentences for `null`, for zero and for a positive count.
  *Test:* `tools/verify_page.py::no_comparison_is_not_no_wins`; breaks
  `found_on_first_build` and `null_found_reads_as_zero`.
  *Breaks when:* the first build of a process compares against an empty model
  and reports every existing win as new; or `refresh_message()` maps `None` and
  `{"new_wins": 0}` to one string, making "could not compare" indistinguishable
  from "compared, found nothing".

- **INV-30** — The refresh notification body is composed from `new_wins` and
  `new_cents` alone. No ticket reference, board label, draw date or division
  name can reach it, whatever a win record beside it holds.
  *Test:* `tools/verify_page.py::notification_carries_no_ticket_data`; break
  `summary_names_a_ticket`.
  *Breaks when:* `refresh_message()`, or whatever `State.finish()` puts in
  `found`, is widened to carry a win record's `ref`, `line`, `date` or
  `matched` — for instance a well-meant "your PowerBall line B won on
  2026-07-04". The case asserts the composed sentence against a fixed shape
  rather than searching it for particular strings, because a summary built from
  two integers cannot contain a reference by construction and a test that
  merely looks for one is green before the rule exists (§7).

## 6. Failure modes

- **The API is down for the whole build.** All three attempts fail on the first
  request; the original `URLError` propagates; `State.fail()` sets `stale`,
  clears `found`, and leaves the model untouched (INV-18). The page shows the
  stale notice, the tray reports `REFRESH_FAILED`. `requests` is left at
  whatever was counted, which is honest — the requests were made.
- **The server restarts.** `found` starts `None` (§3), so the first build after
  a restart announces nothing even if it genuinely found a new win. The page
  still shows it; the notification says "First check this session", which is
  true and is not silence. What this must **not** become is a first build
  reporting its whole win list as new — that is INV-29's breaking input.
- **Two builds race.** They cannot: `State.begin()` returns `False` and the
  route answers 409. If that guard were ever removed, the unlocked counter in
  §4.1 would lose increments — which is why the argument for skipping the lock
  is written down beside it rather than assumed.
- **A retry succeeds after the page has given up.** It has not: the page polls
  until `building` goes false, and `Supervisor.refresh()`'s deadline reports
  `REFRESH_RUNNING` rather than a failure. Retries lengthen the wait; they do
  not change which outcome is reported.
- **A win record the comparison cannot key.** `_compare` runs inside
  `State.finish()`, which runs inside `work()`'s `try`, so a `KeyError` from a
  malformed win record would turn a *successful* build into `state.fail()` —
  the page would show the stale notice and the tray would report a failure, for
  a build that worked. `_win_key` therefore reads only fields
  `check.py::check()` writes unconditionally on every win record, and a
  comparison that raises is a defect in the model shape, not a network failure
  to be reported as one.
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
| `post_retries_transport_failure` | INV-27 | `results._post`'s opener stubbed to raise `URLError` a fixed number of times, then return a canned payload. Asserts three attempts then success, one attempt then re-raise on an `HTTPError`, and that the exception escaping after exhaustion is the *original* object. No socket. |
| `build_progress_is_visible` | INV-28 | The same stub, plus a **stub builder that itself calls `results.draws()`** a known number of times. Driven twice through `serve.refresh()` + `wait_idle(5)`, reading `GET /status` after each. Asserts the second build's figure equals the first's, not double it. |
| `no_comparison_is_not_no_wins` | INV-29 | `serve.make_server()` with a builder returning a scripted sequence of models; `wait_idle(5)` after each refresh. Asserts `found` is `null` after build 1 and an object after build 2, and that `supervise.refresh_message()` returns three distinct strings for `None`, `{"new_wins": 0}` and a positive count. |
| `notification_carries_no_ticket_data` | INV-30 | `supervise.refresh_message(REFRESH_DONE, found)` driven with `found` widened to carry a win record's fields beside the two integers; asserts the result still matches the fixed shape `^Results refreshed\. (No new wins\.\|\d+ new winning lines?, R[\d,]+\.\d\d\.)$` and therefore that no extra field reached it. |

Two seam notes, both of which the cases are wrong without:

- **The transport stub must be scoped, not installed globally.** `results.py`
  does `import urllib.request`, so `results.urllib.request.urlopen` *is* the
  shared module attribute — patching it would also intercept
  `Supervisor.status()` and `Supervisor.post()`, which `build_progress_is_visible`
  itself calls. Both cases save and restore around themselves, or stub the
  opener `_post()` uses rather than the module function.
- **These two cases add a transport seam beside the builder seam, and that is a
  deliberate exception to §7's inherited constraints.** LOTTO-0002 §4.2 pins the
  builder as *the* seam, and an inert stub builder never enters `_post()` — so
  `requests_made` would be 0 on every refresh and both of `build_progress_is_visible`'s
  breaks would be unobservable. It is the same trap INV-17 already documents for
  request-counting. The no-network and no-real-data constraints are untouched:
  nothing here opens a socket or reads the dump.

Each case must be **observed failing** under its named `--break` before it is
believed, per the project's own rule: these are greenfield, so there is no
pre-fix code to red-test against. Seven new breaks: `no_retry`,
`retry_http_error`, `no_counter_reset`, `count_per_call`,
`found_on_first_build`, `null_found_reads_as_zero`, `summary_names_a_ticket` —
taking the total from twenty-two to twenty-nine.

Both refreshing cases call `wait_idle(5)` before asserting, like every other
refreshing case in the file: `refresh()` starts a daemon thread and returns at
once, so an assertion made straight after it races a build that may not have
begun (LOTTO-0002 §4.2).

## 8. Alternatives considered (and rejected)

- **Carry the summary in `POST /refresh`'s response body instead of on
  `/status`.** Rejected: `do_POST` starts the build thread and *then* sends
  202, so the build has begun but cannot have finished — 202 means accepted,
  which `supervise.py::post()`'s own docstring states. A body composed at that
  moment can describe nothing the build found. Same reasoning LOTTO-0018
  already settled.
- **Show "fetched N of 27".** Rejected under §3: 27 is a measurement, not a
  constant, and a denominator that is wrong is worse than none — a bar that
  reaches 100% and keeps working is a stalled counter reading as completion.
- **Diff the win totals rather than the win set.** Rejected: two wins of equal
  value, one replacing another, would net to zero and announce nothing. Set
  difference on `_win_key` costs one pass over ~50 records.
- **Retry in each caller rather than in `_post()`.** Rejected for the reason
  LOTTO-0012 gives: one function serves `draws()`, `divisions()` and therefore
  every script, and per-caller retries would be four copies that drift.
- **Persist the comparison baseline to disk.** Rejected for the reason §3
  gives; tracked by LOTTO-0028.

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
| §4.4 the page's progress element is updated by the poll | **nothing** — `tools/verify_page.py` renders `page.render()` as a string and never executes its JavaScript. The same standing gap LOTTO-0002 §11's last row records for the poll itself; no roadmap id tracks it, and this item does not close it |
| §4.5 the tray composing only the failure line, now that the success line comes from a function rather than a map lookup | **nothing** — `refresh_reports_the_build` (INV-23) drives `supervise.Supervisor.refresh()` and asserts over the `REFRESH_MESSAGE` *map*; it never imports `tray.py`, and INV-29's case asserts `refresh_message()`'s output rather than the tray's use of it |

Eight rows, **four** with a bolded `nothing`. Two (§4.1, §4.4) are standing
limits — nothing here executes browser JavaScript or counts threads. Two are
narrower and closable: §4.2 wants a shape assertion on `/status`'s body, §4.5
wants a case that reads `tray.py`'s composition. Neither is written, and saying
so is the point of the row — this item's honest error budget went **up** by one
when a wrong row claiming `refresh_reports_the_build` covered §4.5 was corrected
to `nothing`, which is the trade the standard asks for.

## 12. Cross-doc impact

- `CLAUDE.md` — the `--break` count (twenty-two → twenty-nine), and the
  `verify_page.py` line naming which invariants it covers.
- `tools/verify_page.py` — its docstring's case count (thirteen → seventeen),
  its invariant range (`INV-12 to INV-21 and INV-23 to INV-25` gains
  `and INV-27 to INV-30`), and its scope sentence: it currently reads "for the
  local page and the tray that drives it", and INV-27/INV-28 are network-layer.
- `docs/specs/LOTTO-0002-local-web-page.md` — §4.2's `State` sketch gains
  `found`, and its `get()` line changes from a five- to a six-tuple
  (`# -> (model|None, building, built, stale, error, found)`). Its §11 last row
  already records the no-JavaScript gap this spec's §11 points back at.
- `docs/specs/LOTTO-0013-tray-and-supervisor.md` — §4.6 describes
  `Supervisor.refresh()` and `REFRESH_MESSAGE`; `refresh_message()` joins them,
  and `Supervisor` gains a `found` attribute. **INV-23 is unchanged in
  property, extended in surface**: the outcome map stays total and only
  `REFRESH_DONE` reads as success, but the sentence a user actually sees is now
  composed by `refresh_message()`, which INV-23's case does not read — §11
  records that as a `nothing`.
- `docs/specs/LOTTO-0014-http-surface-and-security.md` — §4.1 lists `GET
  /status`'s response body.
- `CHANGELOG.md` and `ROADMAP.md` — three bullets flipped, one entry each.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 1 | 2026-08-05 | 3 (cold, identical packet) | 1 | 7 | 9 | 11 | 28 verified, all fixed; 3 dismissed as unverified. Dimensions: dim5×10, dim2×5, dim4×4, dim15×3, dim7×2, dim1×2, dim6×2, dim10×2, dim9/dim13/dim8×1. The CRITICAL and two of the HIGHs were one hole: `requests` and `found` were specified onto `GET /status`'s body and nowhere else, so `render()` would have raised on the opening build and `State.get()`'s five-tuple could not carry the summary at all. Two more HIGHs killed both new test seams — a builder stub never enters `_post()`, so the counter case asserted 0, and the privacy case was green by construction against a two-integer input. Dismissed: a missing TOC (no sibling has one), the `::case` citation style (LOTTO-0002 §11 uses exactly it) and the LOTTO-0012 measurement attribution (its bullet does carry it). One lane's *open question* became a real finding — §11 cited LOTTO-0007 for the no-JavaScript gap, and LOTTO-0007's (a)–(e) tail is not that. |
