"""The guided Bluetooth recovery, against a simulated macOS and the simulated roaster.

Nothing here touches Bluetooth or asks for a password: FakeSystem stands in for macOS (the
authorization dialog, bluetoothd, the Bluetooth power switch and the roaster's serial port) and
records what it was asked to do. The bridge itself is real, on the simulated roaster.
"""

# ruff: noqa: F811  # pytest fixtures imported from test_controller are named again as test arguments

from __future__ import annotations

import sys
import logging
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))

from sim_roaster import SimRoaster  # noqa: E402
from test_controller import Artisan, controller, fast_clocks, link, make, paths, sim, wait_for  # noqa: E402,F401  # fixtures

from kaleido_serial_bridge import recovery as recovery_module  # noqa: E402
from kaleido_serial_bridge.controller import BridgeController, State  # noqa: E402
from kaleido_serial_bridge.recovery import Outcome, Phase, Recovery, Step  # noqa: E402


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeSystem:
    """macOS as the recovery sees it. Each behaviour can be changed by a test."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.calls: list[str] = []
        self.restart = Outcome(True)
        self.service_back_after = 0.5      # seconds after the restart; None: never
        self.power = True
        self.power_follows = True          # the switch takes effect
        self.accept_power = True
        self.port_back_after: float | None = 1.0  # seconds after Bluetooth is on again; None: never
        # As seen on hardware: after the restart the service is back before it is ready. Until then Bluetooth does not
        # report "on", and a power request is ignored (macOS: "can only accept this command while in the powered on state").
        self.ready_after = 0.0             # seconds after the restart; None: never
        self.ignore_off_requests = 0       # this many power-off requests have no effect even when ready
        self.ignore_on_requests = 0
        self.unready_reads: bool | None = False  # what the power state reads as while the service is not ready yet
        self.restarted_at: float | None = None
        self.on_at: float | None = None

    def restart_service(self) -> Outcome:
        self.calls.append('restart_service')
        if self.restart.ok:
            self.restarted_at = self.clock()
        return self.restart

    def service_running(self) -> bool:
        return (self.restarted_at is not None and self.service_back_after is not None
                and self.clock() - self.restarted_at >= self.service_back_after)

    def ready(self) -> bool:
        return (self.service_running() and self.ready_after is not None and self.restarted_at is not None
                and self.clock() - self.restarted_at >= self.ready_after)

    def power_state(self) -> bool | None:
        if not self.service_running():
            return None
        return self.power if self.ready() else self.unready_reads

    def set_power(self, on: bool) -> bool:
        self.calls.append(f'set_power({on})')
        if not self.accept_power:
            return False
        if not self.ready():
            return True  # sent, and ignored
        if not on and self.ignore_off_requests:
            self.ignore_off_requests -= 1
            return True
        if on and self.ignore_on_requests:
            self.ignore_on_requests -= 1
            return True
        if self.power_follows:
            self.power = on
            if on:
                self.on_at = self.clock()
        return True

    def port_exists(self, path: str) -> bool:
        return (self.on_at is not None and self.port_back_after is not None and self.clock() - self.on_at >= self.port_back_after
                and Path(path).exists())


def run(recovery: Recovery, clock: Clock, until: set[Phase], limit: float = 400.0, step: float = 0.5) -> None:
    """Calls step() the way the app's timer does, every half second, until the attempt reaches one of these phases."""
    waited = 0.0
    while recovery.phase not in until and waited < limit:
        recovery.step()
        clock.advance(step)
        waited += step
    assert recovery.phase in until, f'still {recovery.phase} at {recovery.step_now}: {recovery.detail}'


def make_recovery(controller: BridgeController) -> tuple[Recovery, FakeSystem, Clock]:
    clock = Clock()
    system = FakeSystem(clock)
    return Recovery(controller, system, clock=clock), system, clock


