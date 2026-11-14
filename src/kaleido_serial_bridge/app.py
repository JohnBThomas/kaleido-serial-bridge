"""The menu bar app: a status item, its menu, and the alerts. The bridge itself lives in engine.py."""

from __future__ import annotations

import os
import signal
from typing import Any

import objc
from AppKit import (
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSMenu,
    NSMenuItem,
    NSRunLoop,
    NSRunLoopCommonModes,
    NSStatusBar,
    NSTimer,
    NSVariableStatusItemLength,
    NSWorkspace,
)
from Foundation import NSURL, NSObject

from . import APP_NAME, __version__, guide
from .controller import BridgeController, Exit, State, Status
from .engine import EXIT_ABRUPT, EXIT_OK, EXIT_SETUP, EXIT_UPSTREAM
from .menu import Entry, menu_entries
from .recovery import MacSystem, Phase, Recovery, System
from .ui import HelpWindow, SettingsWindow, SetupGuide, copy_text, run_alert, state_symbol

ACTIONS = {
    'start': 'startBridge:', 'stop': 'stopBridge:', 'copy': 'copyVirtualPort:', 'log': 'openLog:', 'settings': 'showSettings:',
    'guide': 'showGuide:', 'help': 'showHelp:', 'about': 'showAbout:', 'quit': 'quitApp:',
}
TICK = 0.5  # seconds between looks at the bridge


