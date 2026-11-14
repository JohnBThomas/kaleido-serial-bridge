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

## Direct Artisan reconnect test

One captured run, without the bridge: Artisan connected to the roaster's own port,
`/dev/cu.Roaster_SRSv6`. Artisan was 5.0.0 run from source with connection diagnostics added
(logging only), as one process. Roaster idle, heater off. This is the observation the bridge is
built on.

| Time | Source | Event |
|---|---|---|
| 16:18:58, 16:19:05 | Artisan log | two attempts at the start of the run: the port opens, the pings go unanswered. What preceded them was not captured |
| 16:19:16 | macOS log | the Bluetooth service (`bluetoothd`) restarts; the roaster's port disappears and is created again at 16:19:28.1 |
| 16:19:28.2 | Artisan log, macOS log | Artisan opens the port, the first open after it reappeared. `bluetoothd` logs an RFCOMM connection attempt in the same second |
| 16:19:29.5 | macOS log | the RFCOMM connection is reported successful |
| 16:19:30.5 | Artisan log | handshake complete; readings follow |
| 16:20:10 | Artisan log, macOS log | **OFF**: Artisan sends `CL AR`, which the roaster answers, and closes the port. `bluetoothd` logs the RFCOMM disconnect and the link going down |
| 16:20:52.1 | Artisan log | **ON**, 41.6 s after the port was closed: the port opens in 2 ms, three pings time out, and the attempt fails at 16:20:58.1 |
| 16:20:58.9 | Artisan log | Artisan tries again by itself, with the same outcome, ending at 16:21:05.0 |
| 16:20:11 – 16:21:35 | macOS log | of the 1,193 lines `bluetoothd` logged from the close until Artisan exited, none is in its serial port category and none mentions RFCOMM |

**Result: the initial open of the serial port was followed by a successful RFCOMM connection. OFF
closed the port, and macOS logged the Bluetooth disconnect. Artisan then reopened the port, and its
pings timed out. No new RFCOMM attempt appeared in the macOS log during that failed reopen.**

This is one captured run on one Mac with one roaster. It shows what the logs contain. It does not
show why macOS made no attempt, and it says nothing about how often this happens. The log excerpts
behind the table are kept outside this repository.

## Hardware result 1: the Terminal prototype

Bridge: the command line prototype, version 0.1.0 (Python 3.14.6, pyserial 3.5), started from
Terminal. The successful run started after a Mac restart at 17:20.

| Time | Event |
|---|---|
| 17:22:21.3 | bridge opens `/dev/cu.Roaster_SRSv6` |
| 17:22:21.4 | macOS reports the roaster as not connected |
| 17:22:34.2 | macOS reports the roaster as connected (12.9 s after the open) |
| 17:22:43 – 17:23:22 | Artisan session 1: readings; 30 commands; ended with `CL AR` |
| 17:23:55 – 17:25:46 | session 2: readings; 77 commands; ended with `CL AR` |
| 17:26:30 – 17:30:00 | session 3: readings; 144 commands; ended with `CL AR` |

Sessions 2 and 3 are the reconnects after **OFF → ON** and after **⌘Q → relaunch → ON**. The
bridge log does not tell the two apart, because Artisan ends both with `CL AR`. Artisan's own log
does: it shows OFF at 17:23:21 and ON at 17:23:55 within one run of Artisan, then `MODE: QUIT` at
17:25:45 while monitoring was on, a new start of Artisan at 17:26:21, and ON at 17:26:30. The
bridge log shows a single "real port … opened" line for the whole run.

**Result: temperatures returned after OFF → ON and after ⌘Q → relaunch → ON, with one open of the
physical port and no Bluetooth reset in between.**

### Starts that stayed silent

Four earlier starts of the prototype on the same day got no replies. The last column is what the
macOS log shows between the previous close of the roaster's port and the start in that row.

| Bridge started | Bridge stopped | Artisan sessions | Bytes from the roaster | Bluetooth reset before this start, per the macOS log |
|---|---|---|---|---|
| 17:03:25 | 17:09:07 | 3 | 0 | the Bluetooth service (`bluetoothd`) restarted at 17:02:24; macOS created the port again at 17:02:36 |
| 17:09:56 | 17:13:23 | 8 | 0 | `bluetoothd` restarted at 17:09:18; port created again at 17:09:30 |
| 17:14:56 | 17:19:10 | 13 | 0 | none: no restart of `bluetoothd` and no switching of Bluetooth between 17:13:23 and 17:14:56 |
| 17:19:35 | 17:20:02 | 2 | 0 | Bluetooth switched off at 17:19:17 and on at 17:19:20; port created again at 17:19:30 |

