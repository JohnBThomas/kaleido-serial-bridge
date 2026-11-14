# Changelog

## 0.2.0 — 2026-11-13, pre-release

First version as a macOS menu bar app. Offered as a pre-release: a disk image for Apple silicon,
signed with a Developer ID and notarized by Apple.

- The signed disk image (app CDHash `a9a59f259cc3528af70e43abbed537cb544186b0`): Gatekeeper
  accepted the notarized disk image and a quarantined copy of the app on the build Mac, and the
  ticket is stapled to the disk image. Not tested: installation on a second Mac, a first launch
  without a network connection, and operation with a roaster. The hardware results further down
  belong to earlier ad hoc builds, not to this one.
- Menu bar status: stopped, waiting for Bluetooth, waiting for Artisan, Artisan attached and
  waiting for the first reply, receiving roaster replies, no replies, stopped after a failure.
  Communication is shown only for replies that were actually forwarded to Artisan.
- Setup guide: pairing, choosing the roaster's port (Kaleido-like names suggested), starting the
  bridge, pointing Artisan at the virtual port, keeping separate direct and bridge `.aset` files.
- Start, Stop, Settings, Copy Virtual Port Path, Open Log. Stop and Quit warn while Artisan is attached.
- Optional "Start the bridge when the app opens" and "Open the app at login", both off by default.
- Alerts when the Bluetooth port fails or Artisan vanishes mid-session; help for a silent first
  connection and for going back to direct Bluetooth.
- Build script for a self-contained app in a drag-to-Applications disk image (Python 3.14, pyserial 3.5, PyObjC inside).
- The bridge engine is the prototype's, with additions for the status display only.
  The virtual port keeps its path, `~/.kaleido-bridge/cu.Roaster_bridge`.
- On hardware (one M2 Lite, idle, heater off; one local ad hoc build, CDHash
  `bab9676fa030389d71bddd6b3565767a7014e9d3`): real readings forwarded, a clean detach, and the
  same physical port kept open for the next attach (OFF → ON, twice).
- On hardware with the later ad hoc test build of this source (CDHash
  `7630086f5c8316900d0bbec2ef9a310eb11cfe2b`): first connection, OFF → ON, ⌘Q → relaunch → ON and
  opening at login, each seen by the tester and confirmed by the logs, with one open of the
  physical port throughout. Starting the bridge automatically was reported but is not confirmed by
  the logs of that run; it stays pending. See docs/EVIDENCE.md.
- Recovery help states the record as it is: a restart of the Mac helped on the tested setup, one
  first start after a restart still did not connect, and no reset is known to bring the connection
  back every time.

## 0.1.0 — 2026-11-13

Command line prototype. On one MacBook Pro (M1 Pro, macOS 27.2) with one Kaleido M2 Lite and
Artisan 5.0.0, roaster idle and heater off: readings after OFF → ON and after quit → relaunch → ON
with one open of the port.
