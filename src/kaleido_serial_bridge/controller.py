"""Runs the bridge engine for the app and says what state it is in. No user interface code here.

The status shown to the user follows two rules:
- an open serial port proves nothing. Only replies of the roaster that were actually forwarded
  to Artisan count as communication.
- while no client is attached, what macOS reports about the Bluetooth link tells "waiting for
  Bluetooth" from "waiting for Artisan". That report is information; nothing acts on it.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum

from . import __version__
from .engine import EXIT_ABRUPT, EXIT_OK, EXIT_SETUP, EXIT_UPSTREAM, Bridge, Snapshot, log
from .linkstate import CONNECTED, UNKNOWN, LinkMonitor, bluetooth_link_state
from .ports import Port, discover
from .settings import Paths, Settings, home

REPLY_FRESH = 6.0        # a reply this recent is live communication
REPLY_QUIET = 30.0       # with nothing unanswered, a reply up to this old still counts (long sampling intervals)
FIRST_REPLY_GRACE = 5.0  # after Artisan attaches, wait this long before calling it "no replies"
RETRY_WINDOW = 12.0      # Artisan retries about every 7 s; between silent attempts the state stays "no replies"
BLUETOOTH_USUAL = 13     # seconds macOS took to report the roaster connected on the tested Mac
BLUETOOTH_PATIENCE = 45.0  # after this long without a connection, point to the recovery help


class State(StrEnum):
    STOPPED = 'stopped'
    FAILED = 'failed'                        # stopped by a failure the user has not seen yet
    WAITING_BLUETOOTH = 'waiting-bluetooth'  # port open, macOS has not connected the roaster
    WAITING_ARTISAN = 'waiting-artisan'      # port open, no client attached
    ARTISAN_ATTACHED = 'artisan-attached'    # client attached, first reply still due
    RECEIVING = 'receiving'                  # replies of the roaster are being forwarded
    NO_REPLIES = 'no-replies'                # client attached or retrying, the roaster does not answer


@dataclass(frozen=True)
class LinkView:
    state: str = ''              # '', connected, not connected, unknown
    changed_at: float = 0.0
    ever_connected: bool = False


@dataclass(frozen=True)
class Exit:
    code: int
    reason: str
    at: float


@dataclass(frozen=True)
class Status:
    state: State
    headline: str
    detail: str
    running: bool = False        # the real port is open
    attached: bool = False       # Artisan holds the virtual port
    session_open: bool = False   # Artisan has a session open at the roaster (stopping now cuts it off)
    attention: bool = False      # something the user should look at
    link: str = ''


def _seconds(value: float) -> str:
    return f'{value:.0f} s'


def derive_status(snapshot: Snapshot | None, link: LinkView, last_exit: Exit | None, now: float) -> Status:
    """The one place that decides what the user is told."""
    if snapshot is None or snapshot.exit_code is not None:
        if last_exit is not None and last_exit.code != EXIT_OK:
            headline = {
                EXIT_SETUP: 'Could not start the bridge',
                EXIT_UPSTREAM: 'Bluetooth port failed, bridge stopped',
                EXIT_ABRUPT: 'Connection lost during an active session. The bridge stopped.',
            }.get(last_exit.code, 'Bridge stopped after an error')
            return Status(State.FAILED, headline, last_exit.reason, attention=True, link=link.state)
        return Status(State.STOPPED, 'Bridge stopped', "The roaster's Bluetooth port is not open.", link=link.state)

    def running(state: State, headline: str, detail: str, attention: bool = False) -> Status:
        return Status(state, headline, detail, running=True, attached=snapshot.attached, session_open=snapshot.session_open,
                      attention=attention, link=link.state)

    if snapshot.attached:
        started = snapshot.session_started if snapshot.session_started is not None else now
        last_reply = snapshot.last_reply_at
        if last_reply is not None:
            age = now - last_reply
            if age <= REPLY_FRESH or (snapshot.unanswered == 0 and age <= REPLY_QUIET):
                return running(State.RECEIVING, 'Receiving roaster replies',
                              f'Last reply {_seconds(age)} ago. {snapshot.commands} commands in session {snapshot.session_number}.')
            if snapshot.unanswered:
                return running(State.NO_REPLIES, 'No replies from the roaster',
                              f'{snapshot.unanswered} commands unanswered, last reply {_seconds(age)} ago.', attention=True)
            return running(State.NO_REPLIES, 'No replies from the roaster',
                          f'Artisan is attached but has sent nothing for {_seconds(age)}.', attention=True)
        if now - started <= FIRST_REPLY_GRACE and snapshot.silent_sessions == 0:
            return running(State.ARTISAN_ATTACHED, 'Artisan attached, waiting for the first reply', 'Nothing has come back from the roaster yet.')
        if snapshot.silent_sessions:
            return running(State.NO_REPLIES, 'No replies from the roaster',
                          f'Artisan keeps asking and nothing comes back (attempt {snapshot.silent_sessions + 1}).', attention=True)
        if snapshot.unanswered:
            return running(State.NO_REPLIES, 'No replies from the roaster',
                          f'{snapshot.unanswered} commands unanswered, nothing has come back.', attention=True)
        return running(State.NO_REPLIES, 'No replies from the roaster', 'Artisan is attached but has not sent a command.', attention=True)

    if snapshot.silent_sessions and snapshot.last_detach_at is not None and now - snapshot.last_detach_at <= RETRY_WINDOW:
        return running(State.NO_REPLIES, 'No replies from the roaster',
                      f'Artisan tried {snapshot.silent_sessions} time(s) and got no answer.', attention=True)
    if link.state == CONNECTED:
        return running(State.WAITING_ARTISAN, 'Waiting for Artisan', 'Bluetooth is connected. In Artisan, click ON.')
    if link.state == UNKNOWN:
        return running(State.WAITING_ARTISAN, 'Waiting for Artisan',
                      'macOS reports no Bluetooth state for this port. Replies will show whether the roaster answers.')
    if link.ever_connected:
        return running(State.WAITING_BLUETOOTH, 'Waiting for Bluetooth',
                      f'macOS reports the roaster as no longer connected (for {_seconds(now - link.changed_at)}).', attention=True)
    waited = now - snapshot.opened_at
    if waited > BLUETOOTH_PATIENCE:
        return running(State.WAITING_BLUETOOTH, 'Waiting for Bluetooth',
                      f'Not connected after {_seconds(waited)}. This start is probably silent: see "No Readings?" in the menu.', attention=True)
    return running(State.WAITING_BLUETOOTH, 'Waiting for Bluetooth',
                  f'macOS has not connected the roaster yet ({_seconds(waited)}). About {BLUETOOTH_USUAL} s is normal.')


def configure_logging(paths: Paths) -> None:
    """The same log lines as the command line bridge, into a file that does not grow without bound."""
    paths.home.mkdir(mode=0o700, parents=True, exist_ok=True)
    for handler in list(log.handlers):
        log.removeHandler(handler)
    handler = logging.handlers.RotatingFileHandler(paths.log, maxBytes=1_000_000, backupCount=3, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s.%(msecs)03d %(levelname)-7s %(message)s', datefmt='%m-%d %H:%M:%S'))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


class BridgeController:

    def __init__(self, paths: Paths | None = None, link_query: Callable[[str], str] = bluetooth_link_state, port_pattern: str = '/dev/cu.*') -> None:
        self.paths = paths if paths is not None else Paths(home())
        self.link_query = link_query
        self.port_pattern = port_pattern
        self.settings = Settings.load(self.paths.settings)
        self.bridge: Bridge | None = None
        self.thread: threading.Thread | None = None
        self.monitor: LinkMonitor | None = None
        self.last_exit: Exit | None = None
        self._exit_event: Exit | None = None
        self._written = ''
        configure_logging(self.paths)

    # ---- settings

    @property
    def virtual_port(self) -> str:
        return str(self.paths.link)

    def needs_setup(self) -> bool:
        return not (self.settings.setup_done and self.settings.device)

    def ports(self) -> list[Port]:
        return discover(self.port_pattern)

    def save(self) -> None:
        self.settings.save(self.paths.settings)

    def choose_device(self, device: str) -> None:
        self.settings.device = device
        self.save()

    def finish_setup(self) -> None:
        self.settings.setup_done = True
        self.save()

    def set_auto_start(self, enabled: bool) -> None:
        self.settings.auto_start = enabled
        self.save()

    # ---- the bridge

    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self) -> tuple[bool, str]:
        """Opens the real port and starts forwarding. Returns (started, what went wrong)."""
        if self.running():
            return True, ''
        device = self.settings.device
        if not device:
            return False, 'No roaster port has been chosen yet. Open the Setup Guide.'
        if not os.path.exists(device):
            self.last_exit = Exit(EXIT_SETUP, f'{device} does not exist. Is Bluetooth on and the roaster paired?', time.time())
            return False, self.last_exit.reason
        log.info('Kaleido Serial Bridge %s (pid %d): starting on %s', __version__, os.getpid(), device)
        bridge = Bridge(device, 57600, self.virtual_port, keep_on_abrupt=False, trace=False, link_check=False)
        if not bridge.setup():
            bridge.teardown()
            self.last_exit = Exit(EXIT_SETUP, bridge.stop_reason or 'the port could not be opened', time.time())
            return False, self.last_exit.reason
        self.last_exit = None
        self._exit_event = None
        self.bridge = bridge
        self.monitor = LinkMonitor(device, idle=lambda: bridge.session is None, query=self.link_query)
        self.thread = threading.Thread(target=bridge.run, name='bridge', daemon=True)
        self.thread.start()
        self.monitor.start()
        return True, ''

    def stop(self, wait: float = 5.0) -> bool:
        """Stops the bridge: the virtual port goes away first, then the real port is closed. Returns True once stopped."""
        bridge, thread = self.bridge, self.thread
        if bridge is None or thread is None:
            return True
        bridge.request_stop()
        thread.join(wait)
        self.poll()
        return not thread.is_alive()

    def poll(self) -> Status:
        """To be called regularly. Notices that the bridge stopped, keeps status.json current, returns the status."""
        bridge, thread = self.bridge, self.thread
        if bridge is not None and thread is not None and not thread.is_alive():
            code = bridge.exit_code if bridge.exit_code is not None else EXIT_UPSTREAM
            self.last_exit = Exit(code, bridge.stop_reason, time.time())
            self._exit_event = self.last_exit
            if self.monitor is not None:
                self.monitor.stop()
            self.bridge = self.thread = self.monitor = None
        status = self.status()
        self._write_status(status)
        return status

    def take_exit(self) -> Exit | None:
        """The exit of the bridge since the last call, once."""
        event, self._exit_event = self._exit_event, None
        return event

    def acknowledge_failure(self) -> None:
        if self.last_exit is not None and self.last_exit.code != EXIT_OK:
            self.last_exit = Exit(EXIT_OK, self.last_exit.reason, self.last_exit.at)

    def link_view(self) -> LinkView:
        monitor = self.monitor
        return LinkView() if monitor is None else LinkView(monitor.state, monitor.changed_at, monitor.ever_connected)

    def status(self) -> Status:
        bridge = self.bridge
        return derive_status(None if bridge is None else bridge.snapshot(), self.link_view(), self.last_exit, time.time())

    def _write_status(self, status: Status) -> None:
        """A small machine readable copy of the status, for support and for tests."""
        bridge = self.bridge
        record = {
            'version': __version__, 'pid': os.getpid(), 'device': self.settings.device, 'virtual_port': self.virtual_port,
            'state': status.state.value, 'headline': status.headline, 'running': status.running, 'attached': status.attached,
            'session_open': status.session_open, 'link': status.link,
            'sessions': 0 if bridge is None else bridge.sessions,
            'last_exit': None if self.last_exit is None else asdict(self.last_exit),
        }
        text = json.dumps(record, sort_keys=True)
        if text == self._written:
            return
        self._written = text
        try:
            temporary = self.paths.status.with_suffix(f'.json.{os.getpid()}')
            temporary.write_text(json.dumps({**record, 'detail': status.detail, 'updated': time.time()}, indent=2) + '\n', encoding='utf-8')
            temporary.replace(self.paths.status)
        except OSError:
            pass

    def shutdown(self) -> None:
        self.stop()
        try:
            self.paths.status.unlink()
        except OSError:
            pass
