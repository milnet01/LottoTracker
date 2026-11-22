<!-- ants-spec-format: 1 -->
# LOTTO-0106 — Run the tracker as an Android app on the phone itself

**Status:** accepted (2026-11-21).
**Kind:** feature.
**Source:** ROADMAP LOTTO-0106 (user-request-2026-11-21). The scope decisions
in §3 were taken with the user on 2026-11-21.

**Pairs with:** LOTTO-0014 (the HTTP surface, whose boundary §4.4 changes on
the phone only), LOTTO-0015 (`paths.py`, which §4.3 gives a third form),
LOTTO-0034 (the re-buy warning, whose notice §4.6 posts unchanged) and
LOTTO-0083 (the stale-data notice, which needs phone wording).

*Layman: an app your friend installs on their Android phone that reads their
lottery SMSes, shows the same page the computer shows, and warns them when a
ticket is about to run out — with no computer involved.*

## 1. Goal

After this ships, one file, `LottoTracker-<version>.apk`, attached to the
GitHub release, installs on an Android phone. Opened, it reads the phone's
lottery SMSes, fetches results, and shows the same page `serve.py` serves on
the desktop, fitted to the phone's width. Each evening it imports new messages
and posts the re-buy warning (LOTTO-0034) as a phone notification. Nothing
leaves the phone except the results fetches the desktop app already makes. The
desktop app behaves as it does today.

## 2. Problem

The tracker runs only on a Linux desktop. Four things stop it running on a
phone, found by reading the code on 2026-11-21:

1. **Messages reach it over KDE Connect from a phone it is not running on.**
   `watch_sms.py::connect()` speaks D-Bus to the KDE Connect daemon. On the
   phone the messages are local, in Android's SMS store, and there is no D-Bus.
2. **The interface is a desktop tray and a desktop browser.** `tray.py` imports
   PySide6, and `supervise.Supervisor` spawns `serve.py` as a child process and
   opens a browser at it. Android has neither a tray nor a separate browser the
   app can trust with ticket data.
3. **The data folder is chosen for a desktop.** `paths.py` has two forms: the
   repository folder, or `$XDG_DATA_HOME/LottoTracker` when `paths.FROZEN`.
   An Android app may write only inside its own private folder.
4. **The page and the notices name desktop things.** `supervise.SMS_QUIET_NOTICE`
   tells the user to check KDE Connect; `supervise.WARN_STATE_NOTICE` tells them
   to restart Lotto Tracker; `page.py`'s missing-archive notice points at "the
   tray menu". On the phone none of those exist.

The security boundary also changes. LOTTO-0014 §2 defends `serve.py`'s
loopback port against the user's own browser being aimed at it. On a desktop
every local process belongs to the same user. **On Android every installed app
is a separate party, and any app holding the `INTERNET` permission can connect
to `127.0.0.1`.** `serve.py`'s `GET /` answers without the token today
(`make_server()`'s `do_GET` passes through `_route()`, which checks the
`Host`, the path and the method, and never the token), so on a phone any app
could read every ticket off the page.

## 3. Scope decisions (agreed with the user)

All four taken by the user on 2026-11-21, offered as choices with their
consequences.

- **Reuse the existing Python, not a rewrite.** The phone runs `tickets.py`,
  `check.py`, `history.py`, `results.py`, `backfill.py`, `expiry.py`,
  `serve.py` and `page.py` as they are, with the modules they import, through
  Chaquopy. One copy of the
  bank's wording and the scoring means a fix lands in both apps. The cost
  accepted: a larger download and a slower first open (§13).
- **Install from a file on GitHub, signed under Google's free "limited
  distribution" developer account.** It reads SMS itself, so it cannot go on
  Google Play (ROADMAP LOTTO-0106 records why). The account keeps it
  installable once Android's developer verification reaches South Africa,
  which Google has announced for 2027.
  Source: https://developer.android.com/blog/posts/android-developer-verification-2027
