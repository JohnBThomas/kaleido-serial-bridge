# Changelog

## 0.2.0 — source only, no binary release

First version as a macOS menu bar app. Published as source; a binary will follow only after
Developer ID signing and notarization have been verified.

- Menu bar status: stopped, waiting for Bluetooth, waiting for Artisan, receiving roaster replies,
  no replies, stopped after a failure. Communication is shown only for replies that were actually
  forwarded to Artisan.
- Setup guide: pairing, choosing the roaster's port (Kaleido-like names suggested), starting the
  bridge, pointing Artisan at the virtual port, keeping separate direct and bridge `.aset` files.
- Start, Stop, Settings, Copy Virtual Port Path, Open Log. Stop and Quit warn while Artisan is attached.
- Optional "Start the bridge when the app opens" and "Open the app at login", both off by default.
- Alerts when the Bluetooth port fails or Artisan vanishes mid-session; help for a silent first
  connection and for going back to direct Bluetooth.
- Build script for a self-contained app in a drag-to-Applications disk image (Python 3.14, pyserial 3.5, PyObjC inside).
- The bridge engine is the prototype's, with additions for the status display only.
  The virtual port keeps its path, `~/.kaleido-bridge/cu.Roaster_bridge`.
- On hardware (one M2 Lite, idle, heater off): real readings forwarded, a clean detach, and the
  same physical port kept open for the next attach (OFF → ON). See docs/EVIDENCE.md.

## 0.1.0 — 2026-11-13

Command line prototype. On one MacBook Pro (M1 Pro, macOS 27.2) with one Kaleido M2 Lite and
Artisan 5.0.0, roaster idle and heater off: readings after OFF → ON and after quit → relaunch → ON
with one open of the port.
