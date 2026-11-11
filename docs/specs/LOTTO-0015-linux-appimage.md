<!-- ants-spec-format: 1 -->
# LOTTO-0015 — Ship the tracker as one Linux AppImage file

**Status:** spec draft (2026-11-11).
**Kind:** package.
**Source:** ROADMAP LOTTO-0015 (user-request-2026-08-02). The scope decisions
in §3 were taken with the user on 2026-11-11.

**Pairs with:** LOTTO-0013 (the supervisor, whose §4.2 spawn rule this
changes), LOTTO-0003 (the watcher, §4.6) and LOTTO-0002 (the page's
no-messages notice, §4.5, and the autostart entry, §4.7).

*Layman: one file you can double-click to run the tracker, with no Python or
Qt to install; it keeps your messages and results in your home folder, and
tells you plainly when that folder is still empty.*

## 1. Goal

A single file, `LottoTracker-<version>-x86_64.AppImage`, that starts the tray,
the page and the SMS watcher on this machine with nothing else installed
beyond KDE Connect. It keeps its data in `~/.local/share/LottoTracker`. Run
from any folder, against a copy of the real dump and archive, it shows the same
tickets a source checkout shows. A source checkout behaves as it does today.

## 2. Problem

The project runs only as `python3 <file>` from the repository. Bundling it with
PyInstaller and wrapping it as an AppImage breaks four things, each found by
reading the code on 2026-11-11:

1. **The code folder is read-only, and four modules write beside their own
   file.** `backfill.py` anchors `CACHE` and `ARCHIVE` to its own folder;
   `watch_sms.py` anchors `DUMP` and `THREADS`; `serve.py` and `supervise.py`
   each anchor a `DUMP`. Inside an AppImage that folder is the read-only mount,
   so every write fails and every read finds nothing.
2. **The helpers are started as scripts.** `supervise.Supervisor.start()` runs
   `[sys.executable, os.path.join(HERE, "serve.py")]` and
   `supervise.SmsWatch.__init__()` builds the same shape for
   `watch_sms.py`. In a frozen build `sys.executable` is the bundled program,
   not a Python interpreter, and no `.py` file ships.
3. **The autostart entry names a script.** `serve.DESKTOP_ENTRY` writes
   `Exec="<sys.executable>" "<HERE>/tray.py"`. From an AppImage both halves
   point inside a temporary mount that is gone at the next login.
4. **The older-results download has no way in.** Results before the official
   feed's start come from `backfill.py`, which the user runs by hand from a
   terminal (`CLAUDE.md` § Commands). An AppImage user has no terminal command
   to run, so every older ticket would stay "not checkable" for good.

A fifth problem is older than this item. The page's no-messages notice,
`page.py::_notice()`'s `no_dump` branch, tells the user to run
`python3 find_lotto_sms.py`. That script prints and writes nothing (`CLAUDE.md`
§ Commands), so the advice cannot fill the empty page. The AppImage needs a
different notice anyway, so this item corrects both.

## 3. Scope decisions (agreed with the user)

- **Linux AppImage only.** The Windows build, and where its messages would come
  from, waits until someone needs it (user, 2026-11-11). The roadmap item's
  Windows half stays open.
- **Data lives in `~/.local/share/LottoTracker` for the AppImage; a source
  checkout keeps the repository folder** (user, 2026-11-11). The first run names
  that folder and says it is empty.
- **Older results come from a tray menu item, "Fetch older results", never
  automatically** (user, 2026-11-11). The page points at it while the archive
  is missing. Nothing slow or network-heavy starts without the user asking.
- **Built on this machine, for this machine** (user, 2026-11-11). The AppImage
  carries this machine's Python and libraries, so it runs on systems at least
  as new as openSUSE Tumbleweed. A build for older systems is a separate item.

Decided here, not by the user, each following from §2:

- `$XDG_DATA_HOME` is honoured, defaulting to `~/.local/share`, because
  `supervise.config_home()` already honours `$XDG_CONFIG_HOME` the same way.
- **Settings stay shared.** Both forms read `~/.config/lotto-tracker`, and both
  write the one autostart file. Running both trays at once already fails on the
  shared port, so a second settings folder would buy nothing.
- **The menu item exists in a source checkout too.** One code path, and a
  source user gains a way to fetch older results without a terminal.

## 4. Design

### 4.1 One module answers "where": `paths.py`

A new Qt-free, stdlib-only module. Every other module takes its paths from it.