- **The re-buy notice says what the desktop's says.** It names the game, the
  final draw date and the draws left — LOTTO-0034 §3.3's one bounded
  exception, held by INV-54. No other notice carries ticket data.
- **The page is the desktop page, fitted to the phone.** `page.py` already
  carries width breakpoints down to `max-width:36rem`. No second set of
  screens.

Three narrower calls made while drafting, each reversible at review:

- **No new-ticket or new-win notification in this item.** The phone's evening
  job imports messages and checks expiry; it does not refresh results. The
  re-buy warning is the app's primary job (`CLAUDE.md` § What this is), the
  bank pays most small wins back by itself (LOTTO-0011), and a nightly results
  fetch costs network and battery for a secondary sign.
- **`READ_SMS` only, no `RECEIVE_SMS`.** The app reads the inbox when it opens
  and once each evening. Nothing time-critical waits on a message arriving
  sooner, and each restricted permission is one more setting the friend must
  allow by hand.
- **The app's folder lives at `android/` in this repository**, so a release
  builds both artifacts from one commit.

## 4. Design

### 4.1 The shape

```
android/                      Gradle project, Kotlin, Chaquopy plugin
  app/src/main/
    AndroidManifest.xml       permissions: READ_SMS, INTERNET, POST_NOTIFICATIONS
    kotlin/.../MainActivity   WebView; starts and stops the server; ⋮ menu
    kotlin/.../SmsReader      queries Telephony.Sms.Inbox, hands rows to Python
    kotlin/.../EveningWorker  WorkManager job, once a day after 22:00 SAST
    res/xml/network_security_config.xml   cleartext to 127.0.0.1 only
android_entry.py              repo root, beside lottotracker.py: the ONLY
                              Python module Kotlin calls
```

Kotlin holds no decision: it moves rows, strings and clicks between Android and
`android_entry.py`, the same split `tray.py` keeps with `supervise.py`. Every
rule stays in Python, where the existing verifiers can reach it headless.

### 4.2 `android_entry.py`

The phone's counterpart of `lottotracker.py`: nothing on the desktop imports
it, and it imports no Qt and no D-Bus.

```python
def import_messages(rows: list[tuple[str, int, str]]) -> int
    # (address, date_ms, body) per inbox row; returns how many were written.
    # Calls paths.ensure_data(), then watch_sms.append_new() — the dump's one
    # writer path and wanted()'s one filter. Imports watch_sms only, never
    # watch_sms.connect(). Kotlin calls it before start_server() on each
    # open, so the first build reads what was just imported.

def since_ms() -> int
    # watch_sms.high_water() less one day, or 0 for an empty dump. Kotlin asks
    # the inbox only for rows newer than this, so the first open reads the
    # whole inbox and every later one reads a day's worth. append_new()'s (date, body) key absorbs
    # the overlap.

def start_server() -> tuple[int, str]
    # serve.main()'s steps, on a free port, serving in a daemon thread:
    # paths.ensure_data(), serve.make_server(), then
    # serve.refresh(state, serve.build_model), so each open builds afresh.
    # Clears supervise._warn_state_unsaved first, so an open is the
    # desktop's restart (LOTTO-0034 §3 item 5). Returns (port, token).
    # Requires the token on every route (§4.4).

def stop_server() -> None

def refresh() -> str
    # The ⋮ menu's "Refresh results": serve.refresh() on the running
    # server's state. Returns at once with supervise.refresh_message() of
    # REFRESH_RUNNING when it started, or of REFRESH_BUSY when one was
    # already running; the page shows the result.

def fetch_older() -> str
    # The ⋮ menu's "Fetch older results": supervise.fetch_older(), waiting
    # for the download, then its FETCH_MESSAGE sentence.

def next_evening_ms() -> int
    # Milliseconds from clock.now() to the next supervise.CHECK_AT in South
    # African time: the evening job's first delay (§4.6).

def evening(today_iso=None) -> list[str]
    # import is done by Kotlin first; this returns
    # supervise.expiry_notices(today) then supervise.sms_quiet_notices(today),
    # each string translated by PHONE_WORDING (§4.5).
```

