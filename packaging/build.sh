#!/bin/bash
# Builds "Kaleido Serial Bridge.app" and a drag-to-Applications disk image.
#
#   OUTPUT_DMG=dist/KaleidoSerialBridge-<version>-<commit>-adhoc-test-arm64.dmg packaging/build.sh
#                                      local test build, signed ad hoc, under a name of its own
#   packaging/build.sh                 the same, written to the release name (see below)
#   CODESIGN_IDENTITY="Developer ID Application: NAME (TEAMID)" packaging/build.sh
#                                      release build with the hardened runtime; then notarize it
#                                      with packaging/notarize.sh (see docs/DISTRIBUTION.md)
#
# PYTHON     the interpreter of an environment with the "dev" dependencies (default: python3)
# BUILD_DIR  where the app is built (default: a folder under $TMPDIR, to keep build files out of synced folders)
# OUTPUT_DMG the disk image to write (default: dist/KaleidoSerialBridge-<version>-arm64.dmg, the release name).
#            Relative paths are taken from the project folder. If the file exists already the build
#            stops before it starts: an existing image, a published one included, is never replaced.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
VERSION="$("$PYTHON" -c "import sys; sys.path.insert(0, '$ROOT/src'); import kaleido_serial_bridge as k; print(k.__version__)")"
APP_NAME="Kaleido Serial Bridge"
BUILD_DIR="${BUILD_DIR:-${TMPDIR:-/tmp}/kaleido-serial-bridge-build}"
DMG="${OUTPUT_DMG:-dist/KaleidoSerialBridge-$VERSION-arm64.dmg}"
case "$DMG" in /*) ;; *) DMG="$ROOT/$DMG" ;; esac
case "$DMG" in *.dmg) ;; *) echo "OUTPUT_DMG must end in .dmg: $DMG" >&2; exit 1 ;; esac
if [ -e "$DMG" ] || [ -L "$DMG" ]; then
    echo "$DMG exists already. Nothing was built and nothing was replaced." >&2
    echo "Move it away first, or choose another name, for example:" >&2
    COMMIT="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo local)"
    echo "  OUTPUT_DMG=dist/KaleidoSerialBridge-$VERSION-$COMMIT-adhoc-test-arm64.dmg packaging/build.sh" >&2
    exit 1
fi

echo "== building $APP_NAME $VERSION in $BUILD_DIR"
echo "   disk image: $DMG"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR" "$(dirname "$DMG")"
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
# KALEIDO_BRIDGE_NO_LOGIN_ITEM=1: the self-test must not ask the login item service. Asking it from this
# copy would make macOS move a registered login item of an installed copy here.
env -i HOME="$HOME" PATH=/usr/bin:/bin KALEIDO_BRIDGE_NO_LOGIN_ITEM=1 "$APP/Contents/MacOS/KaleidoSerialBridge" --selftest

echo "== disk image"
STAGE="$BUILD_DIR/dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp "$ROOT/packaging/dmg-README.txt" "$STAGE/Read Me.txt"
if [ -e "$DMG" ]; then echo "$DMG appeared during the build; not replacing it." >&2; exit 1; fi
hdiutil create -quiet -volname "$APP_NAME $VERSION" -srcfolder "$STAGE" -fs HFS+ -format UDZO "$DMG"
if [ -n "${CODESIGN_IDENTITY:-}" ]; then
    codesign --force --timestamp --sign "$CODESIGN_IDENTITY" "$DMG"
fi
echo "app:        $APP"
echo "disk image: $DMG ($(du -h "$DMG" | cut -f1))"
shasum -a 256 "$DMG"