In each of them the port opened, the bridge's check found macOS reporting the roaster as not
connected and logged no change afterwards, and every ping from Artisan went unanswered (Artisan
retried about every 7 seconds). No RFCOMM attempt appeared in the macOS log at any of the four
opens.

During the third start, at 17:15:43, the macOS log shows a Bluetooth connection being made to the
roaster and the serial port profile attempting to connect. No RFCOMM connection was reported for
the port, and the sessions stayed without replies. The log does not show what started that attempt.

What the logs establish, and what they do not:

- Three of the four silent starts were the first open of the port recorded after a reset of
  Bluetooth: a restart of the service twice, Bluetooth switched off and on once. In these runs a
  reset of Bluetooth was not followed by a connection.
- For the third start no reset is logged since the previous close of the port, 93 seconds earlier.
  The time between two starts says nothing by itself; it is the macOS log that shows no reset in
  that interval.
- The logs show that the service restarted and that Bluetooth was switched. They do not show who
  or what caused it.
- The start that got replies, at 17:22:21, was the first open after a restart of the Mac at 17:20.
- Why macOS made no RFCOMM attempt for these opens is not established by any of the logs.

So the bridge does not make a connection where macOS does not provide one. It depends on its one
open of the port being one that macOS connects.

## Hardware result 2: the packaged menu bar app

App: Kaleido Serial Bridge 0.2.0, a local build signed ad hoc, installed in `/Applications`. Same
Mac, same roaster, idle, heater off. The run started after a Mac restart at 18:10.

**The build that was tested** was made on 2026-11-13 at 17:58:42. Its code directory hash, as
printed by `codesign -dvvv`, is `bab9676fa030389d71bddd6b3565767a7014e9d3`. Everything in this
section is about that build and no other. The signature of the running process was read at 19:52
and carries the same hash.

This source is not that build. Texts were edited afterwards: the docstrings of `engine.py` and
`cli.py`, and texts in `guide.py`, among them the recovery advice. The current local test build of
this source was made at 19:55 and has the hash `7630086f5c8316900d0bbec2ef9a310eb11cfe2b`. Its
hardware results are a section of their own, below. Both report version 0.2.0; only the hash tells
them apart. A comparison of the compiled Python modules inside the two apps found no difference
other than those texts.

An earlier start of the tested build, at 18:07:15, is not part of the result, and it did not lead
to a connection. The Mac had been restarted at 18:02 (that restart closed the prototype's port at
18:01:45), and macOS created the roaster's port again at 18:02:38. The app's start is the first
open of the port recorded after that restart. No RFCOMM attempt appeared in the macOS log for it.
Artisan was not running, so there is no record of replies either way, and the app's own log does
not record the state of the Bluetooth link. The bridge stopped at 18:09:42, seconds before the Mac
shut down for the restart at 18:10. So of the two starts of this build that directly followed a
restart of the Mac, one connected and one did not. The logs do not establish why.

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
| 18:21:55 – 19:45:55 | app log | session 2 lasts 5,040 s (84 minutes): 3,385 commands delivered to the roaster, 198,363 bytes of replies passed on to Artisan |
| 19:45:55 | Artisan log, app log | **OFF**. Session 2 detaches, "clean (Artisan ended its session with CL AR)"; "real port stays open" |
| 19:46:00 | Artisan log, app log | **ON**, 5 seconds later. Session 3 attaches: "real port open for 5463 s, opened once, never reopened" |
| 19:46:00 onward | macOS Bluetooth log, app status | replies arrive again: 606 bytes from the roaster in the first 15 seconds, after 587 bytes in the last 15 seconds before OFF and none in between. The app shows "Receiving roaster replies" |

| 19:46:00 – 20:03:59 | Artisan log, app log | session 3 lasts 1,079 s: 724 commands delivered to the roaster, 41,097 bytes of replies passed on to Artisan. It ends with **OFF**, "clean (Artisan ended its session with CL AR)" |
| 20:04:31 | app log, macOS Bluetooth log | the tester stops the bridge: "real port … closed after 6574 s. It was opened once and never reopened." macOS logs the RFCOMM disconnect in the same second |

