"""Tests of what the app does and shows, without its windows: setup, saved settings, status, stop, failures.

The roaster is tools/sim_roaster.SimRoaster on a pseudo terminal; "Artisan" is a pyserial client that
speaks like Artisan's Kaleido code. What macOS would report about the Bluetooth link is scripted.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import serial

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))

from sim_roaster import SimRoaster  # noqa: E402

from kaleido_serial_bridge import controller as controller_module  # noqa: E402
from kaleido_serial_bridge.controller import BridgeController, Exit, LinkView, State, derive_status  # noqa: E402
from kaleido_serial_bridge.engine import EXIT_ABRUPT, EXIT_OK, EXIT_SETUP, EXIT_UPSTREAM, Snapshot  # noqa: E402
from kaleido_serial_bridge.linkstate import CONNECTED, NOT_CONNECTED, UNKNOWN, LinkMonitor  # noqa: E402
from kaleido_serial_bridge.ports import best_guess, discover  # noqa: E402
from kaleido_serial_bridge.settings import Paths, Settings  # noqa: E402

HANDSHAKE = ['{[PI]}', '{[TU C]}', '{[SC AR]}']


def wait_for(condition: Callable[[], object], timeout: float = 5.0, what: str = 'condition') -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError(f'timed out waiting for {what}')


class Artisan:
    """Opens and talks to a port the way Artisan's Kaleido code does."""

    def __init__(self, port: str, timeout: float = 1.0) -> None:
        self.port = serial.Serial(port, 57600, bytesize=8, parity='N', stopbits=1, timeout=timeout, exclusive=True)

    def ask(self, command: str) -> bytes:
        self.port.write(command.encode('ascii') + b'\n')
        return self.port.readline()

    def on(self) -> None:
        for command in HANDSHAKE:
            self.ask(command)

    def off(self) -> None:
        self.ask('{[CL AR]}')
        self.port.close()

    def vanish(self) -> None:
        self.port.close()


class Link:
    """What macOS reports about the Bluetooth link, set by the test."""

    def __init__(self) -> None:
        self.state = NOT_CONNECTED
        self.asked = 0

    def __call__(self, _device: str) -> str:
        self.asked += 1
        return self.state


@pytest.fixture(autouse=True)
def fast_clocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(LinkMonitor, 'FAST', 0.03)
    monkeypatch.setattr(LinkMonitor, 'SLOW', 0.03)
    monkeypatch.setattr(LinkMonitor, 'STEADY', 0.03)
    monkeypatch.setattr(controller_module, 'REPLY_FRESH', 0.6)
    monkeypatch.setattr(controller_module, 'REPLY_QUIET', 2.0)
    monkeypatch.setattr(controller_module, 'FIRST_REPLY_GRACE', 0.6)
    monkeypatch.setattr(controller_module, 'RETRY_WINDOW', 1.5)


@pytest.fixture
def sim() -> Iterator[SimRoaster]:
    roaster = SimRoaster()
    yield roaster
    roaster.close()


@pytest.fixture
def link() -> Link:
    return Link()


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    return Paths(tmp_path / 'home')


@pytest.fixture
def make(paths: Paths, link: Link) -> Iterator[Callable[..., BridgeController]]:
    made: list[BridgeController] = []

    def factory(**options: object) -> BridgeController:
        controller = BridgeController(paths, link_query=link, **options)  # type: ignore[arg-type]
        made.append(controller)
        return controller

    yield factory
    for controller in made:
        controller.stop()


@pytest.fixture
def controller(make: Callable[..., BridgeController], sim: SimRoaster) -> BridgeController:
    """An app that has been set up for the simulated roaster."""
    result = make()
    result.choose_device(sim.device)
    result.finish_setup()
    return result


def state(controller: BridgeController) -> State:
    return controller.poll().state


