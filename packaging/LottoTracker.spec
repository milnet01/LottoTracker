# PyInstaller recipe for the Linux AppImage (LOTTO-0015 §4.7).
# Built by tools/build_appimage.sh; not meant to be run by hand.
# One-folder mode: the AppImage is the single file, so a one-file bundle
# inside it would only unpack a second time at every start.
import os

ROOT = os.path.dirname(SPECPATH)  # noqa: F821 - SPECPATH is set by PyInstaller

a = Analysis(  # noqa: F821
    [os.path.join(ROOT, "lottotracker.py")],
    pathex=[ROOT],
    datas=[
        (os.path.join(ROOT, "icons"), "icons"),
        (os.path.join(ROOT, "fonts"), "fonts"),
    ],
    # watch_sms.py imports these inside run(); named so a change in what the
    # analysis can see does not silently ship a watcher that dies at start.
    hiddenimports=[
        "dbus", "_dbus_bindings", "dbus.mainloop.glib", "_dbus_glib_bindings",
        "gi", "gi.repository.GLib",
    ],
    # Qt modules the tray does not use (it needs QtCore, QtGui, QtWidgets).
    excludes=[
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebChannel", "PySide6.QtNetwork", "PySide6.QtMultimedia",
        "PySide6.QtPdf", "PySide6.Qt3DCore", "PySide6.QtCharts",
        "PySide6.QtDataVisualization", "PySide6.QtSql", "PySide6.QtTest",
        "tkinter",
    ],
)
# The host's own font libraries, as the AppImage project's exclude list says:
# the build system's older fontconfig cannot parse a newer host's font config
# and prints an error per line of it (LOTTO-0102). freetype and harfbuzz go
# with it, so the host's fontconfig never loads older ones than it was built for.
HOST_ONLY = ("libfontconfig.so", "libfreetype.so", "libharfbuzz.so")
a.binaries = [b for b in a.binaries if not os.path.basename(b[0]).startswith(HOST_ONLY)]
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="lottotracker",
    console=True,  # stdout is the desktop log, as for the source tray
    strip=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="lottotracker", strip=False, upx=False)  # noqa: F821