Between 18:15 and 20:04:31, macOS's Bluetooth log shows no connect or disconnect of the serial
port, and one Bluetooth service process throughout. The app log has a single "real port … opened"
line for the whole run of 110 minutes.

**Result: the packaged app forwarded real temperature data, handled a clean Artisan detach, and
kept the same physical serial port open for the next attach. It did so twice: after a session of
70 seconds and after a session of 84 minutes.**

**Which reconnect sequence this was: OFF → ON, both times.** Artisan's log shows one start of
Artisan in this period, then ON, OFF, ON, OFF, ON, and no quit.

**Not run with this build:** ⌘Q → relaunch → ON, the app opening at login ("Open the app at
login"), and the bridge starting by itself when the app opens ("Start the bridge when the app
opens"). They were run with the newer build; see the next section. Its failure alerts were not
exercised on hardware.

## Hardware result 3: the current local test build

App: Kaleido Serial Bridge 0.2.0, the local ad hoc signed test build of this source. Its code
directory hash is `7630086f5c8316900d0bbec2ef9a310eb11cfe2b`. It was installed in `/Applications`
at 20:05:01 from the disk image with the SHA-256
`a6d6ac54f6bfdc25508faefdc64967c56827bada2bde00235dda37e7638970f3`. The signature of the running
process was read at 20:14 and carries that hash. Everything in this section is about that build
and no other. Same Mac, same roaster, idle, heater off; Artisan 5.0.0, the installed app, Comm Port
set to the virtual port. The run followed a Mac restart at 20:09.

Two kinds of statement are kept apart in this section: what the tester saw and reported, and what
the logs show independently of that.

| Time | Source | Event |
|---|---|---|
| 20:06:21 | macOS log | "Open the app at login" is switched on in the app's settings; macOS announces that the app "will open automatically" at login |
| 20:09:00 | macOS records | the Mac restarts. macOS creates the roaster's port again at 20:09:33 |
| 20:10:07.5 | macOS log | the login window launches `/Applications/Kaleido Serial Bridge.app` from its list of login items. No start of the bridge follows |
| 20:11:15.364 | macOS log | a menu command is performed in the app |
| 20:11:15.377 | app log | the bridge starts: "starting on /dev/cu.Roaster_SRSv6". The port is opened at 20:11:15.390 |
| 20:11:15.389 – 20:11:18.053 | macOS Bluetooth log | RFCOMM connection attempt for that open, reported successful 2.7 s later |
| 20:11:35 | settings file | `settings.json`, with "Start the bridge when the app opens" on, is written for the last time |
| 20:12:19 | Artisan log, app log | **ON**. Session 1 attaches: "real port open for 64 s, opened once, never reopened" |
| 20:12:48 | Artisan log, app log | **OFF**. Session 1 detaches, clean, after 29.1 s: 24 commands delivered to the roaster, 1,153 bytes of replies passed on to Artisan |
| 20:12:51 | Artisan log, app log | **ON**, 3 seconds later. Session 2 attaches: "real port open for 96 s, opened once, never reopened" |
| 20:12:56 | Artisan log, app log | **⌘Q**: `MODE: QUIT` while monitoring is on. Session 2 detaches, "clean (Artisan ended its session with CL AR)", after 5.1 s: 8 commands, 285 bytes of replies; "real port stays open" |
| 20:13:03 | Artisan log | Artisan starts again, serial port = the virtual port |
| 20:13:06 | Artisan log, app log | **ON**. Session 3 attaches: "real port open for 111 s, opened once, never reopened" |
| 20:13:06 onward | macOS Bluetooth log, app status | replies arrive again: 562 bytes from the roaster in the first 15 seconds, and none between the quit and this ON. The app shows "Receiving roaster replies" |

| Check | Reported by the tester | Confirmed by the logs |
|---|---|---|
| First connection after a start | Artisan showed live ET and BT | **Yes.** One RFCOMM connection for the open at 20:11:15; 1,153 bytes of replies in session 1 |
| OFF → ON | readings returned | **Yes.** OFF and ON in Artisan's log, 3 s apart; session 2 on the same open port, with 285 bytes of replies |
| ⌘Q → relaunch → ON | readings returned | **Yes.** `MODE: QUIT`, a new start of Artisan and ON in Artisan's log; session 3 on the same open port, with replies in the macOS log |
| The physical port across both reconnects | not something the tester can see | **Yes.** The app log has one "real port … opened" line, at 20:11:15.390, and "opened once, never reopened" at sessions 2 and 3. The macOS log has one RFCOMM connection and no disconnect up to 20:19 |
| The app opening at login | the app opened at login | **Yes.** Launched by the login window from the login items at 20:10:07.5, 67 s after the restart |
| The bridge starting by itself | the bridge started automatically, with both startup options on | **No.** See below |

**The bridge starting by itself is reported by the tester, and the logs do not confirm it.** For
this run they show another order. The app opened at login at 20:10:07 and no start followed,
although the roaster's port had existed since 20:09:33. The start at 20:11:15.377 came 13 ms after
a menu command in the app, 67 seconds after the app had opened. The settings file that has "Start
the bridge when the app opens" on was written at 20:11:35, after that start, and the app has not
been opened again since. A start by itself would show as a "starting on" line in the app log right
after the app opens, with no menu command in between. There is no such line yet, so this check
stays pending.

**Result, for the build `7630086f…` only: a first connection, OFF → ON and ⌘Q → relaunch → ON all
returned replies through one open of the physical port, and the app opened at login. The tester
observed each of these, and the logs confirm each. The bridge starting by itself was reported by
the tester and is not confirmed by the logs.**

What this run does not show:

- The sessions before the two reconnects were short: 29 seconds and 5 seconds.
- Session 3 was still attached when this was written, at 20:19, so the app log has no totals for
  it yet.
- "Showed ET and BT" is the tester's observation. The logs count commands and bytes, not
  temperatures.
- The login item belongs to this ad hoc signature. A build with another signature needs its own
  run.

An earlier start of this build, at 20:05:35 and before the restart, is not part of the result. It
was made from the menu 64 seconds after the previous build had closed the port (20:04:31), with no
reset of Bluetooth logged in between. No RFCOMM attempt appeared in the macOS log for it, Artisan
did not attach, and the restart ended it at 20:08:39.

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
| `tests/packaged_app_check.py`: the built app started by itself with an empty environment; status from saved settings; replies; clean stop; relaunch | 22 of 22 checks passed on the current local test build (hash `7630086f…`), copied out of its disk image the way a drag to Applications does. 22 of 22 again with Homebrew, `/usr/local`, other Python installations, the Xcode tools and the source tree made unreadable to the app |
| `tests/e2e_artisan.py` with unmodified Artisan 5.0.0 source and the **prototype** bridge: ON, OFF, ON, quit while reading, relaunch, ON | readings every time ON was clicked (three times); the simulated roaster saw its port opened once |

What the simulator cannot show: anything about macOS Bluetooth, the real roaster's firmware, or
timing on a real link.

## Pending

Hardware results exist for two packaged builds, both local and signed ad hoc:

- `bab9676fa030389d71bddd6b3565767a7014e9d3`: **OFF → ON** only.
- `7630086f5c8316900d0bbec2ef9a310eb11cfe2b`, the current local test build of this source: the
  first connection after a start, **OFF → ON**, **⌘Q → relaunch → ON**, and the app opening at
  login.

Still pending:

- The bridge starting by itself when the app opens, on hardware. It was reported for the build
  `7630086f…`, but the logs of that run show a start from the menu. It needs a run in which the app
  opens with the option already on. So far it is confirmed with the simulator only.
- Every hardware check for a build signed with a Developer ID. That would be a third build, and
  its login item belongs to its own signature.

Until these have been run, nothing here says that they work.

## Not verified

- Kaleido models other than the M2 Lite; other Macs; macOS versions other than 27.2
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
4. Wait for "Waiting for Artisan" in the menu. If it stays at "Waiting for Bluetooth" for more than
   a minute, this start is silent: stop the bridge and go back to step 2. On the tested Mac one of
   four starts that directly followed a restart did not lead to a connection.
5. In Artisan (Comm Port = the virtual port), click **ON**. Expect ET and BT, and "Receiving
   roaster replies" in the menu.
6. **OFF → ON:** click OFF, wait 5 seconds, click ON. Expect ET and BT again.
7. **⌘Q → relaunch → ON:** quit Artisan while readings update, open it again, click ON. Expect ET
   and BT again.
8. Click OFF. Open the log from the menu: there should be exactly one "real port … opened" line
   since the start, and each session should end "detached, clean".
