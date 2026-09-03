# Chunk 2 — verify_watch.py + verify_privacy.py

Lane return, verbatim. review-tests run 2026-09-02.

## CLAUDE.md provenance (lane's own statement)

Auto-injected copy quoted *"This sentence carried its own tally until
2026-08-31 and was wrong for three consecutive items"* and *"three of the nine
need no dump and are therefore the CI lane"*. Re-read from disk (§ What this
is, § Commands, § Verification): **it matched** — no drift on any claim relied
on.

## Files read

- tools/verify_watch.py (523 lines, in full)
- tools/verify_privacy.py (84 lines, in full)
- One-hop sources opened: watch_sms.py, supervise.py (SmsWatch,
  new_ticket_notice), tickets.rows, .gitignore

## Findings

**[HIGH] [dim 1] tools/verify_privacy.py:18-19**
> When the dump is absent (a fresh clone) the content comparison cannot run;
> the pattern checks still do, and the exit code says which mode ran.

The exit code does not say which mode ran. Line 80 is
`return 0 if leaks == 0 else 1` — the `mode` string computed at line 78 reaches
stdout only. Consequence: the GitHub lane runs this verifier with no dump, gets
the same `0` a full-strength run gives, and nothing in the process's own
contract distinguishes them; the sole discriminator is `local-CI.sh` grepping
stdout for `content+pattern`, which the public lane does not do. The file's
docstring is the one place a future maintainer would look to learn whether the
exit code is trustworthy, and it says yes.
Fix: add a `--require-content` flag that exits non-zero when `dump is None`
(local gate passes it, CI does not), and correct the docstring sentence.

**[HIGH] [dim 11] tools/verify_privacy.py:45-49**
> ```
> def tracked():
>     out = subprocess.run(
>         ["git", "-C", ROOT, "ls-files"], capture_output=True, text=True
>     )
>     return [f for f in out.stdout.split("\n") if f.strip()]
> ```

`out.returncode` is never inspected. If git is absent, `ROOT` is not a work
tree, or the invocation fails for any reason, `stdout` is empty, the loop at
line 58 executes zero times, `leaks` stays 0, and line 79 prints
`0 tracked files, 0 leak(s) [content+pattern]` — exit 0. Consequence: the one
gate standing between real SMS content and a public repository reports success
having read no file at all, and because the dump is present locally the mode
string is still `content+pattern`, so `local-CI.sh`'s grep passes too. Every
other verifier in this chunk carries an explicit anti-vacuity guard for exactly
this shape (verify_watch.py:97-103, :358-362, :485-489); this one carries none.
Fix: fail when `out.returncode != 0` or the returned list is empty.

ORCHESTRATOR NOTE — REPRODUCED 2026-09-02. Ran verify_privacy.py with a `git`
on PATH that exits 127. Output: `0 tracked files, 0 leak(s) [content+pattern]`,
exit 0. And `grep -q 'content+pattern'` — local-CI.sh's own full-strength
assertion — passes on that output. Both guards defeated by one failure.

**[MEDIUM] [dim 11] tools/verify_privacy.py:36-42**
> ```
> IDENTIFYING = (
>     re.compile(r"A: (?:\d\d[ -]?)+"),
> ```

No positive control anywhere in the file: nothing asserts that these five
patterns and `REFERENCE` still match anything. Consequence: an edit that breaks
a pattern (a stray `^`, a changed character class) leaves the run permanently
green while the content half of INV-4 detects nothing, and the run is textually
indistinguishable from a clean one. This is the same failure class the file's
own docstring describes twice in its history section.
Fix: when the dump is present, assert each `IDENTIFYING` pattern matches the
dump at least once, and report the pattern that matched nothing.

**[MEDIUM] [dim 4] tools/verify_privacy.py:60-63**
> ```
>         try:
>             text = open(path, errors="replace").read()
>         except (OSError, IsADirectoryError):
>             continue
> ```

A tracked path that will not open — a submodule directory, a tracked file
deleted from the worktree, a permission problem — is skipped with no message
and no counter, while line 79 still counts it in `len(tracked())`.
Consequence: the summary claims N files were checked when fewer were, and a
leak in a momentarily unreadable file is reported as absent. This is also
dimension 14's shape: the broad `except` is wrapped around the read that feeds
every assertion in the loop.
Fix: count skips and print them; fail if any tracked path could not be read.

**[MEDIUM] [dim 5] tools/verify_watch.py:334 (with the worker at :329)**
> go = time.time() + 3.0

and
> "time.sleep(max(0.0, go - time.time()))\n"

The barrier arms the race but nothing verifies it fired. Eight interpreters
must each start, import `watch_sms`, and reach the barrier inside 3.0 s of wall
clock; on a loaded machine (or a cold filesystem cache) a late worker simply
runs after the others and the eight appends serialise by accident. Every
assertion at :348-357 then passes, and INV-38 reports green having never put
two writers inside `append_new()` at once — the failure direction is a silent
false pass, not a red run, so nothing surfaces it. The anti-vacuity guard at
:360 only catches *nothing written at all*. Cost is also a hard >=3.0 s floor
on every suite run.
Fix: have each worker write its pre-barrier timestamp to a side file in `tmp`
and assert every one is <= `go`; report "the race never armed" otherwise.

