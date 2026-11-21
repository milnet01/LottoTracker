#!/usr/bin/env bash
# Build dist/LottoTracker-<VERSION>-x86_64.AppImage (LOTTO-0015 §4.7).
#
#     tools/build_appimage.sh
#
# PyInstaller runs inside an Ubuntu 22.04 container (packaging/Containerfile,
# LOTTO-0102): the bundle carries that system's Python and libraries, so it
# runs on systems at least as new as that one. Needs podman.
#
# appimagetool and its runtime are not packaged for openSUSE, so they are
# downloaded into build/tools/ and checked against the SHA-256 below BEFORE
# every run, cached or not. A mismatch stops the build. The pins are fixed
# release tags, never "continuous": that tag is rebuilt in place, so its hash
# would not hold. Each hash was checked against the digest GitHub publishes
# for the asset.
set -euo pipefail

cd "$(dirname "$0")/.."

TOOL_VERSION=1.9.1
TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/$TOOL_VERSION/appimagetool-x86_64.AppImage"
TOOL_SHA256=ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0

RUNTIME_VERSION=20251108
RUNTIME_URL="https://github.com/AppImage/type2-runtime/releases/download/$RUNTIME_VERSION/runtime-x86_64"
RUNTIME_SHA256=2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d

VERSION=$(tr -d '[:space:]' < VERSION)
TOOLS=build/tools
APPDIR=build/AppDir
OUT="dist/LottoTracker-$VERSION-x86_64.AppImage"

# fetch URL SHA256 DEST: download if missing, then verify whatever is there.
fetch() {
    local url=$1 sha=$2 dest=$3
    if [ ! -f "$dest" ]; then
        curl -fsSL -o "$dest.part" "$url"
        mv "$dest.part" "$dest"
    fi
    if ! echo "$sha  $dest" | sha256sum -c --quiet -; then
        echo "build_appimage: $dest does not match its pinned SHA-256; refusing to run it" >&2
        rm -f "$dest"
        exit 1
    fi
    chmod +x "$dest"
}

mkdir -p "$TOOLS" dist
fetch "$TOOL_URL" "$TOOL_SHA256" "$TOOLS/appimagetool-$TOOL_VERSION-x86_64.AppImage"
fetch "$RUNTIME_URL" "$RUNTIME_SHA256" "$TOOLS/runtime-$RUNTIME_VERSION-x86_64"

# Rootless podman maps the container's root to the user, so build/ stays theirs.
# label=disable, not :Z: relabelling would strip the files' own SELinux label
# (on this machine, the Samba share's).
IMAGE=localhost/lottotracker-build:22.04
podman build -q -t "$IMAGE" -f packaging/Containerfile packaging >/dev/null
podman run --rm --security-opt label=disable -v "$PWD:/src" -w /src "$IMAGE" \
    python3 -m PyInstaller --noconfirm --clean \
    --distpath build/pyinstaller --workpath build/work packaging/LottoTracker.spec

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib"
cp -a build/pyinstaller/lottotracker "$APPDIR/usr/lib/lottotracker"
install -m 755 packaging/AppRun "$APPDIR/AppRun"
cp packaging/lottotracker.desktop "$APPDIR/lottotracker.desktop"
cp icons/tray-running.svg "$APPDIR/lottotracker.svg"
ln -s lottotracker.svg "$APPDIR/.DirIcon"

ARCH=x86_64 "$TOOLS/appimagetool-$TOOL_VERSION-x86_64.AppImage" \
    --runtime-file "$TOOLS/runtime-$RUNTIME_VERSION-x86_64" \
    "$APPDIR" "$OUT"
echo "built $OUT ($(du -h "$OUT" | cut -f1))"