With `today_iso` left `None`, `today` is `clock.today()`, as everywhere else
(ADR-0009). Kotlin passes nothing; only a test passes a date. Kotlin calls
every function here off the main thread.

### 4.3 Where the data lives: a third `paths.py` form

```python
ANDROID = sys.platform == "android"     # CPython 3.13+ (PEP 738)
DATA = _data_home() if FROZEN or ANDROID else _HERE
```

Kotlin sets `XDG_DATA_HOME` and `XDG_CONFIG_HOME` to folders under
`Context.getFilesDir()` before Python starts, so `paths.DATA` and
`supervise.config_home()` both land in the app's private storage with no other
change. Chaquopy is pinned to a Python of 3.13 or newer for `sys.platform`.
Source: https://peps.python.org/pep-0738/

`paths.RESOURCES` stays `_HERE` on Android: Chaquopy installs the Python files
and the `icons/` and `fonts/` folders together.

### 4.4 The page on a phone: the token on every request

`MainActivity` shows a `WebView` at `http://127.0.0.1:<port>/`. Before loading,
it sets a cookie `lotto_token=<token>` for that origin through
`CookieManager`. Another app cannot read the WebView's cookie store.

`serve.make_server()` gains a keyword, `token_on_every_route`, default `False`.
When `True`, `GET /` and `GET /status` accept the request only when the token
arrives in the existing header **or** that cookie, compared with
`secrets.compare_digest`; anything else gets `403` with no body. The POST
routes still require the header, as LOTTO-0014 §4.3 says: the cookie alone
never satisfies a POST.
`android_entry.start_server()` is the only caller that passes `True`. The
desktop server is unchanged, byte for byte.

The port is a fresh free port each open (`supervise.free_port()`); the token a
fresh `secrets.token_urlsafe(32)`. The server starts in `onStart` and stops in
`onStop`, so it listens only while the page is on screen.

The rest of LOTTO-0014 holds as written: the `Host` check, the five routes, the
security headers, the body cap.

### 4.5 Phone wording

`serve.py`'s `do_GET` adds a `platform` key, `"desktop"` or `"android"` from
`paths.ANDROID`, to every view it renders, beside `icon` and `font`, so the
states with no model carry it too. `page.py` chooses its wording from it wherever the
desktop form names the tray, KDE Connect, a terminal command or a desktop file:
the phone form names the ⋮ menu or says nothing. The same holds for the
page's script, its comments included. The two settings switches
(`autostart`, `open_on_start`) and their "Tray" heading are not rendered on
Android — neither switch means anything there.

`android_entry.PHONE_WORDING` maps each fixed `supervise` notice that names a
desktop thing to its phone form, and passes every other string through:

| Desktop notice | Phone form |
|---|---|
| `SMS_QUIET_NOTICE` | "No lottery SMS has reached this app for a while, so it cannot warn you about a ticket bought since then. Check that the app is still allowed to read SMS." |
| `WARN_STATE_NOTICE` | "Re-buy warnings are paused: the app could not save which tickets it has already warned you about. Closing and reopening the app will try again." |

`supervise.expiry_notice()` is not in the table: its sentence names nothing on
the desktop and goes out unchanged.

### 4.6 Notifications

One channel, "Ticket warnings". Each notice from `android_entry.evening()`
becomes one notification. Every notification sets a **public version** reading
"Lotto Tracker has a reminder for you", so the lock screen shows no game and no
date; the full text shows once the phone is unlocked. On Android 13 and later
the app asks for `POST_NOTIFICATIONS` at first open.

The evening job is a `PeriodicWorkRequest` of 24 hours, first run after
`android_entry.next_evening_ms()`. WorkManager may run it later than asked;
that is accepted, because a ticket warned about at 23:30 is still warned about
before its last draw.

