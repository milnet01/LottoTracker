#!/usr/bin/env python3
"""LOTTO-0015 INV-113 and INV-114: the built AppImage, run as a user would.

    python3 tools/verify_appimage.py [--scratch DIR] [APPIMAGE]

Local lane only, by hand and before a release; not in ./local-CI.sh. It needs
the built file (tools/build_appimage.sh), the real dump and archive, the
network for the results feed, and the desktop session: with
QT_QPA_PLATFORM=offscreen Qt reports no system tray and the tray exits before
spawning anything. The phone must be UNREACHABLE, so the bundled watcher finds
no device and writes nothing into the copied dump; this refuses otherwise.

Run 1 (INV-113): the AppImage, copied outside the repository and started from
there over COPIES of the dump, archive and cache, serves as many entry rows as
the source checkout's serve.py over the originals; its watcher outlives
SmsWatch.died_early()'s wait; and SIGTERM to it leaves neither child running.
Run 2 (INV-114): started with a data folder that does not exist, it creates
it and serves the no-messages notice naming it, with no ticket table.

DIR (default: the system temporary folder) receives about the AppImage's size
plus the archive cache, and is removed at the end. Nothing here prints a
message body: the comparison is a count of rows.
"""

import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_TIMEOUT = 600.0  # a first build fetches every pool's results
ANSWER_TIMEOUT = 60.0
WATCH_WAIT = 3.0       # supervise.SmsWatch.died_early()'s default
REAP_TIMEOUT = 15.0
ROW = re.compile(r"<tr [^>]*data-pool=")


class Fail(Exception):
    pass


def need(cond, msg):
    if not cond:
        raise Fail(msg)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=30) as r:
        return r.read().decode("utf-8")


def outside_script(html):
    return re.sub(r"<script>.*?</script>", "", html, flags=re.S)


def wait_built(port, proc):
    """Poll /status until a build has finished; the page then holds results."""
    deadline = time.monotonic() + BUILD_TIMEOUT
    while time.monotonic() < deadline:
        need(proc.poll() is None, f"the process exited ({proc.returncode}) before a build finished")
        try:
            s = json.loads(get(port, "/status"))
            if s.get("built") and not s.get("building"):
                return
        except OSError:
            pass
        time.sleep(1.0)
    raise Fail(f"no finished build within {BUILD_TIMEOUT:.0f}s")


def wait_answer(port, proc):
    deadline = time.monotonic() + ANSWER_TIMEOUT
    while time.monotonic() < deadline:
        need(proc.poll() is None, f"the process exited ({proc.returncode}) before answering")
        try:
            return get(port, "/")
        except OSError:
            time.sleep(0.5)
    raise Fail(f"no server answered on port {port} within {ANSWER_TIMEOUT:.0f}s")


