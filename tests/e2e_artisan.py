#!/usr/bin/env python3
"""End-to-end check with Artisan itself: Artisan -> bridge -> simulated roaster. No hardware.

Runs an unmodified Artisan source tree (window off screen) and operates it like a user:
1. applies Artisan's own "Kaleido > Serial" machine preset and saves the settings (Save Settings...)
2. make_bridge_aset.py derives a second settings file that differs only in the Comm Port
3. loads that file: ON, OFF, ON, quit while readings update
4. starts Artisan again (settings as left by the quit): ON, OFF, quit
Passes if readings are live after every ON and the simulated roaster saw its port opened
once and never closed.

    python tests/e2e_artisan.py --artisan-src /path/to/artisan/src

Not part of the automated tests: it needs Artisan's source and its Python environment
(run it with that environment's python). It does not touch the settings of an installed
Artisan: see e2e_artisan_driver.py. Make sure no other Artisan is running.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / 'tools'))

from sim_roaster import SimRoaster  # noqa: E402

TEST_DOMAIN = 'org.kaleido-bridge-e2e.Artisan'  # the preferences of the test instance, see e2e_artisan_driver.py


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--artisan-src', required=True, help="the 'src' directory of an Artisan checkout")
    parser.add_argument('--workdir', default=None)
    args = parser.parse_args()
    src = Path(args.artisan_src).resolve()
    work = Path(args.workdir or tempfile.mkdtemp(prefix='kaleido-bridge-e2e-')).resolve()
    home = work / 'home'
    home.mkdir(parents=True, exist_ok=True)
    link = work / 'kb' / 'cu.Roaster_bridge'
    report = work / 'report.jsonl'
    report.unlink(missing_ok=True)

    env = dict(os.environ, CFFIXED_USER_HOME=str(home), QT_QPA_PLATFORM='offscreen')
    driver = [sys.executable, str(HERE / 'e2e_artisan_driver.py')]
    exit_codes: dict[str, object] = {}

    def forget_test_settings() -> None:
        subprocess.run(['defaults', 'delete', TEST_DOMAIN], capture_output=True, check=False)
        (Path.home() / 'Library' / 'Preferences' / f'{TEST_DOMAIN}.plist').unlink(missing_ok=True)

    def run_artisan(phase: str, *arguments: str) -> None:
        print(f'--- running Artisan: {phase} ---', flush=True)
        try:
            done = subprocess.run([*driver, phase, str(report), *arguments], cwd=src, env=env, timeout=150, capture_output=True, text=True, check=False)
            exit_codes[phase] = done.returncode
            if done.returncode != 0:
                print(done.stderr[-2000:])
        except subprocess.TimeoutExpired:
            exit_codes[phase] = 'timeout'
        time.sleep(1.0)

    forget_test_settings()
    # 1. the settings a user has: Artisan's Kaleido > Serial preset plus the direct port, saved by Artisan itself
    preset = src / 'includes' / 'Machines' / 'Kaleido' / 'Serial.aset'
    direct = work / 'direct.aset'
    via_bridge = work / 'bridge.aset'
    run_artisan('prepare', str(preset), str(direct))
    # 2. the same settings with only the Comm Port changed
    made = subprocess.run([sys.executable, str(ROOT / 'tools' / 'make_bridge_aset.py'), str(direct), str(via_bridge), '--port', str(link)],
                          capture_output=True, text=True, check=False)
    print(made.stdout.strip() or made.stderr.strip())
    before = direct.read_text(encoding='utf-8').splitlines() if direct.exists() else []
    after = via_bridge.read_text(encoding='utf-8').splitlines() if via_bridge.exists() else []
    differing = [(a, b) for a, b in zip(before, after, strict=False) if a != b]
    print(f'settings files: {len(before)} lines each, {len(differing)} line differs: {differing}')

    sim = SimRoaster()
    bridge = subprocess.Popen([sys.executable, '-m', 'kaleido_serial_bridge.cli', sim.device, '--link', str(link), '--no-link-check', '--trace'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 5
    while not link.is_symlink() and time.time() < deadline:
        time.sleep(0.05)
    try:
        run_artisan('off-on-quit', str(via_bridge))   # 3.
        run_artisan('relaunch')                       # 4.
    finally:
        time.sleep(0.5)
        bridge_running = bridge.poll() is None
        links = sim.links()
        commands = sim.commands()
        bridge.terminate()
        bridge.wait(5)
        sim.close()
        forget_test_settings()

    events = [json.loads(line) for line in report.read_text(encoding='utf-8').splitlines()] if report.exists() else []
    print('\n=== what Artisan did and showed ===')
    for event in events:
        extra = {k: v for k, v in event.items() if k not in {'t', 'phase', 'event'}}
        print(f"{event['phase']:12s} {event['t']:6.1f}s  {event['event']}  {json.dumps(extra) if extra else ''}")
    print('\n=== what the simulated roaster saw ===')
    print('port opened/closed:', links)
    compact: list[str] = []
    for command in commands:
        if compact and compact[-1].startswith(command + ' x'):
            compact[-1] = f"{command} x{int(compact[-1].rsplit('x', 1)[1]) + 1}"
        elif compact and compact[-1] == command:
            compact[-1] = f'{command} x2'
        else:
            compact.append(command)
    print('commands:', ' | '.join(compact))
    log_text = (link.parent / 'bridge.log').read_text(encoding='utf-8')
    print('\n=== bridge log (without the per-line trace) ===')
    print('\n'.join(line for line in log_text.splitlines() if ' DEBUG ' not in line))

    readings = [e for e in events if e['event'].endswith(': readings')]
    checks = {
        'Artisan is the unmodified 5.0.0 source': all(e.get('version') == '5.0.0' and e.get('stock_kaleido') for e in events if e['event'] == 'started'),
        'all Artisan runs ended normally': exit_codes == {'prepare': 0, 'off-on-quit': 0, 'relaunch': 0},
        'the two settings files differ only in the Comm Port line': len(before) == len(after) > 100 and len(differing) == 1 and differing[0][1] == f'comport={link}',
        'Comm Port came from the .aset, and survived quit and relaunch': [e.get('comport') for e in events if e['event'] == 'started' and e['phase'] != 'prepare' and e.get('device') == 138 and e.get('kaleido_serial')] == [str(link)] * 2,
        'live, updating readings after each of the 3 ONs': len(readings) == 3 and all(e['updating'] and e['second']['sid'] is not None for e in readings),
        'no dialog needed attention': not any(e['event'] == 'dialog-closed' for e in events),
        'bridge still running at the end': bridge_running,
        'real port opened once and never closed': links == ['up'],
        'three sessions, each started with SC AR and ended with CL AR': commands.count('{[SC AR]}') == 3 and commands.count('{[CL AR]}') == 3,
        'bridge saw three clean detaches': log_text.count('detached, clean (Artisan ended its session with CL AR)') == 3,
    }
    print('\n=== result ===')
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print('work directory:', work)
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
