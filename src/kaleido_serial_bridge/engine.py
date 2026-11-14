#!/usr/bin/env python3
"""Kaleido serial bridge for macOS: the engine.

This is the bridge of the command line prototype. The menu bar app runs it on a thread and only
looks at it (snapshot) and asks it to stop (request_stop).

Opens the Bluetooth serial port of a Kaleido roaster ONCE and keeps it open, and offers a local
pseudo terminal that Artisan uses as its Comm Port instead. Artisan can then disconnect and
reconnect (OFF -> ON, quit -> relaunch) without the real port ever being closed and reopened.

What the bridge does
- forwards bytes unchanged in both directions between one local client and the roaster;
  towards the roaster only whole command lines, in order, each at most once
- discards whatever arrives from the roaster while no client is listening
- drops, and never sends later, anything a client did not get delivered before it went away
  (a command the client had not finished writing is never sent at all)
- reports a failing real port and then stops, taking the client endpoint away

What the bridge never does
- it never sends a byte of its own to the roaster: no ping, no keep alive, no CL AR, no replay
- it never answers Artisan on behalf of the roaster
- it never closes and reopens the real port, and it never touches the Bluetooth stack

It reads Artisan's commands only to know whether Artisan left a session open at the roaster
(any command other than PI, TU and RD opens one, "CL AR" ends it). If the client closes the virtual
port while a session is open the bridge closes the real port, so the roaster sees the link drop
exactly as it would without a bridge, and stops. It cannot tell why the client closed it: Artisan
crashing or being force quit looks the same as Artisan giving up after the roaster stopped answering.
See docs/SAFETY.md.
"""

from __future__ import annotations

import collections
import errno
import fcntl
import logging
import os
import select
import signal
import time
from dataclasses import dataclass
from typing import IO

import serial  # pyserial

EXIT_OK = 0        # stopped on request
EXIT_SETUP = 2     # the real port or the client endpoint could not be set up
EXIT_UPSTREAM = 3  # the real port failed
EXIT_ABRUPT = 4    # the client closed the virtual port with a session open; the real port got closed on purpose

DEFAULT_DIR = os.path.join(os.path.expanduser('~'), '.kaleido-bridge')
DEFAULT_LINK = os.path.join(DEFAULT_DIR, 'cu.Roaster_bridge')

CLIENT_POLL = 0.05        # seconds between checks for a new client while none is attached
SILENCE_WARNING = 5.0     # warn if the roaster did not answer for this long while Artisan keeps asking
QUIET_BEFORE_CLOSE = 2.0  # a roaster silent this long when the client leaves is mentioned in the stop reason
STALL_LIMIT = 3.0         # the real port not taking data for this long counts as a failure
SIGINT_CONFIRM = 5.0      # a second Ctrl-C within this time stops the bridge during an open session
MAX_PENDING = 65536       # bytes kept for a side that is slow to take them
MAX_COMMAND = 4096        # a client sending this much without a line end is not speaking the Kaleido protocol

# Requests that neither open an Artisan session at the roaster nor change what it does.
NEUTRAL_TAGS = frozenset({'PI', 'TU', 'RD'})
SESSION_END = b'{[CL AR]}'

log = logging.getLogger('kaleido_bridge')


def error_name(error: OSError) -> str:
    code = error.errno
    return f"{errno.errorcode.get(code, str(code)) if code is not None else '?'} ({error.strerror})"


def command_tag(line: bytes) -> str | None:
    """Returns the tag of a command line like b'{[HP 30]}' ('HP'), or None if it is not a command."""
    if line.startswith(b'{[') and line.endswith(b']}') and len(line) > 4:
        return line[2:-2].split(b' ', 1)[0].decode('ascii', 'replace')
    return None


class SessionTracker:
    """What the roaster has been asked by Artisan, derived from the commands delivered to it.

    This only observes. A session is open from the first delivered command other than PI, TU and RD
    until "CL AR" is delivered, the command with which Artisan ends its safety guard.
    """

    def __init__(self) -> None:
        self.open = False
        self.opened_by = ''
        self.ended = False  # the current client ended a session with CL AR

    def new_client(self) -> None:
        self.ended = False

    def delivered(self, command: bytes) -> None:
        """Takes a command line that has been written to the real port completely."""
        command = command.strip()
        if command == SESSION_END:
            self.open = False
            self.opened_by = ''
            self.ended = True
        elif command_tag(command) not in NEUTRAL_TAGS and not self.open:
            self.open = True
            self.opened_by = command[:40].decode('ascii', 'replace')
            self.ended = False

    def client_gone(self) -> tuple[bool, str]:
        """Called when the client disappeared. Returns (clean, reason)."""
        if self.open:
            return False, f'a session was open at the roaster (opened by {self.opened_by}) and CL AR was not delivered'
        return True, ('Artisan ended its session with CL AR' if self.ended else 'no session was opened at the roaster')


