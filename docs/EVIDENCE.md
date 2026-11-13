# Evidence

What has been observed, on what, and how. Hardware results and simulator results are separate
sections. Nothing here says the bridge fixes macOS Bluetooth, prevents disconnects or improves the
safety of a roaster; it records what happened in a small number of runs.

## Test setup (hardware)

| | |
|---|---|
| Date | 2026-11-13 |
| Mac | MacBook Pro (MacBookPro18,1), Apple M1 Pro, 16 GB |
| macOS | 27.2 (build 26B123) |
| Roaster | Kaleido M2 Lite, paired over Bluetooth; serial port `/dev/cu.Roaster_SRSv6`, 57600 8N1 |
| Roaster state | idle, heater off, in every run |
| Artisan | 5.0.0 (build b03f31b6c), the installed app, Kaleido → Serial setup, Comm Port set to the virtual port |

One roaster, one Mac, one day.

## Hardware result 1: the Terminal prototype

Bridge: the command line prototype, version 0.1.0 (Python 3.14.6, pyserial 3.5), started from
Terminal. The successful run started after a Mac restart.

| Time | Event |
|---|---|
| 17:22:21.3 | bridge opens `/dev/cu.Roaster_SRSv6` |
| 17:22:21.4 | macOS reports the roaster as not connected |
| 17:22:34.2 | macOS reports the roaster as connected (12.9 s after the open) |
| 17:22:43 – 17:23:22 | Artisan session 1: readings; 30 commands; ended with `CL AR` |
| 17:23:55 – 17:25:46 | session 2: readings; 77 commands; ended with `CL AR` |
| 17:26:30 – 17:30:00 | session 3: readings; 144 commands; ended with `CL AR` |

Sessions 2 and 3 are the reconnects after **OFF → ON** and after **⌘Q → relaunch → ON**, as
reported by the tester. The bridge log does not tell the two apart, because Artisan ends both with
`CL AR`. The log shows a single "real port … opened" line for the whole run.

**Result: temperatures returned after OFF → ON and after ⌘Q → relaunch → ON, with one open of the
physical port and no Bluetooth reset in between.**

### Starts that stayed silent

Two earlier starts of the prototype on the same day got no replies: the port opened, macOS
reported the roaster as not connected and never changed that, and every ping from Artisan went
unanswered (Artisan retried about every 7 seconds). The likely reason is that the roaster's port
had already been opened and closed since the last restart or Bluetooth reset; for the second
silent start that is certain, as it followed the stop of the first by 25 seconds.

So the bridge does not make a connection where macOS does not provide one. It depends on its one
open of the port being one that macOS connects.

## Hardware result 2: the packaged menu bar app

App: Kaleido Serial Bridge 0.2.0, a local build signed ad hoc, installed in `/Applications`. Same
Mac, same roaster, idle, heater off. The run started after a Mac restart.

| Time | Source | Event |
|---|---|---|
| 18:14:57.6 | app log | app opens `/dev/cu.Roaster_SRSv6` |
| 18:14:58.0 | macOS Bluetooth log | serial port profile reports its connection to the roaster as successful |
| 18:15:42 | Artisan log | Artisan 5.0.0 starts, serial port = the virtual port |
| 18:17:33 | Artisan log, app log | **ON**. Session 1 attaches; the port has been open for 156 s |
| 18:17:33 – 18:18:43 | app log | 50 commands delivered to the roaster, 2,679 bytes of replies passed on to Artisan |
| 18:18:42 | Artisan log | **OFF** |
| 18:18:43 | app log | session 1 detaches, "clean (Artisan ended its session with CL AR)"; "real port stays open" |
| 18:21:55 | Artisan log, app log | **ON**. Session 2 attaches: "real port open for 418 s, opened once, never reopened" |
| 18:21:55 onward | app status | "Receiving roaster replies", unchanged for at least 19 minutes |

Between 18:15:40 and 18:41, macOS's Bluetooth log shows no further connect or disconnect of the
serial port.

**Result: the packaged app forwarded real temperature data, handled a clean Artisan detach, and
kept the same physical serial port open for the next attach.**

**Which reconnect sequence this was: OFF → ON.** Artisan's log shows one start of Artisan in this
period, then ON, OFF, ON, and no quit.

**Not run with the packaged app: ⌘Q → relaunch → ON.** Also not exercised on hardware with the
app: its Stop and Quit warnings, its failure alerts, starting the bridge automatically, and
opening at login.

## Simulator results

No roaster and no Bluetooth are involved in anything in this section. The "roaster" is
`tools/sim_roaster.py` on a pseudo terminal; it answers like a Kaleido and records what it is sent
and whether a port is open on it.

| Check | Result |
|---|---|
| `tests/test_engine.py`: forwarding, stale data, normal disconnect, abrupt client exit, bridge exit, upstream loss, silent upstream, second client | 28 passed, 1 skipped (it needs Artisan's source) |
| `tests/test_controller.py`: first run, saved settings, status accuracy, clean stop, failures | 28 passed |
| `tests/test_app.py`: setup guide, menu, stop warnings, failure alerts, driven in-process without clicks | 15 passed |
| The skipped engine test, run with Artisan's source: Artisan's own Kaleido code through the bridge, OFF → ON | passed |
| `tests/packaged_app_check.py`: the built app started by itself with an empty environment; status from saved settings; replies; clean stop; relaunch | 22 of 22 checks passed |
| `tests/e2e_artisan.py` with unmodified Artisan 5.0.0 source and the **prototype** bridge: ON, OFF, ON, quit while reading, relaunch, ON | readings every time ON was clicked (three times); the simulated roaster saw its port opened once |

What the simulator cannot show: anything about macOS Bluetooth, the real roaster's firmware, or
timing on a real link.

## Not verified

- Kaleido models other than the M2 Lite; other Macs; macOS versions other than 27.2
- ⌘Q → relaunch → ON with the packaged app
- opening the app at login, and starting the bridge automatically, on hardware
- **behavior during an Artisan crash or a loss of the Bluetooth link while the roaster is
  heating**, with or without the bridge. All hardware runs were idle with the heater off.
- how a lost Bluetooth link shows up on a port the bridge holds open (as an error, or as silence)
- the link staying up for hours with no Artisan attached
- a build signed with a Developer ID and notarized

## Repeating the hardware test

Roaster idle, heater off.

1. Stop any running bridge (click OFF in Artisan first).
2. Restart the Mac, or reset Bluetooth the way that works on your Mac.
3. Open the app and click **Start Bridge** (the first time, through the setup guide).
4. Wait for "Waiting for Artisan" in the menu.
5. In Artisan (Comm Port = the virtual port), click **ON**. Expect ET and BT, and "Receiving
   roaster replies" in the menu.
6. **OFF → ON:** click OFF, wait 5 seconds, click ON. Expect ET and BT again.
7. **⌘Q → relaunch → ON:** quit Artisan while readings update, open it again, click ON. Expect ET
   and BT again.
8. Click OFF. Open the log from the menu: there should be exactly one "real port … opened" line
   since the start, and each session should end "detached, clean".
