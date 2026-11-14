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
`cli.py`, and texts in `guide.py`, among them the recovery advice. A later ad hoc test build of
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

## Hardware result 3: the later ad hoc test build

App: Kaleido Serial Bridge 0.2.0, the later local ad hoc signed test build of this source. Its code
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
| 20:13:06 – 20:41:36 | Artisan log, app log | session 3 lasts 1,710 s (28.5 minutes): 1,145 commands delivered to the roaster, 65,003 bytes of replies passed on to Artisan. It ends with **OFF**, "clean (Artisan ended its session with CL AR)"; "real port stays open" |
| 20:48:06 | macOS Bluetooth log | the Bluetooth connection to the roaster ends, 6.5 minutes after the last traffic and with no Artisan attached. No switching of Bluetooth and no restart of the Bluetooth service is logged |
| 20:48:29 | app status, app log | the app shows "Waiting for Bluetooth": "macOS reports the roaster as no longer connected". The bridge still holds the port open; its log has no error and no new line |

The bridge starting by itself and the Bluetooth connection are separate results. The first is
about the app: does it open the physical port without a command? The second is about macOS: does
it connect the roaster for that open?

| Check | Reported by the tester | Confirmed by the logs |
|---|---|---|
| The bridge starting by itself: the app opens the physical port without a command | the bridge started automatically, with both startup options on | **No.** The only open on record, at 20:11:15.390, came 26 ms after a menu command. See below |
| Bluetooth connection for the bridge's open of the port | not something the tester can see directly | **Yes.** macOS logged an RFCOMM connection attempt at 20:11:15.389, in the same hundredth of a second as the open, and reported it successful at 20:11:18.053. It is the only RFCOMM connection of the run, and it lasted until 20:48:06 |
| First readings in Artisan | Artisan showed live ET and BT | **Yes.** 1,153 bytes of replies in session 1 |
| OFF → ON | readings returned | **Yes.** OFF and ON in Artisan's log, 3 s apart; session 2 on the same open port, with 285 bytes of replies |
| ⌘Q → relaunch → ON | readings returned | **Yes.** `MODE: QUIT`, a new start of Artisan and ON in Artisan's log; session 3 on the same open port, with replies in the macOS log |
| The physical port across both reconnects | not something the tester can see | **Yes.** The app log has one "real port … opened" line, at 20:11:15.390, and "opened once, never reopened" at sessions 2 and 3. The macOS log has one RFCOMM connection, with no disconnect until 20:48:06, after all three sessions |
| The app opening at login | the app opened at login | **Yes.** Launched by the login window from the login items at 20:10:07.5, 67 s after the restart |

**The bridge starting by itself is reported by the tester, and the logs do not confirm it.** For
this run they show another order. The app opened at login at 20:10:07 and no start followed,
although the roaster's port had existed since 20:09:33. The start at 20:11:15.377 came 13 ms after
a menu command in the app, 67 seconds after the app had opened. The settings file that has "Start
the bridge when the app opens" on was written at 20:11:35, after that start, and the app has not
been opened again since. A start by itself would show as a "starting on" line in the app log right
after the app opens, with no menu command in between. There is no such line yet, so this check
stays pending.

Checked again at 21:48: nothing has changed. The Mac's boot time is still 20:09:00, no later login
and no later launch of the app is on record, and the app's process is the one the login window
started at 20:10:07. So the app has not yet opened with the option on.

**Results, for the build `7630086f…` only:**

- **The bridge starting by itself: not confirmed.** Reported by the tester; the one start on
  record followed a menu command.
- **Bluetooth connection for the bridge's open of the port: confirmed** by the macOS log. One
  RFCOMM connection, made within 2.7 s of the open, carried all three sessions.
- **First readings, OFF → ON and ⌘Q → relaunch → ON: confirmed.** All returned replies through
  that one open of the physical port. The tester observed each, and the logs confirm each.
- **The app opening at login: confirmed** by the tester and by the macOS log.

What this run does not show:

- The sessions before the two reconnects were short: 29 seconds and 5 seconds.
- Why the Bluetooth connection ended at 20:48:06. The logs show that it ended, not what ended it;
  the roaster being switched off would look the same.
- Anything about a lost link while Artisan is attached. When this one ended, nobody was attached.
- "Showed ET and BT" is the tester's observation. The logs count commands and bytes, not
  temperatures.
- The login item belongs to this ad hoc signature. A build with another signature needs its own
  run.

An earlier start of this build, at 20:05:35 and before the restart, is not part of the result. It
was made from the menu 64 seconds after the previous build had closed the port (20:04:31), with no
reset of Bluetooth logged in between. No RFCOMM attempt appeared in the macOS log for it, Artisan
did not attach, and the restart ended it at 20:08:39.

## The signed build

This is the disk image of the 0.2.0 release, `KaleidoSerialBridge-0.2.0-arm64.dmg`, with the
SHA-256 `8d93e48150a8d98ec0c15e27975da071241e8b90ec7cb5cfc2090cb6302a8b1e`. The app in it has the
code directory hash `a9a59f259cc3528af70e43abbed537cb544186b0`. It is signed with a Developer ID,
with the hardened runtime, and was notarized by Apple. It was made from this source: a comparison
of the compiled Python modules found no difference from the ad hoc build `7630086f…`. Only the
signature differs.

### Checks without a roaster

These checks were made on 2026-11-13 on the Mac that built it, with no roaster involved:

| Check | Result |
|---|---|
| Signature of the disk image, of the app and of every binary in it | valid; Developer ID; hardened runtime |
| Notarization ticket | stapled to the disk image. The app itself carries no stapled ticket |
| Gatekeeper on the notarized disk image | accepted, as "Notarized Developer ID" |
| Gatekeeper on a quarantined copy of the app | accepted, as "Notarized Developer ID" |
| `shasum -a 256 -c SHA256SUMS.txt` | OK |

### Hardware run with the signed build

The disk image was downloaded from the published release with Safari and the app was put into
`/Applications` at 22:02:53 on the build Mac. The installed app and the running process both carry
the hash above. Same Mac (macOS 27.2), same Kaleido M2 Lite, idle, heater off; Artisan 5.0.0, Comm
Port set to the virtual port. Both startup options were on. Everything in this subsection is about
this build and no other. As before, what the tester reported and what the logs show are kept apart.

