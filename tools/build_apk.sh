#!/usr/bin/env bash
# Build dist/LottoTracker-<VERSION>.apk (LOTTO-0106 §4.8).
#
#     tools/build_apk.sh
#
# Gradle runs inside packaging/Containerfile.android, which pins the JDK, the
# Android SDK and Gradle. Needs podman.
#
# The signing key lives OUTSIDE the repository: LOTTO_KEYSTORE_DIR (default
# ~/.config/LottoTracker-signing) holds release.jks and the file `password`.
# Every update must be signed with the key that signed the first install, so
# keep a second copy of that folder off this machine.
set -euo pipefail

cd "$(dirname "$0")/.."

KEYDIR=${LOTTO_KEYSTORE_DIR:-$HOME/.config/LottoTracker-signing}
if [ ! -f "$KEYDIR/release.jks" ] || [ ! -f "$KEYDIR/password" ]; then
    echo "build_apk: no signing key in $KEYDIR (needs release.jks and password)" >&2
    exit 1
fi

VERSION=$(tr -d '[:space:]' < VERSION)
OUT="dist/LottoTracker-$VERSION.apk"
mkdir -p dist build/android-gradle

# Rootless podman maps the container's root to the user, so build/ stays
# theirs. label=disable for the reason tools/build_appimage.sh gives.
# Gradle's downloads persist in build/android-gradle between runs.
IMAGE=localhost/lottotracker-android:36
podman build -q -t "$IMAGE" -f packaging/Containerfile.android packaging >/dev/null
LOTTO_KEYSTORE_PASSWORD=$(cat "$KEYDIR/password")
export LOTTO_KEYSTORE_PASSWORD
podman run --rm --security-opt label=disable \
    -v "$PWD:/src" -v "$KEYDIR:/key:ro" -w /src/android \
    -e GRADLE_USER_HOME=/src/build/android-gradle \
    -e LOTTO_KEYSTORE=/key/release.jks -e LOTTO_KEYSTORE_PASSWORD \
    "$IMAGE" gradle --no-daemon -q assembleRelease

cp android/app/build/outputs/apk/release/app-release.apk "$OUT"
echo "built $OUT ($(du -h "$OUT" | cut -f1))"