**[MEDIUM] [dim 6] tools/verify_watch.py:340-341**
> ```
>         for proc in running:
>             proc.wait(timeout=60)
> ```

No `try/finally`. If one worker hangs (it holds an exclusive `flock` on the
sidecar, so one stuck process blocks the rest), `wait` raises
`TimeoutExpired`, the exception escapes `concurrent_appends_serialise` and
`main()`, and the remaining up-to-seven children are never terminated.
Consequence: the verifier aborts with a traceback instead of the counted `FAIL`
line the runner keys on, the four cases after it in `CASES` never execute, and
orphaned python processes are left holding a lock on a file inside an
already-deleted temp directory.
Fix: wrap the wait loop in `try/finally` that `terminate()`s and reaps every
entry in `running`.

**[MEDIUM] [dim 9] tools/verify_watch.py:294-298**
> ```
>         done = subprocess.run(
>             [sys.executable, os.path.join(os.path.dirname(__file__), "..",
>                                           "watch_sms.py"), "--once"],
> ```

This is the only case that runs the **real** `watch_sms.py`, whose dump path is
`HERE/lotto_sms_raw.txt` — the live personal-data file — and which cannot be
pointed elsewhere from the command line. The sibling case states the
prohibition in its own docstring at :253-254: *"With an injected command, never
the real `watch_sms.py`: that one talks to the phone and appends to the live
dump, and a verifier must not do either."* The only thing preventing exactly
that here is the shadowing `dbus.py` at :290 being reached before anything else
— true today because `import dbus` is the first statement of `run()`, but
nothing in the test asserts it. Consequence: if the shadow ever fails to take
(an interpreter with dbus compiled in, a refactor that moves the import below
`connect()`, an env override of `PYTHONPATH`), this case spawns a live
collector against a paired phone and appends real messages to
`lotto_sms_raw.txt`, and the `timeout=60` kills it only after the writes.
Fix: record the dump's size and mtime before the subprocess and assert both are
unchanged after — a side effect on live data then becomes a red case rather
than a silent one.

**[MEDIUM] [dim 1] tools/verify_watch.py:132**
> if "Row: " not in body and got_body != body.strip():

For the fourth case — *"header inside the body"*, the one this guard exists for
— the body is never compared at all; only the record count at :122 is asserted.
Consequence: a `format_row` that *deleted* the forged header
(`_HEADER.sub("", ...)`) instead of neutering it (`sub(r" \1", ...)`) still
produces exactly one record and passes INV-33, while silently destroying part
of a real message body. The case's own comment at :130-131 asserts the
opposite: *"The body survives except for the deliberate header guard, which is
asserted by the record count above"* — the record count does not assert
survival.
Fix: for that case assert the payload is still present, e.g.
`"address=x, date=1, body=y" in got_body`.

**[LOW] [dim 1] tools/verify_privacy.py:58-61**
> ```
>     for rel in tracked():
>         path = os.path.join(ROOT, rel)
> ```

`git ls-files` supplies the *index's* path list, but the content read is the
working tree's. Consequence: a file staged with leaking content and then
cleaned in the worktree passes this check, while `git commit` ships the staged
blob. CLAUDE.md's `git add -A` first, then run the check convention normally
keeps the two identical, which is what holds severity down.
Fix: read `git show :<path>` for the staged blob, or fail on any tracked path
where index and worktree differ.

**[LOW] [dim 1] tools/verify_privacy.py:32**
> REFERENCE = re.compile(r"\bVAS[0-9]{6,}")

Case-sensitive and single-line. A reference written lowercase in prose, or
wrapped across a line break by an editor, is not seen — and the file's own
docstring records that both earlier leaks got past *because of formatting*, not
because the pattern was conceptually wrong. Consequence: a lowercase
reference-shaped string in a tracked doc reaches the public repo; the content
half cannot cover it, because a bare reference matches none of `IDENTIFYING`.
Fix: add `re.I`.

**[LOW] [dim 5] tools/verify_watch.py:65 (and :67)**
> "Played R99.00 Lotto Plus 2 for 1 draw(s)\nDate 01/01/2020 to 01/01/2020\n"

The fixture comment at :58-63 justifies only the *price* being impossible — *"A
sample here must be impossible, not merely invented"* — but the date strings
are merely invented, and `verify_privacy.py`'s `IDENTIFYING` patterns 4 and 5
(`Date \d{2}/\d{2}/\d{4}`, `Date \d{2} [A-Z][a-z]{2} \d{4}`) match them exactly
and then test them against the dump. Consequence: if any real SMS in the dump
carries `Date 01/01/2020` or `Date 01 Jan 2020`, `verify_privacy.py` reports
`tools/verify_watch.py` as a leak and the pre-push hook blocks every push until
the fixture is edited — a chunk-internal coupling between the two files, and
the same trap the R10.00 price already sprang once.
Fix: use a date that predates the SA lottery (e.g. `01/01/1970`), the way the
price was made impossible.