@dataclass
class Session:
    number: int
    started: float
    spoke: bool = False          # the client has sent something; only then roaster data is passed on
    commands: int = 0            # commands delivered to the roaster
    to_roaster_bytes: int = 0
    to_client_bytes: int = 0
    unanswered: int = 0          # commands forwarded since the roaster last sent anything
    last_from_roaster: float | None = None
    last_to_roaster: float | None = None
    warned_silent: bool = False


@dataclass(frozen=True)
class Snapshot:
    """What a display needs to know about a running bridge. Taken from another thread, never written to."""
    exit_code: int | None
    stop_reason: str
    opened_at: float
    sessions: int
    attached: bool                 # a client holds the virtual port
    session_number: int
    session_started: float | None
    session_open: bool             # a session is open at the roaster (see SessionTracker)
    commands: int                  # delivered to the roaster in the current session
    reply_bytes: int               # passed on to the client in the current session
    unanswered: int                # commands delivered since the roaster last sent anything
    last_reply_at: float | None    # in the current session
    last_command_at: float | None  # in the current session
    silent_sessions: int           # finished sessions in a row in which the roaster answered nothing
    last_detach_at: float | None


class Bridge:

    def __init__(self, device: str, baudrate: int, link: str, keep_on_abrupt: bool, trace: bool, link_check: bool) -> None:
        self.device = device
        self.baudrate = baudrate
        self.link = link
        self.keep_on_abrupt = keep_on_abrupt
        self.trace = trace
        self.link_check = link_check

        self.port: serial.Serial | None = None
        self.real_fd = -1
        self.master = -1
        self.slave_name = ''
        self.lock_file: IO[str] | None = None
        self.opened_at = 0.0

        self.tracker = SessionTracker()
        self.session: Session | None = None
        self.sessions = 0
        self.client_hold = bytearray()       # the beginning of a command the client has not finished writing
        self.queue: collections.deque[bytes] = collections.deque()  # whole commands of the current client, not yet started
        self.in_flight = b''                 # the rest of a command the real port has taken only partly
        self.in_flight_command = b''
        self.to_roaster_since: float | None = None
        self.to_client = bytearray()         # from the roaster, not yet taken by the current client
        self.discarded = 0                   # roaster bytes dropped since the last session
        self.trace_partial = bytearray()

        self.exit_code: int | None = None
        self.stop_reason = ''                # why the bridge stopped, if it was not asked to
        self.silent_sessions = 0             # finished sessions in a row in which the roaster answered nothing
        self.last_detach_at: float | None = None
        self.wake_r, self.wake_w = os.pipe()
        os.set_blocking(self.wake_w, False)
        self.signals: list[int] = []
        self.sigint_at: float | None = None

    # ---- setup and teardown

    def setup(self) -> bool:
        os.makedirs(os.path.dirname(self.link), mode=0o700, exist_ok=True)
        self.lock_file = open(self.link + '.lock', 'w', encoding='ascii')  # noqa: SIM115  # held for the life of the bridge
        try:
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            log.error('another bridge is already serving %s', self.link)
            self.stop_reason = 'another bridge is already running'
            return False
        if os.path.lexists(self.link) and not os.path.islink(self.link):
            log.error('%s exists and is not a link left by a bridge; not touching it', self.link)
            self.stop_reason = f'{self.link} exists and was not created by the bridge'
            return False
        # The same open as Artisan (pyserial as used by pymodbus): non-blocking, exclusive lock, raw 8N1.
        try:
            self.port = serial.Serial(self.device, baudrate=self.baudrate, bytesize=8, parity='N', stopbits=1,
                                      timeout=0, write_timeout=0, exclusive=True)
        except (serial.SerialException, OSError) as e:
            log.error('cannot open %s: %s', self.device, e)
            log.error('nothing was changed. Is Bluetooth on, the roaster paired and powered, and Artisan disconnected from this port?')
            self.stop_reason = f'cannot open {self.device}: {e}'
            return False
        fd = self.port.fd
        assert fd is not None
        self.real_fd = fd
        os.set_blocking(self.real_fd, False)
        self.opened_at = time.time()
        log.info('real port %s opened (%s 8N1, fd %s). It is opened this one time and stays open until the bridge stops.',
                 self.device, self.baudrate, self.real_fd)

        self.master, slave = os.openpty()
        self.slave_name = os.ttyname(slave)
        os.close(slave)  # with no client attached a read from the master now returns end-of-file
        os.set_blocking(self.master, False)
        temp = f'{self.link}.{os.getpid()}'
        os.symlink(self.slave_name, temp)
        os.replace(temp, self.link)
        log.info('client endpoint ready: %s -> %s', self.link, self.slave_name)
        log.info('set the Comm Port in Artisan to: %s', self.link)
        return True

    def teardown(self) -> None:
        """Takes the client endpoint away first, then closes the real port."""
        if self.master >= 0:
            try:
                os.close(self.master)  # an attached client now gets an I/O error instead of silence
            except OSError:
                pass
            self.master = -1
        try:
            if os.path.islink(self.link) and os.readlink(self.link) == self.slave_name:
                os.unlink(self.link)
        except OSError:
            pass
        if self.port is not None:
            try:
                self.port.close()
            except (serial.SerialException, OSError):
                pass
            self.port = None
            log.info('real port %s closed after %.0f s. It was opened once and never reopened.', self.device, time.time() - self.opened_at)
            log.info('note: macOS may not reconnect on the next open of this port until Bluetooth has been reset')
        if self.lock_file is not None:
            self.lock_file.close()
            self.lock_file = None

    def stop(self, code: int) -> None:
        if self.exit_code is None:
            self.exit_code = code

    # ---- for the app: look at the bridge and ask it to stop, from another thread

    def snapshot(self) -> Snapshot:
        session = self.session
        return Snapshot(
            exit_code=self.exit_code, stop_reason=self.stop_reason, opened_at=self.opened_at, sessions=self.sessions,
            attached=session is not None,
            session_number=session.number if session is not None else 0,
            session_started=session.started if session is not None else None,
            session_open=self.tracker.open,
            commands=session.commands if session is not None else 0,
            reply_bytes=session.to_client_bytes if session is not None else 0,
            unanswered=session.unanswered if session is not None else 0,
            last_reply_at=session.last_from_roaster if session is not None else None,
            last_command_at=session.last_to_roaster if session is not None else None,
            silent_sessions=self.silent_sessions, last_detach_at=self.last_detach_at)

    def request_stop(self) -> None:
        """Stops the bridge like SIGTERM does: at once, taking the virtual port away first."""
        self.signals.append(signal.SIGTERM)
        try:
            os.write(self.wake_w, b'x')
        except OSError:
            pass

    # ---- signals

    def on_signal(self, signum: int, _frame: object) -> None:
        self.signals.append(signum)
        try:
            os.write(self.wake_w, b'x')
        except OSError:
            pass

    def handle_signals(self) -> None:
        while self.signals:
            signum = self.signals.pop(0)
            if signum == signal.SIGINT and self.session is not None and self.tracker.open:
                now = time.time()
                if self.sigint_at is None or now - self.sigint_at > SIGINT_CONFIRM:
                    self.sigint_at = now
                    log.warning('Artisan is connected and has a session open at the roaster. Stopping now cuts it off like a '
                                'Bluetooth failure: Artisan cannot send CL AR any more. Turn Artisan OFF first, or press '
                                'Ctrl-C again within %.0f s to stop anyway.', SIGINT_CONFIRM)
                    continue
            if self.session is not None:
                log.warning('stopping on %s while Artisan is attached; Artisan loses the port%s', signal.Signals(signum).name,
                            ' and the roaster is left with an open session and a dropped link' if self.tracker.open else '')
            else:
                log.info('stopping on %s', signal.Signals(signum).name)
            self.stop(EXIT_OK)

    # ---- the real port (roaster side)

    def upstream_failed(self, what: str) -> None:
        log.error('BLUETOOTH PORT FAILURE: %s', what)
        if self.session is not None:
            log.error('session %d: taking the port away from Artisan so that it reports the disconnect', self.session.number)
        log.error('the bridge stops. It does not reopen the port or reset Bluetooth; do that yourself, then start the bridge again.')
        self.stop_reason = f'Bluetooth port failure: {what}'
        self.stop(EXIT_UPSTREAM)

    def read_real(self) -> None:
        """To be called only when select() reported the real port as readable.

        The port is in raw mode with VMIN=0/VTIME=0 (as set by pyserial): a read without data waiting returns
        nothing. Readable and nothing to read means the device is gone; pyserial, and thus Artisan, reads it the same way.
        """
        try:
            data = os.read(self.real_fd, 4096)
        except BlockingIOError:
            return
        except OSError as e:
            self.upstream_failed(f'read error {error_name(e)}')
            return
        if not data:
            self.upstream_failed('the port reported end-of-file (device disconnected)')
            return
        session = self.session
        if session is None or not session.spoke:
            # nobody asked for this: a late answer to a client that is gone
            self.discarded += len(data)
            log.debug('discarded %d bytes from the roaster (no client is listening)', len(data))
            return
        session.to_client_bytes += len(data)
        session.last_from_roaster = time.time()
        session.unanswered = 0
        self.silent_sessions = 0
        session.warned_silent = False
        if self.trace:
            self.trace_lines(data)
        if len(self.to_client) + len(data) > MAX_PENDING:
            log.warning('session %d: Artisan is not reading; dropped %d bytes from the roaster', session.number, len(data))
            return
        self.to_client += data
        self.flush_to_client()

    def pending_to_roaster(self) -> bool:
        return bool(self.in_flight or self.queue)

    def flush_to_roaster(self) -> None:
        """Writes whole commands to the real port, one after the other."""
        while True:
            if not self.in_flight:
                if not self.queue:
                    self.to_roaster_since = None
                    return
                self.in_flight = self.in_flight_command = self.queue.popleft()
            try:
                written = os.write(self.real_fd, self.in_flight)
            except BlockingIOError:
                written = 0
            except OSError as e:
                self.upstream_failed(f'write error {error_name(e)}')
                return
            self.in_flight = self.in_flight[written:]
            if self.in_flight:
                if self.to_roaster_since is None:
                    self.to_roaster_since = time.time()
                return
            # delivered completely
            self.tracker.delivered(self.in_flight_command)
            if self.session is not None:
                self.session.commands += 1
                self.session.unanswered += 1
                self.session.last_to_roaster = time.time()
                if self.trace:
                    log.debug('session %d  > %s', self.session.number, self.in_flight_command.strip().decode('ascii', 'replace'))

    # ---- the client endpoint (Artisan side)

    def probe_client(self) -> None:
        """No client is attached: a read from the master returns end-of-file until one opens the endpoint."""
        try:
            data = os.read(self.master, 4096)
        except BlockingIOError:
            self.attach()
            return
        except OSError as e:
            log.error('client endpoint failed: %s', e)
            self.stop(EXIT_SETUP)
            return
        if data:
            self.attach()
            self.from_client(data)

    def attach(self) -> None:
        self.sessions += 1
        self.session = Session(self.sessions, time.time())
        self.tracker.new_client()
        self.client_hold.clear()
        self.queue.clear()
        self.to_client.clear()
        self.trace_partial.clear()
        # drop whatever the roaster sent while nobody was listening (the session has not spoken yet)
        for _ in range(64):
            if self.exit_code is not None or not select.select([self.real_fd], [], [], 0)[0]:
                break
            self.read_real()
        log.info('session %d: Artisan attached | real port open for %.0f s, opened once, never reopened | discarded %d stale bytes from the roaster',
                 self.sessions, time.time() - self.opened_at, self.discarded)
        self.discarded = 0

    def read_client(self) -> None:
        try:
            data = os.read(self.master, 4096)
        except BlockingIOError:
            return
        except OSError:
            data = b''
        if data:
            self.from_client(data)
        else:
            self.client_gone()

    def from_client(self, data: bytes) -> None:
        session = self.session
        assert session is not None
        session.spoke = True
        session.to_roaster_bytes += len(data)
        self.client_hold += data
        end = self.client_hold.rfind(b'\n')
        if end < 0 and len(self.client_hold) > MAX_COMMAND:
            log.warning('session %d: %d bytes without a line end; passing them on as they are', session.number, len(self.client_hold))
            end = len(self.client_hold) - 1
        if end < 0:
            return  # the command is not complete yet; nothing of it is sent
        whole = bytes(self.client_hold[:end + 1])
        del self.client_hold[:end + 1]
        self.queue.extend(whole.splitlines(keepends=True))
        if sum(map(len, self.queue)) > MAX_PENDING:
            self.upstream_failed('the port does not take data any more (too much pending)')
            return
        self.flush_to_roaster()

    def flush_to_client(self) -> None:
        if not self.to_client:
            return
        try:
            written = os.write(self.master, self.to_client)
        except BlockingIOError:
            return
        except OSError:
            self.client_gone()  # no client holds the endpoint any more
            return
        del self.to_client[:written]

    def client_gone(self) -> None:
        session = self.session
        if session is None:
            return
        # Nothing a client left behind is delivered later: commands that were not started are dropped, and so is
        # a command the client had not finished writing. Only a command that is already partly on the wire is completed.
        dropped = len(self.queue) + (1 if self.client_hold else 0)
        self.queue.clear()
        self.client_hold.clear()
        self.to_client.clear()
        self.session = None
        self.last_detach_at = time.time()
        if session.commands and not session.to_client_bytes:
            self.silent_sessions += 1
        clean, reason = self.tracker.client_gone()
        now = time.time()
        summary = (f'after {now - session.started:.1f} s | {session.commands} commands delivered to the roaster, '
                   f'{session.to_client_bytes} bytes passed to Artisan'
                   + (f', {dropped} undelivered command(s) dropped' if dropped else ''))
        if clean:
            log.info('session %d: Artisan detached, clean (%s) %s | real port stays open', session.number, reason, summary)
            return
        # What the bridge saw of the roaster just before: the one hint it has about why the port was closed.
        quiet = ''
        if session.unanswered and session.last_to_roaster is not None:
            silent_for = now - (session.last_from_roaster if session.last_from_roaster is not None else session.started)
            if silent_for >= QUIET_BEFORE_CLOSE:
                quiet = f'The roaster had not answered for {silent_for:.1f} s before that ({session.unanswered} commands unanswered).'
        log.error('session %d: CONNECTION LOST during an active session: the virtual port was closed and %s %s%s', session.number,
                  reason, summary, f' | {quiet}' if quiet else '')
        log.error('the bridge cannot tell why: Artisan crashing or being force quit looks the same as Artisan giving up after the roaster '
                  'stopped answering, for example because the roaster lost power or its Bluetooth link.')
        if self.keep_on_abrupt:
            log.error('real port kept open because of --keep-link-on-abrupt-exit: the roaster still has an Artisan session open, '
                      'the link is up and nobody is talking to it. The bridge sends nothing.')
            return
        log.error('closing the real port so that the roaster sees the link drop, exactly as it would without the bridge. '
                  'The bridge sent nothing to the roaster.')
        self.stop_reason = f'Artisan\'s virtual port was closed while {reason}.' + (f' {quiet}' if quiet else '')
        self.stop(EXIT_ABRUPT)

    def trace_lines(self, data: bytes) -> None:
        self.trace_partial += data
        while True:
            end = self.trace_partial.find(b'\n')
            if end < 0:
                break
            line = bytes(self.trace_partial[:end]).strip()
            del self.trace_partial[:end + 1]
            log.debug('session %d  < %s', self.sessions, line.decode('ascii', 'replace'))

    # ---- main loop

    def housekeeping(self) -> None:
        now = time.time()
        if self.to_roaster_since is not None and now - self.to_roaster_since > STALL_LIMIT:
            self.upstream_failed(f'the port has not taken data for {STALL_LIMIT:.0f} s')
            return
        session = self.session
        if session is not None and session.unanswered >= 2 and not session.warned_silent and session.last_to_roaster is not None:
            reference = session.last_from_roaster if session.last_from_roaster is not None else session.started
            if now - reference > SILENCE_WARNING:
                session.warned_silent = True
                log.warning('session %d: the roaster has not answered for %.0f s (%d commands unanswered). The bridge keeps forwarding '
                            'and answers nothing itself; Artisan will show the timeout. If this persists the Bluetooth link is down.',
                            session.number, now - reference, session.unanswered)

    def run(self) -> int:
        while self.exit_code is None:
            self.handle_signals()
            if self.exit_code is not None:
                break
            if self.session is None:
                self.probe_client()
                if self.exit_code is not None:
                    break
            readers = [self.real_fd, self.wake_r]
            writers = []
            if self.session is not None:
                readers.append(self.master)
                if self.to_client:
                    writers.append(self.master)
            if self.pending_to_roaster():
                writers.append(self.real_fd)
            try:
                readable, writable, _ = select.select(readers, writers, [], CLIENT_POLL if self.session is None else 0.5)
            except InterruptedError:
                continue
            if self.wake_r in readable:
                os.read(self.wake_r, 64)
            # the client first: what it sent has to be read before its close throws it away
            if self.session is not None and self.master in readable:
                self.read_client()
            if self.exit_code is None and self.real_fd in readable:
                self.read_real()
            if self.exit_code is None and self.real_fd in writable:
                self.flush_to_roaster()
            if self.exit_code is None and self.session is not None and self.master in writable:
                self.flush_to_client()
            if self.exit_code is None:
                self.housekeeping()
        self.teardown()
        log.info('bridge stopped (exit code %d) after %d session(s)', self.exit_code, self.sessions)
        return self.exit_code
