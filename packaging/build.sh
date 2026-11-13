#!/bin/bash
# Builds "Kaleido Serial Bridge.app" and a drag-to-Applications disk image.
#
#   packaging/build.sh                 local test build, signed ad hoc
#   CODESIGN_IDENTITY="Developer ID Application: NAME (TEAMID)" packaging/build.sh
#                                      release build with the hardened runtime; then notarize it
#                                      with packaging/notarize.sh (see docs/DISTRIBUTION.md)
#
# PYTHON     the interpreter of an environment with the "dev" dependencies (default: python3)
# BUILD_DIR  where the app is built (default: a folder under $TMPDIR, to keep build files out of synced folders)
# The disk image is written to dist/ in the project.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
VERSION="$("$PYTHON" -c "import sys; sys.path.insert(0, '$ROOT/src'); import kaleido_serial_bridge as k; print(k.__version__)")"
APP_NAME="Kaleido Serial Bridge"
BUILD_DIR="${BUILD_DIR:-${TMPDIR:-/tmp}/kaleido-serial-bridge-build}"
DMG="$ROOT/dist/KaleidoSerialBridge-$VERSION-arm64.dmg"

echo "== building $APP_NAME $VERSION in $BUILD_DIR"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR" "$ROOT/dist"
[ -f "$ROOT/packaging/AppIcon.icns" ] || "$PYTHON" "$ROOT/packaging/make_icon.py"
"$PYTHON" -m PyInstaller --noconfirm --log-level WARN \
    --distpath "$BUILD_DIR/dist" --workpath "$BUILD_DIR/work" "$ROOT/packaging/KaleidoSerialBridge.spec"
APP="$BUILD_DIR/dist/$APP_NAME.app"

echo "== signature"
if [ -n "${CODESIGN_IDENTITY:-}" ]; then
    # sign again from the inside out with the hardened runtime, as notarization requires
    codesign --force --deep --timestamp --options runtime \
        --entitlements "$ROOT/packaging/entitlements.plist" --sign "$CODESIGN_IDENTITY" "$APP"
fi
codesign --verify --deep --strict "$APP"
codesign -dv "$APP" 2>&1 | grep -E "^(Identifier|Signature|TeamIdentifier|Authority)" || true

echo "== self-test of the built app"
env -i HOME="$HOME" PATH=/usr/bin:/bin "$APP/Contents/MacOS/KaleidoSerialBridge" --selftest

echo "== disk image"
STAGE="$BUILD_DIR/dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp "$ROOT/packaging/dmg-README.txt" "$STAGE/Read Me.txt"
rm -f "$DMG"
hdiutil create -quiet -volname "$APP_NAME $VERSION" -srcfolder "$STAGE" -fs HFS+ -format UDZO "$DMG"
if [ -n "${CODESIGN_IDENTITY:-}" ]; then
    codesign --force --timestamp --sign "$CODESIGN_IDENTITY" "$DMG"
fi
echo "app:        $APP"
echo "disk image: $DMG ($(du -h "$DMG" | cut -f1))"
shasum -a 256 "$DMG"
