# Building, signing and notarizing

**Release policy:** only source is published for now. No binary is offered for download until a
build signed with a Developer ID has been notarized and that build has been verified to open and
work on a Mac other than the one it was built on.

## Local test build

```
PYTHON=~/.venvs/kaleido-serial-bridge/bin/python packaging/build.sh
```

writes `dist/KaleidoSerialBridge-<version>-arm64.dmg`. The app is built with PyInstaller and
contains its own Python, pyserial and PyObjC; it needs nothing on the target Mac. Without a signing
identity it is signed ad hoc: it runs on the Mac it was built on, and on other Macs only after the
user allows it in **System Settings » Privacy & Security » Open Anyway**. Such a build is for your
own testing and is not published.

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

None of these exist on the machine this was prepared on (`security find-identity -v -p codesigning`
lists no identity), so **the signing and notarization steps below have not been run**. They follow
Apple's and PyInstaller's documented procedure.

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
   for its verdict. If notarization fails, `xcrun notarytool log <submission id> --keychain-profile
   "kaleido-bridge-notary"` lists the files it objects to.

4. Test the stapled disk image on a second Mac, or on this one after
   `xattr -w com.apple.quarantine "0081;00000000;Safari;" <the dmg>`: it must open without a
   Gatekeeper warning.

5. Publish the disk image together with its SHA-256 (`shasum -a 256`).

## Notes

- **Entitlements.** `packaging/entitlements.plist` allows unsigned executable memory, which the
  embedded Python needs for the callbacks PyObjC creates. If a notarized build crashes at launch
  with a code signing error, check Console for the entitlement it asks for before adding more.
- **Bluetooth permission.** The app does not use Bluetooth APIs. It runs `system_profiler` to ask
  whether the roaster is connected. `Info.plist` carries a usage description in case macOS asks
  the user for consent; in the test runs no such request was logged.
- **Login item.** "Open the app at login" uses `SMAppService`. macOS ties the item to the signed
  app; test it with the signed build in `/Applications`.
- **Architecture.** The build is arm64 only. The problem this app works around has only been
  reported on Apple silicon.
- **Updates.** There is no updater. A new version is a new disk image.
