#!/usr/bin/env python3
"""LOTTO-0015 INV-105 to INV-109: where a frozen build keeps things, and how it
starts its helpers.

    python3 tools/verify_paths.py            # every case
    python3 tools/verify_paths.py --list
    python3 tools/verify_paths.py --break own_dump_path   # RED-TEST: must FAIL

Needs no personal data and no built AppImage, so it runs on both lanes. Every
path is fixed at import, so each set-up runs in a FRESH interpreter that sets
sys.frozen and sys._MEIPASS before importing anything of the project's
(spec §5). A break is applied inside that interpreter, after the import it
simulates a defect in.
"""

import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BREAK = os.environ.get("LOTTO_BREAK") or ""

# The child: argv is ROOT, case, mode ("frozen" or "source"), bundle folder.
# EXPECT_DATA in its environment is the data folder the case expects.
CHILD = r'''
import base64, os, sys
ROOT, CASE, MODE, BUNDLE = sys.argv[1:5]
BREAK = os.environ.get("LOTTO_BREAK", "")
EXPECT = os.environ.get("EXPECT_DATA", "")
if MODE == "frozen":
    sys.frozen = True
    sys._MEIPASS = BUNDLE
sys.path.insert(0, ROOT)


def need(cond, msg):
    if not cond:
        sys.stderr.write(msg + "\n")
        raise SystemExit(1)


def data_paths():
    import backfill, history, serve, supervise, watch_sms  # noqa: E401
    import paths
    if BREAK == "own_dump_path":
        watch_sms.DUMP = os.path.join(ROOT, "lotto_sms_raw.txt")
    need(paths.DATA == EXPECT, f"paths.DATA is {paths.DATA}, want {EXPECT}")
    aliases = {
        "backfill.CACHE": backfill.CACHE, "backfill.ARCHIVE": backfill.ARCHIVE,
        "history.ARCHIVE": history.ARCHIVE,
        "watch_sms.DUMP": watch_sms.DUMP, "watch_sms.THREADS": watch_sms.THREADS,
        "watch_sms.lock_path()": watch_sms.lock_path(watch_sms.DUMP),
        "serve.DUMP": serve.DUMP, "supervise.DUMP": supervise.DUMP,
        "paths.ACCEPTED": paths.ACCEPTED, "serve.ACCEPTED": serve.ACCEPTED,
    }
    for name, p in aliases.items():
        need(os.path.dirname(p) == EXPECT, f"{name} is {p}, not under {EXPECT}")
    if MODE == "frozen":
        need(not os.path.exists(EXPECT), "importing the modules created the data folder")


def resources_from_bundle():
    import paths
    if BREAK == "icon_from_data":
        paths.resource = lambda *p: os.path.join(paths.DATA, *p)
    import serve
    import tray
    icon = serve.APP_ICON and base64.b64decode(serve.APP_ICON.split(",", 1)[1])
    font = serve.APP_FONT and base64.b64decode(serve.APP_FONT.split(",", 1)[1])
    need(icon == b"<svg>bundle</svg>", f"the page icon was read from elsewhere: {icon!r}")
    need(font == b"bundle-font", f"the typeface was read from elsewhere: {font!r}")
    for name in ("ICON_RUNNING", "ICON_STOPPED"):
        p = getattr(tray, name)
        need(p.startswith(BUNDLE + os.sep), f"tray.{name} is {p}, not in the bundle")


def child_commands():
    import paths
    import supervise
    calls = []

    class Child:
        def poll(self):
            return None

    def popen(cmd, **kw):
        calls.append((cmd, kw.get("cwd")))
        return Child()

    supervise.subprocess.Popen = popen
    if BREAK == "frozen_spawns_script":
        supervise.child_command = lambda name, *a: [
            sys.executable, os.path.join(supervise.HERE, supervise.SCRIPT[name]), *a]
    if BREAK == "cwd_is_code":
        paths.DATA = supervise.HERE
    supervise.Supervisor().start()
    supervise.SmsWatch().start()
    if MODE == "frozen":
        want = [[sys.executable, "serve"], [sys.executable, "watch"]]
    else:
        want = [[sys.executable, os.path.join(ROOT, "serve.py")],
                [sys.executable, os.path.join(ROOT, "watch_sms.py")]]
    need([c for c, _ in calls] == want, f"spawned {[c for c, _ in calls]}, want {want}")
    for cmd, cwd in calls:
        need(cwd == EXPECT, f"{cmd[1:]} started in {cwd}, want {EXPECT}")


def autostart_exec():
    import serve
    if BREAK == "autostart_names_mount":
        serve.autostart_exec = lambda: f'"{sys.executable}"'
    serve.write_settings({"autostart": True})
    with open(serve.autostart_path(), encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().splitlines() if ln.startswith("Exec=")]
    want = f'Exec="{os.environ.get("APPIMAGE") or sys.executable}"'
    need(lines == [want], f"the autostart entry has {lines}, want [{want!r}]")


def host_env():
    import supervise
    os.environ["LD_LIBRARY_PATH"] = "/bundle/lib"
    os.environ["LD_LIBRARY_PATH_ORIG"] = "/host/lib"
    if MODE == "source":
        need(supervise.host_env() == dict(os.environ),
             "a source run changed the environment it hands on")
        return
    need(supervise.host_env().get("LD_LIBRARY_PATH") == "/host/lib",
         "the host's LD_LIBRARY_PATH was not restored from LD_LIBRARY_PATH_ORIG")
    del os.environ["LD_LIBRARY_PATH_ORIG"]
    need("LD_LIBRARY_PATH" not in supervise.host_env(),
         "with no LD_LIBRARY_PATH_ORIG, the bundle's LD_LIBRARY_PATH was kept")
    os.environ["LD_LIBRARY_PATH_ORIG"] = "/host/lib"
    # The runtime hooks' search paths: the bundle's entries go, the host's stay.
    os.environ["XDG_DATA_DIRS"] = os.pathsep.join(
        [os.path.join(BUNDLE, "share"), "/usr/local/share/", "/usr/share/"])
    os.environ["QT_PLUGIN_PATH"] = os.path.join(BUNDLE, "PySide6", "Qt", "plugins")
    if BREAK == "bundle_paths_kept":
        supervise.BUNDLE_PATH_VARS = ()
    got = supervise.host_env()
    need(got.get("XDG_DATA_DIRS") == os.pathsep.join(["/usr/local/share/", "/usr/share/"]),
         f"XDG_DATA_DIRS handed on as {got.get('XDG_DATA_DIRS')!r}")
    need("QT_PLUGIN_PATH" not in got, "the bundle's QT_PLUGIN_PATH was handed on")
    seen = {}

    class Child:
        def wait(self, timeout=None):
            return 0

    def popen(cmd, **kw):
        seen["env"] = kw.get("env")
        return Child()

    supervise.shutil.which = lambda name: "/usr/bin/" + name
    supervise.subprocess.Popen = popen
    if BREAK == "browser_bundle_env":
        supervise.host_env = lambda: None  # Popen's env=None: the bundle's own
    supervise.open_browser("http://127.0.0.1:1")
    env = seen.get("env")
    need(env is not None and env.get("LD_LIBRARY_PATH") == "/host/lib",
         "open_browser() handed the browser the bundle's library path")


globals()[CASE]()
'''


