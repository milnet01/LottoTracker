#!/usr/bin/env python3
"""LOTTO-0106 INV-124 and INV-125: what the built APK carries and asks for.

    python3 tools/verify_apk.py [--break NAME] [APK]

Local lane only, by hand and before a release; not in ./local-CI.sh. It needs
the built file (tools/build_apk.sh) and podman with the build image, whose
aapt2 reads the manifest. Nothing here reads the phone or the dump.

INV-124: no member of the APK, nor of any archive inside it (Chaquopy packs
the app's Python into a zip), is a data file. INV-125: the merged manifest
asks for exactly PERMISSIONS and sets allowBackup to false.

--break NAME plants one defect in what was read, after reading it, and the
named case must then fail: `data_file` adds a dump to the listing,
`extra_permission` adds a permission, `backup_on` drops allowBackup="false".
"""

import io
import os
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE = "localhost/lottotracker-android:36"  # tools/build_apk.sh builds it
PACKAGE = "za.co.antsprojectshub.lottotracker"

# Every file that holds the user's data (INV-124), and the cache folder.
DATA_FILES = {"lotto_sms_raw.txt", "archive_results.json", "accepted.json",
              "sms_threads.json", "expiry_warned.json", "settings.json"}
DATA_FOLDER = "archive_cache/"

# The three the app asks for, plus what AndroidX WorkManager merges in, as
# measured on the first build (spec §14). Android grants these at install
# without asking; RECEIVE_BOOT_COMPLETED is what keeps the evening job after
# the phone restarts. The last is AndroidX's own, held by this app alone.
PERMISSIONS = {
    "android.permission.READ_SMS",
    "android.permission.INTERNET",
    "android.permission.POST_NOTIFICATIONS",
    "android.permission.WAKE_LOCK",
    "android.permission.ACCESS_NETWORK_STATE",
    "android.permission.RECEIVE_BOOT_COMPLETED",
    "android.permission.FOREGROUND_SERVICE",
    f"{PACKAGE}.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION",
}

BREAKS = ("data_file", "extra_permission", "backup_on")


class Fail(Exception):
    pass


def members(data, prefix=""):
    """Every member name in a zip, and inside every zip it holds, as paths."""
    names = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            names.append(prefix + name)
            if name.endswith("/"):
                continue
            inner = z.read(name)
            if inner[:4] == b"PK\x03\x04":
                names.extend(members(inner, prefix + name + "!/"))
    return names


def data_leaks(names):
    """INV-124: the member names that are a data file or lie in the cache."""
    leaks = []
    for name in names:
        inner = name.rsplit("!/", 1)[-1]
        if os.path.basename(inner) in DATA_FILES or DATA_FOLDER in "/" + inner:
            leaks.append(name)
    return leaks


def aapt2(apk, *args):
    folder, base = os.path.split(apk)
    out = subprocess.run(
        ["podman", "run", "--rm", "--security-opt", "label=disable",
         "-v", f"{folder}:/apk:ro", IMAGE, "aapt2", *args, f"/apk/{base}"],
        capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise Fail(f"aapt2 {args[0]} failed: {out.stderr.strip()}")
    return out.stdout


def permissions(dump):
    """The uses-permission names in `aapt2 dump permissions` output."""
    found = set()
    for line in dump.splitlines():
        if line.startswith("uses-permission: name='"):
            found.add(line.split("'")[1])
    return found


def backup_off(xmltree):
    return any("allowBackup" in line and line.rstrip().endswith("=false")
               for line in xmltree.splitlines())


def main(argv):
    broken = None
    rest = []
    it = iter(argv)
    for a in it:
        if a == "--break":
            broken = next(it, None)
            if broken not in BREAKS:
                print(f"--break takes one of: {', '.join(BREAKS)}")
                return 2
        else:
            rest.append(a)
    with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as fh:
        version = fh.read().strip()
    apk = os.path.abspath(rest[0] if rest else os.path.join(
        ROOT, "dist", f"LottoTracker-{version}.apk"))
    if not os.path.isfile(apk):
        print(f"cannot run: no APK at {apk}; build it with tools/build_apk.sh")
        return 2
    with open(apk, "rb") as fh:
        data = fh.read()
    print(f"{os.path.basename(apk)}: {len(data) / 1e6:.1f} MB")

    failures = 0

    def case(inv, name, fn):
        nonlocal failures
        try:
            fn()
            print(f"  PASS  {inv}  {name}")
        except Fail as exc:
            failures += 1
            print(f"  FAIL  {inv}  {name}\n          {exc}")

    def no_data_file():
        names = members(data)
        if broken == "data_file":
            names.append("assets/chaquopy/app.imy!/lotto_sms_raw.txt")
        leaks = data_leaks(names)
        if leaks:
            raise Fail(f"data files in the APK: {', '.join(leaks)}")

    def exact_permissions():
        found = permissions(aapt2(apk, "dump", "permissions"))
        if broken == "extra_permission":
            found.add("android.permission.READ_CONTACTS")
        extra, missing = found - PERMISSIONS, PERMISSIONS - found
        if extra or missing:
            raise Fail(f"permissions differ: extra {sorted(extra)}, missing {sorted(missing)}")

    def no_backup():
        tree = aapt2(apk, "dump", "xmltree", "--file", "AndroidManifest.xml")
        if broken == "backup_on":
            tree = tree.replace("allowBackup", "allowbackupRemoved")
        if not backup_off(tree):
            raise Fail('the manifest does not set allowBackup="false"')

    try:
        case("INV-124", "no_data_file", no_data_file)
        case("INV-125", "exact_permissions", exact_permissions)
        case("INV-125", "no_backup", no_backup)
    except FileNotFoundError:
        print("cannot run: podman is not installed")
        return 2
    print(f"\n{3 - failures}/3 cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