class TestFirstRunSetup:

    def test_a_new_installation_needs_setup_and_starts_nothing(self, make: Callable[..., BridgeController]) -> None:
        controller = make()
        assert controller.needs_setup()
        assert controller.settings == Settings(device='', auto_start=False, setup_done=False)
        assert state(controller) is State.STOPPED
        started, problem = controller.start()
        assert not started and 'Setup Guide' in problem

    def test_kaleido_like_ports_are_suggested_and_any_port_can_be_chosen(self, tmp_path: Path, make: Callable[..., BridgeController]) -> None:
        dev = tmp_path / 'dev'
        dev.mkdir()
        for name in ('cu.usbserial-110', 'cu.Roaster_SRSv6', 'cu.Bluetooth-Incoming-Port', 'cu.debug-console', 'cu.JBL-Speaker'):
            (dev / name).touch()
        controller = make(port_pattern=str(dev / 'cu.*'))
        ports = controller.ports()
        assert [(port.name, port.suggested) for port in ports] == [('Roaster_SRSv6', True), ('JBL-Speaker', False), ('usbserial-110', False)]
        assert ports[0].label == 'Roaster_SRSv6  (looks like a Kaleido)'
        guess = best_guess(ports)
        assert guess is not None and guess.path == str(dev / 'cu.Roaster_SRSv6')
        # the user decides: here, deliberately, not the suggestion
        controller.choose_device(ports[2].path)
        assert controller.settings.device == str(dev / 'cu.usbserial-110')
        assert controller.needs_setup()  # until the guide has been completed
        controller.finish_setup()
        assert not controller.needs_setup()

    def test_no_guess_when_several_ports_look_like_a_kaleido(self, tmp_path: Path) -> None:
        for name in ('cu.Roaster_SRSv6', 'cu.KaleidoM10', 'cu.Sniper-M2'):
            (tmp_path / name).touch()
        ports = discover(str(tmp_path / 'cu.*'))
        assert [port.suggested for port in ports] == [True, True, True]
        assert best_guess(ports) is None

    def test_no_ports_at_all(self, tmp_path: Path) -> None:
        assert discover(str(tmp_path / 'cu.*')) == []
        assert best_guess([]) is None

    def test_the_virtual_port_keeps_the_path_of_the_tested_prototype(self, paths: Paths, make: Callable[..., BridgeController]) -> None:
        assert make().virtual_port == str(paths.home / 'cu.Roaster_bridge')


class TestSavedSettings:

    def test_the_choice_is_remembered_across_a_relaunch(self, paths: Paths, make: Callable[..., BridgeController], sim: SimRoaster) -> None:
        first = make()
        first.choose_device(sim.device)
        first.finish_setup()
        relaunched = make()
        assert not relaunched.needs_setup()
        assert relaunched.settings == Settings(device=sim.device, auto_start=False, setup_done=True)
        assert json.loads(paths.settings.read_text())['device'] == sim.device

    def test_automatic_start_is_off_until_turned_on(self, make: Callable[..., BridgeController]) -> None:
        controller = make()
        assert controller.settings.auto_start is False
        controller.set_auto_start(True)
        assert make().settings.auto_start is True

    def test_an_unreadable_settings_file_means_setup_again(self, paths: Paths, make: Callable[..., BridgeController]) -> None:
        paths.home.mkdir(parents=True)
        paths.settings.write_text('{ not json')
        controller = make()
        assert controller.needs_setup()
        assert (paths.home / 'settings.json.unreadable').exists()

    def test_relaunch_does_not_start_the_bridge_by_itself(self, controller: BridgeController, make: Callable[..., BridgeController], sim: SimRoaster) -> None:
        assert not controller.needs_setup()  # set up before the relaunch
        relaunched = make()
        assert state(relaunched) is State.STOPPED
        time.sleep(0.2)
        assert sim.links() == []  # the port of the roaster was not touched