class TestOneAttempt:

    def test_success_runs_the_sequence_once_and_waits_for_real_replies(self, controller: BridgeController, sim: SimRoaster) -> None:
        recovery, system, clock = make_recovery(controller)
        assert recovery.begin()
        run(recovery, clock, {Phase.WAITING_FOR_ARTISAN, Phase.FAILED})
        assert recovery.phase is Phase.WAITING_FOR_ARTISAN and recovery.step_now is Step.WAIT_REPLIES
        assert system.calls == ['restart_service', 'set_power(False)', 'set_power(True)']  # in that order, each once
        assert controller.running()
        wait_for(lambda: sim.links() == ['up'], what='the port to be opened once')
        # an open port is not a recovery: only replies count
        recovery.step()
        assert recovery.phase is Phase.WAITING_FOR_ARTISAN
        artisan = Artisan(controller.virtual_port)
        artisan.on()
        assert artisan.ask('{[RD A0]}').startswith(b'{0,BT:')
        wait_for(lambda: controller.poll().state is State.RECEIVING, what='replies to show')
        recovery.step()
        assert recovery.phase is Phase.SUCCEEDED and 'replies from the roaster are arriving' in recovery.detail
        assert sim.links() == ['up']  # started once
        artisan.off()

    def test_bluetooth_stays_off_for_at_least_two_seconds(self, controller: BridgeController) -> None:
        recovery, system, clock = make_recovery(controller)
        recovery.begin()
        run(recovery, clock, {Phase.WAITING_FOR_ARTISAN, Phase.FAILED}, step=0.1)
        assert system.on_at is not None and recovery.off_at is not None
        assert system.on_at - recovery.off_at >= recovery_module.POWER_OFF_HOLD

    def test_authorization_cancelled_changes_nothing(self, controller: BridgeController, sim: SimRoaster) -> None:
        recovery, system, clock = make_recovery(controller)
        system.restart = Outcome(False, cancelled=True)
        recovery.begin()
        run(recovery, clock, {Phase.FAILED})
        assert recovery.step_now is Step.RESTART_SERVICE
        assert 'authorization was cancelled' in recovery.detail and 'Nothing was changed' in recovery.detail
        assert system.calls == ['restart_service']  # Bluetooth was not switched
        assert not controller.running() and sim.links() == []

    def test_a_failed_restart_names_the_reason(self, controller: BridgeController) -> None:
        recovery, system, clock = make_recovery(controller)
        system.restart = Outcome(False, message='The administrator user name or password was incorrect')
        recovery.begin()
        run(recovery, clock, {Phase.FAILED})
        assert recovery.step_now is Step.RESTART_SERVICE and 'password was incorrect' in recovery.detail
        assert system.calls == ['restart_service'] and not controller.running()

    def test_timeout_when_the_service_does_not_come_back(self, controller: BridgeController, sim: SimRoaster) -> None:
        recovery, system, clock = make_recovery(controller)
        system.service_back_after = None
        recovery.begin()
        run(recovery, clock, {Phase.FAILED})
        assert recovery.step_now is Step.WAIT_SERVICE and f'within {recovery_module.SERVICE_TIMEOUT:.0f} s' in recovery.detail
        assert system.calls == ['restart_service']
        assert not controller.running() and sim.links() == []

    def test_timeout_when_bluetooth_does_not_turn_off(self, controller: BridgeController, sim: SimRoaster,
                                                      caplog: pytest.LogCaptureFixture) -> None:
        recovery, system, clock = make_recovery(controller)
        system.power_follows = False  # every request is ignored
        recovery.begin()
        with caplog.at_level(logging.INFO, logger='kaleido_bridge'):
            run(recovery, clock, {Phase.FAILED})
        assert recovery.step_now is Step.WAIT_OFF and 'did not report "off" within 10 s' in recovery.detail
        requests = system.calls.count('set_power(False)')
        limit = recovery_module.POWER_OFF_TIMEOUT / recovery_module.POWER_RETRY + 1
        assert 2 <= requests <= limit  # retried, at a bounded interval, within the step's limit
        assert f'after {requests} request(s)' in recovery.detail
        assert 'set_power(True)' not in system.calls and system.calls.count('restart_service') == 1  # one authorization
        assert not controller.running() and sim.links() == []
        text = caplog.text
        assert text.count('sending it again') == requests - 1
        assert 'failed at "Wait for Bluetooth to turn off"' in text and 'The bridge was not started by the recovery.' in text
        assert 'Bluetooth power cycle completed' not in text and 'bridge started' not in text

    def test_power_switch_unavailable(self, controller: BridgeController) -> None:
        recovery, system, clock = make_recovery(controller)
        system.accept_power = False  # e.g. the function is missing on this macOS
        recovery.begin()
        run(recovery, clock, {Phase.FAILED})
        assert recovery.step_now is Step.POWER_OFF and not controller.running()

    def test_timeout_when_bluetooth_does_not_turn_on_again(self, controller: BridgeController) -> None:
        recovery, system, clock = make_recovery(controller)
        original = system.set_power

        def stuck_off(on: bool) -> bool:
            if on:
                system.calls.append('set_power(True)')
                return True  # accepted, but nothing happens
            return original(on)
        system.set_power = stuck_off  # type: ignore[method-assign]
        recovery.begin()
        run(recovery, clock, {Phase.FAILED, Phase.WAITING_FOR_ARTISAN})
        assert recovery.phase is Phase.FAILED and recovery.step_now is Step.WAIT_ON and 'Control Center' in recovery.detail
        assert not controller.running()

    def test_missing_serial_port_times_out_and_the_bridge_is_not_started(self, controller: BridgeController, sim: SimRoaster) -> None:
        recovery, system, clock = make_recovery(controller)
        system.port_back_after = None  # macOS never creates the roaster's port again
        recovery.begin()
        run(recovery, clock, {Phase.FAILED, Phase.WAITING_FOR_ARTISAN})
        assert recovery.phase is Phase.FAILED and recovery.step_now is Step.WAIT_PORT
        assert f'did not appear within {recovery_module.PORT_TIMEOUT:.0f} s' in recovery.detail and sim.device in recovery.detail
        assert not controller.running() and sim.links() == []

    def test_no_replies_in_time_leaves_the_bridge_running(self, controller: BridgeController, sim: SimRoaster) -> None:
        recovery, _system, clock = make_recovery(controller)
        recovery.begin()
        run(recovery, clock, {Phase.WAITING_FOR_ARTISAN})
        run(recovery, clock, {Phase.FAILED})  # nobody clicks ON
        assert recovery.step_now is Step.WAIT_REPLIES and 'still running' in recovery.detail
        wait_for(lambda: sim.links() == ['up'], what='the port to be seen open')
        assert controller.running() and sim.links() == ['up']  # not stopped by the recovery


