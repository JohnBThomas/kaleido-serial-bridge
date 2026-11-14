#!/usr/bin/env python3
"""Acceptance check of the built app: runs "Kaleido Serial Bridge.app" itself against the simulated roaster.

    python tests/packaged_app_check.py "/path/to/Kaleido Serial Bridge.app"

The app is started the way macOS starts it, with an empty environment (no PATH to a Python, no
virtual environment) and its own home folder for settings and log (KALEIDO_BRIDGE_HOME), so an
installed copy and its settings are not touched. A status item appears in the menu bar while the
check runs. Nothing is clicked: the app is told to start the bridge by the "start when the app
opens" setting, and what it shows is read from its status file.

Every start of the app has KALEIDO_BRIDGE_NO_LOGIN_ITEM=1 set, so the app never asks the login
item service. (Asking it from a copy of the app makes macOS move a registered login item to that
copy.) The check looks in the unified log for a move of the login item during the run. That needs
no password and shows no dialog. If the log cannot be read, the check says so as UNVERIFIED instead
of passing. (It does not use sfltool dumpbtm: every call of that asks the user for an administrator
password.)

Not covered here, because it needs clicks: the setup guide and the alerts. Those are covered
in-process by tests/test_app.py.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import serial

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))

from sim_roaster import SimRoaster  # noqa: E402

BUNDLE_ID = 'io.github.johnbthomas.KaleidoSerialBridge'
results: list[tuple[bool, str]] = []
unverified: list[str] = []


def check(ok: object, what: str) -> None:
    results.append((bool(ok), what))
    print(('PASS  ' if ok else 'FAIL  ') + what, flush=True)


def login_item_updates(since: str) -> list[str] | None:
    """Lines of the unified log since then in which macOS moved the app's login item to another copy, or None if the
    log could not be read. Asks for no password and shows no dialog."""
    try:
        done = subprocess.run(['/usr/bin/log', 'show', '--style', 'compact', '--start', since, '--predicate',
                               'subsystem == "com.apple.backgroundtaskmanagement" AND eventMessage CONTAINS "_bundleURLForAuditToken"'],
                              capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    return [line for line in done.stdout.splitlines() if 'Kaleido Serial Bridge' in line or BUNDLE_ID in line]


def main() -> int:
    app = Path(sys.argv[1]).resolve()
    binary = app / 'Contents' / 'MacOS' / 'KaleidoSerialBridge'
    home = Path(tempfile.mkdtemp(prefix='ksb-check-')).resolve()
    environment = {'HOME': str(Path.home()), 'PATH': '/usr/bin:/bin', 'KALEIDO_BRIDGE_HOME': str(home),
                   'KALEIDO_BRIDGE_NO_LOGIN_ITEM': '1'}  # every start of the app below gets this environment
    started = time.strftime('%Y-%m-%d %H:%M:%S')
    status_file = home / 'status.json'

    def status() -> dict[str, object]:
        try:
            return dict(json.loads(status_file.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            return {}

    def wait_state(*states: str, timeout: float = 15.0) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = str(status().get('state', ''))
            if state in states:
                return state
            time.sleep(0.1)
        return str(status().get('state', '(no status)'))

    def launch() -> subprocess.Popen[bytes]:
        # like launchd does: empty environment, working directory /
        return subprocess.Popen([str(binary)], env=environment, cwd='/', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ---- the bundle is self-contained
    done = subprocess.run([str(binary), '--selftest'], env=environment, capture_output=True, text=True, timeout=60, check=False)
    print(done.stdout.strip())
    check(done.returncode == 0 and 'bundled: True' in done.stdout, 'self-test passes with an empty environment')
    check(str(app) in done.stdout and '.venvs' not in done.stdout and 'site-packages' not in done.stdout, 'code is loaded from inside the app bundle only')
    check('login item service: not queried' in done.stdout, 'the self-test does not ask the login item service')
    check('guided recovery: IOBluetoothPreferenceGetControllerPowerState found, IOBluetoothPreferenceSetControllerPowerState found, '
          'NSAppleScript found' in done.stdout, 'the bundled app can reach the Bluetooth power switch and the authorization dialog (looked up, not called)')
    screens = home / 'screens'
    done = subprocess.run([str(binary), '--render-screens', str(screens)], env=environment, capture_output=True, text=True, timeout=60, check=False)
    check(done.returncode == 0 and len(list(screens.glob('*.png'))) == 6, 'the setup guide and settings windows can be built inside the bundle')

    # ---- first run: no settings, so nothing may be started. (The app would show its setup guide; not launched here.)
    check(not (home / 'settings.json').exists(), 'a new home folder has no settings')

    sim = SimRoaster()
    try:
        # ---- relaunch with saved settings, automatic start on
        (home / 'settings.json').write_text(json.dumps({'version': 1, 'device': sim.device, 'auto_start': True, 'setup_done': True}))
        process = launch()
        state = wait_state('waiting-bluetooth', 'waiting-artisan')
        check(state in {'waiting-bluetooth', 'waiting-artisan'}, f'the app starts the bridge from its saved settings (state: {state})')
        record = status()
        check(record.get('running') is True and record.get('attached') is False, 'an open port alone is shown as waiting, not as communication')
        check(record.get('device') == sim.device and record.get('virtual_port') == str(home / 'cu.Roaster_bridge'), 'it uses the remembered port and the expected virtual port')
        loaded = subprocess.run(['/usr/sbin/lsof', '-p', str(process.pid)], capture_output=True, text=True, check=False).stdout
        outside = [line.split()[-1] for line in loaded.splitlines() if '/.venvs/' in line or '/site-packages/' in line or str(ROOT) in line]
        check(not outside, f'the running app has no file of the development environment open ({outside if outside else "none"})')

        # ---- status follows actual replies
        artisan = serial.Serial(str(home / 'cu.Roaster_bridge'), 57600, timeout=1.0, exclusive=True)

        def ask(command: str) -> bytes:
            artisan.write(command.encode() + b'\n')
            return artisan.readline()

        for command in ('{[PI]}', '{[TU C]}', '{[SC AR]}'):
            ask(command)
        reading = ask('{[RD A0]}')
        check(reading.startswith(b'{0,BT:'), 'readings pass through the packaged app')
        check(wait_state('receiving') == 'receiving', 'forwarded replies show as "receiving"')
        sim.mute = True
        artisan.timeout = 0.3
        deadline = time.time() + 9
        while time.time() < deadline and status().get('state') != 'no-replies':
            ask('{[RD A0]}')
        check(status().get('state') == 'no-replies', 'a roaster that stops answering shows as "no replies"')
        sim.mute = False
        artisan.timeout = 1.0
        artisan.reset_input_buffer()
        ask('{[RD A0]}')
        check(wait_state('receiving') == 'receiving', 'and as "receiving" again once it answers')
        ask('{[CL AR]}')
        artisan.close()
        check(wait_state('waiting-artisan', 'waiting-bluetooth') in {'waiting-artisan', 'waiting-bluetooth'}, 'after OFF in Artisan the app waits again')
        check(sim.links() == ['up'], 'the port of the roaster was opened once and stayed open')

        # ---- OFF -> ON again through the same open port
        artisan = serial.Serial(str(home / 'cu.Roaster_bridge'), 57600, timeout=1.0, exclusive=True)
        for command in ('{[PI]}', '{[TU C]}', '{[SC AR]}'):
            ask(command)
        check(ask('{[RD A0]}').startswith(b'{0,BT:') and sim.links() == ['up'], 'a second Artisan session works without reopening the port')
        ask('{[CL AR]}')
        artisan.close()
        wait_state('waiting-artisan', 'waiting-bluetooth')

        # ---- clean stop
        process.send_signal(signal.SIGTERM)
        try:
            code = process.wait(15)
        except subprocess.TimeoutExpired:
            process.kill()
            code = -9
        check(code == 0, f'the app quits cleanly when asked to (exit code {code})')
        time.sleep(0.3)
        check(sim.links() == ['up', 'down'], 'quitting closes the port of the roaster')
        check(sim.commands()[-1] == '{[CL AR]}', 'the app itself sent nothing to the roaster')
        check(not (home / 'cu.Roaster_bridge').exists() and not status_file.exists(), 'the virtual port and the status file are gone')
        log = (home / 'bridge.log').read_text(encoding='utf-8')
        check(log.count('opened (57600 8N1') == 1 and log.count('detached, clean (Artisan ended its session with CL AR)') == 2, 'the log shows one open and two clean sessions')

        # ---- relaunch: the same settings, a new open
        process = launch()
        state = wait_state('waiting-bluetooth', 'waiting-artisan')
        check(state in {'waiting-bluetooth', 'waiting-artisan'} and sim.links() == ['up', 'down', 'up'], 'after a relaunch the saved settings are used again')
        process.send_signal(signal.SIGTERM)
        check(process.wait(15) == 0, 'and it quits cleanly again')
    finally:
        sim.close()

    # ---- the registered login item was left alone
    time.sleep(2.0)  # let the unified log catch up
    moved = login_item_updates(started)
    if moved is None:
        unverified.append('the registered login item: the unified log could not be read')
        print('UNVERIFIED  the registered login item: the unified log could not be read', flush=True)
    else:
        check(not moved, f'the unified log shows no move of the login item during the run ({len(moved)} lines)')

    failed = [what for ok, what in results if not ok]
    print(f'\n{len(results) - len(failed)} of {len(results)} checks passed'
          + (f', {len(unverified)} unverified' if unverified else '') + f'. Home folder of this run: {home}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