class TestStatus:

    def test_the_whole_sequence(self, controller: BridgeController, sim: SimRoaster, link: Link) -> None:
        assert state(controller) is State.STOPPED
        assert controller.start() == (True, '')
        # the port is open, but that alone is not communication
        status = controller.poll()
        assert status.state is State.WAITING_BLUETOOTH and status.running and not status.attached
        assert 'About 13 s is normal' in status.detail
        link.state = CONNECTED
        wait_for(lambda: state(controller) is State.WAITING_ARTISAN, what='waiting for Artisan')
        # Artisan opens the port: attached, but nothing has been answered yet
        artisan = Artisan(controller.virtual_port)
        wait_for(lambda: state(controller) is State.ARTISAN_ATTACHED, what='attached')
        artisan.on()
        artisan.ask('{[RD A0]}')
        status = controller.poll()
        assert status.state is State.RECEIVING and status.attached and status.session_open
        # the roaster stops answering while Artisan keeps asking
        sim.mute = True
        artisan.port.timeout = 0.2
        for _ in range(5):
            artisan.ask('{[RD A0]}')
        status = controller.poll()
        assert status.state is State.NO_REPLIES and status.attention
        assert 'commands unanswered' in status.detail
        # and answers again
        sim.mute = False
        artisan.port.timeout = 1.0
        artisan.port.reset_input_buffer()
        artisan.ask('{[RD A0]}')
        assert state(controller) is State.RECEIVING
        artisan.off()
        wait_for(lambda: state(controller) is State.WAITING_ARTISAN, what='waiting for Artisan again')
        assert not controller.poll().session_open
        assert sim.links() == ['up']

    def test_replies_count_even_if_macos_never_reports_the_link(self, controller: BridgeController, link: Link) -> None:
        link.state = UNKNOWN
        controller.start()
        wait_for(lambda: state(controller) is State.WAITING_ARTISAN, what='waiting for Artisan')
        assert 'no Bluetooth state' in controller.poll().detail
        artisan = Artisan(controller.virtual_port)
        artisan.on()
        assert state(controller) is State.RECEIVING
        artisan.off()

    def test_a_quiet_but_answered_session_stays_live_for_a_while(self, controller: BridgeController, link: Link) -> None:
        link.state = CONNECTED
        controller.start()
        artisan = Artisan(controller.virtual_port)
        artisan.on()
        time.sleep(1.0)  # longer than REPLY_FRESH, nothing unanswered: a long sampling interval
        assert state(controller) is State.RECEIVING
        time.sleep(1.3)  # longer than REPLY_QUIET: Artisan has gone quiet
        status = controller.poll()
        assert status.state is State.NO_REPLIES and 'has sent nothing' in status.detail
        artisan.off()

    def test_a_silent_start_is_shown_as_no_replies_while_artisan_retries(self, controller: BridgeController, sim: SimRoaster) -> None:
        """What happened on hardware when macOS had not connected the roaster: Artisan pings, gets nothing, retries."""
        sim.mute = True
        controller.start()
        assert state(controller) is State.WAITING_BLUETOOTH
        for attempt in (1, 2, 3):
            artisan = Artisan(controller.virtual_port, timeout=0.15)
            for _ in range(3):
                assert artisan.ask('{[PI]}') == b''
            if attempt > 1:
                assert state(controller) is State.NO_REPLIES  # not "waiting for the first reply" again
            artisan.vanish()
            wait_for(lambda: not controller.poll().attached, what='detach')
            status = controller.poll()
            assert status.state is State.NO_REPLIES  # stays between the attempts
            assert f'tried {attempt} time(s)' in status.detail
        assert controller.poll().running  # a failed handshake leaves no session open: the port stays open
        assert sim.links() == ['up']
        time.sleep(1.6)  # Artisan gave up
        assert state(controller) is State.WAITING_BLUETOOTH

    def test_the_link_is_only_asked_about_while_no_client_is_attached(self, controller: BridgeController, link: Link) -> None:
        link.state = CONNECTED
        controller.start()
        wait_for(lambda: link.asked >= 2, what='link queries')
        artisan = Artisan(controller.virtual_port)
        artisan.on()
        time.sleep(0.1)
        asked = link.asked
        time.sleep(0.3)
        assert link.asked == asked
        artisan.off()
        wait_for(lambda: link.asked > asked, what='link queries to resume')

    def test_status_file(self, controller: BridgeController, paths: Paths, link: Link) -> None:
        link.state = CONNECTED
        controller.start()
        wait_for(lambda: state(controller) is State.WAITING_ARTISAN)
        record = json.loads(paths.status.read_text())
        assert record['state'] == 'waiting-artisan' and record['running'] is True and record['attached'] is False
        assert record['virtual_port'] == controller.virtual_port and record['link'] == CONNECTED