class TestReadinessAndRetries:
    """What went wrong on hardware on 2026-11-14, and what the recovery now does about it."""

    def test_power_off_waits_until_bluetooth_reports_on(self, controller: BridgeController, caplog: pytest.LogCaptureFixture) -> None:
        recovery, system, clock = make_recovery(controller)
        system.ready_after = 4.0  # the service process is back at once, but ready only after 4 s
        recovery.begin()
        with caplog.at_level(logging.INFO, logger='kaleido_bridge'):
            run(recovery, clock, {Phase.WAITING_FOR_ARTISAN, Phase.FAILED}, step=0.1)
        assert recovery.phase is Phase.WAITING_FOR_ARTISAN
        # no power request was sent before the service was ready, so none was wasted
        assert system.calls == ['restart_service', 'set_power(False)', 'set_power(True)']
        assert system.restarted_at is not None and system.on_at is not None
        assert 'sending it again' not in caplog.text
        assert 'Bluetooth service restarted (bluetoothd is running and Bluetooth reports on, after 4.' in caplog.text

    def test_service_back_but_never_ready_times_out_without_power_requests(self, controller: BridgeController, sim: SimRoaster) -> None:
        recovery, system, clock = make_recovery(controller)
        system.ready_after = None
        recovery.begin()
        run(recovery, clock, {Phase.FAILED})
        assert recovery.step_now is Step.WAIT_SERVICE and 'Bluetooth reports off' in recovery.detail
        assert system.calls == ['restart_service'] and not controller.running() and sim.links() == []

    def test_an_ignored_first_power_off_request_is_sent_again(self, controller: BridgeController, sim: SimRoaster,
                                                            caplog: pytest.LogCaptureFixture) -> None:
        recovery, system, clock = make_recovery(controller)
        system.ignore_off_requests = 1
        recovery.begin()
        with caplog.at_level(logging.INFO, logger='kaleido_bridge'):
            run(recovery, clock, {Phase.WAITING_FOR_ARTISAN, Phase.FAILED}, step=0.1)
        assert recovery.phase is Phase.WAITING_FOR_ARTISAN
        assert system.calls == ['restart_service', 'set_power(False)', 'set_power(False)', 'set_power(True)']  # one retry, then on
        assert system.on_at is not None and recovery.off_at is not None
        assert system.on_at - recovery.off_at >= recovery_module.POWER_OFF_HOLD  # the hold counts from "off", not the request
        text = caplog.text
        assert text.count('request to turn Bluetooth off had no effect') == 1
        assert 'Bluetooth reports off, after 2 request(s)' in text
        wait_for(lambda: sim.links() == ['up'], what='one start of the bridge')

    def test_an_ignored_power_on_request_is_sent_again(self, controller: BridgeController) -> None:
        recovery, system, clock = make_recovery(controller)
        system.ignore_on_requests = 1
        recovery.begin()
        run(recovery, clock, {Phase.WAITING_FOR_ARTISAN, Phase.FAILED}, step=0.1)
        assert recovery.phase is Phase.WAITING_FOR_ARTISAN
        assert system.calls == ['restart_service', 'set_power(False)', 'set_power(True)', 'set_power(True)']

    @pytest.mark.parametrize('unready_reads', [True, False, None], ids=['stale-on', 'off', 'unreadable'])
    def test_the_hardware_failure_of_2026_11_14_now_recovers(self, controller: BridgeController, sim: SimRoaster,
                                                            unready_reads: bool | None) -> None:
        """The service is back within a second but ready only about half a second later. A power request sent into that
        gap was rejected and the attempt failed. What the power state read as during the gap is not in the macOS log, so
        all three possibilities are tried; with a stale "on" the first request may still be lost, and the retry covers it."""
        recovery, system, clock = make_recovery(controller)
        system.service_back_after = 0.1
        system.ready_after = 1.5
        system.unready_reads = unready_reads
        recovery.begin()
        run(recovery, clock, {Phase.WAITING_FOR_ARTISAN, Phase.FAILED}, step=0.5)
        assert recovery.phase is Phase.WAITING_FOR_ARTISAN, recovery.detail
        assert 1 <= system.calls.count('set_power(False)') <= 2 and system.calls.count('restart_service') == 1
        assert controller.running()
        wait_for(lambda: sim.links() == ['up'], what='one start of the bridge')

    def test_the_old_check_would_have_failed_here(self, controller: BridgeController, monkeypatch: pytest.MonkeyPatch) -> None:
        """Guards the test above: without the retry, a stale "on" during the gap loses the only power-off request."""
        monkeypatch.setattr(recovery_module, 'POWER_RETRY', 1e9)  # no retry
        recovery, system, clock = make_recovery(controller)
        system.service_back_after = 0.1
        system.ready_after = 1.5
        system.unready_reads = True
        recovery.begin()
        run(recovery, clock, {Phase.WAITING_FOR_ARTISAN, Phase.FAILED}, step=0.5)
        assert recovery.phase is Phase.FAILED and recovery.step_now is Step.WAIT_OFF


