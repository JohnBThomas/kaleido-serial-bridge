"""Guided Bluetooth recovery: one attempt per click, after the roaster has been switched on again.

The sequence is the manual reset that worked on the tested M2 Lite after a loss of power:

1. check that the bridge is stopped (it never stops a running bridge)
2. restart the Bluetooth service (bluetoothd). This needs administrator rights: macOS shows its
   standard authorization dialog, and only that one command runs as root. The app itself keeps
   running as the user.
3. wait until the service answers again
4. switch Bluetooth off, wait at least two seconds, switch it on
5. wait until the roaster's serial port exists again
6. start the bridge, once
7. wait for real replies from the roaster after the user clicks ON in Artisan

Every wait has a limit. When a step fails or the authorization is cancelled, the attempt ends
there, says which step it was, and nothing further is done; the bridge is never started after a
failed step. Nothing here runs by itself: an attempt begins only when the user asks for one.

Switching Bluetooth off and on uses IOBluetoothPreferenceSetControllerPowerState, a function of
macOS's IOBluetooth framework that Apple does not document (blueutil uses the same one). If it is
missing or does not change the state in time, that step fails and the manual steps are shown.

The parts that touch macOS are in MacSystem; tests replace it.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from .controller import BridgeController, State

SERVICE_TIMEOUT = 20.0     # for bluetoothd to answer again after the restart
POWER_OFF_TIMEOUT = 10.0   # for Bluetooth to report "off"
POWER_OFF_HOLD = 2.0       # Bluetooth stays off at least this long, as in the manual reset
POWER_ON_TIMEOUT = 15.0    # for Bluetooth to report "on"
PORT_TIMEOUT = 45.0        # for macOS to create the roaster's serial port again
REPLY_TIMEOUT = 120.0      # for the first roaster reply after the bridge started

RESTART_COMMAND = '/usr/bin/pkill -x bluetoothd'  # a constant: nothing from outside goes into the privileged command


class Step(Enum):
    CHECK_STOPPED = 'Check that the bridge is stopped'
    RESTART_SERVICE = 'Restart the Bluetooth service'
    WAIT_SERVICE = 'Wait for the Bluetooth service'
    POWER_OFF = 'Turn Bluetooth off'
    WAIT_OFF = 'Wait for Bluetooth to turn off'
    POWER_ON = 'Turn Bluetooth on'
    WAIT_ON = 'Wait for Bluetooth to turn on'
    WAIT_PORT = "Wait for the roaster's serial port"
    START_BRIDGE = 'Start the bridge'
    WAIT_REPLIES = 'Wait for roaster replies'


class Phase(Enum):
    IDLE = 'idle'
    RUNNING = 'running'          # working through the steps
    WAITING_FOR_ARTISAN = 'waiting-for-artisan'  # the bridge has started; the user is to click ON
    SUCCEEDED = 'succeeded'      # roaster replies arrived through the bridge
    FAILED = 'failed'


@dataclass(frozen=True)
class Outcome:
    ok: bool
    cancelled: bool = False
    message: str = ''


class System(Protocol):
    def restart_service(self) -> Outcome: ...
    def service_running(self) -> bool: ...
    def power_state(self) -> bool | None: ...   # None: cannot be read
    def set_power(self, on: bool) -> bool: ...
    def port_exists(self, path: str) -> bool: ...


@dataclass(frozen=True)
class Progress:
    phase: Phase
    step: Step | None
    detail: str
    attempt: int


class Recovery:
    """One recovery attempt at a time, advanced by step() from the app's timer."""

    def __init__(self, controller: BridgeController, system: System, clock: Callable[[], float] = time.monotonic) -> None:
        self.controller = controller
        self.system = system
        self.clock = clock
        self.phase = Phase.IDLE
        self.step_now: Step | None = None
        self.detail = ''
        self.attempts = 0
        self.since = 0.0        # when the current step began
        self.off_at = 0.0       # when Bluetooth was switched off

    # ---- for the app

    @property
    def active(self) -> bool:
        return self.phase in (Phase.RUNNING, Phase.WAITING_FOR_ARTISAN)

    def progress(self) -> Progress:
        return Progress(self.phase, self.step_now, self.detail, self.attempts)

    def begin(self) -> bool:
        """Starts one attempt. Returns False, and does nothing, while an attempt is under way."""
        if self.active:
            return False
        self.attempts += 1
        self.phase = Phase.RUNNING
        self._enter(Step.CHECK_STOPPED, 'Checking that the bridge is stopped.')
        return True

    def step(self) -> None:
        """Does at most one step, or one look at what is being waited for. Never blocks, except while
        macOS shows its authorization dialog."""
        if not self.active or self.step_now is None:
            return
        handler = getattr(self, '_' + self.step_now.name.lower())
        handler()

    # ---- the steps

    def _check_stopped(self) -> None:
        if self.controller.running():
            self._fail('The bridge is running. Click OFF in Artisan and stop the bridge first; the recovery never stops it.')
            return
        device = self.controller.settings.device
        if not device:
            self._fail("No roaster port has been chosen yet. Open the Setup Guide.")
            return
        self._enter(Step.RESTART_SERVICE, 'Asking for permission to restart the Bluetooth service.')

    def _restart_service(self) -> None:
        outcome = self.system.restart_service()
        if outcome.cancelled:
            self._fail('The authorization was cancelled. Nothing was changed.')
        elif not outcome.ok:
            self._fail(f'The Bluetooth service could not be restarted: {outcome.message or "no reason given"}.')
        else:
            self._enter(Step.WAIT_SERVICE, 'Waiting for the Bluetooth service to come back.')

    def _wait_service(self) -> None:
        if self.system.service_running() and self.system.power_state() is not None:
            self._enter(Step.POWER_OFF, 'Turning Bluetooth off.')
        elif self._elapsed() > SERVICE_TIMEOUT:
            self._fail(f'The Bluetooth service did not answer within {SERVICE_TIMEOUT:.0f} s.')

    def _power_off(self) -> None:
        if not self.system.set_power(False):
            self._fail('macOS did not accept the request to turn Bluetooth off.')
            return
        self.off_at = self.clock()
        self._enter(Step.WAIT_OFF, 'Waiting for Bluetooth to turn off.')

    def _wait_off(self) -> None:
        if self.system.power_state() is False and self.clock() - self.off_at >= POWER_OFF_HOLD:
            self._enter(Step.POWER_ON, 'Turning Bluetooth on.')
        elif self._elapsed() > POWER_OFF_TIMEOUT:
            self._fail(f'Bluetooth did not report "off" within {POWER_OFF_TIMEOUT:.0f} s.')

    def _power_on(self) -> None:
        if not self.system.set_power(True):
            self._fail('macOS did not accept the request to turn Bluetooth on. Turn it on in Control Center.')
            return
        self._enter(Step.WAIT_ON, 'Waiting for Bluetooth to turn on.')

    def _wait_on(self) -> None:
        if self.system.power_state() is True:
            self._enter(Step.WAIT_PORT, "Waiting for the roaster's serial port.")
        elif self._elapsed() > POWER_ON_TIMEOUT:
            self._fail(f'Bluetooth did not report "on" within {POWER_ON_TIMEOUT:.0f} s. Turn it on in Control Center.')

    def _wait_port(self) -> None:
        device = self.controller.settings.device
        if self.system.port_exists(device):
            self._enter(Step.START_BRIDGE, 'Starting the bridge.')
        elif self._elapsed() > PORT_TIMEOUT:
            self._fail(f'{device} did not appear within {PORT_TIMEOUT:.0f} s. Is the roaster switched on and paired?')

    def _start_bridge(self) -> None:
        started, problem = self.controller.start()
        if not started:
            self._fail(f'The bridge could not be started: {problem}')
            return
        self.phase = Phase.WAITING_FOR_ARTISAN
        self._enter(Step.WAIT_REPLIES, 'The bridge has started. In Artisan, click ON. Waiting for replies from the roaster.')

    def _wait_replies(self) -> None:
        status = self.controller.status()
        if status.state is State.RECEIVING:
            self.phase = Phase.SUCCEEDED
            self.detail = 'Recovered: replies from the roaster are arriving through the bridge.'
        elif not status.running:
            self._fail(f'The bridge stopped before the roaster answered: {status.headline}')
        elif self._elapsed() > REPLY_TIMEOUT:
            self._fail(f'No reply from the roaster within {REPLY_TIMEOUT:.0f} s of the start. The bridge is still running.')

    # ---- bookkeeping

    def _enter(self, step: Step, detail: str) -> None:
        self.step_now = step
        self.detail = detail
        self.since = self.clock()

    def _elapsed(self) -> float:
        return self.clock() - self.since

    def _fail(self, detail: str) -> None:
        self.phase = Phase.FAILED
        self.detail = detail