class TestDerivedStatus:
    """The timing rules, on made-up snapshots."""

    NOW = 1000.0

    def snapshot(self, **changes: object) -> Snapshot:
        values: dict[str, object] = {
            'exit_code': None, 'stop_reason': '', 'opened_at': self.NOW - 5, 'sessions': 0, 'attached': False, 'session_number': 0,
            'session_started': None, 'session_open': False, 'commands': 0, 'reply_bytes': 0, 'unanswered': 0, 'last_reply_at': None,
            'last_command_at': None, 'silent_sessions': 0, 'last_detach_at': None}
        values.update(changes)
        return Snapshot(**values)  # type: ignore[arg-type]

    def derive(self, snapshot: Snapshot | None, link: LinkView | None = None, last_exit: Exit | None = None) -> controller_module.Status:
        return derive_status(snapshot, link if link is not None else LinkView(), last_exit, self.NOW)

    def test_an_open_port_is_never_live_communication(self) -> None:
        for link in (LinkView(), LinkView(NOT_CONNECTED, self.NOW - 3), LinkView(CONNECTED, self.NOW - 3, True), LinkView(UNKNOWN, self.NOW - 3)):
            assert self.derive(self.snapshot(), link).state in {State.WAITING_BLUETOOTH, State.WAITING_ARTISAN}
        attached = self.snapshot(attached=True, session_number=1, session_started=self.NOW - 60, commands=9, unanswered=9)
        assert self.derive(attached, LinkView(CONNECTED, self.NOW - 60, True)).state is State.NO_REPLIES

    def test_before_the_first_link_report_it_is_waiting_for_bluetooth(self) -> None:
        assert self.derive(self.snapshot(opened_at=self.NOW - 1)).state is State.WAITING_BLUETOOTH

    def test_the_usual_wait_is_not_alarming_a_long_one_is(self) -> None:
        usual = self.derive(self.snapshot(opened_at=self.NOW - 13), LinkView(NOT_CONNECTED, self.NOW - 13))
        assert usual.state is State.WAITING_BLUETOOTH and not usual.attention
        long = self.derive(self.snapshot(opened_at=self.NOW - 60), LinkView(NOT_CONNECTED, self.NOW - 60))
        assert long.state is State.WAITING_BLUETOOTH and long.attention and 'No Readings?' in long.detail

    def test_a_link_that_was_connected_and_is_not_any_more(self) -> None:
        status = self.derive(self.snapshot(opened_at=self.NOW - 600), LinkView(NOT_CONNECTED, self.NOW - 20, True))
        assert status.state is State.WAITING_BLUETOOTH and status.attention and 'no longer connected' in status.detail

    def test_stopped_and_failed(self) -> None:
        assert self.derive(None).state is State.STOPPED
        assert self.derive(None, last_exit=Exit(EXIT_OK, '', self.NOW)).state is State.STOPPED
        for code, word in ((EXIT_SETUP, 'Could not start'), (EXIT_UPSTREAM, 'Bluetooth port failed'), (EXIT_ABRUPT, 'Artisan vanished')):
            status = self.derive(None, last_exit=Exit(code, 'why', self.NOW))
            assert status.state is State.FAILED and status.attention and word in status.headline and status.detail == 'why'