class TestLogging:

    def test_a_successful_attempt_logs_the_four_milestones_in_order(self, controller: BridgeController,
                                                                   caplog: pytest.LogCaptureFixture) -> None:
        recovery, _system, clock = make_recovery(controller)
        with caplog.at_level(logging.INFO, logger='kaleido_bridge'):
            recovery.begin()
            run(recovery, clock, {Phase.WAITING_FOR_ARTISAN})
            artisan = Artisan(controller.virtual_port)
            artisan.on()
            artisan.ask('{[RD A0]}')
            wait_for(lambda: controller.poll().state is State.RECEIVING, what='replies')
            recovery.step()
            artisan.off()
        assert recovery.phase is Phase.SUCCEEDED
        text = caplog.text
        milestones = ['recovery 1: begun by the user', 'authorization granted', 'Bluetooth service restarted', 'request 1 to turn Bluetooth off',
                      'Bluetooth reports off', 'request 1 to turn Bluetooth on', 'Bluetooth power cycle completed',
                      "the roaster's serial port", 'bridge started', 'roaster replies received']
        positions = [text.find(m) for m in milestones]
        assert all(p >= 0 for p in positions), [m for m, p in zip(milestones, positions, strict=True) if p < 0]
        assert positions == sorted(positions)
        assert text.count('step: ') == len(recovery_module.Step)  # every step is logged once
        for word in ('password', 'credential', 'token'):
            assert word not in text.lower()

    def test_a_cancelled_authorization_is_logged_without_details(self, controller: BridgeController, caplog: pytest.LogCaptureFixture) -> None:
        recovery, system, clock = make_recovery(controller)
        system.restart = Outcome(False, cancelled=True)
        with caplog.at_level(logging.INFO, logger='kaleido_bridge'):
            recovery.begin()
            run(recovery, clock, {Phase.FAILED})
        assert 'authorization cancelled by the user' in caplog.text
        assert 'failed at "Restart the Bluetooth service"' in caplog.text and 'not started by the recovery' in caplog.text


