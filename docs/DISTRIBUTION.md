# Building, signing and notarizing

**Release policy:** a binary is offered only as a disk image that is signed with a Developer ID,
notarized by Apple and stapled, and only after the checks in step 3 have passed on the Mac that
built it. Until that image has also been installed and opened on a second Mac (step 4), it is
published as a **pre-release**, and its release notes say that it was checked on the build Mac
only. The pre-release mark comes off after the second-Mac check.

Version 0.2.0 is such a pre-release. What was and was not checked for it is listed under
[State of 0.2.0](#state-of-020).

## Local test build

```
PYTHON=~/.venvs/kaleido-serial-bridge/bin/python packaging/build.sh
```

writes `dist/KaleidoSerialBridge-<version>-arm64.dmg`. The app is built with PyInstaller and
contains its own Python, pyserial and PyObjC; it needs nothing on the target Mac. Without a signing
identity it is signed ad hoc: it runs on the Mac it was built on, and on other Macs only after the
user allows it in **System Settings » Privacy & Security » Open Anyway**. Such a build is for your
own testing and is not published. Before keeping a local test image, give it a name that says what
it is, for example `KaleidoSerialBridge-<version>-arm64-adhoc-local-test.dmg`: a release build
writes to the same path and would replace it.

Check a build with

```
python tests/packaged_app_check.py "$TMPDIR/kaleido-serial-bridge-build/dist/Kaleido Serial Bridge.app"
```

## What a public release needs

| Needed | Where it comes from |
|---|---|
| Apple Developer Program membership | developer.apple.com, 99 USD per year |
| A **Developer ID Application** certificate with its private key in the login keychain | Xcode » Settings » Accounts » Manage Certificates, or developer.apple.com » Certificates |
| The Team ID | developer.apple.com » Membership |
| Credentials for the notary service: an Apple ID with an **app-specific password** (appleid.apple.com), or an App Store Connect API key | stored once in the keychain, see below |

For 0.2.0 all of these were in place, and the steps below were run on 2026-11-13, except step 4
on a second Mac. They follow Apple's and PyInstaller's documented procedure.
`security find-identity -v -p codesigning` shows whether the certificate and its key are usable.

Before the first release, also decide on:

- the **bundle identifier**. It is `io.github.johnbthomas.KaleidoSerialBridge` in
  `src/kaleido_serial_bridge/__init__.py`. It should stay the same for the life of the app.
- the **license holder and year** in `LICENSE`.
- the **version** in `src/kaleido_serial_bridge/__init__.py`, and an entry in `CHANGELOG.md`.

## Steps

1. Store the notary credentials once (this asks for the app-specific password and saves it in the
   keychain under a name of your choice; nothing is written to the project):

   ```
   xcrun notarytool store-credentials "kaleido-bridge-notary" --apple-id "you@example.com" --team-id "TEAMID"
   ```

2. Build and sign with the hardened runtime:

   ```
   CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" \
   PYTHON=~/.venvs/kaleido-serial-bridge/bin/python packaging/build.sh
   ```

   The script signs the app with `--options runtime` and `packaging/entitlements.plist`, verifies
   the signature, runs the app's self-test, builds the disk image and signs it.

3. Notarize and staple:

   ```
   NOTARY_PROFILE="kaleido-bridge-notary" packaging/notarize.sh dist/KaleidoSerialBridge-<version>-arm64.dmg
   ```

   This submits the disk image, waits for the result, staples the ticket to it and asks Gatekeeper
   for its verdict. Only when all of that has passed does it write `SHA256SUMS.txt` next to the
   disk image and check it with `shasum -a 256 -c SHA256SUMS.txt`. Stapling changes the file, so a
   checksum taken before it would not match the image that gets published. If notarization fails,
   `xcrun notarytool log <submission id> --keychain-profile "kaleido-bridge-notary"` lists the
   files it objects to.

4. Test the stapled disk image on a second Mac: download it through a browser, open it, drag the
   app into Applications and open it from there. It must open without a Gatekeeper refusal. Until
   this has been done, the release stays a pre-release.

   On the build Mac alone, Gatekeeper's verdict can be asked without opening the app, for the disk
   image and for a copy of the app that is marked as downloaded:

   ```
   spctl --assess --type open --context context:primary-signature -vv <the dmg>
   xattr -rw com.apple.quarantine "0083;00000000;Safari;" <a copy of the app>
   spctl --assess --type execute -vv <that copy>
   ```

   Both should answer `accepted` and `source=Notarized Developer ID`. This does not replace the
   second Mac.

5. Publish the disk image together with the `SHA256SUMS.txt` from step 3, as a pre-release if
   step 4 has not been done on a second Mac. With both files in one folder, a download can be
   checked with `shasum -a 256 -c SHA256SUMS.txt`.

## State of 0.2.0

The disk image of the 0.2.0 pre-release was built, signed, notarized and stapled on 2026-11-13. It
has the SHA-256 `8d93e48150a8d98ec0c15e27975da071241e8b90ec7cb5cfc2090cb6302a8b1e`. The app in it
has the CDHash `a9a59f259cc3528af70e43abbed537cb544186b0`.

| Check | Result |
|---|---|
| Developer ID signature of the disk image, of the app and of every binary in it, with the hardened runtime | valid |
| Notarization | accepted. The ticket is stapled to the disk image, not to the app inside it |
| Gatekeeper on the notarized disk image, on the build Mac | accepted |
| Gatekeeper on a quarantined copy of the app, on the build Mac | accepted |
| `shasum -a 256 -c SHA256SUMS.txt` | OK |
| Installation on a second Mac | **not tested** |
| First launch without a network connection | **not tested** |
| Operation with a roaster | one M2 Lite, idle, heater off, on the build Mac: opening at login, automatic bridge start, live readings and OFF → ON confirmed by the logs. ⌘Q → relaunch → ON is pending. See [EVIDENCE.md](EVIDENCE.md) |

## Notes

- **Entitlements.** `packaging/entitlements.plist` allows unsigned executable memory, which the
  embedded Python needs for the callbacks PyObjC creates. If a notarized build crashes at launch
  with a code signing error, check Console for the entitlement it asks for before adding more.
- **Bluetooth permission.** The app does not use Bluetooth APIs. It runs `system_profiler` to ask
  whether the roaster is connected. `Info.plist` carries a usage description in case macOS asks
  the user for consent; in the test runs no such request was logged.
- **Stapling.** `packaging/notarize.sh` staples the ticket to the disk image. The app inside
  carries no ticket of its own, so a first launch on a Mac without a network connection has not
  been shown to work.
- **Login item.** "Open the app at login" uses `SMAppService`. macOS ties the item to the signed
  app; test it with the signed build in `/Applications`.
- **The self-test moves the login item.** `packaging/build.sh` and `tests/packaged_app_check.py`
  run the built app's self-test, which asks macOS for the state of the login item. While "Open the
  app at login" is on for an installed copy, macOS was seen to move that login item to the copy
  that asked, twice on 2026-11-13. After a build, check where it points:

  ```
  /usr/bin/log show --last 1d --style compact --predicate 'process == "backgroundtaskmanagementd" AND eventMessage CONTAINS "updating item" AND eventMessage CONTAINS "Kaleido"' | tail -1
  ```

  The path after `URL to:` in the last line is where the item points now. Write `/usr/bin/log` in
  full: in zsh, `log` alone is a shell builtin and prints nothing here.
- **Architecture.** The build is arm64 only. The problem this app works around has only been
  reported on Apple silicon.
- **Updates.** There is no updater. A new version is a new disk image.