```python
FROZEN: bool              # getattr(sys, "frozen", False): True under PyInstaller
RESOURCES: str            # FROZEN: sys._MEIPASS; else this file's folder
DATA: str                 # FROZEN: $XDG_DATA_HOME or ~/.local/share, + "/LottoTracker"
                          # else: this file's folder (the repository)
DUMP: str                 # DATA + "/lotto_sms_raw.txt"
THREADS: str              # DATA + "/sms_threads.json"
ARCHIVE: str              # DATA + "/archive_results.json"
CACHE: str                # DATA + "/archive_cache"

def resource(*parts) -> str   # RESOURCES joined with parts
def ensure_data() -> None     # makedirs(DATA, exist_ok=True); called by tray.main()
                              # and by each child's main(), never at import
```

The existing names stay as aliases so no caller changes shape:
`backfill.CACHE = paths.CACHE`, `backfill.ARCHIVE = paths.ARCHIVE`,
`watch_sms.DUMP = paths.DUMP`, `watch_sms.THREADS = paths.THREADS`,
`serve.DUMP` and `supervise.DUMP` likewise. `history.py` keeps importing
`ARCHIVE` from `backfill`. The lock file follows the dump, because
`watch_sms.py` derives it from the dump's path.

Resources move to `paths.resource()`: `serve._data_address()` for the icon and
font, and `tray.ICON_RUNNING` and `tray.ICON_STOPPED`.

`paths.py` touches no file at import. `LOTTO-0013` INV-19 (importing `serve` or
`supervise` starts nothing) holds unchanged.

### 4.2 Starting the helpers: one function, two forms

```python
# supervise.py
def child_command(name, *args) -> list[str]:
    """name is "serve" or "watch"."""
    # source: [sys.executable, os.path.join(HERE, SCRIPT[name]), *args]
    #         SCRIPT = {"serve": "serve.py", "watch": "watch_sms.py"}
    # frozen: [sys.executable, name, *args]
```

`Supervisor.start()` and `SmsWatch.__init__()` call it. Both spawns set
`cwd=paths.DATA`, replacing `cwd=HERE`. In a source checkout the two are the
same folder, so LOTTO-0013 §4.2's reason for the `cwd` still holds and nothing
changes there.

The frozen program's entry point is a new `lottotracker.py`, used only by the
build:

```python
# argv[1] == "serve"  -> serve.main()
# argv[1] == "watch"  -> watch_sms.main()   (argv[2:] passed through: --once)
# anything else       -> tray.main()
```