class TestStop:

    def test_clean_stop_and_start_again(self, controller: BridgeController, sim: SimRoaster, paths: Paths) -> None:
        controller.start()
        artisan = Artisan(controller.virtual_port)
        artisan.on()
        artisan.off()
        wait_for(lambda: not controller.poll().attached)
        assert controller.stop() is True
        status = controller.poll()
        assert status.state is State.STOPPED and not status.running
        assert not paths.link.exists()
        wait_for(lambda: sim.links() == ['up', 'down'], what='the port to be closed')
        assert sim.commands()[-1] == '{[CL AR]}'  # stopping sent nothing
        assert json.loads(paths.status.read_text())['state'] == 'stopped'
        # starting again opens the port again, once
        controller.start()
        wait_for(lambda: sim.links() == ['up', 'down', 'up'], what='the port to be opened again')
        assert paths.link.is_symlink()

    def test_the_status_says_when_stopping_would_cut_artisan_off(self, controller: BridgeController, sim: SimRoaster) -> None:
        controller.start()
        before = controller.poll()
        assert not before.attached and not before.session_open  # nothing to warn about
        artisan = Artisan(controller.virtual_port)
        artisan.on()
        during = controller.poll()
        assert during.attached and during.session_open  # the app warns before stopping now
        controller.stop()  # the user insisted
        with pytest.raises(serial.SerialException):
            artisan.ask('{[RD A0]}')  # Artisan sees the port fail, not silence
        artisan.vanish()
        wait_for(lambda: sim.links() == ['up', 'down'])
        assert '{[CL AR]}' not in sim.commands()  # the app did not end the guard for Artisan
        assert state(controller) is State.STOPPED

    def test_stop_when_not_running_is_harmless(self, controller: BridgeController) -> None:
        assert controller.stop() is True
        assert state(controller) is State.STOPPED


class TestFailures:

    def test_artisan_vanishing_mid_session_stops_the_bridge_and_says_so(self, controller: BridgeController, sim: SimRoaster) -> None:
        controller.start()
        artisan = Artisan(controller.virtual_port)
        artisan.on()
        artisan.ask('{[RD A0]}')
        artisan.vanish()  # a crash or force quit: no CL AR
        wait_for(lambda: state(controller) is State.FAILED, what='the failure to show')
        status = controller.poll()
        assert status.headline == 'Artisan vanished mid-session, bridge stopped' and status.attention and not status.running
        assert 'CL AR was not delivered' in status.detail
        event = controller.take_exit()
        assert event is not None and event.code == EXIT_ABRUPT
        assert controller.take_exit() is None  # reported once
        wait_for(lambda: sim.links() == ['up', 'down'])
        assert sim.guard_armed and '{[CL AR]}' not in sim.commands()
        controller.acknowledge_failure()
        assert state(controller) is State.STOPPED

    def test_losing_the_real_port_stops_the_bridge_and_says_so(self, controller: BridgeController, sim: SimRoaster, paths: Paths) -> None:
        controller.start()
        artisan = Artisan(controller.virtual_port)
        artisan.on()
        sim.drop_link()
        wait_for(lambda: state(controller) is State.FAILED, what='the failure to show')
        status = controller.poll()
        assert status.headline == 'Bluetooth port failed, bridge stopped' and 'Bluetooth port failure' in status.detail
        event = controller.take_exit()
        assert event is not None and event.code == EXIT_UPSTREAM
        with pytest.raises(serial.SerialException):
            artisan.ask('{[RD A0]}')
        artisan.vanish()
        assert not paths.link.exists()

    def test_a_port_that_does_not_exist(self, make: Callable[..., BridgeController], tmp_path: Path) -> None:
        controller = make()
        controller.choose_device(str(tmp_path / 'cu.Gone'))
        controller.finish_setup()
        started, problem = controller.start()
        assert not started and 'does not exist' in problem and 'Bluetooth' in problem
        status = controller.poll()
        assert status.state is State.FAILED and status.headline == 'Could not start the bridge'

    def test_a_second_instance_cannot_take_the_port(self, controller: BridgeController, make: Callable[..., BridgeController], sim: SimRoaster) -> None:
        controller.start()
        second = make()
        started, problem = second.start()
        assert not started and problem == 'another bridge is already running'
        assert state(controller) in {State.WAITING_BLUETOOTH, State.WAITING_ARTISAN}  # the first is not disturbed
        wait_for(lambda: sim.links() == ['up'], what='the port to be open')
        time.sleep(0.2)
        assert sim.links() == ['up']

    def test_restart_after_a_failure(self, controller: BridgeController, sim: SimRoaster) -> None:
        controller.start()
        wait_for(lambda: sim.links() == ['up'], what='the port to be open')
        artisan = Artisan(controller.virtual_port)
        artisan.on()
        artisan.vanish()
        wait_for(lambda: state(controller) is State.FAILED)
        assert controller.start() == (True, '')  # only because the user asked; nothing restarts by itself
        assert state(controller) is State.WAITING_BLUETOOTH
        assert controller.take_exit() is None
