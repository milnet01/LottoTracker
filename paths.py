"""Where the tracker's files are: one answer for every module (LOTTO-0015 §4.1).

Two forms. A source checkout keeps its data in the repository folder, as it
always has. A frozen build (PyInstaller, inside the AppImage) runs from a
read-only folder, so its data goes to $XDG_DATA_HOME/LottoTracker, or
~/.local/share/LottoTracker when that is unset, and its bundled icons and
fonts are read from the bundle (sys._MEIPASS).

Stdlib only and Qt-free. Importing this touches no file: the data folder is
created by ensure_data(), which tray.main() and each child's main() call, so
LOTTO-0013 INV-19 (importing serve or supervise starts nothing) still holds.
Every path is fixed at import, so a test of the frozen form sets sys.frozen
before importing anything of the project's (INV-105).
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

FROZEN = bool(getattr(sys, "frozen", False))
RESOURCES = getattr(sys, "_MEIPASS", _HERE) if FROZEN else _HERE


def _data_home():
    # Unset and empty both mean "no preference", as for $XDG_CONFIG_HOME in
    # supervise.config_home().
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "LottoTracker")


DATA = _data_home() if FROZEN else _HERE
DUMP = os.path.join(DATA, "lotto_sms_raw.txt")
THREADS = os.path.join(DATA, "sms_threads.json")
ARCHIVE = os.path.join(DATA, "archive_results.json")
CACHE = os.path.join(DATA, "archive_cache")


def resource(*parts):
    """A file shipped with the program: an icon or the typeface. Never data."""
    return os.path.join(RESOURCES, *parts)


def ensure_data():
    """Create the data folder if it is missing. Never called at import."""
    os.makedirs(DATA, exist_ok=True)