It is the PyInstaller entry script and nothing else imports it. Each branch
imports its own module inside the branch, so the `serve` and `watch` children
never load Qt (LOTTO-0013 INV-19's reason). `serve.main()`
and `watch_sms.main()` already exist. `watch_sms.main()` reads
`sys.argv[1:]` for `--once`, so the dispatcher removes `"watch"` from
`sys.argv` before calling it.

### 4.3 Programs the frozen build starts that are not its own

PyInstaller's bootloader sets `LD_LIBRARY_PATH` to the bundle and keeps the
host's value in `LD_LIBRARY_PATH_ORIG`. A host program inheriting the bundle's
path can load the wrong libraries. `supervise.open_browser()` starts
`systemd-run` and `xdg-open`, which start the user's browser.

```python
# supervise.py
def host_env() -> dict[str, str]:
    # os.environ copied. When FROZEN: LD_LIBRARY_PATH set from
    # LD_LIBRARY_PATH_ORIG, or removed where that is absent.
    # Not frozen: os.environ unchanged.
```

`open_browser()` passes `env=host_env()` to its `Popen`. Its `webbrowser.open()`
fallback, taken only where `systemd-run` or `xdg-open` is missing, takes no
`env` and keeps the bundle's path; this machine has both (§3). The project's own
children (§4.2) keep the bundle's environment: they are the bundle.

Unverified until the build runs: that this PyInstaller version sets the two
variables this way for a one-folder build. The build's first run measures it
(§7, INV-113), and §4.3 is corrected if it differs.

### 4.4 The autostart entry

`serve.DESKTOP_ENTRY`'s `Exec` line is filled by a new function:

```python
# serve.py
def autostart_exec() -> str:
    # FROZEN and $APPIMAGE set: '"<$APPIMAGE>"'
    # FROZEN, no $APPIMAGE:     '"<sys.executable>"'   (an unpacked build)
    # source:                   '"<sys.executable>" "<HERE>/tray.py"'  (today's bytes)
```

`$APPIMAGE` is the path of the `.AppImage` file, set by the AppImage runtime.
The source form is byte-identical to today's, so LOTTO-0014 INV-14 and
`tools/verify_page.py`'s autostart assertions keep passing unchanged.

### 4.5 What the page says when data is missing

**No messages (`no_dump`).** The model gains `data_dir: paths.DATA`. The notice:

- names the folder by its full path;
- says the messages file is not in it, and that this is not zero wins;
- names a way in that writes: keep the tray running with KDE Connect paired,
  and new lottery messages arrive by themselves; or copy an existing
  `lotto_sms_raw.txt` into that folder;
- never names `find_lotto_sms.py`.

LOTTO-0002 §6's rule stands unchanged: no ticket table, zero total or empty
wins list beneath the notice.

**No older results (`no_archive`).** New. `serve.build_model()` sets
`no_archive: True` when the dump exists and `paths.ARCHIVE` does not. The page
then shows a notice above the tickets: results for older draws have not been
fetched, so older tickets show as not checkable, and **Fetch older results** in
the tray menu fetches them. The notice adds to the page; it removes nothing beneath
it, because the tickets it describes are still correct.

### 4.6 "Fetch older results"

```python
# backfill.py
def write_archive() -> int:
    # build(), then _write_atomic(ARCHIVE, ...). Returns the draw count.
    # backfill.py's __main__ calls it, so there is one writer.

# supervise.py (Qt-free, so the wording is checkable headless)
FETCH_DONE, FETCH_FAILED = "done", "failed"
FETCH_MESSAGE: dict[str, str]      # one fixed sentence per outcome
def fetch_older(write=backfill.write_archive) -> str:
    # FETCH_DONE if write() returns; FETCH_FAILED on any Exception.
```

`tray.py` adds the menu item. It runs `supervise.fetch_older` through
`run_async`, like every long action (LOTTO-0013 §4.3). The item is disabled
and reads "Fetching older results…" while it runs. On `FETCH_DONE` it starts a
refresh, if the server is running, so the page re-scores. On either outcome it
shows that outcome's `FETCH_MESSAGE` sentence. A sentence carries no figure,
date or game: the notification rule in `CLAUDE.md` § Privacy applies, and this
is not its exception.

`backfill.build()` refuses to write a partial archive, and `_write_atomic()`
writes whole files, so a failure leaves the previous archive as it was.

### 4.7 The build

New files:

- `packaging/LottoTracker.spec` — the PyInstaller recipe, one-folder mode,
  entry `lottotracker.py`. Bundles `icons/` and `fonts/`. Collects
  `dbus` (with `_dbus_bindings` and `dbus.mainloop.glib`) and `gi` with the
  GLib typelibs.
- `packaging/AppRun`, `packaging/lottotracker.desktop` — the AppImage's launcher
  and menu entry; the icon is `icons/tray-running.svg`. `AppRun` `exec`s the
  bundled program and sets no `LD_LIBRARY_PATH`, so §4.3's
  `LD_LIBRARY_PATH_ORIG` holds the host's value and INV-113's `SIGTERM` reaches
  the tray, not a shell.
- `tools/build_appimage.sh` — runs PyInstaller, assembles the AppDir, and runs
  `appimagetool`. Output: `dist/LottoTracker-<VERSION>-x86_64.AppImage`, the
  version read from `VERSION`.

`appimagetool` is not installed and no openSUSE package carries it
(`zypper search appimagetool appimagekit` found nothing, 2026-11-11). The build
script downloads a pinned release and its runtime file into `build/tools/`, and
checks each against a SHA-256 recorded in the script before running it. The
version and both hashes are recorded when the script is written.

`build/` and `dist/` are added to `.gitignore`.

## 5. Invariants

Numbers continue the project's single sequence. A `paths` case runs in a fresh
interpreter that sets `sys.frozen` and `sys._MEIPASS` **before** importing the
project's modules, because every path is fixed at import.

- **INV-105** — In a frozen run every data path (`DUMP`, `THREADS`, `ARCHIVE`,
  `CACHE`, and each module's alias of them) lies under
  `$XDG_DATA_HOME/LottoTracker`, or `~/.local/share/LottoTracker` when that is
  unset. In a source run each lies in the repository folder.
  *Test:* `tools/verify_paths.py`, case `data_paths`. It imports `backfill`,
  `watch_sms`, `serve`, `supervise` and `history` under three set-ups —
  frozen with `XDG_DATA_HOME` set, frozen with it unset and a redirected
  `$HOME`, and source — and checks each alias.
  *Breaks when:* a module keeps its own `os.path.dirname(__file__)` path, or
  computes one fresh instead of taking `paths`' (`--break own_dump_path`).

- **INV-106** — In a frozen run the icon and font resolve under
  `sys._MEIPASS`, never under the data folder.
  *Test:* `tools/verify_paths.py`, case `resources_from_bundle`.
  *Breaks when:* a resource is resolved with `paths.DATA`
  (`--break icon_from_data`).

- **INV-107** — `supervise.child_command(name)` returns
  `[sys.executable, name]` in a frozen run and
  `[sys.executable, <repository>/serve.py or watch_sms.py]` in a source run;
  both spawns use `cwd=paths.DATA`.
  *Test:* `tools/verify_paths.py`, case `child_commands`. It records the
  `Popen` arguments of `Supervisor.start()` and a default `SmsWatch`
  through a stand-in `Popen`, so nothing starts.
  *Breaks when:* the frozen form still passes a `.py` path
  (`--break frozen_spawns_script`), or `cwd` stays the code folder
  (`--break cwd_is_code`).

- **INV-108** — The autostart entry's `Exec` line names `$APPIMAGE` in a frozen
  run that has it, and is today's bytes in a source run.
  *Test:* `tools/verify_paths.py`, case `autostart_exec`, for the frozen forms;
  `tools/verify_page.py`'s existing autostart assertions for the source form.
  *Breaks when:* the frozen form writes `sys.executable` while `$APPIMAGE` is
  set (`--break autostart_names_mount`); the entry then points into a mount that
  is gone at next login.

- **INV-109** — In a frozen run, `supervise.host_env()` sets
  `LD_LIBRARY_PATH` from `LD_LIBRARY_PATH_ORIG`, or removes it where that is
  absent; in a source run it returns the environment unchanged.
  `open_browser()` passes it.
  *Test:* `tools/verify_paths.py`, case `host_env`, for the function and for
  the `env` `open_browser()` hands its `Popen`, with `shutil.which` stubbed to
  find both programs.
  *Breaks when:* `open_browser()` omits `env=` (`--break browser_bundle_env`).
  Whether a browser started with the bundle's path actually fails is not
  tested; the case checks that it is not given that path.

- **INV-110** — The no-messages notice names the data folder's full path, says
  it is not zero wins, and names no command that writes nothing. Nothing from
  LOTTO-0002 §6's forbidden list renders beneath it.
  *Test:* `tools/verify_page.py`, case `no_dump_names_folder`, with a fixture
  path that is not this machine's. It asserts the path appears, and that
  `find_lotto_sms.py` does not.
  *Breaks when:* the notice drops the path (`--break no_dump_hides_folder`), or
  the old advice returns (`--break no_dump_inspect_advice`).

- **INV-111** — With the dump present and the archive missing, the page shows
  the older-results notice naming **Fetch older results**, and still shows the
  tickets. With the archive present it shows no such notice.
  *Test:* `tools/verify_page.py`, case `no_archive_points_at_menu`, on two
  fixture models.
  *Breaks when:* the notice is shown whatever the archive's state
  (`--break archive_notice_always`), or replaces the tickets
  (`--break archive_notice_hides_tickets`).

- **INV-112** — `supervise.fetch_older()` returns `FETCH_FAILED` when the write
  raises, and `FETCH_DONE` only when it returns. Every `FETCH_MESSAGE` sentence
  is fixed text with no digit, and only `FETCH_DONE`'s contains `fetched`,
  case-folded.
  *Test:* `tools/verify_page.py`, case `fetch_older_reports_outcome`, with stub
  writers that return and that raise.
  *Breaks when:* an exception is swallowed as success
  (`--break fetch_failure_is_done`), or a sentence carries a count
  (`--break fetch_message_counts`).

- **INV-113** — The built AppImage, copied to a folder outside the repository
  and started from there with a data folder holding copies of the real dump,
  archive and cache, serves a page with as many entry rows (`tr[data-pool]`) as a source
  checkout's page over the same files; its watcher is still alive after
  `SmsWatch.died_early()`'s wait; and `SIGTERM` to it leaves neither
  child running.
  *Test:* `tools/verify_appimage.py`, local lane only, run by hand and before a
  release. It starts the AppImage in the desktop session: with
  `QT_QPA_PLATFORM=offscreen` Qt reports no system tray, and `tray.main()`
  then exits before spawning anything (measured 2026-11-11). It sets a free
  `LOTTO_PORT`, a scratch `XDG_DATA_HOME` and `XDG_CONFIG_HOME` with
  `open_on_start` false, and reads `GET /`. Both runs are made with the phone unreachable, so the
  watcher finds no device, stays alive and writes nothing (§6).
  *Breaks when:* the bundle lacks `dbus` or `gi` (the watcher dies at start), a
  resource or path still resolves to the code folder (the page shows the
  no-messages notice), or a spawn still names a script (no server answers).

- **INV-114** — The same AppImage started with a data folder that does not
  exist yet creates that folder and serves the no-messages notice naming it, with no ticket
  table.
  *Test:* `tools/verify_appimage.py`, its second run.
  *Breaks when:* `ensure_data()` is not called before the watcher writes, or the
  notice shows a path other than the one in use.

## 6. Failure modes

- **The `.AppImage` is moved after autostart was switched on.** The entry names
  the old path, and the tray does not start at login. The settings panel still
  shows autostart on, because presence of the file is the state (LOTTO-0002
  §4.7). Switching it off and on rewrites the path. Not repaired automatically:
  a source tray rewriting the entry on start would steal it from an AppImage the
  user chose.
- **Both a source tray and the AppImage tray run.** The second cannot bind the
  shared port. That is today's behaviour for two source trays; nothing new.
- **FUSE is missing on another machine.** The AppImage will not mount. This
  machine has `fusermount` and `libfuse.so.2`. `--appimage-extract-and-run` is
  the documented fallback, named in the README.
- **The phone is not paired on first run.** The watcher runs and writes nothing,
  so the no-messages notice stays. That notice is the correct state, not a
  fault.
- **"Fetch older results" fails part-way.** `build()` raises before writing, the
  previous archive (or none) stays, and the notification says it failed. Pages
  already fetched are cached, so a retry is cheaper.
- **The page is being built while the archive is replaced.** `_write_atomic()`
  renames a whole file, so a reader sees the old archive or the new one.

## 7. Tests

- `tools/verify_paths.py` — new, both lanes, needs no personal data. Cases
  `data_paths`, `resources_from_bundle`, `child_commands`, `autostart_exec`,
  `host_env` (INV-105, INV-106, INV-107, INV-108, INV-109). Each case runs in a fresh interpreter, for
  the reason §5 opens with. Carries `--break` and `--list` like
  `verify_page.py`.
- `tools/verify_page.py` — three new cases: `no_dump_names_folder`,
  `no_archive_points_at_menu`, `fetch_older_reports_outcome`
  (INV-110, INV-111, INV-112).
- `tools/verify_appimage.py` — new, local lane, by hand and before a release
  (INV-113, INV-114). It needs the built artifact, the real dump, the network
  for the results feed and a running KDE Connect, so it is not in
  `./local-CI.sh`.

Every named `--break` must be observed turning its case red before the item is
called done. INV-113 and INV-114 have no `--break`; their red run is a
build of today's code, with `tray.py` as the recipe's entry, before §4.1 to
§4.4 land.

The new verifiers are added to `.claude/rules/verifiers.md`, and
`verify_paths.py` to `./local-CI.sh`.

## 8. Alternatives considered (and rejected)

- **Data beside the `.AppImage` file.** Rejected by the user (§3): a download
  folder is a poor home for personal data, and moving the file would lose it.
- **Bundle Python and the scripts, and keep spawning `.py` files.** It keeps
  §4.2 unchanged, but ships an interpreter and loose scripts next to
  PyInstaller's frozen copy: two copies of every module. The dispatcher is a
  few lines.
- **Run the server and watcher as threads in the tray.** Removes spawning
  entirely, but breaks LOTTO-0013's reaping contract and the watcher's crash
  isolation, and puts dbus in the Qt process.
- **Detect the AppImage by `$APPIMAGE` rather than `sys.frozen`.** An unpacked
  PyInstaller build has the same read-only and spawning problems with no
  `$APPIMAGE`. `$APPIMAGE` is used only where the file's own path is needed
  (§4.4).
- **A server route for "Fetch older results".** It would add a POST to the
  security surface LOTTO-0014 bounds, for an action only the tray offers.
- **Fetch older results automatically on first run.** Rejected by the user
  (§3).
- **Build in an older container for wider reach.** Deferred by the user (§3).

## 9. Out of scope

- The Windows executable — the rest of LOTTO-0015, deferred by the user
  2026-11-11.
- An AppImage for systems older than this one — deferred; not yet queued.
- Publishing the AppImage as a release asset. That happens at the first
  release (`cut-release`), and the website session is told then, as the roadmap
  item's 2026-09-28 note asks.
- Bulk history import (adb) from the AppImage. A source checkout keeps
  `tools/import_adb.py`; an AppImage user copies the resulting file in.
- The command lines of `check.py`, `results.py`, `find_lotto_sms.py` and
  `backfill.py`. The AppImage offers none of them, but bundles all four as
  modules: the page imports `check` and `results`, the watcher imports
  `find_lotto_sms`, and `history` imports `backfill`.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-105 | `tools/verify_paths.py::data_paths` |
| INV-106 | `tools/verify_paths.py::resources_from_bundle` |
| INV-107 | `tools/verify_paths.py::child_commands` |
| INV-108 | `tools/verify_paths.py::autostart_exec` (frozen); `tools/verify_page.py` autostart assertions (source) |
| INV-109 | Partial: `tools/verify_paths.py::host_env` checks the environment handed over; **nothing** checks that a browser started with the bundle's path would fail |
| INV-110 | `tools/verify_page.py::no_dump_names_folder` |
| `lottotracker.py` imports each module inside its branch | **nothing** — INV-19's check imports `serve` and `supervise`, never the dispatcher |
| INV-111 | `tools/verify_page.py::no_archive_points_at_menu` |
| INV-112 | `tools/verify_page.py::fetch_older_reports_outcome` |
| INV-113 | Partial: `tools/verify_appimage.py`, hand-run and before a release; **nothing** runs it on push |
| INV-114 | Partial: `tools/verify_appimage.py`, as INV-113 |
| The tray menu item is disabled while a fetch runs, and refreshes after | **nothing** — needs a `QSystemTrayIcon`, the gap LOTTO-0013 §11 records for every tray rule |
| `appimagetool` and its runtime match their pinned hashes | `tools/build_appimage.sh` refuses to run on a mismatch |

## 11. Cross-doc impact

- **LOTTO-0013 §4.2** — the spawn command and `cwd`: amend to cite
  `child_command()` and `cwd=paths.DATA`, keeping the reasoning for `cwd`.
- **LOTTO-0003 §4.6** — the watcher's `cwd=HERE`: same amendment.
- **LOTTO-0002 §4.5** — the no-messages notice's content (INV-110) and the new
  older-results notice (INV-111). **§4.7** — the autostart `Exec` line's frozen
  form.
- **`.claude/rules/architecture.md`** — a `paths.py` entry; `supervise.py`
  gains `child_command`, `host_env` and `fetch_older`.
- **`.claude/rules/verifiers.md`** — `verify_paths.py` and
  `verify_appimage.py`.
- **`CLAUDE.md`** § Commands — the build command and `verify_appimage.py`.
- **`README.md`** — how to run the AppImage, where its data lives, the FUSE
  fallback, and the "Fetch older results" item.
- **`CHANGELOG.md`** — one entry citing LOTTO-0015.

## 12. Cold-eyes loop log

Rows live in `../reviews/LOTTO-0015-linux-appimage-loop-log.md`.

## 13. Resource cost

- **Size.** The AppImage carries Python, PySide6, dbus-python and PyGObject.
  Its size is measured at the first build and recorded in the CHANGELOG entry,
  not estimated here. Unused Qt modules are excluded in the PyInstaller recipe.
- **Disk at run time.** The data folder holds what the repository folder holds
  today; nothing new grows.
- **New build-time dependencies:** `appimagetool` and its runtime, pinned by
  hash (§4.7). PyInstaller 6.20.0 is already installed. Nothing new at run time.

## 14. Migration / compatibility

- A source checkout keeps its data where it is. Nothing moves.
- An AppImage user with an existing dump copies `lotto_sms_raw.txt`, and
  optionally `archive_results.json` and `archive_cache/`, into the data folder.
  The no-messages notice says where. Nothing copies them automatically: the
  AppImage cannot know where a source checkout lives.

## 15. Open questions

- The `appimagetool` release to pin, and its hashes — recorded when
  `tools/build_appimage.sh` is written (§4.7).
- Whether PyInstaller 6.20.0 sets `LD_LIBRARY_PATH_ORIG` for a one-folder
  build as §4.3 assumes — measured at the first build.
