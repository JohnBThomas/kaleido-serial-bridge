"""The windows of the app: setup guide, settings and help. AppKit only; what they say comes from guide.py."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import objc
from AppKit import (
    NSAlert,
    NSAlertStyleCritical,
    NSAlertStyleWarning,
    NSApp,
    NSAppearance,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSBitmapImageFileTypePNG,
    NSButton,
    NSColor,
    NSFont,
    NSGraphicsContext,
    NSImage,
    NSImageView,
    NSLayoutAttributeCenterY,
    NSLayoutAttributeLeading,
    NSLayoutConstraint,
    NSMakeRect,
    NSPasteboard,
    NSPasteboardTypeString,
    NSPopUpButton,
    NSStackView,
    NSTextField,
    NSTextView,
    NSUserInterfaceLayoutOrientationHorizontal,
    NSUserInterfaceLayoutOrientationVertical,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskTitled,
    NSWorkspace,
)
from Foundation import NSURL, NSAttributedString, NSMutableAttributedString, NSObject

from . import APP_NAME, __version__, guide, loginitem
from .controller import BridgeController, State, Status
from .menu import SYMBOLS
from .ports import Port, best_guess
from .recovery import Phase, Progress

WIDTH = 580.0
MARGIN = 22.0
TEXT_WIDTH = WIDTH - 2 * MARGIN
BLUETOOTH_SETTINGS = 'x-apple.systempreferences:com.apple.BluetoothSettings'


# ---- small building blocks

def label(text: str, size: float = 13.0, bold: bool = False, secondary: bool = False, selectable: bool = False) -> Any:
    field = NSTextField.wrappingLabelWithString_(text)
    field.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
    field.setPreferredMaxLayoutWidth_(TEXT_WIDTH)
    field.setSelectable_(selectable)
    if secondary:
        field.setTextColor_(NSColor.secondaryLabelColor())
    return field


class Callback(NSObject):
    """Lets a button call a Python function. The windows themselves are plain Python objects."""

    def initWithFunction_(self, function: Callable[[Any], None]) -> Any:  # noqa: N802
        self = objc.super(Callback, self).init()  # noqa: PLW0642  # the Objective-C way to initialize
        if self is None:
            return None
        self.function = function
        return self

    def call_(self, sender: Any) -> None:
        self.function(sender)


_callbacks: list[Any] = []  # controls do not keep their target alive


def callback(function: Callable[[Any], None]) -> Any:
    target = Callback.alloc().initWithFunction_(function)
    _callbacks.append(target)
    return target


def button(title: str, function: Callable[[Any], None]) -> Any:
    return NSButton.buttonWithTitle_target_action_(title, callback(function), 'call:')


def checkbox(title: str, function: Callable[[Any], None]) -> Any:
    return NSButton.checkboxWithTitle_target_action_(title, callback(function), 'call:')


def popup(function: Callable[[Any], None]) -> Any:
    control = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(0, 0, 360, 26), False)
    control.setTarget_(callback(function))
    control.setAction_('call:')
    return control


def stack(views: list[Any], vertical: bool = True, spacing: float = 10.0) -> Any:
    result = NSStackView.stackViewWithViews_(views)
    result.setOrientation_(NSUserInterfaceLayoutOrientationVertical if vertical else NSUserInterfaceLayoutOrientationHorizontal)
    result.setAlignment_(NSLayoutAttributeLeading if vertical else NSLayoutAttributeCenterY)
    result.setSpacing_(spacing)
    return result


def spacer() -> Any:
    """Takes up whatever height is left, so that what follows sits at the bottom."""
    view = NSView.alloc().init()
    view.setContentHuggingPriority_forOrientation_(1, 1)
    view.setContentCompressionResistancePriority_forOrientation_(1, 1)
    return view


def make_window(title: str, content: Any, height: float) -> Any:
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, WIDTH, height), NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable,
        NSBackingStoreBuffered, False)
    window.setTitle_(title)
    window.setReleasedWhenClosed_(False)
    root = window.contentView()
    content.setTranslatesAutoresizingMaskIntoConstraints_(False)
    root.addSubview_(content)
    NSLayoutConstraint.activateConstraints_([
        content.leadingAnchor().constraintEqualToAnchor_constant_(root.leadingAnchor(), MARGIN),
        content.trailingAnchor().constraintEqualToAnchor_constant_(root.trailingAnchor(), -MARGIN),
        content.topAnchor().constraintEqualToAnchor_constant_(root.topAnchor(), MARGIN),
        content.bottomAnchor().constraintEqualToAnchor_constant_(root.bottomAnchor(), -MARGIN),
    ])
    window.center()
    return window


def bring_forward(window: Any) -> None:
    NSApp.activateIgnoringOtherApps_(True)
    window.makeKeyAndOrderFront_(None)


def copy_text(text: str) -> None:
    pasteboard = NSPasteboard.generalPasteboard()
    pasteboard.clearContents()
    pasteboard.setString_forType_(text, NSPasteboardTypeString)


def run_alert(message: str, text: str, buttons: list[str], critical: bool = False) -> int:
    """Shows an alert and returns the index of the button that was clicked. The first button is the default."""
    alert = NSAlert.alloc().init()
    alert.setMessageText_(message)
    alert.setInformativeText_(text)
    alert.setAlertStyle_(NSAlertStyleCritical if critical else NSAlertStyleWarning)
    for title in buttons:
        alert.addButtonWithTitle_(title)
    NSApp.activateIgnoringOtherApps_(True)
    return int(alert.runModal()) - 1000


def symbol(name: str, description: str) -> Any:
    image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, description)
    if image is not None:
        image.setTemplate_(True)
    return image


def render_png(window: Any, path: str) -> None:
    """Draws the content of a window into a PNG file without it being on screen (for checks and documentation)."""
    window.setAppearance_(NSAppearance.appearanceNamed_('NSAppearanceNameAqua'))  # the same picture in light and dark mode
    view = window.contentView()
    view.layoutSubtreeIfNeeded()
    bounds = view.bounds()
    bitmap = view.bitmapImageRepForCachingDisplayInRect_(bounds)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(NSGraphicsContext.graphicsContextWithBitmapImageRep_(bitmap))
    NSColor.colorWithCalibratedWhite_alpha_(0.93, 1.0).setFill()
    NSBezierPath.fillRect_(bounds)
    NSGraphicsContext.restoreGraphicsState()
    view.cacheDisplayInRect_toBitmapImageRep_(bounds, bitmap)
    bitmap.representationUsingType_properties_(NSBitmapImageFileTypePNG, {}).writeToFile_atomically_(path, True)


class StatusLine:
    """A symbol and two lines of text that show the current status inside a window."""

    def __init__(self) -> None:
        self.image = NSImageView.alloc().init()
        self.headline = label('', bold=True)
        self.detail = label('', size=12.0, secondary=True)
        self.detail.setPreferredMaxLayoutWidth_(TEXT_WIDTH - 40)
        self.view = stack([self.image, stack([self.headline, self.detail], spacing=2.0)], vertical=False, spacing=10.0)

    def show(self, status: Status) -> None:
        self.image.setImage_(symbol(SYMBOLS[status.state], status.headline))
        self.headline.setStringValue_(status.headline)
        self.detail.setStringValue_(status.detail)


def fill_ports(popup: Any, ports: list[Port], chosen: str) -> list[str]:
    """Fills a pop-up with the ports and returns their paths in menu order. A chosen port that is gone stays listed."""
    popup.removeAllItems()
    paths: list[str] = []
    for port in ports:
        popup.addItemWithTitle_(port.label)
        paths.append(port.path)
    if chosen and chosen not in paths:
        popup.addItemWithTitle_(f'{chosen}  (not present right now)')
        paths.append(chosen)
    if not paths:
        popup.addItemWithTitle_('No serial ports found')
        popup.setEnabled_(False)
        return paths
    popup.setEnabled_(True)
    if chosen in paths:
        popup.selectItemAtIndex_(paths.index(chosen))
    else:
        guess = best_guess(ports)
        popup.selectItemAtIndex_(paths.index(guess.path) if guess is not None else 0)
    return paths


# ---- setup guide

class SetupGuide:

    def __init__(self, app: Any) -> None:
        self.app = app
        self.controller: BridgeController = app.controller
        self.index = 0
        self.paths: list[str] = []
        self.counter = label('', size=12.0, secondary=True)
        self.title = label('', size=18.0, bold=True)
        self.body = stack([], spacing=12.0)
        self.back = button('Back', self.go_back)
        self.forward = button('Continue', self.go_forward)
        self.forward.setKeyEquivalent_('\r')
        footer = stack([self.back, self.forward], vertical=False)
        content = stack([self.counter, self.title, self.body, spacer(), footer], spacing=12.0)
        self.window = make_window(f'{APP_NAME} Setup', content, 440.0)
        # widgets that live in one of the steps
        self.found = label('', secondary=True)
        self.popup = popup(self.port_chosen)
        self.chosen = label('', size=12.0, secondary=True, selectable=True)
        self.start = button('Start Bridge', self.start_bridge)
        self.status = StatusLine()
        self.path = label(self.controller.virtual_port, selectable=True)
        self.path.setFont_(NSFont.monospacedSystemFontOfSize_weight_(12.0, 0.0))
        self.copied = label('', size=12.0, secondary=True)
        self.show_step()

    def steps(self) -> list[guide.Step]:
        return guide.setup_steps(self.controller.settings.device)

    def step(self) -> guide.Step:
        return self.steps()[self.index]

    def show(self) -> None:
        self.show_step()
        bring_forward(self.window)

    def show_step(self) -> None:
        steps = self.steps()
        step = steps[self.index]
        self.counter.setStringValue_(f'Step {self.index + 1} of {len(steps)}')
        self.title.setStringValue_(step.title)
        for view in list(self.body.arrangedSubviews()):
            self.body.removeArrangedSubview_(view)
            view.removeFromSuperview()
        views = [label(step.body)]
        if step.key == 'pair':
            views += [button('Open Bluetooth Settings…', self.open_bluetooth), self.found]
        elif step.key == 'port':
            views += [stack([self.popup, button('Refresh', self.refresh_clicked)], vertical=False), self.chosen]
            self.refresh_ports()
        elif step.key == 'start':
            views += [self.start, self.status.view]
        elif step.key == 'artisan':
            self.copied.setStringValue_('')
            views += [self.path, stack([button('Copy Path', self.copy_path), self.copied], vertical=False), self.status.view]
        for view in views:
            self.body.addArrangedSubview_(view)
        self.back.setHidden_(self.index == 0)
        self.forward.setTitle_('Done' if self.index == len(steps) - 1 else 'Continue')
        self.update(self.controller.status())

    def refresh_ports(self) -> None:
        self.paths = fill_ports(self.popup, self.controller.ports(), self.controller.settings.device)
        self.show_choice()

    def selected_path(self) -> str:
        index = int(self.popup.indexOfSelectedItem())
        return self.paths[index] if 0 <= index < len(self.paths) else ''

    def show_choice(self) -> None:
        path = self.selected_path()
        self.chosen.setStringValue_(path if path else 'Pair the roaster first, then click Refresh.')

    def update(self, status: Status) -> None:
        """Called by the app whenever the status may have changed."""
        key = self.step().key
        if key == 'pair':
            names = [port.name for port in self.controller.ports() if port.suggested]
            self.found.setStringValue_(('Found: ' + ', '.join(names)) if names else 'No port that looks like a Kaleido yet.')
        self.status.show(status)
        self.start.setEnabled_(not status.running)
        self.start.setTitle_('Bridge Is Running' if status.running else 'Start Bridge')
        if key == 'port':
            self.forward.setEnabled_(bool(self.selected_path()))
        elif key == 'start':
            self.forward.setEnabled_(status.running)
        else:
            self.forward.setEnabled_(True)

    # actions

    def go_back(self, _sender: Any = None) -> None:
        if self.index > 0:
            self.index -= 1
            self.show_step()

    def go_forward(self, _sender: Any = None) -> None:
        key = self.step().key
        if key == 'port':
            path = self.selected_path()
            if not path:
                return
            self.controller.choose_device(path)
        if self.index == len(self.steps()) - 1:
            self.controller.finish_setup()
            self.window.close()
            self.index = 0
            return
        self.index += 1
        self.show_step()

    def open_bluetooth(self, _sender: Any = None) -> None:
        NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(BLUETOOTH_SETTINGS))

    def refresh_clicked(self, _sender: Any = None) -> None:
        self.refresh_ports()
        self.update(self.controller.status())

    def port_chosen(self, _sender: Any = None) -> None:
        self.show_choice()
        self.update(self.controller.status())

    def start_bridge(self, _sender: Any = None) -> None:
        self.app.start_bridge()

    def copy_path(self, _sender: Any = None) -> None:
        copy_text(self.controller.virtual_port)
        self.copied.setStringValue_('Copied.')


# ---- settings

class SettingsWindow:

    def __init__(self, app: Any) -> None:
        self.app = app
        self.controller: BridgeController = app.controller
        self.paths: list[str] = []
        self.popup = popup(self.port_chosen)
        self.refresh = button('Refresh', self.refresh_clicked)
        self.port_note = label('', size=12.0, secondary=True)
        self.auto_start = checkbox('Start the bridge when the app opens', self.toggle_auto_start)
        self.auto_note = label('Off by default. The bridge opens the Bluetooth port when it starts, and that should happen when you intend it.',
                               size=12.0, secondary=True)
        self.login = checkbox('Open the app at login', self.toggle_login)
        self.login_note = label('', size=12.0, secondary=True)
        self.path = label(self.controller.virtual_port, selectable=True)
        self.path.setFont_(NSFont.monospacedSystemFontOfSize_weight_(12.0, 0.0))
        content = stack([
            label("Roaster's serial port", bold=True),
            stack([self.popup, self.refresh], vertical=False),
            self.port_note,
            label('Starting', bold=True),
            self.auto_start, self.auto_note, self.login, self.login_note,
            label('Virtual port for Artisan', bold=True),
            self.path,
            stack([button('Copy Path', self.copy_path), button('Setup Guide…', self.open_guide)], vertical=False),
            spacer(),
            label(f'{APP_NAME} {__version__}', size=11.0, secondary=True),
        ], spacing=9.0)
        self.window = make_window(f'{APP_NAME} Settings', content, 470.0)

    def show(self) -> None:
        self.reload()
        bring_forward(self.window)

    def reload(self) -> None:
        self.paths = fill_ports(self.popup, self.controller.ports(), self.controller.settings.device)
        self.auto_start.setState_(1 if self.controller.settings.auto_start else 0)
        if loginitem.available():
            self.login.setEnabled_(True)
            self.login.setState_(1 if loginitem.is_enabled() else 0)
            self.login_note.setStringValue_('Listed in System Settings » General » Login Items. This opens the app; it starts the bridge only if the option above is on.')
        else:
            self.login.setEnabled_(False)
            self.login_note.setStringValue_(f'Not available: {loginitem.NOT_QUERIED}.' if loginitem.opted_out()
                                            else 'Available when running as the installed app.')
        self.update(self.controller.status())

    def update(self, status: Status) -> None:
        editable = not status.running and bool(self.paths)
        self.popup.setEnabled_(editable)
        self.refresh.setEnabled_(not status.running)
        self.port_note.setStringValue_('Stop the bridge to change the port.' if status.running else 'Ports that look like a Kaleido are listed first.')

    def port_chosen(self, _sender: Any = None) -> None:
        index = int(self.popup.indexOfSelectedItem())
        if 0 <= index < len(self.paths):
            self.controller.choose_device(self.paths[index])

    def refresh_clicked(self, _sender: Any = None) -> None:
        self.reload()

    def toggle_auto_start(self, sender: Any) -> None:
        self.controller.set_auto_start(bool(sender.state()))

    def toggle_login(self, sender: Any) -> None:
        done, problem = loginitem.set_enabled(bool(sender.state()))
        if not done:
            self.app.ask('Login item not changed', problem, ['OK'], False)
        self.reload()

    def copy_path(self, _sender: Any = None) -> None:
        copy_text(self.controller.virtual_port)

    def open_guide(self, _sender: Any = None) -> None:
        self.app.show_guide()


# ---- help

class HelpWindow:

    def __init__(self, app: Any) -> None:
        self.app = app
        scroll = NSTextView.scrollableTextView()
        self.text = scroll.documentView()
        self.text.setEditable_(False)
        self.text.setTextContainerInset_((6.0, 8.0))
        self.text.setDrawsBackground_(False)
        scroll.setDrawsBackground_(False)
        scroll.setHasVerticalScroller_(True)
        # one recovery attempt per click; the app asks for confirmation first (see AppDelegate.reset_bluetooth_and_restart)
        self.reset_button = button(guide.RECOVERY_BUTTON, lambda _sender: app.reset_bluetooth_and_restart())
        self.progress = label('', size=12.0, secondary=True)
        content = stack([self.reset_button, self.progress, scroll], spacing=8.0)
        NSLayoutConstraint.activateConstraints_([
            scroll.widthAnchor().constraintEqualToAnchor_(content.widthAnchor()),
            scroll.heightAnchor().constraintGreaterThanOrEqualToConstant_(380.0),
        ])
        self.window = make_window(f'{APP_NAME} Help', content, 620.0)

    def update_recovery(self, progress: Progress | None) -> None:
        """Shows how a recovery attempt is going. The button is off while one is under way."""
        active = progress is not None and progress.phase in (Phase.RUNNING, Phase.WAITING_FOR_ARTISAN)
        self.reset_button.setEnabled_(not active)
        if progress is None or progress.phase is Phase.IDLE:
            self.progress.setStringValue_('')
        elif progress.phase is Phase.FAILED and progress.step is not None:
            self.progress.setStringValue_(f'Stopped at "{progress.step.value}": {progress.detail}')
        else:
            self.progress.setStringValue_(progress.detail)

    def show(self) -> None:
        controller: BridgeController = self.app.controller
        document = NSMutableAttributedString.alloc().init()
        heading = {'NSFont': NSFont.boldSystemFontOfSize_(15.0), 'NSColor': NSColor.labelColor()}
        body = {'NSFont': NSFont.systemFontOfSize_(13.0), 'NSColor': NSColor.labelColor()}
        for topic in guide.help_topics(controller.settings.device):
            document.appendAttributedString_(NSAttributedString.alloc().initWithString_attributes_(topic.title + '\n\n', heading))
            document.appendAttributedString_(NSAttributedString.alloc().initWithString_attributes_(topic.body + '\n\n\n', body))
        self.text.textStorage().setAttributedString_(document)
        bring_forward(self.window)


def state_symbol(state: State, description: str) -> Any:
    return symbol(SYMBOLS[state], description)