| Time | Source | Event |
|---|---|---|
| 22:04:38 | macOS records | the Mac restarts. macOS creates the roaster's port again at 22:05:14 |
| 22:05:21 | Artisan log | Artisan starts, serial port = the virtual port |
| 22:05:55 | macOS log | the login window launches `/Applications/Kaleido Serial Bridge.app` from its list of login items |
| 22:05:56.726 | app log | the bridge starts: "starting on /dev/cu.Roaster_SRSv6", 43 ms after the app received its launch event. No menu command is logged in the app before it. The port is opened at 22:05:56.728 |
| 22:05:56.728 – 22:05:57.963 | macOS Bluetooth log | RFCOMM connection attempt for that open, reported successful 1.2 s later |
| 22:06:40 | Artisan log, app log | **ON**. Session 1 attaches: "real port open for 43 s, opened once, never reopened" |
| 22:08:39 | Artisan log, app log | **OFF**. Session 1 detaches, clean, after 119.7 s: 84 commands delivered to the roaster, 4,617 bytes of replies passed on to Artisan |
| 22:08:43 | Artisan log, app log | **ON**, 4 seconds later. Session 2 attaches: "real port open for 167 s, opened once, never reopened" |
| 22:08:53 | Artisan log, app log | **⌘Q**: `MODE: QUIT` while monitoring is on. Session 2 detaches, "clean (Artisan ended its session with CL AR)", after 9.7 s: 11 commands, 456 bytes of replies; "real port stays open" |
| 22:08:53 – 22:20:42 | Artisan log, app log, macOS log | Artisan is not running. The bridge keeps running with the port open; no data passes in either direction, and macOS logs no disconnect |
| 22:20:42 | Artisan log | Artisan starts again, serial port = the virtual port |
| 22:20:46 | Artisan log, app log | **ON**. Session 3 attaches: "real port open for 890 s, opened once, never reopened" |
| 22:20:46 onward | macOS Bluetooth log, app status | replies arrive again: 606 bytes from the roaster in the first 15 seconds, and none between the quit and this ON. The app shows "Receiving roaster replies" |

| Check | Reported by the tester | Confirmed by the logs |
|---|---|---|
| The app opening at login | not reported | **Yes.** Launched by the login window from the login items at 22:05:55 |
| The bridge starting by itself | not reported | **Yes.** The start follows the app's launch by 43 ms, with no menu command in between |
| Bluetooth connection for that open of the port | not something the tester can see directly | **Yes.** One RFCOMM connection, successful 1.2 s after the open, and no disconnect up to 22:21 |
| First live readings | Artisan showed live ET and BT | **Yes.** 4,617 bytes of replies in session 1 |
| OFF → ON | readings returned | **Yes.** OFF and ON in Artisan's log, 4 s apart; session 2 on the same open port, with 456 bytes of replies |
| ⌘Q → relaunch → ON | live ET and BT returned after quitting with ⌘Q, relaunching and clicking ON, with the bridge left running | **Yes.** `MODE: QUIT` at 22:08:53, a new start of Artisan at 22:20:42 and ON at 22:20:46 in Artisan's log; session 3 on the same open port, with replies in the macOS log. The relaunch came 12 minutes after the quit |
| The physical port throughout | the bridge stayed running | **Yes.** The app log has one "real port … opened" line, at 22:05:56.728, and "opened once, never reopened" at sessions 2 and 3. The macOS log has one RFCOMM connection and no disconnect |

**Results, for the signed build only, on one M2 Lite, idle, with the heater off: the app opened at
login, the bridge started by itself, macOS connected the roaster for that open, the first readings
arrived, and both OFF → ON and ⌘Q → relaunch → ON returned replies through the same open of the
physical port. The tester observed the readings each time, and the logs confirm each result.**

Session 3 was still attached when this was written, at 22:21, so the app log has no totals for it
yet. An earlier check, at 22:15, had found no relaunch on record; the relaunch followed at 22:20.

An earlier start of this build, at 22:02:54 and before the restart, is not part of the result. The
app started the bridge by itself when it was opened after installation, two minutes after the ad
hoc build had closed the port (22:00:37), with no reset of Bluetooth logged in between. No RFCOMM
attempt appeared in the macOS log for it, Artisan did not attach, and the restart ended it.

"Showed ET and BT" is the tester's observation; the logs count commands and bytes. The sessions
were short: two minutes and ten seconds.

### Not tested with this build

- installation on a second Mac. This is not planned: the author has one Mac. The signed build was
  downloaded with a browser, installed and opened on the build Mac
- a first launch without a network connection
- anything with the heater on, and any roaster other than this one M2 Lite

## Idle power-loss test

One run, on 2026-11-13, with the signed build (`a9a59f259cc3528af70e43abbed537cb544186b0`). It was
the same process as the hardware run above, started at login at 22:05:55, with no restart of the
Mac in between; its signature was read again afterwards and carries that hash. Same Mac
(macOS 27.2), same Kaleido M2 Lite, idle, heater off. Artisan 5.0.0 (build b03f31b6c), the
installed app, Comm Port set to the virtual port. Artisan was monitoring, with a session open at the
roaster, when the tester unplugged the roaster's power. As before, what the tester reported and
what the logs show are kept apart.

| Time | Source | Event |
|---|---|---|
| 22:46:01 | Artisan log, app log | **ON**. Session 5 attaches: "real port open for 2405 s, opened once, never reopened" |
| 23:01:28.4 | macOS Bluetooth log | the last data from the roaster reaches the Mac. Artisan's next three commands go out at 23:01:30.0, 23:01:31.2 and 23:01:32.9 and get no reply. Neither the roaster's port nor the app log reports an error |
| 23:01:33.44 | macOS Bluetooth log | the serial port profile logs an update of the RFCOMM port properties. The log does not show what caused it |
| 23:01:33.463 | app log | "session 5: Artisan VANISHED: a session is open at the roaster (opened by {[SC AR]}) and CL AR was not delivered", after 931.9 s, 627 commands and 35,298 bytes of replies. No "roaster has not answered" warning comes before it. The bridge closes the roaster's port at 23:01:33.471 and stops with exit code 4 |
| 23:01:34 | Artisan log | Artisan tries to open the virtual port again and gets "No such file or directory". It is Artisan's first logged error of the run |
| 23:01:34.745 | macOS Bluetooth log | the Bluetooth connection to the roaster ends and the serial port is marked disconnected, 1.3 s after the bridge closed the port |
| 23:02:51, 23:02:55 | Artisan log | **OFF**, then quit |
| 23:11:13, 23:11:17 | Artisan log | Artisan starts again; **ON** |
| 23:11:26.957 | macOS log, app log | a menu command in the app; the bridge starts and opens the port at 23:11:26.968. No RFCOMM attempt appears in the macOS log for this open |
| 23:11:27 – 23:12:01 | app log | Artisan attaches six times. In each of the first five it sends three commands, gets no reply and leaves after about 6 s, "clean (no session was opened at the roaster)". The tester stops the bridge at 23:12:01.8, after a menu command at 23:11:58 |
| 23:12:24.7 | macOS log | the Bluetooth service (`bluetoothd`) exits and launchd starts a new one. `sudo` ran at 23:12:17 |
| 23:12:26.45 | macOS log | Bluetooth is switched off |
| 23:12:28.89 | macOS log | Bluetooth is switched on |
| 23:13:33.207 | macOS log, app log | a menu command in the app; the bridge starts and opens the port at 23:13:33.214 |
| 23:13:33.219 – 23:13:33.758 | macOS Bluetooth log | RFCOMM connection attempt for that open; the serial port is reported connected 0.5 s later |
| 23:13:48 | Artisan log, app log | **ON**. Session 1 attaches |
| 23:13:48 – 23:14:03 | macOS Bluetooth log | 549 bytes from the roaster in the first 15 seconds |

The reset between 23:12:17 and 23:12:29 was made with a local script of the tester's, kept outside
this repository. It restarts the Bluetooth service with `sudo pkill -x bluetoothd`, waits until the
service answers again, switches Bluetooth off, waits two seconds and switches it on. The macOS log
shows those steps in that order.

