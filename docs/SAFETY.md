# Safety notes

**The bridge is not a safety device.** It does not make a roaster safer and it is not meant for
unattended operation. This page describes what it passes on and what it does when something goes
wrong, so that its behavior can be judged. The table was tested with a simulated roaster. On
hardware, only its first row has been observed; see [EVIDENCE.md](EVIDENCE.md).

Artisan arms the roaster's safety guard with `SC AR` after connecting and ends it with `CL AR`
when it disconnects on purpose (OFF, quit). **What the Kaleido firmware does while the guard is
armed is not publicly documented.** This page therefore states what the roaster gets to *see* in
each situation, with a direct Bluetooth connection and through the bridge.

## Rules the bridge follows

1. Artisan's commands and the roaster's replies are forwarded without changing their content. A
   command is held until its line is complete and is then sent whole, in order, at most once. A
   command Artisan had not finished writing is never sent.
2. The bridge never sends anything of its own to the roaster: no ping, no keep-alive, no `CL AR`,
   no replay. It never answers Artisan on behalf of the roaster.
3. Whatever arrives from the roaster while no client is attached, or before a new client has sent
   its first byte, is discarded. Commands a client had queued but that were not delivered when it
   went away are discarded.
4. The roaster's port is opened once per start and never reopened. Bluetooth is never reset.
5. It watches which commands were delivered, for one purpose: to know whether Artisan left a
   session open at the roaster. `PI`, `TU` and `RD` only read; any other command opens a session;
   `CL AR` ends it.

## What the roaster sees

| Event | Direct connection | Through the bridge | The app |
|---|---|---|---|
| Artisan OFF or quit | `CL AR`, then the link drops | `CL AR` (answered by the roaster itself); the link stays up; nothing more is sent | keeps the port open, shows "Waiting for Artisan" |
| Artisan crashes or is force quit with a session open | no `CL AR`, commands stop, link drops | no `CL AR`, commands stop, **link drops** a few milliseconds later | closes the port on purpose, removes the virtual port, stops, shows an alert |
| Artisan hangs but keeps its port open | no `CL AR`, commands stop, link stays up | the same | keeps forwarding; shows "No replies from the roaster" once Artisan has been silent for 30 s |
| Artisan goes away before `SC AR` (a failed handshake) | only `PI`/`TU`, then the link drops | only `PI`/`TU`; link stays up | keeps the port open |
| The app is stopped, quits or crashes with a session open | — | no `CL AR`, commands stop, link drops | Artisan gets an I/O error on its port and reports the disconnect. Stop and Quit warn first. |
| The Bluetooth port fails (error, device gone) | — | — | stops, takes the virtual port away so Artisan reports the disconnect, shows an alert. No reopen, no reset |
| The roaster stops answering, link still up | Artisan times out | Artisan times out the same way; no answer is made up, not even for `CL AR` | shows "No replies from the roaster" |

Every "through the bridge" entry is covered by a test against the simulated roaster
(`tests/test_engine.py`, `tests/test_controller.py`, `tests/test_app.py`).

### Why the bridge closes the port when Artisan vanishes

If Artisan disappears while it has a session open, keeping the link up would leave the roaster
with an armed guard, a live link, and nobody talking to it. Whether the roaster then protects
itself depends on firmware behaviour nobody has verified. So the bridge makes that case look
as it does without a bridge: the link drops. This is a choice about what the bridge passes on, not a
claim about what the roaster then does. The price is a Bluetooth reset after a crash.

The command line bridge has an option to keep the link instead (`--keep-link-on-abrupt-exit`).
The app does not offer it.

A hung Artisan (third row) is the one case the bridge can neither improve nor worsen.

## Not verified

- **Anything while heating.** All hardware testing was done with the roaster idle and the heater
  off. What the roaster does when its guard is armed and (a) the commands stop while the link stays
  up, or (b) the link drops, is unknown, with or without the bridge.
- How a lost Bluetooth link shows up on a port the bridge holds open: as an error (the bridge then
  stops and says so) or as silence (the app then shows "No replies" once Artisan is asking, and
  "Waiting for Bluetooth" while idle, if macOS reports the link as gone).
- Whether the link stays up for hours while no client is attached.
- Roasters other than the M2 Lite, and macOS versions other than 27.2.
- On hardware, every row of the table above except the first (a normal OFF followed by ON).