class TestGuards:

    def test_a_running_bridge_is_never_touched(self, controller: BridgeController, sim: SimRoaster) -> None:
        controller.start()
        wait_for(lambda: sim.links() == ['up'])
        recovery, system, clock = make_recovery(controller)
        recovery.begin()
        run(recovery, clock, {Phase.FAILED})
        assert recovery.step_now is Step.CHECK_STOPPED and 'stop the bridge first' in recovery.detail
        assert system.calls == []  # no password asked, Bluetooth not switched
        assert controller.running() and sim.links() == ['up']  # and the bridge was left alone

    def test_only_one_attempt_at_a_time(self, controller: BridgeController) -> None:
        recovery, system, clock = make_recovery(controller)
        assert recovery.begin()
        assert not recovery.begin()  # a second click while one is under way does nothing
        run(recovery, clock, {Phase.WAITING_FOR_ARTISAN})
        assert not recovery.begin()  # still under way: waiting for replies
        assert system.calls.count('restart_service') == 1 and recovery.attempts == 1

    def test_a_new_attempt_after_a_failed_one(self, controller: BridgeController) -> None:
        recovery, system, clock = make_recovery(controller)
        system.restart = Outcome(False, cancelled=True)
        recovery.begin()
        run(recovery, clock, {Phase.FAILED})
        system.restart = Outcome(True)
        assert recovery.begin() and recovery.attempts == 2
        run(recovery, clock, {Phase.WAITING_FOR_ARTISAN})
        assert system.calls.count('restart_service') == 2

    def test_clearing_forgets_a_finished_outcome_but_never_an_active_attempt(self, controller: BridgeController) -> None:
        recovery, system, clock = make_recovery(controller)
        assert not recovery.clear_outcome()  # nothing to clear
        recovery.begin()
        assert not recovery.clear_outcome() and recovery.phase is Phase.RUNNING  # progress is kept
        run(recovery, clock, {Phase.WAITING_FOR_ARTISAN})
        assert not recovery.clear_outcome() and recovery.phase is Phase.WAITING_FOR_ARTISAN
        controller.stop()
        run(recovery, clock, {Phase.FAILED})  # the bridge stopped before any reply
        assert recovery.clear_outcome()
        assert recovery.phase is Phase.IDLE and recovery.step_now is None and recovery.detail == ''
        system.calls.clear()
        assert recovery.begin() and recovery.attempts == 2  # and a new attempt can begin

    def test_nothing_happens_without_a_click(self, controller: BridgeController) -> None:
        recovery, system, _clock = make_recovery(controller)
        for _ in range(10):
            recovery.step()
        assert recovery.phase is Phase.IDLE and system.calls == []

    def test_the_privileged_command_is_a_constant(self) -> None:
        assert recovery_module.RESTART_COMMAND == '/usr/bin/pkill -x bluetoothd'