### 4.7 First run and permissions

Until a lottery SMS has been imported, the page is the existing no-dump notice.
Its phone form names the one step outside the app:
*Settings → Apps → Lotto Tracker → ⋮ → Allow restricted settings*, then allow
SMS. The page has no separate permission state: to Python, a denied permission
and an inbox with no lottery SMS look the same. Never an empty ticket table (`CLAUDE.md`'s cardinal rule; LOTTO-0002
§6). Source for the restricted-settings step:
https://www.androidauthority.com/android-15-restricted-settings-sideloading-3481098/

### 4.8 Build, signing and release

`tools/build_apk.sh` builds `dist/LottoTracker-<VERSION>.apk` inside a podman
container, as `tools/build_appimage.sh` does, from
`packaging/Containerfile.android`, which pins the JDK, the Android
command-line tools and Gradle. `versionName` is
`VERSION`'s text; `versionCode` is `major*10000 + minor*100 + patch`, so every
release is higher than the one before.

**The Python sources are an explicit list** in the Gradle file — every project module
`android_entry.py` reaches, directly or through another module, function-level
imports included (`serve.build_model()` imports `check`, `history` and
`tickets` inside its body), and `icons/` and `fonts/` — never the repository
folder. The working tree holds `lotto_sms_raw.txt`, `archive_results.json` and
`archive_cache/`, all gitignored and all real data, and a folder-wide source set
would ship them inside the APK.

`android:allowBackup="false"`, plus `dataExtractionRules` excluding every
domain: Android's cloud backup would otherwise copy the dump to Google Drive.

The signing key lives outside the repository, in the folder
`LOTTO_KEYSTORE_DIR` names (default `~/.config/LottoTracker-signing`), and the
user keeps a second copy off this machine.
**An app's updates must be signed with the key that signed its first install**;
a lost key means the friend uninstalls, which deletes their data.

Before 2027 the user registers the package name and the key's certificate on a
limited distribution account in the Android Developer Console.
`tools/verify_apk.py`, by hand before a release like `verify_appimage.py`,
checks the built file (§7).

The package name is `za.co.antsprojectshub.lottotracker`. It is permanent once
the friend installs.

## 5. Invariants

Numbered after LOTTO-0001's INV-121, the highest in the project before this
spec (`grep -oh "INV-[0-9]\+" docs/specs/*.md | sort -t- -k2 -n | tail -1` →
`INV-121`).

- **INV-122** — On the phone, every route refuses a request carrying no token:
  `GET /` and `GET /status` with neither the header nor the cookie get `403` and
  a zero-length body, and no ticket field appears in any response to them.
  *Test:* `tools/verify_page.py::android_routes_need_token`, which starts
  `make_server(..., token_on_every_route=True)` on `fixture_model()` and requests
  each route bare, with a wrong cookie, with a wrong header, with the right
  cookie alone and with the right header alone; and `POST /refresh` with the
  right cookie and no header, which gets `403`. Red under `--break`
  `get_token_unchecked`, `cookie_ignored` and `post_takes_cookie`.
  *Breaks when:* `do_GET` checks the token only for POST, or reads the cookie
  but not the header, or the reverse, or a POST accepts the cookie.

- **INV-123** — The desktop server is unchanged: with `token_on_every_route`
  unset, `GET /` with no token still gets `200`.
  *Test:* `tools/verify_page.py::desktop_get_needs_no_token`; red under
  `--break token_default_on`.
  *Breaks when:* the default flips, so the desktop page loaded from the tray's
  plain URL starts answering `403`.

- **INV-124** — The APK holds no data file: no member named
  `lotto_sms_raw.txt`, `archive_results.json`, `accepted.json`,
  `sms_threads.json`, `expiry_warned.json` or `settings.json`, and none under
  `archive_cache/`.
  *Test:* `tools/verify_apk.py`, by hand, on the built APK — no arrow; it reads
  the APK's zip listing and the listing of every archive inside it. Red under
  `--break data_file`.
  *Breaks when:* the Gradle source set names the repository folder instead of
  the explicit list.