def _ppid(pid):
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            return int(fh.read().rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        return None


def _argv(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            return [a.decode(errors="replace") for a in fh.read().split(b"\0") if a]
    except OSError:
        return []


def descendants(root):
    pids = [int(p) for p in os.listdir("/proc") if p.isdigit()]
    parent = {p: _ppid(p) for p in pids}
    found, frontier = set(), {root}
    while frontier:
        frontier = {p for p, pp in parent.items() if pp in frontier and p not in found}
        found |= frontier
    return found


def children_by_role(root):
    """{"serve": pid, "watch": pid} among root's descendants, by argv[1]."""
    roles = {}
    for pid in descendants(root):
        argv = _argv(pid)
        if len(argv) >= 2 and os.path.basename(argv[0]) == "lottotracker" \
                and argv[1] in ("serve", "watch"):
            roles[argv[1]] = pid
    return roles


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie still answers kill(0); it has exited all the same.
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def stop_and_check_reaped(proc, roles):
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=REAP_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise Fail(f"the AppImage did not exit within {REAP_TIMEOUT:.0f}s of SIGTERM")
    deadline = time.monotonic() + REAP_TIMEOUT
    while time.monotonic() < deadline and any(alive(p) for p in roles.values()):
        time.sleep(0.2)
    left = [r for r, p in roles.items() if alive(p)]
    for r in left:
        os.kill(roles[r], signal.SIGKILL)
    need(not left, f"SIGTERM left {left} running")


def env_report(pid, launched):
    """Spec §15: what the bundle sets that a host program would inherit."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as fh:
            raw = fh.read().split(b"\0")
    except OSError:
        return
    env = dict(e.decode(errors="replace").split("=", 1) for e in raw if b"=" in e)
    changed = sorted(k for k in set(env) | set(launched) if env.get(k) != launched.get(k))
    print(f"    env set or changed inside the bundle: {', '.join(changed) or 'none'}")
    for k in ("LD_LIBRARY_PATH", "LD_LIBRARY_PATH_ORIG", "QT_PLUGIN_PATH",
              "GI_TYPELIB_PATH", "PYTHONPATH", "PYTHONHOME"):
        if k in changed:
            print(f"      {k}={env.get(k, '(removed)')}  (launcher: {launched.get(k, '(unset)')})")


def launch(appimage, cwd, data_home, config_home, port, log):
    env = dict(os.environ, LOTTO_PORT=str(port), XDG_DATA_HOME=data_home,
               XDG_CONFIG_HOME=config_home)
    env.pop("PORT", None)  # $PORT wins over $LOTTO_PORT (serve.resolve_port)
    proc = subprocess.Popen([appimage], cwd=cwd, env=env, stdout=log,
                            stderr=subprocess.STDOUT, start_new_session=True)
    return proc, env


def write_settings(config_home):
    os.makedirs(os.path.join(config_home, "lotto-tracker"), exist_ok=True)
    with open(os.path.join(config_home, "lotto-tracker", "settings.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"open_on_start": False}, fh)


def source_rows():
    """The source checkout's page over the originals: the number to match."""
    port = free_port()
    env = dict(os.environ, LOTTO_PORT=str(port), LOTTO_TOKEN=secrets.token_urlsafe(16))
    env.pop("PORT", None)
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py")], cwd=ROOT,
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_built(port, proc)
        return len(ROW.findall(outside_script(get(port, "/"))))
    finally:
        proc.terminate()
        proc.wait(timeout=REAP_TIMEOUT)


def run_with_data(appimage, scratch):
    """INV-113."""
    run = os.path.join(scratch, "elsewhere")
    os.makedirs(run)
    copy = os.path.join(run, os.path.basename(appimage))
    shutil.copy2(appimage, copy)
    data_home = os.path.join(scratch, "data")
    data = os.path.join(data_home, "LottoTracker")
    os.makedirs(data)
    shutil.copy2(os.path.join(ROOT, "lotto_sms_raw.txt"), data)
    shutil.copy2(os.path.join(ROOT, "archive_results.json"), data)
    shutil.copytree(os.path.join(ROOT, "archive_cache"), os.path.join(data, "archive_cache"))
    config_home = os.path.join(scratch, "config")
    write_settings(config_home)
    with open(os.path.join(ROOT, "lotto_sms_raw.txt"), "rb") as fh:
        before = fh.read()

    port = free_port()
    with open(os.path.join(scratch, "run1.log"), "wb") as log:
        proc, env = launch(copy, run, data_home, config_home, port, log)
        roles = {}
        try:
            wait_built(port, proc)
            html = outside_script(get(port, "/"))
            need("No messages found" not in html,
                 "the AppImage shows the no-messages notice over a data folder holding the dump")
            got = len(ROW.findall(html))
            roles = children_by_role(proc.pid)
            need(set(roles) == {"serve", "watch"},
                 f"found children {sorted(roles)}, want serve and watch")
            time.sleep(WATCH_WAIT)
            need(alive(roles["watch"]), "the watcher died at start (is dbus or gi bundled?)")
            env_report(roles["watch"], env)
        finally:
            if proc.poll() is None:
                stop_and_check_reaped(proc, roles or children_by_role(proc.pid))
    with open(os.path.join(data, "lotto_sms_raw.txt"), "rb") as fh:
        need(fh.read() == before, "the watcher wrote into the copied dump: was the phone reachable?")
    want = source_rows()
    need(want > 0, "the source checkout's page shows no entry rows; nothing to compare")
    need(got == want, f"the AppImage shows {got} entry rows, the source checkout {want}")
    print(f"    {got} entry rows in both")


def run_without_data(appimage, scratch):
    """INV-114."""
    data_home = os.path.join(scratch, "new-data")
    data = os.path.join(data_home, "LottoTracker")
    config_home = os.path.join(scratch, "config2")
    write_settings(config_home)
    port = free_port()
    with open(os.path.join(scratch, "run2.log"), "wb") as log:
        proc, _env = launch(appimage, scratch, data_home, config_home, port, log)
        roles = {}
        try:
            html = outside_script(wait_answer(port, proc))
            roles = children_by_role(proc.pid)
            need(os.path.isdir(data), "the data folder was not created")
            need("No messages found" in html, "the no-messages notice is not shown")
            need(data in html, f"the notice does not name {data}")
            need("<table " not in html and "<table>" not in html,
                 "a table renders beneath the no-messages notice")
        finally:
            if proc.poll() is None:
                stop_and_check_reaped(proc, roles or children_by_role(proc.pid))


def preconditions(appimage):
    need(os.path.isfile(appimage), f"{appimage} does not exist; run tools/build_appimage.sh")
    need(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"),
         "no desktop session: the tray needs a real system tray")
    for name in ("lotto_sms_raw.txt", "archive_results.json", "archive_cache"):
        need(os.path.exists(os.path.join(ROOT, name)), f"{name} is missing")
    need(shutil.which("kdeconnect-cli"), "kdeconnect-cli is missing, so the phone's state is unknown")
    out = subprocess.run(["kdeconnect-cli", "--list-available", "--id-only"],
                         capture_output=True, text=True, timeout=30)
    need(out.returncode == 0, "kdeconnect-cli failed, so the phone's state is unknown")
    need(not out.stdout.strip(),
         "a phone is reachable over KDE Connect; make it unreachable (turn its Wi-Fi off) "
         "so the bundled watcher writes nothing, then run this again")


def main(argv):
    scratch_parent = None
    rest = []
    it = iter(argv)
    for a in it:
        if a == "--scratch":
            scratch_parent = next(it, None)
        else:
            rest.append(a)
    with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as fh:
        version = fh.read().strip()
    appimage = os.path.abspath(rest[0] if rest else os.path.join(
        ROOT, "dist", f"LottoTracker-{version}-x86_64.AppImage"))
    try:
        preconditions(appimage)
    except Fail as exc:
        print(f"cannot run: {exc}")
        return 2
    scratch = tempfile.mkdtemp(prefix="lotto-appimage-", dir=scratch_parent)
    failures = 0
    try:
        for inv, name, fn in (("INV-113", "run_with_data", run_with_data),
                              ("INV-114", "run_without_data", run_without_data)):
            try:
                fn(appimage, scratch)
                print(f"  PASS  {inv}  {name}")
            except Fail as exc:
                failures += 1
                print(f"  FAIL  {inv}  {name}\n          {exc}")
                log = os.path.join(scratch, "run1.log" if inv == "INV-113" else "run2.log")
                if os.path.exists(log):
                    with open(log, encoding="utf-8", errors="replace") as fh:
                        tail = fh.read().splitlines()[-15:]
                    print("          last lines of its log:")
                    for line in tail:
                        print(f"            {line}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    print(f"\n{2 - failures}/2 cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
