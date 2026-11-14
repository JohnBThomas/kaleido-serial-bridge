"""Everything the app tells the user in more than a line: the setup guide and the help. No user interface code.

Kept in one place so that the windows, the README and the tests say the same thing.
"""

from __future__ import annotations

from dataclasses import dataclass

from .controller import BLUETOOTH_USUAL

ARTISAN_PORT_MENU = 'Config » Port… » ET/BT » Comm Port'


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    body: str


def setup_steps(device: str) -> list[Step]:
    """The first-run guide. device is the chosen physical port, or '' if none has been chosen yet."""
    direct = device or "the roaster's own port"
    return [
        Step('pair', 'Pair the roaster',
             'Switch the roaster on and connect to it once in Bluetooth settings. macOS then creates a serial port '
             'for it, named after the roaster, for example cu.Roaster_SRSv6.\n\n'
             'If Artisan already reads the roaster over Bluetooth on this Mac, it is paired: continue.'),
        Step('port', "Choose the roaster's serial port",
             'Pick the port of your roaster. It is the one Artisan uses today as its Comm Port. Ports whose name looks '
             'like a Kaleido are listed first; the choice is yours and is remembered.'),
        Step('start', 'Start the bridge',
             'In Artisan, click OFF first.\n\n'
             'On the setup this was developed on, macOS connected the roaster only on a first open of its port after a '
             'restart or a Bluetooth reset, and not on every one of those. Let that first open be the bridge: it opens the '
             'port once and keeps it open, while Artisan comes and goes.\n\n'
             f'After Start, "Waiting for Bluetooth" is normal for about {BLUETOOTH_USUAL} seconds. '
             'If it stays for a minute, see "No Readings?" in the menu.'),
        Step('artisan', 'Point Artisan at the virtual port',
             f'In Artisan open {ARTISAN_PORT_MENU}, paste the path below and click OK. Everything else in the '
             'Kaleido serial setup stays as it is (57600, 8, N, 1).\n\n'
             'Then click ON in Artisan. This window shows "Receiving roaster replies" as soon as readings flow.'),
        Step('aset', 'Keep two settings files',
             'Artisan can save its whole configuration to a file. Two files let you switch between the bridge and '
             'the direct connection:\n\n'
             '1.  Now, with the Comm Port set to the virtual port: Help » Save Settings… and name it artisan-bridge.aset\n\n'
             f'2.  Set the Comm Port back to {direct}, then Help » Save Settings… as artisan-direct.aset\n\n'
             '3.  Help » Load Settings… and pick artisan-bridge.aset to return to the bridge.\n\n'
             'From then on, Help » Load Settings… switches between the two.'),
    ]


@dataclass(frozen=True)
class Topic:
    title: str
    body: str


def help_topics(device: str) -> list[Topic]:
    direct = device or "the roaster's own port, for example /dev/cu.Roaster_SRSv6"
    return [
        Topic('No readings after Start',
              'The menu shows "Waiting for Bluetooth" for more than a minute, or "No replies from the roaster" while '
              'Artisan shows no temperatures.\n\n'
              'Most likely macOS did not connect the roaster for this open of its port. On the tested setup that happened on '
              'opens after the port had been closed, by Artisan or by an earlier start of the bridge, and also on some first '
              'opens after a reset. Waiting did not help there, and neither did clicking ON again.\n\n'
              '1.  In Artisan, click OFF.\n'
              '2.  Stop the bridge.\n'
              '3.  Reset Bluetooth yourself. Restarting the Mac is the reset that helped on the tested setup, but not every '
              'time: one first start after a restart still did not connect. Restarting the Bluetooth service in Terminal with '
              '"sudo pkill -x bluetoothd", or turning Bluetooth off and on, did not get the bridge connected there.\n'
              '4.  Start the bridge and wait for "Waiting for Artisan". If the menu stays at "Waiting for Bluetooth" for more '
              'than a minute, stop the bridge and restart the Mac once more.\n'
              '5.  In Artisan, click ON.\n\n'
              'No reset is known to bring the connection back every time. The bridge never resets Bluetooth and never reopens '
              'the port on its own.'),
        Topic('Back to direct Bluetooth',
              '1.  In Artisan, click OFF.\n'
              '2.  Stop the bridge. This closes the roaster\'s port.\n'
              f'3.  In Artisan, load artisan-direct.aset (Help » Load Settings…), or set {ARTISAN_PORT_MENU} back to {direct}.\n'
              '4.  Click ON.\n\n'
              'Because the port was just closed, macOS may again fail to connect on this next open. '
              'If Artisan shows no readings, reset Bluetooth as described above.'),
        Topic('When the bridge stops by itself',
              'Artisan vanished mid-session: Artisan crashed or was force quit while it was connected. It could not tell the '
              'roaster that it was leaving, so the bridge closed the port; the roaster sees the link drop exactly as it would '
              'without a bridge. Check the roaster, then reset Bluetooth and start the bridge again.\n\n'
              'Bluetooth port failed: the port reported an error or disappeared, for example because the roaster was '
              'switched off or went out of range. Artisan is told at once through its own port. Check the roaster, reset '
              'Bluetooth if needed, and start the bridge again.'),
        Topic('What the bridge does and does not do',
              'It passes bytes between Artisan and the roaster unchanged, including Artisan\'s own safety commands. '
              'It never answers for the roaster, never repeats a command, and never keeps the roaster\'s safety guard '
              'alive when Artisan is gone.\n\n'
              'It has been tested with the roaster idle and the heater off. What the roaster does if Artisan crashes or '
              'the Bluetooth link is lost while it is heating has not been verified, with or without the bridge. '
              'The bridge is not a safety device and is not meant for unattended operation. Stay with the roaster while it is hot.'),
    ]


STOP_WHILE_ATTACHED = (
    'Artisan is connected through the bridge.',
    'Stopping now takes the port away from Artisan like a Bluetooth failure: Artisan can no longer tell the roaster '
    'that it is leaving (CL AR), and the roaster sees the link drop.\n\nClick OFF in Artisan first, then stop the bridge.')

STOP_IDLE = (
    'Stop the bridge?',
    "This closes the roaster's Bluetooth port. macOS may not connect the roaster again on the next start. "
    'On the tested setup that took a restart of the Mac, and one restart was not always enough.')

FAILURE_ADVICE = {
    'setup': 'Nothing was changed. Check that Bluetooth is on, the roaster is paired and switched on, and that Artisan '
             'is not connected to the roaster directly.',
    'upstream': 'Artisan has been told through its own port. Check the roaster. Then reset Bluetooth if needed and start the bridge again.',
    'abrupt': 'Artisan went away without telling the roaster, so the bridge closed the port: the roaster sees the link drop, '
              'as it would without a bridge. Check the roaster. Then reset Bluetooth and start the bridge again.',
}