- **INV-125** — The APK asks for exactly `READ_SMS`, `INTERNET` and
  `POST_NOTIFICATIONS`, plus what AndroidX WorkManager merges in:
  `WAKE_LOCK`, `ACCESS_NETWORK_STATE`, `RECEIVE_BOOT_COMPLETED`,
  `FOREGROUND_SERVICE` and AndroidX's own
  `<package>.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`. Android grants those
  five at install without asking. Its manifest sets `allowBackup="false"`.
  *Test:* `tools/verify_apk.py`, reading the merged manifest with the SDK's
  `aapt2 dump permissions` and `aapt2 dump xmltree` inside the build
  container. Red under `--break extra_permission` and `--break backup_on`.
  *Breaks when:* a library merges in a permission not in the list, or backup
  is left at its default of on.

- **INV-126** — No phone notification carries ticket data beyond the re-buy
  exception, and every phone notice that names a desktop thing is translated:
  no string `android_entry.evening()` can return contains "KDE Connect",
  "tray" or "restart".
  *Test:* `tools/verify_expiry.py::phone_wording`, which feeds every member of
  `supervise.FAULT_NOTICES` and an `expiry_notice()` through `PHONE_WORDING`,
  then calls `evening()` on a temporary data folder holding no dump, with one
  qualifying ticket and a settings folder that cannot be written, and checks
  it returns exactly the phone forms of `WARN_STATE_NOTICE` and
  `SMS_QUIET_NOTICE`. A pause already set would attempt no save, so it would
  never produce the paused notice. Red under `--break phone_wording_skipped`.
  *Breaks when:* a new desktop notice is added to `supervise` and not to the
  table, or `evening()` skips the table.

- **INV-127** — The phone's page never names a desktop thing: rendered with
  `platform: "android"`, the HTML, script included, contains none of "tray",
  "KDE Connect", "python3" or "autostart" in any letter case, in every notice
  state `fixture_model()` can produce.
  *Test:* `tools/verify_page.py::android_page_wording`; red under `--break`
  `android_tray_heading`, `android_notice_desktop_words` and
  `android_js_wires_switches`.
  *Breaks when:* `page.py` gains a desktop sentence with no `platform` branch.

- **INV-128** — On the phone, `paths.DATA` is under `$XDG_DATA_HOME` and never
  the code folder.
  *Test:* `tools/verify_paths.py::android_form`, which sets
  `sys.platform = "android"` and `XDG_DATA_HOME` in a subprocess before importing
  `paths`, as INV-105's frozen case does; red under
  `--break android_data_is_code`.
  *Breaks when:* `DATA` tests `FROZEN` alone.

- **INV-129** — The phone imports through the dump's one writer path: every
  message `android_entry.import_messages()` writes passes `watch_sms.wanted()`,
  and a second call with the same rows writes nothing.
  *Test:* `tools/verify_watch.py::android_import`, on a temporary dump, with
  one wanted row, one `EXCLUDE` row and a repeat; red under
  `LOTTO_BREAK=import_own_writer`, since that verifier has no `--break` flag.
  *Breaks when:* `import_messages()` writes the dump itself, or filters with its
  own keyword list.

LOTTO-0014's invariants and LOTTO-0034's INV-52 to INV-56 hold unchanged on the
phone; this spec adds the boundary above and does not restate them.

## 6. Failure modes

- **The friend never allows restricted settings.** `READ_SMS` stays denied; the
  page shows §4.7's notice, never an empty table. Nothing else is attempted.
- **The friend revokes SMS later.** The evening import reads nothing; after
  `SMS_QUIET_DAYS` the phone-worded quiet notice says to check the permission.
- **The results feed is unreachable.** As on the desktop: the page says results
  could not be fetched, and nothing reads as "did not win".