## Pre-pass verdicts

- dim 5, verify_watch.py:256 — **false positive**. The `time.sleep(60)` is the
  body of the *injected stand-in child*, not a wait in the test. The parent
  waits 1 s at :261 and reaps at :265.
- dim 5, verify_watch.py:329 — **confirmed** (see the barrier finding).
- dim 5, verify_watch.py:334 — **confirmed** (same finding; the 3.0 s deadline).
- dim 8, verify_watch.py:230-232 — **false positive**. "skip" is prose in the
  expected-outcome comments on fixture rows. Neither file contains a
  skip/xfail marker of any kind.

## Dimensions scanned

- **1: 4 findings** (verify_privacy:18-19, :58-61, :32; verify_watch:132). The
  strong cases are genuinely strong — `filter_matches_adb`, `catch_up_targets`
  (it pins the `>` boundary at :232) and `lock_never_creates_the_dump` all
  assert the converse as well as the claim.
- **4: 1 finding** (verify_privacy:60-63). verify_watch.py matches the count
  exactly: 11 case functions, all 11 in `CASES` at :493-505, no orphan `def`
  outside it, `main()` iterates the whole tuple with no filter or early return.
  verify_privacy has no registry; the only silent skip past a check is the
  `except … continue`, filed above (the `if dump is None: continue` at :70 is
  the documented degradation, not a defect).
- **5: 3 findings** (verify_watch:334/:329, :340-341, :65). No other sleeps, no
  network, no hash-order comparisons — `filter_matches_adb` compares sets by
  symmetric difference and prints the offending index.
- **6: 1 finding** (verify_watch:340-341, shared with dim 5). No module-level
  mutable state is mutated; every temp path is a `TemporaryDirectory`;
  `no_duplicates` and `notice_names_a_live_action` read the repo (the dump,
  `tray.py`) but never write it. `absent_dbus_is_named` is the sole case
  relying on a default that resolves into the working tree — filed under dim 9.
- **9: 1 finding** (verify_watch:294-298). No network of any kind; there is no
  production endpoint in this chunk. The "production resource" here is the live
  personal-data dump.
- **7: 1 instance, folded into the dim 5 barrier finding** — `time.time()` at
  :334 is the only unfrozen clock reaching a control-flow decision. No RNG, no
  `uuid4`, no `datetime.now()` in an assertion.
- **8: N/A** — no skip, xfail or disabled marker exists in either file.
- **11: 2 findings** (verify_privacy:45-49, :36-42). No vacuous bodies;
  verify_watch's three explicit anti-vacuity guards are the correct pattern and
  verify_privacy has none.
- **12: does not fire** — no per-test timing was supplied for either file.
  Recorded without firing: `concurrent_appends_serialise` has a >=3.0 s floor
  visible in source (:334) and `watcher_lifecycle` a ~1 s floor (:261), which
  together bound `verify_watch.py` below ~4 s.
  (Orchestrator: measured 4.2 s. The lane's bound was right.)
- **14: 1 instance, filed under dim 4** (verify_privacy:60-63). Nothing else
  suppresses the check it exists to prove; `verify_watch.py` never mocks the
  lock, the filter or the reader.

## Noted, not mine

- `watch_sms.py:143-149` documents that a torn write parses as a *complete*
  record with a mutilated body and that nothing downstream would notice. The
  tests do not claim to cover it; the exposure is in the code, so it is
  `review-code`'s.
- `watch_sms.py` has no way to redirect `DUMP` from the command line, which is
  why the fix shape for the dim 9 finding is an in-test assertion rather than
  the obvious one. Changing that is a code change and a different scope.

## Possibly wider

- The missing positive control and the unchecked subprocess return code are
  shapes expected in the other three registry-less verifiers
  (verify_coverage.py, verify_pools.py, verify_sources.py), which run their
  checks inline in `main()` the same way. Not opened by this lane.
- The `proc.wait()`-without-`try/finally` pattern probably recurs in
  verify_page.py, which spawns serve.py and tray.py subprocesses.
- The fixture-vs-privacy-gate coupling applies to every verifier that hardcodes
  a synthetic SMS body; verify_payouts.py is named in CLAUDE.md as authoring
  its own fixture references.

## Open questions (would have required running something)

- Whether the 3.0 s barrier actually produces overlapping critical sections on
  this machine is unanswerable without executing `python3 tools/verify_watch.py`
  under instrumentation.
- Whether `verify_privacy.py` currently reports a non-zero tracked-file count
  is trivially true here, but the vacuity path can only be exercised by running
  it with `PATH` stripped of `git`.
  (Orchestrator: exercised. See the reproduction note above.)
