# Chunk 1 — verify_page.py (2,068 lines)

Lane return, verbatim (methodology prose dropped; findings unedited).
review-tests run 2026-09-02.

Staleness check (lane's own): re-read CLAUDE.md from disk, spot-checked
CLAUDE.md:236 ("every case in tools/verify_page.py is renderer-only") and
:120 ("--list shows the thirty-one breaks"). Both matched the injected copy.
One-hop reads: serve.py, supervise.py, page.py, results.py, tray.py.

## Findings

**[HIGH] [dim 1] tools/verify_page.py:783-788 (runs to 823)**
> ```
>         root = tempfile.mkdtemp(prefix="lotto-qt-")
>         for f in ("serve.py", "page.py", "supervise.py", "check.py", "history.py",
>                   "tickets.py", "results.py", "backfill.py"):
>             shutil.copy(os.path.join(ROOT, f), root)
> ```

The two Qt breaks redden `serve_is_headless` for a reason that has nothing to
do with Qt. `expiry.py` exists at the repository root and is NOT in that copy
list, while supervise.py:27 does `import expiry` at module level and
serve.py:63 does `from supervise import (...)` at module level. So in the
copied tree the probe's `import serve` dies with
`ModuleNotFoundError: No module named 'expiry'` BEFORE the Qt-detection line is
reached, and the case fails at the wrong assertion (:818).

Consequence: `--break qt_import` and `--break pyqt_import` both print
`red test OK: serve_is_headless failed as it should` and exit 0 while the `qt`
detection at :799-800 never runs. These two breaks are the ONLY evidence the
project has that this case can catch a Qt import at all (INV-19 is the one
invariant with no other verifier), and that evidence is void. A regression that
broke the `PySide|Qt|PyQt\d*` predicate itself would leave both red tests still
"passing".
Fix: add "expiry.py" to the copy list (or copy *.py from ROOT).

ORCHESTRATOR REPRODUCTION 2026-09-02 — CONFIRMED, twice over.
1. Copied exactly that eight-file list to a temp dir; `python3 -c "import serve"`
   -> ModuleNotFoundError: No module named 'expiry'. Adding expiry.py -> OK.
2. Ran `python3 tools/verify_page.py --break qt_import`. Output:
     RED TEST: break=qt_import - serve_is_headless is expected to FAIL
       FAIL  INV-19  serve_is_headless
               importing serve failed: Traceback (most recent call last):
     red test OK: serve_is_headless failed as it should
   exit 0. The red test passes on the wrong failure.

**[MEDIUM] [dim 9, dim 1] tools/verify_page.py:416-418**
> ```
>         st, _, _ = req(child_port, "POST", "/refresh", host=f"127.0.0.1:{child_port}",
>                         headers={"X-Lotto-Token": "childtoken-0123456789"})
>         need(st == 202, f"child did not accept its LOTTO_TOKEN: got {st}")
> ```

This is the one place the file leaves its own no-network / no-real-data box,
and it starts a real build. serve.py:826 passes the *real* build_model to
make_server unconditionally; LOTTO_NO_BUILD (set at :402) only gates the
OPENING build at serve.py:831-832. So this POST enters
serve.refresh(state, build_model) in the child, which reads the real
lotto_sms_raw.txt (serve.py:223-226, anchored to the repo root, not $HOME) and
then calls check.check() -> results._post() ->
https://www.nationallottery.co.za/api. The child is SIGTERMed a few
milliseconds later, so the build is killed mid-flight — which makes the blast
radius small but leaves it *raced* rather than *prevented*.

This falsifies two stated guarantees: the file's own header (:16-20) "No
network. The seam is the BUILDER, not the model" and "No real data … tickets
built from the VAS00000000000 sentinel rather than lotto_sms_raw.txt"; and
CLAUDE.md:239's "nothing in that file calls build_model()".
Fix: assert the child's token on a route that starts no build, or spawn this
one child with the dump path pointed at the temp $HOME.

**[MEDIUM] [dim 1] tools/verify_page.py:609-673**
> `"""INV-16 — the compared spend is the apportioned cost of the checkable`
> `    entries of RESOLVED tickets, and nothing else."""`

The case asserts a number it computed itself and placed in the fixture.
`expected_cmp` is accumulated by the case (:631, "# recomputed from
TIER_PRICES directly") and then written into the model it renders (:643,
"compared_cents": expected_cmp). Nothing under test decides `compared_cents` —
the derivation the docstring names lives in serve.py::build_model (:244-275),
which this file never invokes for an assertion. page.render only formats the
integer it was handed, so the final check (:670-673) compares the case's
arithmetic against the case's own fixture value.

The break confirms it: `spend_is_lifetime` (:649-650) mutates
model["spend"]["compared_cents"], i.e. the FIXTURE, not any production code. No
change to build_model can turn this case red, so a regression in the "checkable
entries of RESOLVED tickets" apportionment — the actual subject of INV-16 —
ships green. What the case DOES verify is real but narrower: that
_spend_section puts the compared figure in the compared row.
Fix: apportionment needs the treatment period_buckets already got — a pure
function taking its data as arguments, asserted the way verify_periods.py
asserts INV-57..60; meanwhile narrow this docstring to the rendering clause it
actually holds.

**[MEDIUM] [dim 14] tools/verify_page.py:802-806 (asserted at 821)**
> ```
> "try:\n"
> "    import glob\n"
> "    for p in glob.glob('/proc/self/task/*/children'):\n"
> "        kids += open(p).read().split()\n"
> "except OSError:\n"
> "    pass\n"
> ```

The `except OSError: pass` sits around the only source of the data one of
INV-19's three clauses is asserted from. If /proc/self/task/*/children is
absent (kernel built without CONFIG_PROC_CHILDREN) or unreadable, `kids` stays
[] and `need(not data["children"], ...)` passes vacuously — the "importing it
spawns nothing" clause reports green having measured nothing, and nothing
distinguishes that from a real pass. There is no positive control, in a file
otherwise scrupulous about them (:308). Neither Qt break exercises this clause
either, so the vacuity has no second net.
Fix: fail the probe when the glob matches nothing, rather than swallowing to an
empty list.

**[LOW] [dim 5] tools/verify_page.py:961-970**
> `need(time.monotonic() - started < 0.2, "the 409 was polled on rather than reported at once")`

A 0.2 s wall-clock budget on one localhost POST round-trip. The margin against
the failure it discriminates is enormous (a polled result would take seconds),
so the threshold could be 2 s and lose nothing; at 0.2 s a loaded machine turns
a correct implementation red with a message naming a defect it does not have.
Fix: raise the bound to ~2 s.

**[LOW] [dim 5] tools/verify_page.py:324, 395, 498, 770, 1066, 1022-1023**
> `        srv.shutdown()`

serve_on() starts a real ThreadingHTTPServer; shutdown() stops serve_forever
but does NOT close the listening socket. Only build_progress_is_visible pairs
it with server_close() (:1690). A full run leaves ~9 listening sockets bound
and ~9 fds open for the life of the process. Bounded and small today; it is the
shape that bites under a low `ulimit -n` or a future aggregate runner.
Fix: srv.server_close() beside every srv.shutdown(), as :1690 already does.

**[LOW] [dim 6] tools/verify_page.py:79-84**
> ```
> def temp_home():
>     """A fresh $HOME and $XDG_CONFIG_HOME. Both, never just $HOME."""
>     d = tempfile.mkdtemp(prefix="lotto-verify-")
> ```

15 cases call it; only two (:396, :499) rmtree the result. Every run leaves 13
lotto-verify-* directories in /tmp, some containing a written autostart
.desktop file. No test depends on the leftovers, so accumulation rather than
cross-test contamination.
Fix: register the directory for removal at the end of the case, or a
module-level list drained in main()'s finally.

## Pre-pass verdicts
- :407 `deadline = time.time() + 10` — mitigated: a poll-with-deadline loop
  (:407-415) with a `while…else: raise Fail`. Nit: time.time() where the file's
  other readiness loop uses time.monotonic() (:1085).
- :413 sleep(0.1) — false positive: the poll interval of that same loop.
- :840 sleep(0.5) — false positive: inside the `terminate_only` break body,
  i.e. the deliberate defect being injected, not test timing.
- :859 / :882 sleep(0.1) — mitigated: poll intervals of two bounded
  `for _ in range(50)` loops, each with an explicit need() on the outcome.
- :1095 sleep(0.1) — mitigated: poll interval inside _child_on's monotonic
  deadline loop, with an early child.poll() exit.
- :875-876 and :1265-1266 raw socket bind — false positive: both bind 127.0.0.1
  on a port the test owns; :1268 is the deliberate trap proving a rejected PORT
  did not fall back.
- :410 / :1090 urlopen — false positive as network targets (loopback). The
  child behind :410 is the subject of the MEDIUM above, for the build it
  starts, not this URL.
- :1314 http://127.0.0.1:65000 — false positive: a FakeSup class attribute
  inside TRAY_PROBE; nothing fetches it.
- :1353 except BaseException — false positive: captures into out["error"],
  which is exactly what tray_headless_when_managed asserts on (:1383, :1398).
- :1526 except Exception: pass — mitigated: the swallowed exception is not the
  subject; the assertion two lines down is on len(http_calls) == 1. It does
  mean nothing checks WHICH exception escapes the HTTPError path.
- :1605 except Exception — false positive: inside the `rigged` break
  replacement, mirroring serve.refresh's own work().
- :2053 except Exception — false positive: main()'s per-case handler; it
  increments failures and prints the type.

## Dimensions scanned
- 1: 3 findings. Every other break traced bites the thing its case names —
  verified against source for host_endswith/no_security_headers,
  token_exempt_refresh, reflect_path, the three uncheckable_not_a_loss breaks,
  clear_after_build, clear_model_on_failure, terminate_only, url_pushstate, the
  three refresh_reports_the_build breaks, the four port breaks, both tray
  breaks, no_retry/retry_http_error, the three counter breaks, and the three
  notification breaks.
- 4: clean. All ten non-registered module-level defs are helpers with call
  sites; none is a case that never runs. All 33 BREAKS values name a registered
  case, and all 18 registered cases carry at least one break.
  TWO STALE COUNTS, filed nowhere because no dimension covers them: the module
  docstring says "Seventeen cases" / "all seventeen" / "binding on all
  thirteen" against 18 registered cases, and CLAUDE.md:120 says "thirty-one
  breaks" against 33.
- 5: 2 findings. Also noted, not filed: supervise.free_port() binds port 0,
  reads the number and closes — a TOCTOU window every case using it inherits.
- 6: 1 finding. Otherwise sound: every case that mutates os.environ
  PORT/LOTTO_PORT/LOTTO_NO_BUILD restores it in a finally; _stub_transport's
  urlopen swap is restored in every finally. One residue: if
  post_retries_transport_failure fails inside its first block the later finally
  at :1533 never runs, leaving results.BACKOFF at 0.001. Harmless because a
  --break run executes exactly one case.
- 7: clean bar one nit — no RNG, no uuid4, no datetime.now() in an assertion.
  The nit is time.time() for the :407 deadline.
- 9: 1 finding — the live nationallottery.co.za build started by the
  token_required child. Everything else is loopback or a stubbed transport.
- 11: clean. The nearest thing to a vacuous body is the /proc children clause,
  filed under dim 14.
- 12: N/A — the baseline gives a file total (7.6 s for 18 cases) and no
  per-case attribution.
- 14: 1 finding.
- 8: N/A — no skip/xfail/disable mechanism; --only is an invocation filter,
  which the dimension excludes explicitly.

## On the two file-specific questions

(a) The CLAUDE.md:236-240 claim. SPLIT VERDICT.
- "fixture_model() is a hand-authored dict" — TRUE (:87-169).
- "render_pure() installs an all_draws double that raises" — TRUE (:597-606);
  worth knowing that only 3 of the 18 cases go through render_pure. The other
  renders reach page.render through a live do_GET or directly with
  history.all_draws un-doubled. Those three are enough to hold the no-I/O
  claim, so not a finding — but the guarantee is narrower than the sentence
  suggests.
- "every case … is renderer-only" — FALSE as written, though harmlessly so: 12
  cases run a real ThreadingHTTPServer, four spawn serve.py subprocesses, one
  spawns a tray.py probe.
- "nothing in that file calls build_model()" — FALSE, and this one has a
  consequence: token_required:416 causes the real build_model() to execute in a
  child process.
- "a builder-side defect cannot be seen there" — TRUE, and it is the
  load-bearing half. No assertion anywhere observes build_model's output. So
  the instruction "Do not move these cases into it" stands on a correct
  premise, but its stated reason is wrong in a way that hides a live-API call.

(b) Do the breaks break the right thing? 31 of 33 do — traced each against
source, and several are notably well-built (dash_for_unscorable renders &mdash;
and the case unescapes entities to catch it; blank_numbers_cell patches
_boards_cell rather than _balls because _boards_cell is what decides absence).
The two exceptions are the Qt pair (HIGH) and spend_is_lifetime (MEDIUM).

## Noted, not mine
- serve.py:826 hands the real build_model to make_server regardless of
  LOTTO_NO_BUILD, so POST /refresh always builds for real. review-code's call.
- results.py:88-89 — after the retry loop, `payload` is referenced outside the
  for; the ATTEMPTS comment already owns it.

## Possibly wider
- The srv.shutdown()-without-server_close() pattern and the un-cleaned
  temp_home() almost certainly recur in verify_watch.py and verify_expiry.py,
  which both import supervise.
- The "copy a subset of the tree into a temp dir and import it" break idiom may
  be unique to this file, but if any other verifier hard-codes a module list
  the same way, the same missing-expiry.py failure applies.