- **HTTPS fails on the phone's Python.** The AppImage needed
  `lottotracker.use_host_certificates()` because its bundled OpenSSL did not find
  the host's certificates (LOTTO-0102). Whether Chaquopy's Python finds a
  certificate store on Android is **unverified**; the first device build must
  fetch results before anything else is built on it (§15).
- **Android kills the app while the page is open.** The server thread dies with
  it; the next open starts a new one with a new port and token. Nothing is lost:
  the dump is written in one append (`watch_sms.append_new()`).
- **WorkManager defers the evening job for days** (battery saver, a manufacturer's
  task killer). The warning is late. The page's own Overview still says what is
  running out (`serve.running_view()`) whenever the app is opened.
- **The signing key is lost.** No update can install over the friend's copy;
  they must uninstall, losing their data, and import again from the inbox. The
  SMSes are still on the phone, so the ledger rebuilds; accepted wins and the
  warned-ticket record do not.
- **Developer verification reaches South Africa before the key is registered.**
  New installs and updates refuse, short of Android's advanced flow for
  unregistered apps. Register before shipping the first APK to the friend.
- **The friend's bank messages differ from the user's.** Same bank, so the
  same parser applies; any unparsed ticket surfaces through the existing
  malformed and unknown-game notices, never silently.

## 7. Tests

| Test | Locks | Where |
|---|---|---|
| `android_routes_need_token` | INV-122 | `tools/verify_page.py` |
| `desktop_get_needs_no_token` | INV-123 | `tools/verify_page.py` |
| `android_page_wording` | INV-127 | `tools/verify_page.py` |
| `phone_wording` | INV-126 | `tools/verify_expiry.py` |
| `android_form` | INV-128 | `tools/verify_paths.py` |
| `android_import` | INV-129 | `tools/verify_watch.py` |
| `verify_apk.py` | INV-124, INV-125 | `tools/`, by hand before a release |

