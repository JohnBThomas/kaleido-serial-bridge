"""The app itself, driven in-process: its menu, setup guide, settings, warnings and failure alerts.

Buttons are "clicked" by calling what they call. Nothing appears on screen: windows are built but not
shown, alerts are answered by the test, and the clipboard is replaced.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip('AppKit')

from AppKit import NSApplication, NSApplicationActivationPolicyProhibited, NSMenu  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))

from sim_roaster import SimRoaster  # noqa: E402
from test_controller import Artisan, Link, wait_for  # noqa: E402

from kaleido_serial_bridge import app as app_module  # noqa: E402
from kaleido_serial_bridge import controller as controller_module  # noqa: E402
from kaleido_serial_bridge import guide, loginitem, ui  # noqa: E402
from kaleido_serial_bridge.app import AppDelegate  # noqa: E402
from kaleido_serial_bridge.controller import BridgeController, State  # noqa: E402
from kaleido_serial_bridge.linkstate import CONNECTED, LinkMonitor  # noqa: E402
from kaleido_serial_bridge.settings import Paths  # noqa: E402


class Alerts:
    """Stands in for the user at every alert: records it and clicks the scripted button."""

    def __init__(self) -> None:
        self.shown: list[tuple[str, str, list[str], bool]] = []
        self.answers: list[int] = []

    def __call__(self, message: str, text: str, buttons: list[str], critical: bool = False) -> int:
        self.shown.append((message, text, buttons, critical))
        return self.answers.pop(0) if self.answers else 0


class FakeApplication:
    def __init__(self) -> None:
        self.terminated = False

    def terminate_(self, _sender: Any) -> None:
        self.terminated = True

    def activateIgnoringOtherApps_(self, _flag: bool) -> None:  # noqa: N802
        pass


@pytest.fixture(scope='session', autouse=True)
def application() -> None:
    NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyProhibited)  # no Dock icon, no windows


@pytest.fixture(autouse=True)
def quiet(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {'front': [], 'clipboard': None}
    monkeypatch.setattr(ui, 'bring_forward', lambda window: seen['front'].append(window.title()))
    monkeypatch.setattr(ui, 'copy_text', lambda text: seen.__setitem__('clipboard', text))
    monkeypatch.setattr(app_module, 'copy_text', lambda text: seen.__setitem__('clipboard', text))
    monkeypatch.setattr(LinkMonitor, 'FAST', 0.03)
    monkeypatch.setattr(LinkMonitor, 'STEADY', 0.03)
    monkeypatch.setattr(controller_module, 'FIRST_REPLY_GRACE', 0.6)
    return seen


@pytest.fixture
def sim() -> Iterator[SimRoaster]:
    roaster = SimRoaster()
    yield roaster
    roaster.close()


@pytest.fixture
def dev(tmp_path: Path, sim: SimRoaster) -> Path:
    """A /dev with the simulated roaster in it under a Kaleido-like name, next to ports that are not a roaster."""
    directory = tmp_path / 'dev'
    directory.mkdir()
    (directory / 'cu.Roaster_SIM').symlink_to(sim.device)
    (directory / 'cu.usbserial-110').touch()
    (directory / 'cu.Bluetooth-Incoming-Port').touch()
    return directory


@pytest.fixture
def launch(tmp_path: Path, dev: Path) -> Iterator[Callable[[], Any]]:
    """Opens the app (again) on the same home folder, like a relaunch."""
    link = Link()
    link.state = CONNECTED
    opened: list[Any] = []

    def start() -> Any:
        controller = BridgeController(Paths(tmp_path / 'home'), link_query=link, port_pattern=str(dev / 'cu.*'))
        delegate = AppDelegate.alloc().initWithController_(controller)
        delegate.ask = Alerts()
        delegate.menu = NSMenu.alloc().init()  # the menu without a status item in the real menu bar
        delegate.launch()
        delegate.refresh()
        opened.append(delegate)
        return delegate

    yield start
    for delegate in opened:
        delegate.controller.stop()


def menu(delegate: Any) -> dict[str, bool]:
    """Title -> enabled, for every item of the menu."""
    delegate.refresh()
    items = [delegate.menu.itemAtIndex_(index) for index in range(delegate.menu.numberOfItems())]
    return {str(item.title()): bool(item.isEnabled()) for item in items if not item.isSeparatorItem()}


def complete_setup(delegate: Any, sim: SimRoaster | None = None) -> None:
    wizard = delegate.guide_window
    wizard.go_forward()  # pair -> port
    wizard.go_forward()  # port -> start (saves the choice)
    wizard.start_bridge()
    delegate.refresh()
    if sim is not None:  # the simulator looks at its port every 10 ms: let it see the open before anything closes it
        wait_for(lambda: sim.links()[-1:] == ['up'], what='the port to be opened')
    wizard.go_forward()  # start -> artisan
    wizard.go_forward()  # artisan -> settings files
    wizard.go_forward()  # done


class TestFirstRun:

    def test_the_setup_guide_opens_and_nothing_is_started(self, launch: Callable[[], Any], sim: SimRoaster, quiet: dict[str, Any]) -> None:
        delegate = launch()
        assert quiet['front'] == ['Kaleido Serial Bridge Setup']
        assert delegate.controller.poll().state is State.STOPPED
        assert menu(delegate)['Start Bridge'] and not menu(delegate)['Stop Bridge…']
        time.sleep(0.2)
        assert sim.links() == []

    def test_walking_through_the_guide(self, launch: Callable[[], Any], sim: SimRoaster, dev: Path, quiet: dict[str, Any]) -> None:
        delegate = launch()
        wizard = delegate.guide_window
        controller: BridgeController = delegate.controller
        # 1. pairing: the Kaleido-like port is reported as found
        assert wizard.step().key == 'pair'
        assert str(wizard.found.stringValue()) == 'Found: Roaster_SIM'
        wizard.go_forward()
        # 2. the port: suggestion first and preselected, every port selectable
        assert wizard.step().key == 'port'
        titles = [str(title) for title in wizard.popup.itemTitles()]
        assert titles == ['Roaster_SIM  (looks like a Kaleido)', 'usbserial-110']
        assert wizard.selected_path() == str(dev / 'cu.Roaster_SIM')
        assert bool(wizard.forward.isEnabled())
        wizard.popup.selectItemAtIndex_(1)   # the user may pick any port ...
        wizard.port_chosen()
        assert str(wizard.chosen.stringValue()) == str(dev / 'cu.usbserial-110')
        wizard.popup.selectItemAtIndex_(0)   # ... and picks the roaster
        wizard.port_chosen()
        wizard.go_forward()
        assert controller.settings.device == str(dev / 'cu.Roaster_SIM')
        # 3. starting: Continue only once the bridge runs
        assert wizard.step().key == 'start'
        assert not bool(wizard.forward.isEnabled())
        wizard.start_bridge()
        delegate.refresh()
        assert controller.poll().running
        assert bool(wizard.forward.isEnabled()) and not bool(wizard.start.isEnabled())
        assert str(wizard.start.title()) == 'Bridge Is Running'
        wait_for(lambda: sim.links() == ['up'], what='the port to be opened')
        wizard.go_forward()
        # 4. Artisan: the path to paste, and the live status
        assert wizard.step().key == 'artisan'
        assert str(wizard.path.stringValue()) == controller.virtual_port
        wizard.copy_path()
        assert quiet['clipboard'] == controller.virtual_port
        assert guide.ARTISAN_PORT_MENU in wizard.step().body
        artisan = Artisan(controller.virtual_port)
        artisan.on()
        artisan.ask('{[RD A0]}')
        delegate.refresh()
        assert str(wizard.status.headline.stringValue()) == 'Receiving roaster replies'
        artisan.off()
        wizard.go_forward()
        # 5. the two settings files
        assert wizard.step().key == 'aset'
        assert 'artisan-bridge.aset' in wizard.step().body and 'artisan-direct.aset' in wizard.step().body
        assert str(dev / 'cu.Roaster_SIM') in wizard.step().body  # names the direct port to switch back to
        assert str(wizard.forward.title()) == 'Done'
        assert controller.needs_setup()
        wizard.go_forward()
        assert not controller.needs_setup()
        assert delegate.ask.shown == []

    def test_without_any_port_the_guide_does_not_continue(self, launch: Callable[[], Any], dev: Path) -> None:
        for entry in dev.iterdir():
            entry.unlink()
        delegate = launch()
        wizard = delegate.guide_window
        assert str(wizard.found.stringValue()) == 'No port that looks like a Kaleido yet.'
        wizard.go_forward()
        assert [str(title) for title in wizard.popup.itemTitles()] == ['No serial ports found']
        assert not bool(wizard.forward.isEnabled())
        wizard.go_forward()
        assert wizard.step().key == 'port'  # still there


class TestRelaunch:

    def test_saved_settings_are_used_and_the_bridge_is_not_started(self, launch: Callable[[], Any], sim: SimRoaster, dev: Path, quiet: dict[str, Any]) -> None:
        first = launch()
        complete_setup(first, sim)
        first.controller.stop()
        wait_for(lambda: sim.links() == ['up', 'down'])
        quiet['front'].clear()
        relaunched = launch()
        assert quiet['front'] == []  # no setup guide this time
        assert relaunched.controller.settings.device == str(dev / 'cu.Roaster_SIM')
        assert relaunched.controller.poll().state is State.STOPPED
        time.sleep(0.2)
        assert sim.links() == ['up', 'down']  # automatic connection is off by default
        assert menu(relaunched)['Start Bridge']

    def test_with_automatic_start_turned_on(self, launch: Callable[[], Any], sim: SimRoaster) -> None:
        first = launch()
        complete_setup(first, sim)
        first.settings_window = ui.SettingsWindow(first)
        first.settings_window.reload()
        assert int(first.settings_window.auto_start.state()) == 0
        first.settings_window.auto_start.setState_(1)
        first.settings_window.toggle_auto_start(first.settings_window.auto_start)
        first.controller.stop()
        wait_for(lambda: sim.links() == ['up', 'down'])
        relaunched = launch()
        assert relaunched.controller.poll().running
        wait_for(lambda: sim.links() == ['up', 'down', 'up'])


class TestMenu:

    def test_the_menu_follows_the_status(self, launch: Callable[[], Any], quiet: dict[str, Any]) -> None:
        delegate = launch()
        complete_setup(delegate)
        wait_for(lambda: 'Waiting for Artisan' in menu(delegate), what='waiting for Artisan')
        entries = menu(delegate)
        assert not entries['Start Bridge'] and entries['Stop Bridge…']
        assert entries['Copy Virtual Port Path'] and entries['Open Log'] and entries['Settings…'] and entries['Setup Guide…']
        artisan = Artisan(delegate.controller.virtual_port)
        wait_for(lambda: 'Artisan attached, waiting for the first reply' in menu(delegate), what='attached')
        artisan.on()
        artisan.ask('{[RD A0]}')
        assert 'Receiving roaster replies' in menu(delegate)
        artisan.off()
        wait_for(lambda: 'Waiting for Artisan' in menu(delegate))
        delegate.copyVirtualPort_(None)
        assert quiet['clipboard'] == delegate.controller.virtual_port

    def test_settings_cannot_change_the_port_while_the_bridge_runs(self, launch: Callable[[], Any]) -> None:
        delegate = launch()
        complete_setup(delegate)
        delegate.show_settings()
        assert not bool(delegate.settings_window.popup.isEnabled())
        assert str(delegate.settings_window.port_note.stringValue()) == 'Stop the bridge to change the port.'
        delegate.controller.stop()
        delegate.refresh()
        assert bool(delegate.settings_window.popup.isEnabled())


class TestStopping:

    def test_stopping_while_artisan_is_attached_warns_and_defaults_to_cancel(self, launch: Callable[[], Any], sim: SimRoaster) -> None:
        delegate = launch()
        complete_setup(delegate, sim)
        artisan = Artisan(delegate.controller.virtual_port)
        artisan.on()
        delegate.stopBridge_(None)  # the user dismisses the alert with its default button
        message, text, buttons, critical = delegate.ask.shown[-1]
        assert message == 'Artisan is connected through the bridge.' and 'CL AR' in text
        assert buttons == ['Cancel', 'Stop Anyway'] and critical
        assert delegate.controller.poll().running
        assert artisan.ask('{[RD A0]}').startswith(b'{0,BT:')  # undisturbed
        artisan.off()  # the right way round: OFF in Artisan first
        wait_for(lambda: not delegate.controller.poll().attached)
        delegate.stopBridge_(None)
        message, text, buttons, critical = delegate.ask.shown[-1]
        assert message == 'Stop the bridge?' and 'restart of the Mac' in text and buttons == ['Stop Bridge', 'Cancel'] and not critical
        assert not delegate.controller.poll().running
        wait_for(lambda: sim.links() == ['up', 'down'])
        assert sim.commands()[-1] == '{[CL AR]}'

    def test_stop_anyway(self, launch: Callable[[], Any], sim: SimRoaster) -> None:
        delegate = launch()
        complete_setup(delegate, sim)
        artisan = Artisan(delegate.controller.virtual_port)
        artisan.on()
        delegate.ask.answers = [1]  # Stop Anyway
        delegate.stopBridge_(None)
        assert not delegate.controller.poll().running
        artisan.vanish()
        wait_for(lambda: sim.links() == ['up', 'down'])
        assert '{[CL AR]}' not in sim.commands()
        delegate.tick_(None)
        assert len(delegate.ask.shown) == 1  # the stop the user asked for is not reported as a failure

    def test_quit_asks_too(self, launch: Callable[[], Any], monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeApplication()
        monkeypatch.setattr(app_module, 'NSApp', fake)
        delegate = launch()
        complete_setup(delegate)
        delegate.ask.answers = [1]  # Cancel
        delegate.quitApp_(None)
        assert not fake.terminated and delegate.controller.poll().running
        delegate.quitApp_(None)  # Stop Bridge
        assert fake.terminated and not delegate.controller.poll().running

    def test_a_signal_quits_in_order(self, launch: Callable[[], Any], sim: SimRoaster, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeApplication()
        monkeypatch.setattr(app_module, 'NSApp', fake)
        delegate = launch()
        complete_setup(delegate, sim)
        delegate.on_signal(15, None)
        delegate.tick_(None)
        assert fake.terminated
        assert delegate.applicationShouldTerminate_(None) == 1
        wait_for(lambda: sim.links() == ['up', 'down'])


class TestFailureAlerts:

    def test_artisan_vanishing_mid_session(self, launch: Callable[[], Any], sim: SimRoaster, quiet: dict[str, Any]) -> None:
        delegate = launch()
        complete_setup(delegate, sim)
        artisan = Artisan(delegate.controller.virtual_port)
        artisan.on()
        artisan.vanish()
        wait_for(lambda: not delegate.controller.running(), what='the bridge to stop')
        delegate.ask.answers = [1]  # Help
        quiet['front'].clear()
        delegate.tick_(None)
        message, text, buttons, critical = delegate.ask.shown[-1]
        assert message == 'Connection lost during an active session. The bridge stopped.' and critical and buttons == ['OK', 'Help']
        assert 'CL AR was not delivered' in text and 'cannot tell whether Artisan crashed or was force quit' in text
        assert 'the roaster sees the link drop' in text and 'reset Bluetooth yourself first' in text
        assert quiet['front'] == ['Kaleido Serial Bridge Help']
        delegate.tick_(None)
        assert len(delegate.ask.shown) == 1  # told once
        entries = menu(delegate)
        assert 'Connection lost during an active session. The bridge stopped.' in entries and entries['Start Bridge']
        wait_for(lambda: sim.links() == ['up', 'down'])

    def test_bluetooth_port_failure(self, launch: Callable[[], Any], sim: SimRoaster) -> None:
        delegate = launch()
        complete_setup(delegate, sim)
        sim.drop_link()
        wait_for(lambda: not delegate.controller.running(), what='the bridge to stop')
        delegate.tick_(None)
        message, text, _, critical = delegate.ask.shown[-1]
        assert message == 'Bluetooth port failed, bridge stopped' and critical and 'Check the roaster' in text
        assert 'starting the bridge alone may then not reconnect' in text and 'Reset Bluetooth yourself' in text

    def test_a_start_that_fails_is_explained(self, launch: Callable[[], Any], dev: Path) -> None:
        delegate = launch()
        complete_setup(delegate)
        delegate.controller.stop()
        (dev / 'cu.Roaster_SIM').unlink()  # Bluetooth off, or the roaster unpaired
        delegate.startBridge_(None)
        message, text, _, _ = delegate.ask.shown[-1]
        assert message == 'The bridge could not be started' and 'does not exist' in text and 'Nothing was changed' in text
        assert 'Could not start the bridge' in menu(delegate)

    def test_help_explains_recovery_and_the_way_back(self) -> None:
        topics = {topic.title: topic.body for topic in guide.help_topics('/dev/cu.Roaster_SRSv6')}
        silent = topics['No readings after Start']
        assert 'Reset Bluetooth yourself' in silent and 'never resets Bluetooth' in silent
        # the advice promises nothing: a restart helped on the tested setup, and one first start after a restart still failed
        assert 'worked each time' not in silent and 'not every time' in silent
        assert 'No reset is known to bring the connection back every time' in silent
        stops = topics['When the bridge stops by itself']
        # the cause is not claimed: a crash and Artisan's own timeout on a silent roaster look the same to the bridge
        assert stops.startswith('Connection lost during an active session') and 'cannot tell why' in stops
        assert 'vanished' not in stops
        # switching the roaster on again may need a manual Bluetooth reset; the bridge does none itself
        assert 'starting the bridge alone may not reconnect' in stops and 'Reset Bluetooth yourself before' in stops
        assert 'sudo pkill -x bluetoothd' in stops and 'In both tests this manual reset' in stops and 'not a guarantee' in stops
        assert 'does not reset Bluetooth, reopen the port or start again on its own' in stops
        back = topics['Back to direct Bluetooth']
        assert 'artisan-direct.aset' in back and '/dev/cu.Roaster_SRSv6' in back and guide.ARTISAN_PORT_MENU in back
        assert 'has not been verified' in topics['What the bridge does and does not do']


class ServiceSpy:
    """Stands in for loginitem._service and records every call. With the opt-out set it must never be called."""

    def __init__(self, status: int = 1) -> None:
        self.calls = 0
        self.status_value = status
        self.registered: list[bool] = []

    def __call__(self) -> Any:
        self.calls += 1
        return self

    def status(self) -> int:
        return self.status_value

    def registerAndReturnError_(self, _error: Any) -> tuple[bool, Any]:  # noqa: N802
        self.registered.append(True)
        return True, None

    def unregisterAndReturnError_(self, _error: Any) -> tuple[bool, Any]:  # noqa: N802
        self.registered.append(False)
        return True, None


class TestLoginItemOptOut:
    """KALEIDO_BRIDGE_NO_LOGIN_ITEM=1 keeps checks of a built app away from the login item service of macOS."""

    @pytest.fixture
    def service(self, monkeypatch: pytest.MonkeyPatch) -> ServiceSpy:
        spy = ServiceSpy()
        monkeypatch.setattr(sys, 'frozen', True, raising=False)  # as in the built app, where the service would be asked
        monkeypatch.setattr(loginitem, '_service', spy)
        return spy

    def test_with_the_opt_out_nothing_asks_the_service(self, monkeypatch: pytest.MonkeyPatch, service: ServiceSpy) -> None:
        monkeypatch.setenv(loginitem.OPT_OUT_VARIABLE, '1')
        assert not loginitem.available()
        assert loginitem.state() == loginitem.NOT_QUERIED == 'not queried (KALEIDO_BRIDGE_NO_LOGIN_ITEM=1)'
        assert not loginitem.is_enabled()
        for enabled in (True, False):
            done, problem = loginitem.set_enabled(enabled)
            assert not done and 'KALEIDO_BRIDGE_NO_LOGIN_ITEM=1' in problem
        assert service.calls == 0 and service.registered == []

    def test_with_the_opt_out_the_self_test_reports_not_queried(self, monkeypatch: pytest.MonkeyPatch, service: ServiceSpy,
                                                               capsys: pytest.CaptureFixture[str]) -> None:
        from kaleido_serial_bridge import __main__ as entry  # pylint: disable=import-outside-toplevel
        monkeypatch.setenv(loginitem.OPT_OUT_VARIABLE, '1')
        assert entry.selftest() == 0
        assert 'login item service: not queried (KALEIDO_BRIDGE_NO_LOGIN_ITEM=1)' in capsys.readouterr().out
        assert service.calls == 0

    def test_with_the_opt_out_settings_disable_the_checkbox_and_refuse_changes(self, monkeypatch: pytest.MonkeyPatch, service: ServiceSpy,
                                                                               launch: Callable[[], Any]) -> None:
        monkeypatch.setenv(loginitem.OPT_OUT_VARIABLE, '1')
        delegate = launch()
        settings = ui.SettingsWindow(delegate)
        settings.reload()
        assert not bool(settings.login.isEnabled())
        assert 'not queried' in str(settings.login_note.stringValue())
        settings.login.setState_(1)
        settings.toggle_login(settings.login)  # as if the checkbox had been clicked anyway
        message, text, _, _ = delegate.ask.shown[-1]
        assert message == 'Login item not changed' and 'KALEIDO_BRIDGE_NO_LOGIN_ITEM=1' in text
        assert service.calls == 0 and service.registered == []

    def test_with_the_opt_out_rendering_the_windows_does_not_ask_the_service(self, monkeypatch: pytest.MonkeyPatch, service: ServiceSpy,
                                                                             tmp_path: Path) -> None:
        monkeypatch.setenv(loginitem.OPT_OUT_VARIABLE, '1')
        monkeypatch.setenv('KALEIDO_BRIDGE_HOME', str(tmp_path / 'home'))  # not the real settings
        written = app_module.render_screens(str(tmp_path / 'screens'))
        assert any(path.endswith('settings.png') for path in written)
        assert service.calls == 0

    def test_without_the_opt_out_the_service_is_asked_as_before(self, monkeypatch: pytest.MonkeyPatch, service: ServiceSpy,
                                                                launch: Callable[[], Any]) -> None:
        monkeypatch.delenv(loginitem.OPT_OUT_VARIABLE, raising=False)
        assert loginitem.available() and loginitem.state() == 'on' and loginitem.is_enabled()
        monkeypatch.setenv(loginitem.OPT_OUT_VARIABLE, '0')  # only "1" opts out
        assert loginitem.available()
        monkeypatch.delenv(loginitem.OPT_OUT_VARIABLE)
        delegate = launch()
        settings = ui.SettingsWindow(delegate)
        settings.reload()
        assert bool(settings.login.isEnabled()) and int(settings.login.state()) == 1
        settings.login.setState_(0)
        settings.toggle_login(settings.login)
        assert service.registered == [False] and service.calls > 0