class AppDelegate(NSObject):

    def initWithController_(self, controller: BridgeController) -> Any:  # noqa: N802
        self = objc.super(AppDelegate, self).init()  # noqa: PLW0642  # the Objective-C way to initialize
        if self is None:
            return None
        self.controller = controller
        self.ask = run_alert              # replaced in tests
        self.item: Any = None
        self.menu: Any = None
        self.entries: list[Entry] = []
        self.shown: Status | None = None
        self.guide_window: Any = None
        self.settings_window: Any = None
        self.help_window: Any = None
        self.recovery_system: System | None = None  # MacSystem on first use; replaced in tests
        self.recovery: Recovery | None = None
        self.recovery_told: tuple[int, Phase] | None = None  # the last outcome an alert was shown for
        self.timer: Any = None
        self.busy = False
        self.quit_requested = False
        return self

    # ---- life cycle

    def applicationDidFinishLaunching_(self, _notification: Any) -> None:  # noqa: N802
        self.build_status_item()
        self.timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(TICK, self, 'tick:', None, True)
        NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSRunLoopCommonModes)  # keeps running while a menu or an alert is open
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(signum, self.on_signal)
        self.launch()

    @objc.python_method
    def launch(self) -> None:
        """What the app does by itself when it opens: the setup guide on first run, and nothing else unless asked to."""
        if self.controller.needs_setup():
            self.show_guide()
        elif self.controller.settings.auto_start:
            self.start_bridge()

    @objc.python_method
    def on_signal(self, _signum: int, _frame: object) -> None:
        self.quit_requested = True

    def applicationShouldTerminate_(self, _sender: Any) -> int:  # noqa: N802
        # Asking happens in quitApp_. When macOS itself ends the app (logout, restart) there is nobody to ask:
        # the bridge is stopped in order, virtual port first.
        self.controller.shutdown()
        return 1  # NSTerminateNow

    # ---- status item and menu

    @objc.python_method
    def build_status_item(self) -> None:
        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.menu = NSMenu.alloc().init()
        self.menu.setAutoenablesItems_(False)
        self.item.setMenu_(self.menu)
        self.refresh()

    @objc.python_method
    def refresh(self) -> Status:
        status = self.controller.poll()
        if status != self.shown:
            self.shown = status
            self.show_status(status)
        for window in (self.guide_window, self.settings_window):
            if window is not None:
                window.update(status)
        return status

    @objc.python_method
    def show_status(self, status: Status) -> None:
        if self.item is not None:
            button = self.item.button()
            image = state_symbol(status.state, status.headline)
            if image is not None:
                button.setImage_(image)
                button.setTitle_('')
            else:
                button.setTitle_('KB')
            button.setToolTip_(f'{APP_NAME}: {status.headline}')
        entries = menu_entries(status, __version__)
        if self.menu is not None and entries != self.entries:
            self.entries = entries
            self.menu.removeAllItems()
            for entry in entries:
                if not entry.key:
                    self.menu.addItem_(NSMenuItem.separatorItem())
                    continue
                item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(entry.title, ACTIONS.get(entry.key), '')
                item.setTarget_(self)
                item.setEnabled_(entry.enabled)
                if entry.key == 'headline':
                    item.setImage_(state_symbol(status.state, status.headline))
                self.menu.addItem_(item)

    def tick_(self, _timer: Any) -> None:
        if self.busy:
            return  # an alert of ours is open
        self.busy = True
        try:
            if self.quit_requested:
                NSApp.terminate_(None)
                return
            self.refresh()
            event = self.controller.take_exit()
            if event is not None and event.code != EXIT_OK:
                self.report_failure(event)
            if self.recovery is not None and self.recovery.active:
                self.advance_recovery()
        finally:
            self.busy = False

    # ---- what the menu does

    @objc.python_method
    def start_bridge(self) -> bool:
        if self.controller.needs_setup() and not self.controller.settings.device:
            self.show_guide()
            return False
        started, problem = self.controller.start()
        self.controller.take_exit()
        self.refresh()
        if not started:
            self.ask('The bridge could not be started', f"{problem}\n\n{guide.FAILURE_ADVICE['setup']}", ['OK'], False)
        return started

    @objc.python_method
    def confirm_and_stop(self) -> bool:
        """Stops the bridge if the user agrees. Returns False if it is still running."""
        status = self.controller.poll()
        if not status.running:
            return True
        if status.attached:
            message, text = guide.STOP_WHILE_ATTACHED
            agreed = self.ask(message, text, ['Cancel', 'Stop Anyway'], True) == 1
        else:
            message, text = guide.STOP_IDLE
            agreed = self.ask(message, text, ['Stop Bridge', 'Cancel'], False) == 0
        if agreed:
            self.controller.stop()
            self.controller.take_exit()
            self.refresh()
        return agreed

    @objc.python_method
    def report_failure(self, event: Exit) -> None:
        kind = {EXIT_SETUP: 'setup', EXIT_UPSTREAM: 'upstream', EXIT_ABRUPT: 'abrupt'}.get(event.code, 'upstream')
        status = self.controller.status()
        if self.ask(status.headline, f'{event.reason}\n\n{guide.FAILURE_ADVICE[kind]}', ['OK', 'Help'], True) == 1:
            self.show_help()

    # ---- guided Bluetooth recovery (one attempt per click, from the Help window)

    @objc.python_method
    def reset_bluetooth_and_restart(self) -> bool:
        """Asks first, then begins one recovery attempt. Returns whether one began."""
        if self.recovery is None:
            self.recovery = Recovery(self.controller, self.recovery_system if self.recovery_system is not None else MacSystem())
        if self.recovery.active:
            return False  # one at a time; the button is off meanwhile
        if self.controller.running():
            self.ask('Stop the bridge first.', 'The recovery works only while the bridge is stopped, and it never stops the '
                     'bridge itself. Click OFF in Artisan, then choose Stop Bridge in the menu.', ['OK'], False)
            return False
        message, text = guide.RECOVERY_CONFIRM
        if self.ask(message, text, ['Cancel', 'Reset Bluetooth'], True) != 1:
            return False
        self.recovery.begin()
        self.advance_recovery()
        return True

    @objc.python_method
    def advance_recovery(self) -> None:
        recovery = self.recovery
        if recovery is None:
            return
        recovery.step()
        progress = recovery.progress()
        if self.help_window is not None:
            self.help_window.update_recovery(progress)
        self.refresh()
        told = (progress.attempt, progress.phase)
        if progress.phase in (Phase.IDLE, Phase.RUNNING) or told == self.recovery_told:
            return
        self.recovery_told = told
        if progress.phase is Phase.WAITING_FOR_ARTISAN:
            self.ask(*guide.RECOVERY_STARTED, ['OK'], False)
        elif progress.phase is Phase.SUCCEEDED:
            self.ask(*guide.RECOVERY_SUCCEEDED, ['OK'], False)
        elif progress.phase is Phase.FAILED:
            step = progress.step.value if progress.step is not None else 'Recovery'
            self.ask(f'Recovery stopped at: {step}', f'{progress.detail}\n\n{guide.RECOVERY_MANUAL}', ['OK'], True)

    @objc.python_method
    def show_guide(self) -> None:
        if self.guide_window is None:
            self.guide_window = SetupGuide(self)
        self.guide_window.show()

    @objc.python_method
    def show_settings(self) -> None:
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self)
        self.settings_window.show()

    @objc.python_method
    def show_help(self) -> None:
        if self.help_window is None:
            self.help_window = HelpWindow(self)
        self.help_window.show()
        self.help_window.update_recovery(self.recovery.progress() if self.recovery is not None else None)

    def startBridge_(self, _sender: Any) -> None:  # noqa: N802
        self.start_bridge()

    def stopBridge_(self, _sender: Any) -> None:  # noqa: N802
        self.confirm_and_stop()

    def copyVirtualPort_(self, _sender: Any) -> None:  # noqa: N802
        copy_text(self.controller.virtual_port)

    def openLog_(self, _sender: Any) -> None:  # noqa: N802
        log = self.controller.paths.log
        if not log.exists():
            log.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            log.touch()
        NSWorkspace.sharedWorkspace().openURL_(NSURL.fileURLWithPath_(str(log)))

    def showSettings_(self, _sender: Any) -> None:  # noqa: N802
        self.show_settings()

    def showGuide_(self, _sender: Any) -> None:  # noqa: N802
        self.show_guide()

    def showHelp_(self, _sender: Any) -> None:  # noqa: N802
        self.show_help()

    def showAbout_(self, _sender: Any) -> None:  # noqa: N802
        NSApp.activateIgnoringOtherApps_(True)
        NSApp.orderFrontStandardAboutPanelWithOptions_({
            'ApplicationName': APP_NAME, 'ApplicationVersion': __version__, 'Version': '',
            'Copyright': 'MIT License. Not affiliated with Kaleido or the Artisan project.',
        })

    def quitApp_(self, _sender: Any) -> None:  # noqa: N802
        if self.confirm_and_stop():
            NSApp.terminate_(None)