| Check | Reported by the tester | Confirmed by the logs |
|---|---|---|
| The bridge stopped after the power was unplugged | it stopped and showed "Artisan vanished mid-session" | **Yes.** Exit code 4 at 23:01:33.472. That alert text belongs to this build |
| Artisan was still open | Artisan was still open | **Yes.** No quit in Artisan's log until 23:02:55, and it tried to open the virtual port again at 23:01:34 |
| What the bridge saw | not something the tester can see | The roaster stopped answering at 23:01:28.4 while its port reported no error. 5.0 s later the virtual port was closed without `CL AR` while a session was open. The bridge then closed the roaster's port and stopped |
| Why the virtual port was closed | not something the tester can see | **Not in the logs.** Artisan's debug logging was off, and its log has no line for the close. Artisan 5.0.0's source closes its serial port and tries again when no reply line arrives for 5 s (`_read_timeout` in `artisanlib/kaleido.py`). That fits the 5.0 s and the new open at 23:01:34, but the logs do not show it directly |
| After the roaster was switched on again, a start of the bridge alone | did not reconnect | **Yes.** No RFCOMM attempt for the open at 23:11:26.968, and no reply to any of Artisan's commands in 35 s |
| After the Bluetooth reset, a new start of the bridge | live ET and BT returned | **Yes, for replies.** RFCOMM connection 0.5 s after the open and 549 bytes of replies in the first 15 seconds. ET and BT are the tester's observation; the logs count bytes |

**Result, for the signed build only, in one run on one M2 Lite, idle, heater off:** with Artisan
monitoring, unplugging the roaster's power stopped the bridge with the alert for a vanished
Artisan, although Artisan was still running. The roaster's port reported no error. What the bridge
saw was Artisan's virtual port closing during a session, 5 s after the roaster's last reply. After
the power came back, a start of the bridge alone got no replies, and macOS logged no RFCOMM attempt
for it. After a restart of the Bluetooth service followed by Bluetooth off and on, the next start
connected and replies returned.

What this run does not show:

- When the power was unplugged and when it came back. Neither is in any log; the last reply at
  23:01:28.4 is the nearest sign of the first.
- Whether the reset was needed because of the loss of power. The bridge had just closed the port,
  and in earlier runs opens after a close got no replies with the roaster powered throughout.
- Whether a later start without a reset would have connected. Only one start was tried, for 35 s.
- Whether a lost link with the roaster still powered, for example out of range, looks the same.
- Anything with the heater on.

**Changed in the source after this run:** the alert now reads "Connection lost during an active
session. The bridge stopped.", and it adds whether the roaster had stopped answering before the
port closed. The recovery help says that a roaster switched on again may need a manual Bluetooth
reset before the bridge is started again. The stop behavior is unchanged. These changes are in
`src/`, so this source is no longer the signed build. The new alert was then run on hardware
from source; see the next section. No packaged build of it exists yet.

### Idle power-loss test with source commit `f1825c9`

One run, on 2026-11-13, of this source at commit `f1825c9379896c71de2a512bff7ebf8c3b7bfd48` on the
branch `power-loss-alert`. **It is a source run, not a build:** the app was started from Terminal
with `python -m kaleido_serial_bridge` in the repository's Python environment (Python 3.14,
pyserial 3.5), as one process for the whole run. The module was loaded from the repository's
`src/`. The working tree was clean and its source files were last changed before that commit was
made. Nothing in this section is about the signed build or any other build. Same Mac (macOS 27.2),
same Kaleido M2 Lite, idle, heater off; Artisan 5.0.0 (build b03f31b6c), the installed app, as one
process throughout, Comm Port set to the virtual port. Before the run the installed app's bridge
was stopped (23:39:41) and the app quit.

| Time | Source | Event |
|---|---|---|
| 23:40:04 – 23:40:14 | macOS log | Bluetooth reset with the tester's local script (kept outside this repository): `sudo` at 23:40:04, the Bluetooth service restarts at 23:40:10.2, Bluetooth off at 23:40:11.85 and on at 23:40:14.24 |
| 23:40:33.645 | app log | the source app starts the bridge by itself as it opens ("Start the bridge when the app opens" is on; no menu command in the app before it). The port is opened at 23:40:33.646 |
| 23:40:33.636 – 23:40:34.482 | macOS Bluetooth log | RFCOMM connection attempt for that open, reported connected 0.8 s later |
| 23:40:56 | Artisan log, app log | **ON**. Session 1 attaches; 549 bytes of replies in the first 15 seconds |
| 23:41:27.97 | macOS Bluetooth log | the last data from the roaster reaches the Mac. Artisan's next three commands go out at 23:41:29.44, 23:41:30.94 and 23:41:32.44 and get no reply. Neither the roaster's port nor the app log reports an error |
| 23:41:32.974 | macOS Bluetooth log | the serial port profile logs an update of the RFCOMM port properties, as in the first run. The log does not show what caused it |
| 23:41:32.982 | app log | "session 1: CONNECTION LOST during an active session: the virtual port was closed and a session was open at the roaster (opened by {[SC AR]}) and CL AR was not delivered after 36.8 s \| 27 commands delivered to the roaster, 1233 bytes passed to Artisan \| The roaster had not answered for 5.0 s before that (3 commands unanswered).", followed by "the bridge cannot tell why …" |
| 23:41:32.985 – 23:41:32.988 | app log | the bridge closes the roaster's port and stops with exit code 4 |
| 23:41:33 | Artisan log | Artisan tries to open the virtual port again and gets "No such file or directory". Artisan keeps running |
| 23:41:33.139 | macOS Bluetooth log | the Bluetooth connection to the roaster ends and the serial port is marked disconnected, 0.15 s after the bridge closed the port |
| 23:43:29.534 | macOS log, app log | a menu command in the source app; the bridge starts and opens the port, with no Bluetooth reset since the stop (the same Bluetooth service process since 23:40:10). No RFCOMM attempt appears in the macOS log, no data comes from the roaster, and Artisan does not attach. The bridge is stopped at 23:43:55.3 |
| 23:44:00 – 23:44:11 | macOS log | Bluetooth reset with the same script: `sudo` at 23:44:00.7, the Bluetooth service restarts at 23:44:06.6, Bluetooth off at 23:44:08.19 and on at 23:44:10.58 |
| 23:44:46 | Artisan log | **OFF** |
| 23:44:50.893 | macOS log, app log | a menu command in the source app; the bridge starts and opens the port at 23:44:50.896 |
| 23:44:50.889 – 23:44:52.107 | macOS Bluetooth log | RFCOMM connection attempt for that open, reported connected 1.2 s later |
| 23:45:04 | Artisan log, app log | **ON**. Session 1 attaches; 549 bytes of replies in the first 15 seconds, and the app shows "Receiving roaster replies" |