# ---- macOS

class MacSystem:
    """The real thing. Every call is quick except restart_service, which waits for the user's answer."""

    IOBLUETOOTH = '/System/Library/Frameworks/IOBluetooth.framework/IOBluetooth'

    def __init__(self) -> None:
        self._library: Any = None

    def restart_service(self) -> Outcome:
        # NSAppleScript's "do shell script ... with administrator privileges" shows macOS's standard
        # authorization dialog and runs only this command as root. Must be called on the main thread.
        from Foundation import NSAppleScript  # pylint: disable=import-outside-toplevel
        source = f'do shell script "{RESTART_COMMAND}; exit 0" with administrator privileges'
        script = NSAppleScript.alloc().initWithSource_(source)
        _result, error = script.executeAndReturnError_(None)
        if error is None:
            return Outcome(True)
        number = int(error.get('NSAppleScriptErrorNumber', 0))
        if number == -128:  # userCanceledErr
            return Outcome(False, cancelled=True)
        return Outcome(False, message=str(error.get('NSAppleScriptErrorMessage', f'error {number}')))

    def service_running(self) -> bool:
        try:
            return subprocess.run(['/usr/bin/pgrep', '-x', 'bluetoothd'], capture_output=True, timeout=5, check=False).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _bluetooth(self) -> Any:
        if self._library is None:
            library = ctypes.CDLL(self.IOBLUETOOTH)
            library.IOBluetoothPreferenceGetControllerPowerState.restype = ctypes.c_int
            library.IOBluetoothPreferenceGetControllerPowerState.argtypes = []
            library.IOBluetoothPreferenceSetControllerPowerState.restype = None
            library.IOBluetoothPreferenceSetControllerPowerState.argtypes = [ctypes.c_int]
            self._library = library
        return self._library

    def power_state(self) -> bool | None:
        try:
            return bool(self._bluetooth().IOBluetoothPreferenceGetControllerPowerState())
        except (OSError, AttributeError):
            return None

    def set_power(self, on: bool) -> bool:
        try:
            self._bluetooth().IOBluetoothPreferenceSetControllerPowerState(1 if on else 0)
        except (OSError, AttributeError):
            return False
        return True

    def port_exists(self, path: str) -> bool:
        return bool(path) and os.path.exists(path)


def parts_available() -> str:
    """For the self-test: whether this app can reach what the recovery needs. Looks the parts up; calls none of them."""
    found = []
    try:
        library = ctypes.CDLL(MacSystem.IOBLUETOOTH)
        for name in ('IOBluetoothPreferenceGetControllerPowerState', 'IOBluetoothPreferenceSetControllerPowerState'):
            found.append(f'{name} {"found" if hasattr(library, name) else "MISSING"}')
    except OSError as e:
        found.append(f'IOBluetooth not loaded ({e})')
    try:
        from Foundation import NSAppleScript  # pylint: disable=import-outside-toplevel
        found.append('NSAppleScript found' if NSAppleScript is not None else 'NSAppleScript MISSING')
    except ImportError:
        found.append('NSAppleScript MISSING')
    return ', '.join(found)