def run() -> int:
    """Starts the menu bar app and returns when it quits."""
    application = NSApplication.sharedApplication()
    application.setActivationPolicy_(NSApplicationActivationPolicyAccessory)  # menu bar only, no Dock icon
    delegate = AppDelegate.alloc().initWithController_(BridgeController())
    application.setDelegate_(delegate)
    application.run()
    return 0


def render_screens(directory: str) -> list[str]:
    """Draws every window into a PNG and writes the menu as text, without showing anything. For checks and documentation."""
    from .ui import render_png
    NSApplication.sharedApplication()
    os.makedirs(directory, exist_ok=True)
    delegate = AppDelegate.alloc().initWithController_(BridgeController())
    written = []
    wizard = SetupGuide(delegate)
    for index, step in enumerate(wizard.steps()):
        wizard.index = index
        wizard.show_step()
        path = os.path.join(directory, f'setup-{index + 1}-{step.key}.png')
        render_png(wizard.window, path)
        written.append(path)
    settings = SettingsWindow(delegate)
    settings.reload()
    path = os.path.join(directory, 'settings.png')
    render_png(settings.window, path)
    written.append(path)
    path = os.path.join(directory, 'menu.txt')
    with open(path, 'w', encoding='utf-8') as f:
        for state in State:
            status = Status(state, f'<{state.value}>', 'detail', running=state not in {State.STOPPED, State.FAILED})
            f.write(f'--- {state.value} (symbol available: {state_symbol(state, "") is not None})\n')
            for entry in menu_entries(status, __version__):
                f.write(('    ' + ('' if entry.enabled else '(disabled) ') + entry.title if entry.key else '    ----') + '\n')
    written.append(path)
    return written
