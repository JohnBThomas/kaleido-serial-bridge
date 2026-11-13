"""What macOS says about the Bluetooth link behind a serial port. Read-only, and information only.

The bridge itself never acts on this: whether the roaster communicates is decided by forwarded
replies alone. It is used to tell "waiting for Bluetooth" from "waiting for Artisan" while no
client is attached.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections.abc import Callable

CONNECTED = 'connected'
NOT_CONNECTED = 'not connected'
UNKNOWN = 'unknown'


def device_name(device: str) -> str:
    """The Bluetooth device name macOS derives a serial port from: /dev/cu.Roaster_SRSv6 -> Roaster_SRSv6."""
    name = os.path.basename(device)
    for prefix in ('cu.', 'tty.'):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name


def bluetooth_link_state(device: str) -> str:
    """What macOS reports for the Bluetooth device behind a /dev/cu.<name> port: 'connected', 'not connected' or 'unknown'.

    Read-only: asks system_profiler. Nothing is sent to the roaster.
    """
    name = device_name(device)
    try:
        out = subprocess.run(['/usr/sbin/system_profiler', 'SPBluetoothDataType', '-json'], capture_output=True, timeout=20, check=True).stdout
        data = json.loads(out)['SPBluetoothDataType'][0]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError):
        return UNKNOWN
    for key, state in (('device_connected', CONNECTED), ('device_not_connected', NOT_CONNECTED)):
        for entry in data.get(key, []):
            if name in entry:
                return state
    return UNKNOWN


class LinkMonitor:
    """Asks now and then, on its own thread, while the bridge runs and no client is attached."""

    FAST = 2.0        # seconds between questions while the roaster is not connected yet
    FAST_FOR = 90.0   # ... for this long after the start, then SLOW
    SLOW = 10.0
    STEADY = 30.0     # once connected, or if macOS has no state for the port

    def __init__(self, device: str, idle: Callable[[], bool], query: Callable[[str], str] = bluetooth_link_state) -> None:
        self.device = device
        self.idle = idle          # True while no client is attached; a session is judged by its replies instead
        self.query = query
        self.state = ''           # '' until the first answer
        self.started_at = time.time()
        self.changed_at = self.started_at
        self.ever_connected = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name='link-monitor', daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            if self.idle() or not self.state:
                state = self.query(self.device)
                if self._stop.is_set():
                    return
                if state != self.state:
                    self.state = state
                    self.changed_at = time.time()
                    if state == CONNECTED:
                        self.ever_connected = True
            if self.state == NOT_CONNECTED:
                wait = self.FAST if time.time() - self.started_at < self.FAST_FOR else self.SLOW
            elif self.state in (CONNECTED, UNKNOWN):
                wait = self.STEADY
            else:
                wait = self.FAST
            self._stop.wait(wait)
