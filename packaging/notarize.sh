#!/bin/bash
# Notarizes and staples a disk image that was built with a Developer ID signature, then writes its checksum file.
#
#   NOTARY_PROFILE="kaleido-bridge-notary" packaging/notarize.sh dist/KaleidoSerialBridge-<version>-arm64.dmg
#
# NOTARY_PROFILE is the name given to `xcrun notarytool store-credentials`. See docs/DISTRIBUTION.md.
# Not run during development: it needs an Apple Developer account.
#
# SHA256SUMS.txt is written next to the disk image as the last step, and only if every step before it passed.
# So it only ever describes an image that is signed, notarized and stapled. Stapling changes the file:
# a checksum taken before it would not match the image that gets published.
set -euo pipefail

DMG="${1:?usage: NOTARY_PROFILE=name packaging/notarize.sh path/to.dmg}"
: "${NOTARY_PROFILE:?set NOTARY_PROFILE to the keychain profile created with notarytool store-credentials}"

codesign --verify --strict "$DMG" || { echo "the disk image is not signed; build it with CODESIGN_IDENTITY set" >&2; exit 1; }
xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait
xcrun stapler staple "$DMG"
xcrun stapler validate "$DMG"
spctl --assess --type open --context context:primary-signature --verbose=2 "$DMG"

cd "$(dirname "$DMG")"
shasum -a 256 "$(basename "$DMG")" > SHA256SUMS.txt
shasum -a 256 -c SHA256SUMS.txt
echo "checksum file: $(pwd)/SHA256SUMS.txt"