class Fail(Exception):
    pass


def need(cond, msg):
    if not cond:
        raise Fail(msg)


_TEMP = []


def scratch():
    d = tempfile.mkdtemp(prefix="lotto-paths-")
    _TEMP.append(d)
    return d


def bundle():
    """A stand-in sys._MEIPASS whose icon and font are told apart by content."""
    b = scratch()
    for sub, name, body in (("icons", "tray-running.svg", b"<svg>bundle</svg>"),
                            ("icons", "tray-stopped.svg", b"<svg>bundle</svg>"),
                            ("fonts", "AtkinsonHyperlegibleNext-latin-wght.woff2",
                             b"bundle-font")):
        os.makedirs(os.path.join(b, sub), exist_ok=True)
        with open(os.path.join(b, sub, name), "wb") as fh:
            fh.write(body)
    return b


def run(case, mode, expect, extra=None):
    """One fresh interpreter, with $XDG_CONFIG_HOME in scratch.

    $HOME stays real unless `extra` moves it: on this machine PySide6 is in the
    user site-packages under it, and resources_from_bundle imports tray.
    """
    env = {k: v for k, v in os.environ.items()
           if k not in ("XDG_DATA_HOME", "APPIMAGE", "LD_LIBRARY_PATH",
                        "LD_LIBRARY_PATH_ORIG")}
    env["XDG_CONFIG_HOME"] = os.path.join(scratch(), ".config")
    env["EXPECT_DATA"] = expect
    env.update(extra or {})
    r = subprocess.run([sys.executable, "-c", CHILD, ROOT, case, mode, bundle()],
                       env=env, cwd=scratch(), capture_output=True, text=True,
                       timeout=120)
    tail = (r.stderr.strip().splitlines() or [f"exit {r.returncode}"])[-1]
    need(r.returncode == 0, f"{mode}: {tail}")


