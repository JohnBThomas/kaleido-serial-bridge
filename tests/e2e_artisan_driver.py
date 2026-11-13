#!/usr/bin/env python3
"""Runs inside an Artisan process and operates it like a user would. Started by e2e_artisan.py.

Artisan's own code is not modified. Two things differ from a normal start, both to protect the
settings of a real Artisan installation on this machine:
- the preferences domain is renamed before Artisan starts, so it reads and writes its own settings
- the caller redirects the home folder (CFFIXED_USER_HOME), so the log and data files go elsewhere

usage (current directory: Artisan's src):
    e2e_artisan_driver.py prepare     REPORT.jsonl PRESET.aset SAVED.aset   apply a machine preset, save the settings
    e2e_artisan_driver.py off-on-quit REPORT.jsonl SETTINGS.aset            load settings; ON, OFF, ON, quit
    e2e_artisan_driver.py relaunch    REPORT.jsonl                          start with the settings of the last quit; ON, OFF, quit
"""

from __future__ import annotations

import json
import os
import sys
import time

phase, report_path = sys.argv[1:3]
extra = sys.argv[3:]
sys.path.insert(0, os.getcwd())

import artisanlib.util as util  # noqa: E402

REAL_DOMAIN = util.application_organization_domain
util.application_organization_domain = 'kaleido-bridge-e2e.org'  # type: ignore[misc]  # -> preferences domain org.kaleido-bridge-e2e.Artisan

# off-on-quit: like opening the .aset with Artisan (same code as Help >> Load Settings...); otherwise a plain start
sys.argv = ['artisan.py', extra[0]] if phase == 'off-on-quit' else ['artisan.py']

from PyQt6.QtCore import QSettings, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from artisanlib import main  # noqa: E402  # creates the application object

settings_file = QSettings().fileName()
assert 'kaleido-bridge-e2e' in settings_file and REAL_DOMAIN.split('.')[0] not in os.path.basename(settings_file), settings_file

T0 = time.time()


def report(event: str, **data: object) -> None:
    with open(report_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'t': round(time.time() - T0, 2), 'phase': phase, 'event': event, **data}) + '\n')


def window() -> main.ApplicationWindow | None:
    for widget in QApplication.topLevelWidgets():
        if isinstance(widget, main.ApplicationWindow):
            return widget
    return None


def close_dialogs() -> None:
    """Nobody can click on a dialog of a window that is off screen: note it and close it."""
    dialog = QApplication.activeModalWidget()
    if dialog is not None:
        text = getattr(dialog, 'text', lambda: '')()
        report('dialog-closed', title=dialog.windowTitle(), text=str(text)[:200], kind=type(dialog).__name__)
        dialog.close()


def readings(aw: main.ApplicationWindow) -> dict[str, object]:
    kaleido = aw.kaleido
    return {
        'lcd_et': aw.lcd2.value(), 'lcd_bt': aw.lcd3.value(),
        'sid': None if kaleido is None else kaleido.get_state('sid'),
        'bt': None if kaleido is None else kaleido.get_state('BT'),
        'et': None if kaleido is None else kaleido.get_state('ET'),
        'monitoring': bool(aw.qmc.flagon),
    }


def live(aw: main.ApplicationWindow) -> bool:
    now = readings(aw)
    return bool(now['monitoring']) and now['sid'] is not None and float(now['lcd_bt']) > 0 and float(now['lcd_et']) > 0  # type: ignore[arg-type]


def script():  # type: ignore[no-untyped-def]
    """The steps, as a generator: yield a condition to wait for (or a number of seconds)."""
    aw = window()
    while aw is None:
        yield 0.2
        aw = window()
    yield 3.0
    from artisanlib.kaleido import KaleidoPort
    report('started', version=main.__version__, revision=main.__revision__, stock_kaleido=not hasattr(KaleidoPort(), '_diag'),
           settings_file=os.path.basename(settings_file), device=aw.qmc.device, kaleido_serial=aw.kaleidoSerial, comport=aw.ser.comport,
           baudrate=aw.ser.baudrate, bytesize=aw.ser.bytesize, parity=aw.ser.parity, stopbits=aw.ser.stopbits, timeout=aw.ser.timeout)

    def on(label: str):  # type: ignore[no-untyped-def]
        aw.qmc.ToggleMonitor()  # the ON button
        report(f'{label}: ON clicked')
        yield lambda: live(aw)
        yield 3.2  # two more sampling intervals
        first = readings(aw)
        yield 3.2
        second = readings(aw)
        report(f'{label}: readings', first=first, second=second, updating=first['bt'] != second['bt'] or first['et'] != second['et'])

    def off(label: str):  # type: ignore[no-untyped-def]
        aw.qmc.ToggleMonitor()  # the OFF button
        report(f'{label}: OFF clicked')
        yield lambda: aw.kaleido is None and not aw.qmc.flagsamplingthreadrunning
        report(f'{label}: disconnected', readings=readings(aw))

    if phase == 'prepare':
        preset, saved = extra
        # what Config >> Machine >> Kaleido >> Serial does, and the port its dialog would then ask for
        aw.loadSettings(fn=preset, remember=False, machine=True, reload=False)
        aw.ser.comport = '/dev/cu.DirectPortPlaceholder'  # stands for the direct Bluetooth port; never opened
        yield 1.0
        # what Help >> Save Settings... does
        report('preset applied and settings saved', saved=bool(aw.closeEventSettings(saved)), device=aw.qmc.device,
               kaleido_serial=aw.kaleidoSerial, comport=aw.ser.comport, baudrate=aw.ser.baudrate)
    elif phase == 'off-on-quit':
        yield from on('first ON')
        yield from off('OFF')
        yield 5.0
        yield from on('second ON (after OFF)')
        report('quit requested while readings are updating')
    else:
        yield from on('ON after relaunch')
        yield from off('final OFF')
        yield 1.0
        report('quit requested')
    aw.fileQuit()  # the Quit menu action (Cmd-Q)
    report('quit returned')


steps = script()
waiting_for = None
deadline = 0.0


def advance() -> None:
    global waiting_for, deadline  # pylint: disable=global-statement
    close_dialogs()
    try:
        if waiting_for is not None:
            if callable(waiting_for):
                if not waiting_for():
                    if time.time() > deadline:
                        aw = window()
                        report('TIMEOUT', readings=None if aw is None else readings(aw))
                        os._exit(3)  # pylint: disable=protected-access
                    QTimer.singleShot(100, advance)
                    return
            elif time.time() < deadline:
                QTimer.singleShot(100, advance)
                return
        waiting_for = next(steps)
        deadline = time.time() + (20.0 if callable(waiting_for) else float(waiting_for))
        QTimer.singleShot(100, advance)
    except StopIteration:
        pass
    except Exception as e:  # pylint: disable=broad-except
        report('ERROR', error=repr(e))
        os._exit(4)  # pylint: disable=protected-access


QTimer.singleShot(500, advance)
main.main()
report('process exiting normally')
