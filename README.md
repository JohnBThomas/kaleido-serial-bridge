# Kaleido Serial Bridge

Kaleido Serial Bridge is an independent macOS menu bar utility designed to keep a Kaleido
roaster's Bluetooth serial port open while Artisan disconnects and reconnects through a virtual
serial port. It was developed to investigate a reconnect issue observed on one M2 Lite setup. It
is unaffiliated with Kaleido and Artisan.

```
Artisan  <-->  virtual port (~/.kaleido-bridge/cu.Roaster_bridge)  <-->  this app  <-->  roaster's Bluetooth port
               opened and closed by Artisan as often as it likes        opened once, kept open
```

## Read this first

- **It is an experiment, tested on one setup, with the roaster idle and the heater off.** See
  [Evidence](#evidence) for exactly what was and was not tested.
- **It does not fix macOS Bluetooth and does not prevent disconnects.** It avoids closing and
  reopening the roaster's serial port, which is where the issue showed on the tested setup.
- **It is not a safety device and does not make the roaster safer.** What the roaster does if
  Artisan crashes or the Bluetooth link is lost while it is heating has not been verified, with or
  without the bridge.
- **It is not suitable for unattended operation.** Stay with the roaster while it is hot.
- **There is no binary download.** The app can be built from source (see [Build](#build)). A
  public binary will only be released once Developer ID signing and notarization have been verified.

## Background

On the tested setup (Apple silicon MacBook Pro, macOS 27.2, Artisan 5.0.0, Kaleido M2 Lite over
Bluetooth), Artisan showed temperatures on the first ON after a restart, and none after
**OFF → ON** or **quit → relaunch → ON**, until Bluetooth was reset. Others report the same in
[artisan#1705](https://github.com/artisan-roaster-scope/artisan/issues/1705).

In the logs captured on that setup, Artisan closed the roaster's serial port in order, macOS
closed the Bluetooth connection, and on the next open of the port macOS's Bluetooth service
logged no new connection attempt: the port opened, Artisan's pings were accepted, and nothing came
back. The bridge is built on that observation: it opens the port once and does not close it, so
there is no second open.

## Evidence

Hardware results and simulator results are kept apart. Details, with timelines:
[docs/EVIDENCE.md](docs/EVIDENCE.md).

**On hardware** — one Kaleido M2 Lite, one Apple silicon MacBook Pro, macOS 27.2, Artisan 5.0.0,
roaster idle, heater off:

- The **Terminal prototype** (version 0.1.0 of the bridge) passed **OFF → ON** and
  **⌘Q → relaunch → ON**: temperatures returned both times, with one open of the physical port.
  The successful run started after a Mac restart.
- The **packaged menu bar app** (0.2.0, a local ad hoc signed build) forwarded real temperature
  data, handled a clean Artisan detach, and kept the same physical serial port open for the next
  attach. The sequence the logs establish for the app is **OFF → ON**. ⌘Q → relaunch → ON has not
  been run with the packaged app.

**With a simulated roaster** — no hardware involved: 72 automated tests of the bridge, the status
logic and the app's menu, setup guide and alerts; a check that runs the packaged app by itself;
and a run of unmodified Artisan 5.0.0 source through the prototype bridge.

**Not verified:**

- other Kaleido models, other Macs and other macOS versions
- opening the app at login
- behavior during an Artisan crash or a loss of the Bluetooth link **while the roaster is heating**
- the Bluetooth link staying up for hours with no Artisan attached
- a signed and notarized build

## Requirements

- A Mac with Apple silicon, macOS 13 or later (tested on macOS 27.2 only)
- A Kaleido roaster paired over Bluetooth and used with Artisan's **Kaleido → Serial** setup
- To build: Python 3.11 or later (3.14 was used)

## Build

```
git clone https://github.com/JohnBThomas/kaleido-serial-bridge.git
cd kaleido-serial-bridge
python3 -m venv ~/.venvs/kaleido-serial-bridge
source ~/.venvs/kaleido-serial-bridge/bin/activate
pip install -e ".[dev]"

python -m pytest          # the checks, against a simulated roaster
packaging/build.sh        # builds the app and a disk image into dist/
```

Keep the virtual environment outside folders synced by iCloud Drive.

The result, `dist/KaleidoSerialBridge-<version>-arm64.dmg`, contains a self-contained app (its own
Python, pyserial and PyObjC). It is signed ad hoc: it opens normally on the Mac that built it. On
another Mac, macOS refuses it until you allow it in **System Settings » Privacy & Security »
Open Anyway**. Signing and notarizing for distribution is described in
[docs/DISTRIBUTION.md](docs/DISTRIBUTION.md); those steps have not been run yet.

To install your build: open the disk image, drag **Kaleido Serial Bridge** onto **Applications**
and open it from there. It has no Dock icon and no window of its own; look for its symbol in the
menu bar.

To run from source without building: `python -m kaleido_serial_bridge` (the app) or
`python -m kaleido_serial_bridge.cli /dev/cu.Roaster_SRSv6` (the bridge alone, in a terminal).

## Setup

The first time the app opens, a setup guide leads through five steps. It can be reopened from the
menu (**Setup Guide…**).

1. **Pair the roaster.** Switch it on and connect to it once in Bluetooth settings. If Artisan
   already reads the roaster over Bluetooth, it is paired.
2. **Choose the roaster's serial port.** Ports whose name looks like a Kaleido, such as
   `Roaster_SRSv6`, are listed first. You pick the exact port; the choice is remembered.
3. **Start the bridge.** Click OFF in Artisan first. After Start, "Waiting for Bluetooth" was
   normal for about 13 seconds on the tested Mac.
4. **Point Artisan at the virtual port.** In Artisan open **Config » Port… » ET/BT » Comm Port**,
   paste the path the guide shows (there is a Copy button) and click OK. Leave the rest of the
   Kaleido serial setup as it is (57600, 8, N, 1). Then click ON.
5. **Keep two settings files**, to switch between the bridge and the direct connection:
   - with the Comm Port set to the virtual port: **Help » Save Settings…** → `artisan-bridge.aset`
   - set the Comm Port back to the roaster's own port: **Help » Save Settings…** → `artisan-direct.aset`
   - **Help » Load Settings…** switches between the two from then on.

### The menu bar symbol

| Shows | Means |
|---|---|
| Bridge stopped | The roaster's Bluetooth port is not open. |
| Waiting for Bluetooth | The port is open, but macOS has not reported the roaster as connected. |
| Waiting for Artisan | The port is open and nobody is using the virtual port. In Artisan, click ON. |
| Artisan attached, waiting for the first reply | Artisan has opened the virtual port; nothing has come back yet. |
| Receiving roaster replies | Replies of the roaster are being passed on to Artisan right now. |
| No replies from the roaster | Artisan is asking and the roaster does not answer. |
| Stopped after a failure | The Bluetooth port failed, or Artisan vanished mid-session. An alert says which. |

An open port is never shown as communication. Only replies that were actually passed on to
Artisan count.

The menu has **Start Bridge**, **Stop Bridge…**, **Copy Virtual Port Path**, **Open Log**,
**Settings…**, **Setup Guide…**, help, About and Quit. Stop and Quit ask first. If Artisan is
attached, the answer defaults to Cancel: stopping then takes the port away from Artisan before it
can tell the roaster that it is leaving. Click OFF in Artisan first.

### Settings

- **Roaster's serial port** — can be changed while the bridge is stopped.
- **Start the bridge when the app opens** — off by default. Starting opens the Bluetooth port, and
  that should happen when you intend it.
- **Open the app at login** — off by default, and not yet tested. It uses the login item service
  of macOS; the app then appears in **System Settings » General » Login Items**.

### Using it

On the tested setup the sequence that worked was: restart the Mac, start the bridge once, wait for
"Waiting for Artisan", then use Artisan as usual. Stopping the bridge closes the roaster's port;
on that setup the next open of the port then got no replies until Bluetooth was reset.

## Manual recovery: no readings

The menu shows "Waiting for Bluetooth" for more than a minute, or "No replies from the roaster",
and Artisan shows no temperatures.

Most likely macOS did not connect the roaster for this open of its port. On the tested setup that
happened when the port had already been opened and closed since the last restart or Bluetooth
reset, by Artisan or by an earlier start of the bridge. Waiting did not help there, and neither
did clicking ON again.

1. In Artisan, click OFF.
2. Stop the bridge.
3. Reset Bluetooth yourself. On the tested Mac, restarting the Mac worked each time. Turning
   Bluetooth off and on again is quicker but was not enough there; restarting the Bluetooth
   service in Terminal with `sudo pkill -x bluetoothd` and then turning Bluetooth off and on did work.
4. Start the bridge and wait for "Waiting for Artisan".
5. In Artisan, click ON.

The app never resets Bluetooth and never reopens the port on its own.

## Switching back to direct Bluetooth

1. In Artisan, click OFF.
2. Stop the bridge (or quit the app).
3. In Artisan, load `artisan-direct.aset`, or set **Config » Port… » ET/BT » Comm Port** back to
   the roaster's own port, for example `/dev/cu.Roaster_SRSv6`.
4. Click ON. Since the port was just closed, the next open may again get no replies; if so, reset
   Bluetooth as above.

## What it does and does not do

- It passes bytes between Artisan and the roaster unchanged, including Artisan's own safety
  commands (`SC AR` when Artisan connects, `CL AR` when it disconnects). Towards the roaster it
  passes whole command lines only, in order, each at most once.
- It never sends anything of its own to the roaster. It never answers Artisan for the roaster,
  never repeats a command, and never keeps the roaster's safety guard alive when Artisan is gone.
- It opens the roaster's port once per start and never reopens it. It never changes Bluetooth
  settings and never resets Bluetooth.
- One Artisan at a time: a second one gets "Could not exclusively lock port".
- If Artisan **crashes or is force quit while connected**, the bridge closes the roaster's port
  and stops, so that the roaster sees the link drop as it would without the bridge. An alert says
  so. This has been tested with the simulator only.
- If the **Bluetooth port reports an error**, the bridge stops, takes the virtual port away so
  that Artisan reports the disconnect, and shows an alert. This has been tested with the simulator
  only; how a real lost link shows up on the port is not known.

What the roaster gets to see in each case, and what is unknown: [docs/SAFETY.md](docs/SAFETY.md).

## Uninstall

1. If you had turned on **Open the app at login**, turn it off in Settings.
2. Quit the app from its menu.
3. Move **Kaleido Serial Bridge** from Applications to the Trash.
4. Delete the folder `.kaleido-bridge` in your home folder (Finder: **Go » Go to Folder…** and
   enter `~/.kaleido-bridge`). It holds the settings, the log and the virtual port.
5. In Artisan, set the Comm Port back to the roaster's own port.

Nothing else is installed.

## Files it uses

| | |
|---|---|
| `~/.kaleido-bridge/cu.Roaster_bridge` | the virtual port (exists while the bridge runs) |
| `~/.kaleido-bridge/settings.json` | the chosen port and the two options |
| `~/.kaleido-bridge/bridge.log` | the log (**Open Log**); kept below 4 MB |
| `~/.kaleido-bridge/status.json` | the current status in machine readable form (exists while the app runs) |

`KALEIDO_BRIDGE_HOME=/some/folder` makes the app use another folder.

## For developers

```
python -m pytest                              # 72 tests against a simulated roaster, about 30 s
ruff check . && mypy && codespell
packaging/build.sh
python tests/packaged_app_check.py "$TMPDIR/kaleido-serial-bridge-build/dist/Kaleido Serial Bridge.app"
```

| | |
|---|---|
| `src/kaleido_serial_bridge/engine.py` | the bridge itself |
| `src/kaleido_serial_bridge/controller.py` | runs the engine for the app and derives the status |
| `src/kaleido_serial_bridge/app.py`, `ui.py`, `menu.py`, `guide.py` | menu bar item, windows, texts |
| `src/kaleido_serial_bridge/cli.py` | command line entry |
| `tools/sim_roaster.py` | a simulated roaster on a pseudo terminal |
| `tools/make_bridge_aset.py` | copies an Artisan `.aset`, changing only the Comm Port |
| `tests/` | engine, controller and app tests; the check of the packaged app; an end-to-end run with Artisan itself |
| `packaging/` | PyInstaller spec, icon, build and notarization scripts |

## License and attribution

[MIT](LICENSE). The code in this repository was written for this project; it contains no code from
Artisan or from Kaleido. Components that end up inside a built app are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

"Kaleido" and "Artisan" are names of their respective owners and are used here only to say what
the utility works with.