def frozen_xdg():
    xdg = scratch()
    return {"XDG_DATA_HOME": xdg}, os.path.join(xdg, "LottoTracker")


def data_paths():
    """INV-105 — every data path lies in the data folder of the form running."""
    extra, want = frozen_xdg()
    run("data_paths", "frozen", want, extra)
    # Unset: ~/.local/share, with $HOME redirected so nothing real is read.
    home = scratch()
    run("data_paths", "frozen", os.path.join(home, ".local", "share", "LottoTracker"),
        {"HOME": home})
    run("data_paths", "source", ROOT)


def resources_from_bundle():
    """INV-106 — the icon and font come from sys._MEIPASS, never the data folder."""
    extra, want = frozen_xdg()
    # A decoy in the data folder, so a resource read from there is told apart.
    for sub, name in (("icons", "tray-running.svg"), ("icons", "tray-stopped.svg"),
                      ("fonts", "AtkinsonHyperlegibleNext-latin-wght.woff2")):
        os.makedirs(os.path.join(want, sub), exist_ok=True)
        with open(os.path.join(want, sub, name), "wb") as fh:
            fh.write(b"from-the-data-folder")
    run("resources_from_bundle", "frozen", want, extra)


def child_commands():
    """INV-107 — the frozen build starts itself by name, in the data folder."""
    extra, want = frozen_xdg()
    run("child_commands", "frozen", want, extra)
    run("child_commands", "source", ROOT)


def autostart_exec():
    """INV-108 — the frozen autostart entry names the .AppImage file itself."""
    extra, want = frozen_xdg()
    run("autostart_exec", "frozen", want,
        dict(extra, APPIMAGE="/opt/fixture/LottoTracker-fixture-x86_64.AppImage"))
    run("autostart_exec", "frozen", want, extra)  # unpacked: sys.executable


def host_env():
    """INV-109 — a program that is not ours gets the host's library path."""
    extra, want = frozen_xdg()
    run("host_env", "frozen", want, extra)
    run("host_env", "source", ROOT)


CASES = [
    ("data_paths", "INV-105", data_paths),
    ("resources_from_bundle", "INV-106", resources_from_bundle),
    ("child_commands", "INV-107", child_commands),
    ("autostart_exec", "INV-108", autostart_exec),
    ("host_env", "INV-109", host_env),
]

# Each break must make exactly the named case fail. Named in the *Test:* clauses.
BREAKS = {
    "own_dump_path": "data_paths",
    "icon_from_data": "resources_from_bundle",
    "frozen_spawns_script": "child_commands",
    "cwd_is_code": "child_commands",
    "autostart_names_mount": "autostart_exec",
    "browser_bundle_env": "host_env",
    "bundle_paths_kept": "host_env",
}


def main(argv):
    global BREAK
    if "--list" in argv:
        for name, inv, _ in CASES:
            print(f"{inv}  {name}")
        print("\nbreaks:")
        for b, case in sorted(BREAKS.items()):
            print(f"  --break {b:24} -> {case} must FAIL")
        return 0
    for i, a in enumerate(argv):
        if a == "--break" and i + 1 < len(argv):
            os.environ["LOTTO_BREAK"] = argv[i + 1]
    BREAK = os.environ.get("LOTTO_BREAK") or ""
    only = None
    if BREAK:
        only = BREAKS.get(BREAK)
        if only is None:
            print(f"unknown break {BREAK!r}; --list shows them all")
            return 2
        print(f"RED TEST: break={BREAK} — {only} is expected to FAIL\n")

    failures = 0
    ran = 0
    try:
        for name, inv, fn in CASES:
            if only and name != only:
                continue
            ran += 1
            try:
                fn()
                print(f"  PASS  {inv}  {name}")
            except Fail as exc:
                failures += 1
                print(f"  FAIL  {inv}  {name}\n          {exc}")
            except Exception as exc:  # noqa: BLE001 - report, do not mask
                failures += 1
                print(f"  ERROR {inv}  {name}\n          {type(exc).__name__}: {exc}")
    finally:
        for d in _TEMP:
            shutil.rmtree(d, ignore_errors=True)

    if BREAK:
        if failures:
            print(f"\nred test OK: {only} failed as it should")
            return 0
        print(f"\nRED TEST DID NOT GO RED: {only} passed with {BREAK} applied")
        return 1
    print(f"\n{ran - failures}/{ran} cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
