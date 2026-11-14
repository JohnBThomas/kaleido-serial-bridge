# Changelog

## Unreleased

- Guided Bluetooth recovery: a **Reset Bluetooth & Restart Bridge** button in the Help window (the
  connection-loss alert's Help button opens it). After a confirmation that the roaster is switched
  on, idle and its heater off, one click makes one attempt: restart the Bluetooth service (with
  macOS's standard authorization dialog), turn Bluetooth off and on, wait for the roaster's serial
  port, start the bridge once, and wait for real replies after the user clicks ON in Artisan.
  Every wait has a limit; a cancelled authorization or a failed step stops the attempt, names the
  step and shows the manual steps. The confirmation is a sheet on the Help window, and all status
  ("Click ON in Artisan", with "If Artisan is still monitoring, click OFF, then ON. Otherwise,
  click ON.", then "Readings are back", or failures) is shown in that window; closing it leaves an
  attempt running. The recovery never activates the app or opens an alert after the
  confirmation. The menu item for the Help window is now "Troubleshooting…".
  After the restart of the Bluetooth service it waits until Bluetooth reports on before asking to
  turn it off, and repeats a power request without effect every 2 s within the step's limit (on
  hardware a request sent too early was rejected and two attempts failed). Every step, retry and
  outcome goes to bridge.log. It refuses to run while the bridge is running; the stop after a
  connection loss is unchanged. The power switch uses an undocumented IOBluetooth function.
  The simulator tests and the packaged checks passed (test build app CDHash
  `1640c79eab7c23259790e6a65d27cfbdd95110de`). On hardware, with the notarized test build of
  commit `50e0101` (app CDHash `5bdc6388ab1cfbe23a2dff12c673cc092f86685e`, hardened runtime): one
  guided recovery after a loss of power on the M2 Lite, idle, heater off, worked; the logs confirm
  the service restart, the power cycle, one open of the roaster's port and replies. An earlier
  notarized build (`3195ebea…`) failed twice at the power switch, which led to the readiness fix.
  With that build the tester saw and used Touch ID successfully in the administrator prompt. The
  macOS log corroborates that the prompt was eligible for Touch ID and that the authorization
  succeeded; it does not identify which credential completed it. On this Mac, the earlier ad hoc
  test build (`1640c79e…`) got a password-only prompt, and macOS logged "biometry prohibited" for
  it. The completion update left the tester in Artisan's Space, but the alert's Help button
  switched to the Space where the Help window was.
- The alert for a session that ends without `CL AR` now reads "Connection lost during an active
  session. The bridge stopped." instead of "Artisan vanished mid-session". The bridge sees only
  that Artisan's virtual port closed during a session; it cannot tell a crash from Artisan giving
  up after 5 seconds without a reply. The alert now adds whether the roaster had stopped answering
  before the port closed. What the bridge does in that case is unchanged: it closes the roaster's
  port and stops. Tested with the simulator, and on hardware once, from source: commit `f1825c9`
  run with `python -m kaleido_serial_bridge`, in an idle power-loss test on one M2 Lite with the
  heater off. The tester saw the new alert with "5.0 s" and three unanswered commands, and the
  logs confirm the stop and its reason. **No packaged or signed build of this change exists yet;
  verification of one is pending.**
- Recovery help: after the roaster has been switched on again, starting the bridge alone may not
  reconnect. In both observed idle power-loss tests on one M2 Lite, a start of the bridge alone got
  no replies, and a manual Bluetooth reset (restart of the Bluetooth service, then Bluetooth off and
  on) followed by a new start of the bridge restored readings. Two tests on one roaster are not a
  guarantee. The app does not reset Bluetooth or reconnect by itself.
- docs/EVIDENCE.md records two idle power-loss tests: the first with the signed 0.2.0 build, which
  showed the old wording, and a repeat from source at commit `f1825c9`, which showed the new one.
  In both, a start of the bridge without a Bluetooth reset got no replies, and a start after the
  manual reset connected.

## 0.2.0 — 2026-11-13

First version as a macOS menu bar app. Offered as a download: a disk image for Apple silicon,
signed with a Developer ID and notarized by Apple.

- The signed disk image (app CDHash `a9a59f259cc3528af70e43abbed537cb544186b0`): Gatekeeper
  accepted the notarized disk image and a quarantined copy of the app on the build Mac, and the
  ticket is stapled to the disk image. On one M2 Lite, idle, heater off: the app opened at login, the
  bridge started by itself, live readings arrived, and they returned after OFF → ON and after
  ⌘Q → relaunch → ON, each seen by the tester and confirmed by the logs.
  Not tested: installation on a second Mac (not planned; the author has one) and a first launch
  without a network connection. The
  hardware results further down belong to earlier ad hoc builds.
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