| Check | Reported by the tester | Confirmed by the logs |
|---|---|---|
| The new alert after the power was unplugged | "Connection lost during an active session. The bridge stopped." appeared | **Yes, for the stop and its reason.** Exit code 4 at 23:41:32.988. The app log does not record alerts; the headline for this exit code is in this commit's source, and the alert's text is the same stop reason the log line carries |
| The roaster's silence in the alert | 5.0 s without a reply, three commands unanswered | **Yes.** "The roaster had not answered for 5.0 s before that (3 commands unanswered)" in the app log. The macOS log shows the last data at 23:41:27.97 and three unanswered commands after it |
| Artisan was still open | not reported | **Yes.** No quit in Artisan's log; it tried to open the virtual port again at 23:41:33 |
| The stop behavior | not something the tester can see | **Unchanged.** The bridge closed the roaster's port and stopped, as before |
| A start of the bridge alone after the power came back | not reported | **No connection.** The start at 23:43:29 had no Bluetooth reset before it, no RFCOMM attempt and no data from the roaster |
| After the Bluetooth reset and a new start | live ET and BT returned | **Yes, for replies.** RFCOMM connection 1.2 s after the open at 23:44:50.896 and 549 bytes of replies in the first 15 seconds. ET and BT are the tester's observation |

**Result, for source commit `f1825c9` run from source, in one run on one M2 Lite, idle, heater
off:** with Artisan monitoring, unplugging the roaster's power stopped the bridge with the new alert,
"Connection lost during an active session. The bridge stopped.", and the stop reason said that the
roaster had not answered for 5.0 s (3 commands unanswered). Artisan stayed open. The bridge closed
the roaster's port and stopped, as before. After the power came back, a start of the bridge without
a reset got no replies and no RFCOMM attempt. After a restart of the Bluetooth service followed by
Bluetooth off and on, the next start connected and replies returned.

What this run does not show:

- Anything about a packaged or signed build of this source. None has been made.
- When the power was unplugged and when it came back; neither is in any log.
- Whether the reset was needed because of the loss of power or because the port had been closed.
- The alert as drawn on screen. That is the tester's observation; the app log records the stop
  reason, not the alert.
- Anything with the heater on.

### Packaged test build of `c6bfea8`: idle power loss and manual recovery

One run, on 2026-11-14, with a local test build of commit `c6bfea845c2d787bb6c81909a97dd6e6ad99ce11`:
the app with the code directory hash `61bb0351c20def68b95b52e65c2baac09f5619a8`, signed ad hoc, from
the disk image `KaleidoSerialBridge-0.2.0-c6bfea8-adhoc-test-arm64.dmg` (SHA-256
`d6566d8d11a9e84e83fbfc31782d1e4079625d250f3ec859def31e723b7c7fc3`). Its compiled modules were
compared with the source at that commit before the run and matched. It reports version 0.2.0;
only the hash tells it apart. Everything in this section is about that build and no other: not the
signed 0.2.0 build, and not the later commits on this branch. Same Mac (macOS 27.2), same Kaleido
M2 Lite, idle, heater off; Artisan 5.0.0 (build b03f31b6c), the installed app, as one process
throughout, Comm Port set to the virtual port.

**Where it ran: from `/Applications`, not from a separate folder.** The test was planned from a
separate folder. The macOS log shows Finder copy operations at 00:09:52 and 00:10:47 (their
destinations are not shown in the log) and the disk image mounted at 00:11:00. At 00:12:18 the app
was started from `/Applications/Kaleido Serial Bridge.app`, which the kernel reported as signed ad
hoc. The app in `/Applications` afterwards has the hash `61bb0351…`; the signed build that was
installed there before has been replaced. The login item still points to that path, and no move of
it is logged during the run.

| Time | Source | Event |
|---|---|---|
| 00:12:18.25 | macOS log | the app starts from `/Applications` (process 9761, the same process for the whole run) |
| 00:12:19.102 | app log | the bridge starts by itself ("Start the bridge when the app opens" is on). No Bluetooth reset since the previous close of the port at 23:58:53; no RFCOMM attempt appears for this open and no data comes from the roaster. A menu command at 00:12:36; the bridge stops at 00:12:39.3 |
| 00:12:50 – 00:13:01 | macOS log | Bluetooth reset with the tester's local script: `sudo` at 00:12:50, the Bluetooth service restarts at 00:12:56.6, Bluetooth off at 00:12:58.23 and on at 00:13:00.62 |
| 00:13:13.638 | macOS log, app log | a menu command; the bridge starts. RFCOMM connection attempt at 00:13:13.644, reported connected at 00:13:14.940 |
| 00:13:27 | Artisan log, app log | **ON**. Session 1 attaches; 549 bytes of replies in the first 15 seconds |
| 00:13:47.7 | macOS Bluetooth log | the last data from the roaster before the stop |
| 00:13:52.708 | app log | "CONNECTION LOST during an active session … CL AR was not delivered after 24.8 s \| 19 commands delivered to the roaster, 777 bytes passed to Artisan \| The roaster had not answered for 5.0 s before that (3 commands unanswered)." The bridge closes the roaster's port and stops with exit code 4 at 00:13:52.717 |
| 00:13:53 | Artisan log | Artisan tries to open the virtual port again ("No such file or directory"); it keeps running |
| 00:13:52.894 | macOS Bluetooth log | the Bluetooth connection to the roaster ends, 0.18 s after the bridge closed the port |
| 00:15:42, 00:16:56, 00:17:18 | macOS log | menu commands in the app. The log does not say which items they were. No start of the bridge follows them |
| 00:17:55 – 00:18:05 | macOS log | Bluetooth reset with the same script: `sudo` at 00:17:55, the Bluetooth service restarts at 00:18:00.9, Bluetooth off at 00:18:02.47 and on at 00:18:04.92 |
| 00:18:18.988 | macOS log, app log | a menu command; the bridge starts. RFCOMM connection attempt at 00:18:18.985, reported connected at 00:18:21.452 |
| 00:18:36, 00:18:40 | Artisan log, app log | **OFF**, **ON**. Session 1 attaches; 549 bytes of replies in the first 15 seconds |
| 00:19:04.5 | macOS Bluetooth log | the last data from the roaster before the second stop |
| 00:19:09.550 | app log | a second "CONNECTION LOST during an active session", after 29.3 s, 22 commands and 948 bytes, again with "The roaster had not answered for 5.0 s before that (3 commands unanswered)". Exit code 4 at 00:19:09.557 |
| 00:19:10.498 | macOS Bluetooth log | the Bluetooth connection to the roaster ends |
| 00:23:12 | Artisan log | **OFF**. No further start of the bridge up to 00:23 |

| Check | Reported by the tester | Confirmed by the logs |
|---|---|---|
| The packaged alert after the power was unplugged | it appeared | **Yes, for the stop and its reason.** Exit code 4 at 00:13:52.717 with the reason "The roaster had not answered for 5.0 s before that (3 commands unanswered)". The headline is in this build's code, as checked before the run. The app log does not record alerts |
| The alert's Help button | it worked | **Not in the logs.** Neither the app log nor the macOS log records which window opened. Three menu commands between 00:15:42 and 00:17:18 are logged, without their names |
| Manual recovery: Bluetooth reset, then a new start of the bridge | live readings returned | **Yes, for replies.** Reset at 00:17:55 – 00:18:05, start at 00:18:18.988, RFCOMM connected 2.5 s later, 549 bytes of replies in the first 15 seconds after ON. "Live readings" is the tester's observation |
| The stop behavior | not something the tester can see | **Unchanged.** Both stops closed the roaster's port and stopped the bridge |
| A start without a reset | not reported | **No connection.** The automatic start at 00:12:19, after the port had been closed at 23:58:53 with no reset in between, had no RFCOMM attempt and no data |
| The second stop at 00:19:09 | not reported | The same pattern as the first: 5.0 s without a reply, three unanswered commands, then exit code 4. The logs do not show what caused it. No recovery attempt follows it in the logs |
| Where the app ran | from a separate folder (planned) | **From `/Applications`.** The signed build that was installed there has been replaced by this test build |

