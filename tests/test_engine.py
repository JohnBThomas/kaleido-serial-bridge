"""Tests of the bridge engine against a simulated roaster. No hardware, no Bluetooth.

These are the tests of the command line prototype, unchanged except for where the code lives.

The "real port" is a pseudo terminal with sim_roaster.SimRoaster behind it. The simulator records
what a roaster would observe: every command, and whether a port is open on it (its "link").
The bridge always runs as a separate process, as it does in real use.

Optional: with Artisan's source available (ARTISAN_SRC=/path/to/artisan/src) the last test
class drives Artisan's own Kaleido code.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import serial

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / 'tools'))

from kaleido_serial_bridge.engine import EXIT_ABRUPT, EXIT_OK, EXIT_SETUP, EXIT_UPSTREAM, SessionTracker, command_tag  # noqa: E402
from sim_roaster import SimRoaster  # noqa: E402

HANDSHAKE = ['{[PI]}', '{[TU C]}', '{[SC AR]}']


def wait_for(condition: Callable[[], object], timeout: float = 5.0, what: str = 'condition') -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError(f'timed out waiting for {what}')


class BridgeProcess:

    def __init__(self, directory: Path, device: str, *options: str) -> None:
        self.link = directory / 'cu.Roaster_bridge'
        self.log = directory / 'bridge.log'
        self.process = subprocess.Popen(
            [sys.executable, '-m', 'kaleido_serial_bridge.cli', device, '--link', str(self.link), '--no-link-check', '--trace', *options],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_for(lambda: self.link.is_symlink() or self.process.poll() is not None, what='the bridge to start')

    def text(self) -> str:
        return self.log.read_text(encoding='utf-8') if self.log.exists() else ''

    def wait_exit(self, timeout: float = 5.0) -> int:
        return self.process.wait(timeout)

    def running(self) -> bool:
        return self.process.poll() is None

    def stop(self) -> None:
        if self.running():
            self.process.terminate()
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(5)


class Client:
    """Talks to a port the way Artisan does: pyserial, exclusive, whole command lines."""

    def __init__(self, port: Path | str) -> None:
        self.port = serial.Serial(str(port), 57600, bytesize=8, parity='N', stopbits=1, timeout=1.0, exclusive=True)

    def ask(self, command: str) -> bytes:
        self.port.write(command.encode('ascii') + b'\n')
        return self.port.readline()

    def handshake(self) -> list[bytes]:
        return [self.ask(command) for command in HANDSHAKE]

    def off(self) -> bytes:
        """What Artisan does on OFF and on quit."""
        answer = self.ask('{[CL AR]}')
        self.port.close()
        return answer

    def vanish(self) -> None:
        """What the operating system does with the port of a process that died."""
        self.port.close()


@pytest.fixture
def sim() -> Iterator[SimRoaster]:
    roaster = SimRoaster()
    yield roaster
    roaster.close()


@pytest.fixture
def start_bridge(tmp_path: Path, sim: SimRoaster) -> Iterator[Callable[..., BridgeProcess]]:
    started: list[BridgeProcess] = []

    def start(*options: str, device: str | None = None) -> BridgeProcess:
        bridge = BridgeProcess(tmp_path, sim.device if device is None else device, *options)
        started.append(bridge)
        return bridge

    yield start
    for bridge in started:
        bridge.stop()


@pytest.fixture
def bridge(start_bridge: Callable[..., BridgeProcess]) -> BridgeProcess:
    return start_bridge()


def fake_artisan(port: Path, *options: str) -> subprocess.Popen[str]:
    process = subprocess.Popen([sys.executable, str(HERE / 'fake_artisan.py'), str(port), *options], stdout=subprocess.PIPE, text=True)
    assert process.stdout is not None
    assert process.stdout.readline().startswith('READY'), 'the handshake did not complete'
    return process


class TestSessionTracker:

    def test_command_tag(self) -> None:
        assert command_tag(b'{[PI]}') == 'PI'
        assert command_tag(b'{[HP 30]}') == 'HP'
        assert command_tag(b'{0,BT:100.0}') is None
        assert command_tag(b'') is None

    def test_reading_never_opens_a_session(self) -> None:
        tracker = SessionTracker()
        for command in (b'{[PI]}\n', b'{[TU C]}\n', b'{[RD A0]}\n'):
            tracker.delivered(command)
        assert tracker.client_gone() == (True, 'no session was opened at the roaster')

    def test_guard_opens_and_cl_ar_ends_a_session(self) -> None:
        tracker = SessionTracker()
        tracker.delivered(b'{[SC AR]}\n')
        assert tracker.open
        clean, reason = tracker.client_gone()
        assert not clean
        assert '{[SC AR]}' in reason
        tracker.delivered(b'{[CL AR]}\r\n')
        assert tracker.client_gone() == (True, 'Artisan ended its session with CL AR')

    def test_any_control_command_opens_a_session(self) -> None:
        for command in (b'{[HP 30]}', b'{[FC 50]}', b'{[HS 1]}', b'{[TS 200]}', b'{[EV 2]}', b'{[XX 1]}', b'garbage'):
            tracker = SessionTracker()
            tracker.delivered(command)
            assert tracker.open, command

    def test_a_control_command_after_cl_ar_reopens_the_session(self) -> None:
        tracker = SessionTracker()
        for command in (b'{[SC AR]}', b'{[CL AR]}', b'{[HP 30]}'):
            tracker.delivered(command)
        assert not tracker.client_gone()[0]

    def test_a_read_request_after_cl_ar_keeps_it_ended(self) -> None:
        tracker = SessionTracker()
        for command in (b'{[SC AR]}', b'{[CL AR]}', b'{[RD A0]}'):
            tracker.delivered(command)
        assert tracker.client_gone()[0]


class TestForwarding:

    def test_handshake_and_readings_pass_through_unchanged(self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        client = Client(bridge.link)
        assert client.handshake() == [b'{0}\r\n', b'{0,TU:C}\r\n', b'{0,SN:SIM000000001}\r\n']
        reading = client.ask('{[RD A0]}')
        assert reading.startswith(b'{0,BT:') and reading.endswith(b'}\r\n')
        assert client.off() == b'{0,SN:SIM000000001}\r\n'
        assert sim.commands() == [*HANDSHAKE, '{[RD A0]}', '{[CL AR]}']

    def test_off_on_keeps_the_real_port_open(self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        for _ in range(3):  # ON ... OFF, three times
            client = Client(bridge.link)
            client.handshake()
            assert client.ask('{[RD A0]}').startswith(b'{0,BT:')
            client.off()
            time.sleep(0.3)
        # every command arrived exactly once and in order; nothing was replayed
        assert sim.commands() == [*HANDSHAKE, '{[RD A0]}', '{[CL AR]}'] * 3
        assert sim.links() == ['up']  # opened once, never closed
        assert not sim.guard_armed
        text = bridge.text()
        assert text.count('opened (57600 8N1') == 1
        assert text.count('detached, clean (Artisan ended its session with CL AR)') == 3
        assert bridge.running()

    def test_quit_and_relaunch_keeps_the_real_port_open(self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        for _ in range(2):  # a process that ends like Artisan's quit, then a new one
            process = fake_artisan(bridge.link, '--polls', '3', '--off')
            assert process.wait(10) == 0
        assert sim.commands() == [*HANDSHAKE, *['{[RD A0]}'] * 3, '{[CL AR]}'] * 2
        assert sim.links() == ['up']
        assert bridge.running()

    def test_a_second_client_is_refused(self, bridge: BridgeProcess) -> None:
        first = Client(bridge.link)
        first.handshake()
        with pytest.raises(serial.SerialException, match='Could not exclusively lock port'):
            Client(bridge.link)
        assert first.ask('{[RD A0]}').startswith(b'{0,BT:')  # the first client is not disturbed
        first.off()

    def test_the_real_port_cannot_be_shared_with_a_direct_client(self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        with pytest.raises(serial.SerialException, match='Could not exclusively lock port'):
            Client(sim.device)
        assert bridge.running()


class TestStaleData:

    def test_a_late_answer_between_sessions_is_discarded(self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        first = Client(bridge.link)
        first.handshake()
        first.off()
        time.sleep(0.2)
        sim.send_unsolicited(b'{0,LATE:1}\r\n')
        time.sleep(0.3)
        second = Client(bridge.link)
        assert second.ask('{[PI]}') == b'{0}\r\n'  # not the late answer
        second.vanish()
        wait_for(lambda: 'discarded 12 stale bytes' in bridge.text(), what='the discard to be logged')

    def test_data_arriving_before_the_client_speaks_is_discarded(self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        client = Client(bridge.link)
        wait_for(lambda: 'session 1: Artisan attached' in bridge.text(), what='the client to be noticed')
        sim.send_unsolicited(b'{0,LATE:2}\r\n')
        time.sleep(0.3)
        assert client.ask('{[PI]}') == b'{0}\r\n'
        client.vanish()

    def test_an_unfinished_command_is_never_sent(self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        first = Client(bridge.link)
        assert first.ask('{[PI]}') == b'{0}\r\n'
        first.port.write(b'{[HP 5')  # dies while writing a heater command
        time.sleep(0.2)
        first.vanish()
        time.sleep(0.2)
        second = Client(bridge.link)
        second.handshake()
        second.off()
        # the roaster never saw any part of it, and the next session was not glued onto it
        assert sim.commands() == ['{[PI]}', *HANDSHAKE, '{[CL AR]}']
        assert sim.links() == ['up']
        assert '1 undelivered command(s) dropped' in bridge.text()


class TestFailures:

    def test_normal_disconnect(self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        client = Client(bridge.link)
        client.handshake()
        assert sim.guard_armed
        client.off()
        time.sleep(1.0)
        assert not sim.guard_armed            # ended by Artisan's own CL AR
        assert sim.links() == ['up']          # the link stays
        assert sim.commands()[-1] == '{[CL AR]}'  # and the bridge said nothing afterwards
        assert bridge.running()

    def test_abrupt_artisan_exit_drops_the_link(self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        process = fake_artisan(bridge.link)
        wait_for(lambda: sim.commands().count('{[RD A0]}') >= 3, what='polling')
        process.send_signal(signal.SIGKILL)
        process.wait(5)
        assert bridge.wait_exit() == EXIT_ABRUPT
        wait_for(lambda: sim.links() == ['up', 'down'], what='the link to drop')
        assert sim.guard_armed                       # nobody ended the guard on Artisan's behalf
        assert '{[CL AR]}' not in sim.commands()
        assert set(sim.commands()) == {*HANDSHAKE, '{[RD A0]}'}  # nothing but what Artisan itself sent
        assert not bridge.link.exists()
        text = bridge.text()
        assert ('CONNECTION LOST during an active session: the virtual port was closed and a session was open at the roaster '
                '(opened by {[SC AR]})') in text
        assert 'the bridge cannot tell why' in text
        assert 'had not answered' not in text  # the roaster was answering until Artisan went
        assert 'closing the real port so that the roaster sees the link drop' in text

    def test_artisan_timing_out_on_a_silent_roaster_drops_the_link_and_says_the_roaster_was_silent(
            self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        # Seen on hardware: the roaster lost power, its port reported nothing, and Artisan's read timeout
        # closed the virtual port without CL AR. To the bridge that is the same as a crash.
        client = Client(bridge.link)
        client.handshake()
        sim.mute = True  # the port stays open and reports no error; nothing comes back
        client.port.timeout = 0.3
        for _ in range(3):
            assert client.ask('{[RD A0]}') == b''
        time.sleep(1.5)
        client.vanish()  # Artisan gives up: it closes the port and sends no CL AR
        assert bridge.wait_exit() == EXIT_ABRUPT  # the stop behaviour is the same as for a crash
        wait_for(lambda: sim.links() == ['up', 'down'], what='the link to drop')
        assert sim.guard_armed and '{[CL AR]}' not in sim.commands()
        assert not bridge.link.exists()
        text = bridge.text()
        assert 'CONNECTION LOST during an active session' in text
        assert 'The roaster had not answered for' in text and '(3 commands unanswered)' in text
        assert 'the bridge cannot tell why' in text

    def test_a_silent_client_that_keeps_the_port_open_is_left_alone(self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        client = Client(bridge.link)
        client.handshake()
        seen = len(sim.commands())
        time.sleep(1.5)  # a hung Artisan: the port stays open, nothing is sent
        assert bridge.running()
        assert sim.links() == ['up']
        assert sim.guard_armed
        assert len(sim.commands()) == seen  # the bridge does not fill the silence
        client.off()

    def test_abrupt_exit_before_a_session_is_open_keeps_the_link(self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        client = Client(bridge.link)
        assert client.ask('{[PI]}') == b'{0}\r\n'
        client.vanish()  # e.g. a failed handshake, or a crash before SC AR
        time.sleep(0.5)
        assert bridge.running()
        assert sim.links() == ['up']
        assert 'detached, clean (no session was opened at the roaster)' in bridge.text()

    def test_abrupt_exit_with_keep_option_leaves_the_link_up_and_silent(self, sim: SimRoaster, start_bridge: Callable[..., BridgeProcess]) -> None:
        bridge = start_bridge('--keep-link-on-abrupt-exit')
        process = fake_artisan(bridge.link)
        wait_for(lambda: sim.commands().count('{[RD A0]}') >= 2, what='polling')
        process.send_signal(signal.SIGKILL)
        process.wait(5)
        seen = len(sim.commands())
        time.sleep(1.5)
        assert bridge.running()
        assert sim.links() == ['up']
        assert sim.guard_armed
        assert len(sim.commands()) == seen       # the bridge sends nothing: the roaster just hears silence
        silence = sim.silence()
        assert silence is not None and silence > 1.4
        assert 'real port kept open because of --keep-link-on-abrupt-exit' in bridge.text()
        # a new client can pick the roaster up again and end the session properly
        client = Client(bridge.link)
        client.handshake()
        client.off()
        assert not sim.guard_armed

    def test_bridge_stopped_during_a_session(self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        client = Client(bridge.link)
        client.handshake()
        bridge.process.send_signal(signal.SIGTERM)
        assert bridge.wait_exit() == EXIT_OK
        wait_for(lambda: sim.links() == ['up', 'down'], what='the link to drop')
        assert sim.guard_armed
        assert '{[CL AR]}' not in sim.commands()   # the bridge does not end the guard for Artisan
        with pytest.raises(serial.SerialException):
            client.ask('{[RD A0]}')                # Artisan gets an error, not silence
        assert not bridge.link.exists()
        client.vanish()

    def test_bridge_killed_during_a_session(self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        client = Client(bridge.link)
        client.handshake()
        bridge.process.send_signal(signal.SIGKILL)
        bridge.wait_exit()
        wait_for(lambda: sim.links() == ['up', 'down'], what='the link to drop')
        assert sim.guard_armed
        with pytest.raises(serial.SerialException):
            client.ask('{[RD A0]}')
        client.vanish()

    def test_ctrl_c_during_a_session_has_to_be_confirmed(self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        client = Client(bridge.link)
        client.handshake()
        bridge.process.send_signal(signal.SIGINT)
        time.sleep(0.6)
        assert bridge.running()
        assert 'press Ctrl-C again' in bridge.text()
        assert client.ask('{[RD A0]}').startswith(b'{0,BT:')  # still serving
        bridge.process.send_signal(signal.SIGINT)
        assert bridge.wait_exit() == EXIT_OK
        client.vanish()
        wait_for(lambda: sim.links() == ['up', 'down'], what='the link to drop')

    def test_ctrl_c_without_a_session_stops_at_once(self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        client = Client(bridge.link)
        client.handshake()
        client.off()
        time.sleep(0.2)
        bridge.process.send_signal(signal.SIGINT)
        assert bridge.wait_exit() == EXIT_OK
        assert not sim.guard_armed

    def test_upstream_link_loss_is_reported_and_passed_on(self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        client = Client(bridge.link)
        client.handshake()
        sim.drop_link()  # the real port disappears under the bridge
        assert bridge.wait_exit() == EXIT_UPSTREAM
        with pytest.raises(serial.SerialException):
            client.ask('{[RD A0]}')
        client.vanish()
        text = bridge.text()
        assert 'BLUETOOTH PORT FAILURE' in text
        assert 'It does not reopen the port or reset Bluetooth' in text
        assert text.count('opened (57600 8N1') == 1
        assert not bridge.link.exists()

    def test_upstream_link_loss_without_a_client(self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        sim.drop_link()
        assert bridge.wait_exit() == EXIT_UPSTREAM
        assert not bridge.link.exists()

    def test_silent_upstream_is_not_papered_over(self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        client = Client(bridge.link)
        client.handshake()
        sim.mute = True  # the link stays up, the roaster stops answering
        client.port.timeout = 0.3
        for _ in range(3):
            assert client.ask('{[RD A0]}') == b''   # no answer is made up
        assert client.ask('{[CL AR]}') == b''        # not even for the safety command
        wait_for(lambda: 'the roaster has not answered for' in bridge.text(), timeout=8, what='the silence warning')
        assert bridge.running()
        assert sim.commands()[-4:] == ['{[RD A0]}'] * 3 + ['{[CL AR]}']  # all of it was passed on, once
        client.vanish()

    def test_real_port_that_cannot_be_opened(self, tmp_path: Path, start_bridge: Callable[..., BridgeProcess]) -> None:
        bridge = start_bridge(device=str(tmp_path / 'no-such-port'))
        assert bridge.wait_exit() == EXIT_SETUP
        assert not bridge.link.exists()
        assert 'cannot open' in bridge.text()

    def test_a_second_bridge_is_refused(self, start_bridge: Callable[..., BridgeProcess]) -> None:
        first = start_bridge()
        second = start_bridge()
        assert second.wait_exit() == EXIT_SETUP
        assert first.running()
        assert first.link.is_symlink()


def artisan_kaleido() -> object:
    """Artisan's own Kaleido module, if its source is around."""
    candidates = [os.environ.get('ARTISAN_SRC')]
    for candidate in candidates:
        if candidate and (Path(candidate) / 'artisanlib' / 'kaleido.py').exists():
            sys.path.insert(0, candidate)
            try:
                import artisanlib.kaleido as module  # pylint: disable=import-outside-toplevel
                return module
            except Exception:  # pylint: disable=broad-except
                sys.path.remove(candidate)
    return None


class TestWithArtisanCode:
    """Artisan's own KaleidoPort (pyserial through the pymodbus serial transport) as the client."""

    def test_off_on_with_artisans_kaleido_port(self, sim: SimRoaster, bridge: BridgeProcess) -> None:
        module = artisan_kaleido()
        if module is None:
            pytest.skip('Artisan source not available')
        settings = {'port': str(bridge.link), 'baudrate': 57600, 'bytesize': 8, 'stopbits': 1, 'parity': 'N', 'timeout': 0.6, 'clear_HUPCL': False}
        for _ in range(2):
            port = module.KaleidoPort()  # type: ignore[attr-defined]
            port.start('C', serial=settings)
            wait_for(lambda p=port: p.get_state('TU') is not None, what="Artisan's handshake")
            bt, et, sid = port.getBTET()
            assert sid == 0 and 90 < bt < 110 and 110 < et < 130
            port.stop()  # what OFF and quit call
            time.sleep(0.6)
        commands = sim.commands()
        assert commands.count('{[SC AR]}') == 2 and commands.count('{[CL AR]}') == 2
        assert commands[-1] == '{[CL AR]}'
        assert sim.links() == ['up']
        assert bridge.text().count('detached, clean (Artisan ended its session with CL AR)') == 2