The Python cases run headless in `./local-CI.sh` on both lanes where their
verifier already does. Each needs a `--break` (or the verifier's equivalent)
showing it red: no pre-fix code exists for greenfield cases, as `CLAUDE.md`
§ Commands says of `verify_page.py`.

**What no test reaches: the Kotlin.** The WebView, the cookie, the inbox query,
WorkManager and the notification are checked by a manual recipe on the user's
own phone before the friend gets a copy: install the APK, allow restricted
settings and SMS, confirm the page lists the same tickets the desktop page
does, then set the phone's clock to the evening before a ticket's last-but-one
draw and run the job from Android's developer options.

## 8. Alternatives considered (and rejected)

- **A Kotlin rewrite.** Smaller and faster, but the bank's wording, the
  admission filter and the scoring would exist twice, and INV-32's lesson is
  that two filters drift. The user chose reuse (§3).
- **BeeWare (Briefcase and Toga), all in Python.** Its interface is native
  widgets, which would mean a second interface beside `page.py`, the opposite
  of the user's screens choice. Briefcase uses Chaquopy underneath anyway.
- **No socket: hand the page to the WebView through `shouldInterceptRequest`.**
  It removes the port entirely, but Android's interception hook cannot read a
  POST body, so `page.py`'s `XMLHttpRequest` POSTs would need a JavaScript
  bridge and a phone branch in the page's script — more change to LOTTO-0002's
  script than §4.4's one keyword.
- **Google Play with share-to-app import.** Passes Play's SMS rule, but the
  friend would forward each SMS by hand, which defeats "on its own". Kept as a
  possible later route, not built.
- **`RECEIVE_SMS` to import each message as it arrives.** Rejected in §3.
- **Leaving the lock screen to show the full re-buy notice.** The exception
  in LOTTO-0034 §3.3 permits the content in a notification; the public version
  costs nothing and keeps it off a phone lying face-up.

## 9. Out of scope

- A Windows version — tracked by LOTTO-0099.
- An iPhone version — tracked by LOTTO-0103.
- Banks other than Standard Bank — tracked by LOTTO-0079.
- New-ticket and new-win notifications on the phone — deferred (§3); not yet
  queued.
- In-app update checks; the user tells the friend when a new APK is out —
  deferred; not yet queued.
- A Play Store or F-Droid listing — deferred; F-Droid's rules on SMS
  permissions were not found in its inclusion policy and are unchecked.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-122 | `tools/verify_page.py::android_routes_need_token` |
| INV-123 | `tools/verify_page.py::desktop_get_needs_no_token` |
| INV-124 | `tools/verify_apk.py`, by hand before a release |
| INV-125 | `tools/verify_apk.py`, by hand before a release |
| INV-126 | `tools/verify_expiry.py::phone_wording` |
| INV-127 | `tools/verify_page.py::android_page_wording` |
| INV-128 | `tools/verify_paths.py::android_form` |
| INV-129 | `tools/verify_watch.py::android_import` |
| Kotlin holds no decision (§4.1) | **nothing** — a reviewer reading the Kotlin |
| Lock-screen public version (§4.6) | **nothing** — the manual recipe in §7 |
| Signing key kept off the repo and backed up (§4.8) | **nothing** — no `.gitignore` pattern or `verify_privacy.py` check covers a key file, and nothing checks the backup exists |
| Evening job runs after 22:00 SAST (§4.6) | **nothing** — the manual recipe in §7 |

## 11. Cross-doc impact

- **LOTTO-0014** — amended in place: §4 gains the `token_on_every_route`
  keyword and INV-122's boundary, citing this spec as its origin.
- **LOTTO-0015** — §4.1's `paths.py` gains the Android form.
- **LOTTO-0083 / LOTTO-0034** — cite `PHONE_WORDING` as the phone's form of
  their fixed sentences.
- **`CLAUDE.md`** — § Commands gains `tools/build_apk.sh` and
  `tools/verify_apk.py`; § Architecture's diagram gains the phone's inbox as a
  third source into `append_new()`.
- **`.claude/rules/architecture.md`** — a note for `android_entry.py` and
  `android/`.
- **`.claude/rules/verifiers.md`** — `verify_apk.py`'s row.
- **`README.md`** — an "On an Android phone" install section, including the
  restricted-settings step.
- **`CHANGELOG.md`** — the release that ships it.

## 12. Cold-eyes loop log

Rows live in `../reviews/LOTTO-0106-android-app-loop-log.md`.

## 13. Resource cost

- **Download size.** Chaquopy bundles a Python runtime; the stdlib-only code
  adds little. 38.8 MB for 1.1.1 with both ABIs (`verify_apk.py`, which prints
  it, 2026-11-22).
- **Storage.** The archive download on the desktop holds `archive_cache/` at
  25M (`du -sh archive_cache`, this machine, 2026-11-21) and
  `archive_results.json` at about 450 KB (`ls -la`). The phone holds the same.
- **Memory and battery.** The Python runtime runs only while the page is on
  screen and for the evening job's few seconds. No service stays resident, no
  loop polls, and the WebView page runs no script while idle (`CLAUDE.md`
  § Working conventions).
- **New dependencies.** Chaquopy (Gradle plugin) and AndroidX WorkManager —
  build-time and on-phone only. The WebView and its cookie store are
  Android's own. The desktop gains none.

## 14. Open questions

- **Does HTTPS work out of the box on Chaquopy's Python?** Settled by the first
  device build fetching results (§6).
- **How a limited distribution account authorises a device** — Google's posts
  give the device cap but this spec has not read the registration steps.
  Settled before the friend's first install.
- **Whether `supervise.fetch_older()`'s scrape is acceptable on a phone's data
  plan.** One fetch per pool per year since `backfill.FIRST_YEAR` (2022);
  measure the bytes on the first build and say it on the page if large.
- **Whether each open should rebuild.** `start_server()` builds afresh on every
  `onStart`, so returning to the app re-fetches results. Measure the time and
  bytes on the first build; keeping the model for the process's life is the
  alternative.