**Result, for the packaged test build `61bb0351…` (commit `c6bfea8`) only, in one run on one M2
Lite, idle, heater off:** unplugging the roaster's power stopped the bridge with the packaged alert
"Connection lost during an active session. The bridge stopped.", and its reason named 5.0 s
without a reply and three unanswered commands. After the power came back, a Bluetooth reset (the
service restart, then Bluetooth off and on) followed by a new start of the bridge connected, and
replies returned. The stop behavior was unchanged. The Help button is the tester's observation.

What this run does not show:

- Anything about a signed or notarized build of this change. None existed at the time of this run.
- The Help window's contents on screen, or which window the Help button opened.
- When the power was unplugged and when it came back; neither is in any log.
- Anything with the heater on.

## Simulator results

No roaster and no Bluetooth are involved in anything in this section. The "roaster" is
`tools/sim_roaster.py` on a pseudo terminal; it answers like a Kaleido and records what it is sent
and whether a port is open on it.

| Check | Result |
|---|---|
| `tests/test_engine.py`: forwarding, stale data, normal disconnect, abrupt client exit, a client giving up on a silent roaster, bridge exit, upstream loss, silent upstream, second client | 29 passed, 1 skipped (it needs Artisan's source) |
| `tests/test_controller.py`: first run, saved settings, status accuracy, clean stop, failures | 29 passed |
| `tests/test_app.py`: setup guide, menu, stop warnings, failure alerts, help texts, driven in-process without clicks | 15 passed |
| The skipped engine test, run with Artisan's source: Artisan's own Kaleido code through the bridge, OFF → ON | passed |
| `tests/packaged_app_check.py`: the built app started by itself with an empty environment; status from saved settings; replies; clean stop; relaunch | 22 of 22 checks passed on the later ad hoc test build (hash `7630086f…`), copied out of its disk image the way a drag to Applications does. 22 of 22 again with Homebrew, `/usr/local`, other Python installations, the Xcode tools and the source tree made unreadable to the app |
| `tests/e2e_artisan.py` with unmodified Artisan 5.0.0 source and the **prototype** bridge: ON, OFF, ON, quit while reading, relaunch, ON | readings every time ON was clicked (three times); the simulated roaster saw its port opened once |

What the simulator cannot show: anything about macOS Bluetooth, the real roaster's firmware, or
timing on a real link.

### Guided Bluetooth recovery: checks without hardware

The Help window's **Reset Bluetooth & Restart Bridge**, as in commit
`0f2f02a6cb99468b4183130b863f766640dbf214`. Its local test build is the disk image
`KaleidoSerialBridge-0.2.0-guided-recovery-b5db64379547-adhoc-test-arm64.dmg` (SHA-256
`fcda040c2fccfdd68109f4268ae1019e5796067e130e3ed13bcfb462328d23f1`), with the app's code
directory hash `1640c79eab7c23259790e6a65d27cfbdd95110de`, signed ad hoc, version 0.2.0. It was
built from exactly the tree of that commit: the diff against `661dd2f` was compared byte for byte
before the commit, and the compiled modules in the app match the source.

| Check | Result |
|---|---|
| `tests/test_recovery.py`: the recovery against a simulated macOS and the simulated roaster: success; a cancelled authorization; a failed restart; the Bluetooth service, the power off, the power on and the serial port each not coming back in time; the power switch unavailable; no replies in time; a running bridge; one attempt at a time; nothing without a click | 15 passed |
| `tests/test_app.py`, the recovery part: after a real connection-loss stop, the Help button, the confirmation and its texts, cancel, success with real replies, a cancelled authorization and a missing port named in the alert with the manual steps, a running bridge refused | 6 passed (26 in the file) |
| The whole test suite | 99 passed, 1 skipped (it needs Artisan's source; run with it, it passed) |
| `tests/packaged_app_check.py` on a copy of the app taken out of that disk image, with `KALEIDO_BRIDGE_NO_LOGIN_ITEM=1` | 26 of 26, among them: the bundled app finds the two IOBluetooth power functions and `NSAppleScript` (looked up, not called), and the registered login item is the same before and after |

**Pending on hardware:** the restart of the Bluetooth service through the administrator prompt,
the real switching of Bluetooth off and on, whether macOS asks for Bluetooth permission, and a
recovery after a loss of power on the M2 Lite. None of these has been run. **Untested:** the
recovery in a build with the hardened runtime (a signed build), including the
`com.apple.security.device.bluetooth` entitlement and `NSAppleScript` under it.

### Guided recovery, notarized test build: two guided failures, then manual recovery

One run, on 2026-11-14, with the Developer ID signed, hardened runtime, notarized test build of the
tree of commits `2146aa9` and `dde9e1a` (disk image
`KaleidoSerialBridge-0.2.0-guided-recovery-ee47364e976c-devid-notarized-test-arm64.dmg`, SHA-256
`7bb4ef0d94d6bb26ee2c4037fc7d2866aa1bfbe5c31f97ec907a0e3bd4171fd3`), installed in
`/Applications` at 01:13. The installed app and the running process (pid 14928, started 01:19:39)
both have the code directory hash `3195ebea9d3394a67cb0978d6b31d06430af0769`. Everything in this
section is about that build. M2 Lite idle, heater off; Artisan 5.0.0, the installed app.

**Result: two guided attempts after a loss of power failed; a manual start of the bridge then
connected and live readings returned.** The app does not log its recovery steps, so which step
each attempt reported is inferred from the macOS log, as described below.

| Time | Source | Event |
|---|---|---|
| 01:20:23 – 01:20:40 | macOS log, app log | a guided attempt before the power was unplugged, not part of the report: authorization succeeded at 01:20:25.6, `bluetoothd` restarted at 01:20:25.7, a Bluetooth permission prompt of macOS for the app was answered at 01:20:28.4, the app's power-off request was accepted at 01:20:28.8 (off at 01:20:28.87), its power-on request at 01:20:31.3 (on at 01:20:31.62), the bridge started at 01:20:38.836, RFCOMM connected at 01:20:40.488 |
| 01:20:46 | Artisan log, app log | **ON**. Session 1 attaches |
| 01:21:23.486 | app log | "CONNECTION LOST during an active session"; exit code 4. Artisan keeps running |
| 01:22:00.2 – 01:22:01.8 | macOS log | **guided attempt 1** (Artisan still ON): the authorization dialog, which SecurityAgent marked "AEWP notarized 1, biometry prohibited 0", succeeds at 01:22:01.755. `bluetoothd` restarts at 01:22:01.857 |
| 01:22:02.832 | macOS log, in the app's process | the app's power-off request, while the app's Bluetooth connection to the restarted service was still being re-established ("XPC connection interrupted, resetting" at 01:22:01.830): "updateBTPowerStateTo … inState: 0, Current State: 2", then "API MISUSE: … can only accept this command while in the powered on state". Bluetooth is not switched off. The new service reports "on" at 01:22:03.319. No power-on request follows |
| 01:22:05 | Artisan log | **OFF** |
| 01:22:22.5 – 01:22:24.6 | macOS log | **guided attempt 2**: authorization succeeds at 01:22:24.493; `bluetoothd` restarts at 01:22:24.587 |
| 01:22:25.332 | macOS log, in the app's process | the same rejection of the power-off request, "Current State: 2" and "API MISUSE". The new service reports "on" at 01:22:26.030. No power-on request follows |
| 01:23:10.476 | macOS log, app log | a menu command: the tester starts the bridge. RFCOMM connection attempt at 01:23:10.486, connected at 01:23:10.929 |
| 01:23:27 | Artisan log, app log | **ON**. Session 1 attaches; the tester saw live ET and BT |

| Check | Reported by the tester | Confirmed by the logs |
|---|---|---|
| The alert after the power was unplugged | the new alert appeared | **Yes, for the stop.** Exit code 4 at 01:21:23.490 |
| Guided attempt 1 | the app reported that Bluetooth did not reset | **The step is inferred, not logged.** The service restarted; Bluetooth was not switched off, because macOS rejected the power-off request; no power-on request was made. That fits a failure at "Wait for Bluetooth to turn off" (limit 10 s, so at about 01:22:13). Artisan was turned OFF at 01:22:05, before that |
| Guided attempt 2 | it failed again | **Same as attempt 1**, at about 01:22:35 by the same reasoning |
| `bluetoothd` restarted | not something the tester can see | **Yes, in both attempts** (new processes at 01:22:01.857 and 01:22:24.587) |
| Bluetooth cycled off and on | not something the tester can see | **No, in neither attempt.** It did in the attempt at 01:20, where the app's Bluetooth connection was new |
| Manual start | live ET and BT returned | **Yes, for replies.** RFCOMM connected 0.44 s after the start; Artisan attached at 01:23:27 |
| Touch ID in the administrator prompt | not yet reported | SecurityAgent logged "AEWP notarized 1, biometry prohibited 0" for all three prompts, and found Touch ID available. Whether the dialog offered it, and whether it was used, is not in the log |
| Focus and Spaces during the attempts | not yet reported | The Dock switched Spaces three times, at 01:22:01.9, 01:22:24.6 and 01:23:00.4, each time for a window of **Artisan**, not of this app. The first two came right after the authorization dialog closed and macOS brought Artisan forward. After the confirmations of attempts 1 and 2, this app did not make itself the front app; it became front only when the Space was changed (01:22:08.7, 01:22:30.1, 01:22:46.2). During the attempt at 01:20 it became front at 01:20:30.4, right after the Bluetooth permission prompt closed |

**Why the guided attempts failed, as far as the logs show:** after the restart of `bluetoothd`, the
app waited only until a `bluetoothd` process existed and the power state could be read. In the
attempts after the first one, its own connection to Bluetooth was still being re-established at
that moment, and macOS rejected the power-off request. The recovery then waited 10 s for "off",
which never came, and stopped without starting the bridge. In the first attempt the connection was
new, and the permission prompt delayed the request by 2.4 s until the service was on. The
power-on step was never reached.

**What this run shows besides:** the restart of `bluetoothd` had taken effect in both failed
attempts, and a start of the bridge after the second one connected at once, without Bluetooth
being switched off and on. One run; it does not show that the restart alone is enough in general.

Not shown: the exact text the app displayed for each failure (the app does not log it), Touch ID
in the dialog, and the focus result as the tester saw it.

### Guided recovery after a loss of power: notarized build `5bdc6388…`

One run, on 2026-11-14, with the Developer ID signed, hardened runtime, notarized test build of
commit `50e0101aa87f73f611019dee59f71cd4b764c661` (disk image
`KaleidoSerialBridge-0.2.0-guided-recovery-readiness-33113035ff06-devid-notarized-test-arm64.dmg`,
SHA-256 `c238b6dfba6ffe37b2ea344a18e8834bc0c6fd33c6ed7e0506ef6467082dfc08`), installed in
`/Applications`. The installed app and the running process (pid 16692, started 01:42:18) both have
the code directory hash `5bdc6388ab1cfbe23a2dff12c673cc092f86685e`. Everything in this section is
about that build. M2 Lite idle, heater off; Artisan 5.0.0, the installed app. This build logs
every recovery step to the app log, so the app's own account of each step is on record and is
compared with the macOS log.

**Result: a guided recovery after a loss of power worked.** The tester observed it, and the logs
confirm each part of it.

| Time | Source | Event |
|---|---|---|
| 01:42:40 – 01:43:08 | app log, macOS log | recovery 1, before the power was unplugged (the bridge had been stopped at 01:41:42 by the previous app): service restarted, power cycle completed, the bridge started at 01:42:56.542, RFCOMM connected at 01:42:57.618, replies received at 01:43:08. Not the result of this section, but the start of the run |
| 01:43:07 | Artisan log, app log | **ON**. Session 1 attaches; 549 bytes of replies in the first 15 seconds |
| 01:43:35.96 | macOS Bluetooth log | the last data from the roaster before the stop |
| 01:43:40.970 | app log | "CONNECTION LOST during an active session", with "The roaster had not answered for 5.0 s before that (3 commands unanswered)". The bridge closes the roaster's port and stops with exit code 4 |
| 01:43:41.933 | macOS Bluetooth log | the Bluetooth connection to the roaster ends |
| 01:44:37.391 | app log | **recovery 2: begun by the user** |
| 01:44:37.955 – 01:44:40.115 | macOS log, app log | the authorization dialog, which SecurityAgent marked "AEWP notarized 1, biometry prohibited 0", succeeds; the app logs "authorization granted" at 01:44:40.262 |
| 01:44:40.202 | macOS log | `bluetoothd` restarts (a new process). It reports Bluetooth on at 01:44:41.648 |
| 01:44:42.078 | app log | "**Bluetooth service restarted** (bluetoothd is running and Bluetooth reports on, after 1.8 s)" |
| 01:44:42.531 – 01:44:42.572 | macOS log | the app's request to turn Bluetooth off, the first one, is followed by Bluetooth off 41 ms later. No retry was needed |
| 01:44:46.030 – 01:44:46.313 | macOS log | its request to turn Bluetooth on, again the first one, is followed by Bluetooth on |
| 01:44:46.543 | app log | "**Bluetooth power cycle completed** (on again after 1 request(s))" |
| 01:44:52.543 | app log | the roaster's serial port exists |
| 01:44:53.043 – 01:44:53.058 | app log | "starting on /dev/cu.Roaster_SRSv6"; "real port … opened" at 01:44:53.048; "**bridge started**; waiting for the user to click ON in Artisan" |
| 01:44:53.035 – 01:44:53.607 | macOS Bluetooth log | RFCOMM connection attempt for that open, reported connected 0.57 s later |
| 01:45:01, 01:45:06 | Artisan log | **OFF**, **ON** |
| 01:45:06.176 | app log | session 1 attaches: "real port open for 13 s, opened once, never reopened" |
| 01:45:07.047 | app log | "**roaster replies received** through the bridge; recovery succeeded". 549 bytes of replies in the first 15 seconds, by the macOS log |
| 01:47:03.050 | Artisan log, app log | **OFF**. Session 1 detaches, clean, after 116.9 s: 81 commands, 4,446 bytes of replies |
| 01:47:15.277 | app log | the tester stops the bridge: "real port … closed after 142 s. It was opened once and never reopened." |

| Check | Reported by the tester | Confirmed by the logs |
|---|---|---|
| Guided recovery after the loss of power | it worked | **Yes.** Recovery 2 went through every step and ended with "recovery succeeded" |
| The Bluetooth service restarted | not something the tester can see | **Yes.** A new `bluetoothd` at 01:44:40.202, in the macOS log; "Bluetooth service restarted" in the app log |
| Bluetooth switched off and on again | not something the tester can see | **Yes.** Off at 01:44:42.572 and on at 01:44:46.313, each right after the app's first request; no request was rejected and none was repeated |
| The bridge opened the physical port once after the reset | not something the tester can see | **Yes.** One "real port … opened" line between the reset and the stop, at 01:44:53.048; "opened once, never reopened" at the attach and at the close. One RFCOMM connection, from 01:44:53.607 until the close |
| Roaster replies resumed | not reported separately | **Yes.** 549 bytes in the first 15 seconds after ON, and 4,446 bytes in the session |
| Touch ID offered and used in the administrator prompt | the tester saw Touch ID in the administrator prompt and used it successfully to authorize the Bluetooth reset (direct observation) | **Corroborated, not identified.** SecurityAgent marked both prompts as eligible for Touch ID ("AEWP notarized 1, biometry prohibited 0"), `coreauthd` started a Touch ID match for each when the dialog appeared (01:42:41.407, 01:44:37.972), and both authorizations succeeded. The log does not identify which credential completed them |
| Focus and Spaces during recovery 2 | the connection-loss alert appeared in Artisan's Space. Clicking Help switched to the main desktop. After the Bluetooth reset macOS switched back to Artisan, and the bridge was waiting for Artisan; OFF, then ON in Artisan restored live ET and BT. The completion update left the tester in Artisan's Space; the Help window, returned to by hand, was still open and said "Readings are back" | **Consistent.** The alert made the app the front app at 01:43:41.083 with no change of Space. At 01:44:01.617, when Help was clicked, the Dock switched to Space 1 "for window … ordered on non-visible space" of this app: the Help window was on Space 1, and bringing it forward took the tester there. At 01:44:40.127, right after the authorization succeeded, macOS brought Artisan forward and the Dock switched to Artisan's Space (60); that comes from the authorization dialog closing, not from this app. Artisan OFF at 01:45:01 and ON at 01:45:06; replies at 01:45:07. Around the completion the log shows no change of Space and no activation by this app; the tester changed Spaces by gesture at 01:45:00 and 01:45:10 |

What this run does not show:

- Anything with the heater on, or on another Mac or roaster.
- How often this works. One recovery after a loss of power succeeded, with no retry needed; the
  retry itself has been exercised with the simulator only.
- When the power was unplugged and when it came back; neither is in any log.

### Troubleshooting in the current Space: notarized build `62973c3d…`

The Developer ID signed, hardened runtime, notarized test build of commit
`198d03f013890cca2ade3f1560a411813dbeb194` (disk image
`KaleidoSerialBridge-0.2.0-troubleshooting-spaces-198d03f-devid-notarized-test-arm64.dmg`, SHA-256
`add88b96d9a51d3a2df5d5257261396e1f7a602fe48dce3c6627059f29c07773`), installed in
`/Applications`. The installed app and the running process (pid 23276, started 08:52:57 on
2026-11-14) have the code directory hash `62973c3dac0826cd10525a41791ab530212cdb0b`. That commit
gives the Troubleshooting window the collection behaviors moveToActiveSpace and
fullScreenAuxiliary and orders it front before the app is activated. Everything in this section is
about that build.

| Check | Reported by the tester | Confirmed by the logs |
|---|---|---|
| Troubleshooting from the menu bar, Artisan full screen | opened in the current Space: **passed** | see below |
| Troubleshooting from the menu bar, Artisan on a second regular desktop | opened in the current Space: **passed** | see below |
| Troubleshooting from the connection-loss alert, Artisan full screen | opened in the current Space: **passed** | see below |
| Troubleshooting from the connection-loss alert, Artisan on a second regular desktop | opened in the current Space: **passed** | see below |

What the logs show for this run, from 08:52:57 on: menu commands in the app at 08:53:34,
08:53:40 and 08:56:10, each with the app becoming the front app; a connection loss at 08:57:20.840
and the app becoming the front app for its alert at 08:57:21.375. The Dock logged **no** "switching
to space … ordered on non-visible space" for this app's windows at any time in the run. With the
previous build (`5bdc6388…`) the Help button of the alert caused exactly such a switch (01:44:01).
The logs do not record which Space layout each opening happened in, so the four arrangements are
the tester's report. The same run also has two guided recoveries that ended with "recovery
succeeded" (08:54:30, and 08:58:42 after the connection loss).

### Release candidate 0.2.1 (`8ef1777d…`): update check, Troubleshooting, Touch ID, guided recovery

One run, on 2026-11-14 between 09:15 and 09:21, with the signed, notarized release candidate of
commit `753bddcfd4edb4742e9f74bb4b7828358f37b7e1` (disk image
`KaleidoSerialBridge-0.2.1-rc-525f8ad9c4e6-arm64.dmg`, SHA-256
`d1bc97c982b57e9cff4f12a3681f7cd3248300bdedaf58456bd122fc56e337e5`). The installed app and the
running process (pid 25206, started 09:15:22) have the code directory hash
`8ef1777d5b780031adab16f5af715dc5eb5dd61a` and report version 0.2.1. M2 Lite idle, heater off;
Artisan 5.0.0 in a full-screen Space. The tester took a screenshot at 9:17 (the macOS log records
a capture at 09:17:01.93; the image file is not on this Mac, so it was not reviewed here) and six
more from 09:18:45 to 09:20:52, which were reviewed. What the screenshots show, what the tester
reported and what the logs confirm are kept apart.

| Time | Source | Event |
|---|---|---|
| 09:16:10 – 09:16:37 | app log, macOS log | guided recovery 1 (a first connection): service restarted, power cycle completed, the bridge started at 09:16:24.797, Artisan ON at 09:16:36, "recovery succeeded" at 09:16:37.807 |
| 09:16:52 | macOS log, the app's process | one HTTPS request: TLS trust evaluated and passed, response status 304 (macOS revalidated its cached copy of the answer with GitHub), "finished successfully" |
| 09:17 | screenshot (tester's report of it) | "Kaleido Serial Bridge is up to date", installed version 0.2.1, latest published release 0.2.0 |
| 09:18:26.763 | app log | "CONNECTION LOST during an active session"; exit code 4 |
| 09:18:45 | screenshot | the connection-loss alert over Artisan; Artisan shows `UU` for ET and BT, "Kaleido disconnected" |
| 09:19:02 | screenshot | the Help window open over Artisan. It already says "Readings are back" and "Recovered: replies from the roaster are arriving through the bridge." Artisan still shows `UU` |
| 09:19:21 | screenshot | the confirmation sheet on the Help window |
| 09:19:35.616 | app log | guided recovery 2 begun by the user |
| 09:19:40 | screenshot | macOS's prompt "Allow administrator access for "Kaleido Serial Bridge"?" with "Touch ID or enter your password" and "Use Password…" |
| 09:19:36 – 09:19:58 | macOS log | SecurityAgent "AEWP notarized 1, biometry prohibited 0"; coreauthd starts a Touch ID match at 09:19:36.247 and again at 09:19:56.576; the authorization succeeds at 09:19:57.992 |
| 09:19:59.862 – 09:20:10.819 | app log | "Bluetooth service restarted", "Bluetooth power cycle completed", "bridge started"; one "real port … opened" at 09:20:10.803 |
| 09:20:16 | screenshot | "Click ON in Artisan" with "If Artisan is still monitoring, click OFF, then ON. Otherwise, click ON." |
| 09:20:42, 09:20:45 | Artisan log | **OFF**, **ON** |
| 09:20:46.801 | app log | "roaster replies received through the bridge; recovery succeeded" |
| 09:20:52 | screenshot | Artisan shows ET 77.2 and BT 78.0, "Kaleido connected" |

| Check | Screenshot | Reported by the tester | Confirmed by the logs |
|---|---|---|---|
| Check for Updates… | the 9:17 screenshot shows "Kaleido Serial Bridge is up to date" with installed version 0.2.1 and latest published release 0.2.0 (as the tester reports it; the image was not available for review here) | up to date, installed 0.2.1, latest 0.2.0 | **The request.** One HTTPS request from the app at 09:16:52, completed successfully, and a screenshot capture at 09:17:01.93. The app does not log the text it showed |
| Help over full-screen Artisan | Help window over Artisan (09:19:02) | it opened over full-screen Artisan | **Yes.** Artisan was in a full-screen Space (Spaces configuration, 09:14:45), and the Dock logged no Space switch in the whole run |
| Touch ID offered, authorization succeeded | the prompt offers Touch ID and "Use Password…" (09:19:40) | Touch ID appeared | **Yes, both.** Eligible ("biometry prohibited 0"), a Touch ID match started, and the authorization succeeded at 09:19:57.992. Which credential completed it is in neither the screenshot nor the log, so this run shows Touch ID offered, not used |
| Live ET and BT after guided recovery | ET 77.2, BT 78.0, "Kaleido connected" (09:20:52) | they returned | **Yes.** Recovery 2 went through every step; one open of the port; Artisan OFF and ON; replies at 09:20:46 |
| The status shown when Help opened after the connection loss | "Readings are back" while Artisan showed `UU` (09:19:02) | stale | **A defect.** It was the outcome of recovery 1 (09:16:37), left in the window after the connection loss at 09:18:26 |

The stale "Readings are back" is a defect of this release candidate.

## Pending

Hardware results exist for three packaged builds, two local ad hoc builds and the signed build:

- `bab9676fa030389d71bddd6b3565767a7014e9d3`: **OFF → ON** only.
- `7630086f5c8316900d0bbec2ef9a310eb11cfe2b`, the later ad hoc test build of this source: the
  first connection after a start, **OFF → ON**, **⌘Q → relaunch → ON**, and the app opening at
  login.
- `a9a59f259cc3528af70e43abbed537cb544186b0`, the signed build of the 0.2.0 release: the app opening at
  login, the bridge starting by itself, the first readings, **OFF → ON** and
  **⌘Q → relaunch → ON**. See
  [The signed build](#the-signed-build).

Still pending:

- The guided Bluetooth recovery: with the notarized build `5bdc6388…` the tester saw and used
  Touch ID successfully in the administrator prompt, a guided recovery after a loss of power
  worked once, and the completion update left the tester in Artisan's Space. The Help button of
  the alert then switched to the Space where the Help window was; with the build `62973c3d…`
  Troubleshooting opened in the current Space from the menu bar and from the alert, with Artisan
  full screen and on a second desktop, as the tester reported
  ([that section](#troubleshooting-in-the-current-space-notarized-build-62973c3d)). See also
  [that run](#guided-recovery-after-a-loss-of-power-notarized-build-5bdc6388). With the earlier
  build `3195ebea…` two guided attempts failed at the power switch; see
  [that run](#guided-recovery-notarized-test-build-two-guided-failures-then-manual-recovery).
- The new alert wording ("Connection lost during an active session. The bridge stopped.") in a
  published build. On hardware it has been run from source at commit `f1825c9`, in the packaged
  ad hoc test build of `c6bfea8` (hash `61bb0351…`), and in the notarized test builds `3195ebea…`
  and `5bdc6388…`, where the logs show the stop and its reason; see
  [the source run](#idle-power-loss-test-with-source-commit-f1825c9),
  [the c6bfea8 package](#packaged-test-build-of-c6bfea8-idle-power-loss-and-manual-recovery) and
  the guided recovery runs.
- The bridge starting by itself with the ad hoc build `7630086f…`: reported, but the logs of that
  run show a start from the menu. It is confirmed for the signed build, and with the simulator.

Until these have been run, nothing here says that they work.

## Not verified

- Kaleido models other than the M2 Lite; other Macs; macOS versions other than 27.2
- **behavior during an Artisan crash or a loss of the Bluetooth link while the roaster is
  heating**, with or without the bridge. All hardware runs were idle with the heater off.
- how a lost Bluetooth link shows up on a port the bridge holds open while Artisan is attached, in
  general. It was seen twice, in the [idle power-loss test](#idle-power-loss-test) and its
  repeat from source, both times by unplugging the roaster's power: the port reported no error,
  and Artisan closed its virtual port after 5 s of silence before macOS reported the link as lost. With nobody attached it was seen once, in hardware result 3: the port
  reported no error, the bridge kept running, and the app showed "Waiting for Bluetooth"
- the link staying up for hours with no Artisan attached. In the one case on record it ended 6.5
  minutes after the last traffic, and the logs do not show why
- the signed build on a second Mac (not planned: the author has one Mac), and its first launch
  without a network connection

## Repeating the hardware test

Roaster idle, heater off.

1. Stop any running bridge (click OFF in Artisan first).
2. Restart the Mac, or reset Bluetooth the way that works on your Mac.
3. Open the app and click **Start Bridge** (the first time, through the setup guide).
4. Wait for "Waiting for Artisan" in the menu. If it stays at "Waiting for Bluetooth" for more than
   a minute, this start is silent: stop the bridge and go back to step 2. On the tested Mac one of
   five starts that directly followed a restart did not lead to a connection.
5. In Artisan (Comm Port = the virtual port), click **ON**. Expect ET and BT, and "Receiving
   roaster replies" in the menu.
6. **OFF → ON:** click OFF, wait 5 seconds, click ON. Expect ET and BT again.
7. **⌘Q → relaunch → ON:** quit Artisan while readings update, open it again, click ON. Expect ET
   and BT again.
8. Click OFF. Open the log from the menu: there should be exactly one "real port … opened" line
   since the start, and each session should end "detached, clean".
