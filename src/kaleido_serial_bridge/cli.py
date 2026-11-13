"""The bridge as a command line program, without the menu bar.

    python -m kaleido_serial_bridge.cli /dev/cu.Roaster_SRSv6

The menu bar app does the same with a status display around it.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time

from . import __version__
from .engine import DEFAULT_LINK, EXIT_SETUP, Bridge, log
from .linkstate import bluetooth_link_state


def watch_link(bridge: Bridge) -> None:
    """Logs what macOS reports about the Bluetooth link: after the open, and while no client is attached.

    Information only. The bridge never acts on it.
    """
    last = ''
    started = time.time()
    while bridge.exit_code is None:
        if bridge.session is None or not last:
            state = bluetooth_link_state(bridge.device)
            if state != last:
                if state == 'connected':
                    log.info('macOS reports the Bluetooth link to the roaster as connected')
                elif state == 'not connected':
                    log.warning('macOS reports the roaster as NOT connected. If this stays so for more than a few seconds after the '
                                'start, macOS did not establish the link for this open: Artisan will get no answers. Reset Bluetooth '
                                'yourself and start the bridge again.')
                else:
                    log.info('macOS does not list a Bluetooth device for this port; link state unknown')
                last = state
        wait = 2.0 if (last != 'connected' and time.time() - started < 30) else 60.0
        deadline = time.time() + wait
        while bridge.exit_code is None and time.time() < deadline:
            time.sleep(0.2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='kaleido-serial-bridge', description='Keeps the serial port of a Kaleido roaster open across Artisan sessions.')
    parser.add_argument('device', help='the real serial port of the roaster, e.g. /dev/cu.Roaster_SRSv6')
    parser.add_argument('--baudrate', type=int, default=57600, help='default: 57600 (the Kaleido Serial preset of Artisan)')
    parser.add_argument('--link', default=DEFAULT_LINK, help=f'path of the client endpoint to use as Comm Port in Artisan (default: {DEFAULT_LINK})')
    parser.add_argument('--log', default=None, help='log file (default: bridge.log next to the client endpoint)')
    parser.add_argument('--trace', action='store_true', help='also log every forwarded line (the answers contain the serial number of the roaster)')
    parser.add_argument('--no-link-check', action='store_true', help='do not ask macOS for the state of the Bluetooth link')
    parser.add_argument('--keep-link-on-abrupt-exit', action='store_true',
                        help='keep the real port open even if Artisan vanishes with a session open at the roaster. '
                             'Only for hardware that is known to stop heating by itself when the commands stop.')
    parser.add_argument('--version', action='version', version=__version__)
    args = parser.parse_args(argv)

    link = os.path.abspath(os.path.expanduser(args.link))
    os.makedirs(os.path.dirname(link), mode=0o700, exist_ok=True)
    log_path = os.path.abspath(os.path.expanduser(args.log)) if args.log else os.path.join(os.path.dirname(link), 'bridge.log')
    formatter = logging.Formatter('%(asctime)s.%(msecs)03d %(levelname)-7s %(message)s', datefmt='%m-%d %H:%M:%S')
    for handler in (logging.StreamHandler(sys.stderr), logging.FileHandler(log_path, encoding='utf-8')):
        handler.setFormatter(formatter)
        log.addHandler(handler)
    log.setLevel(logging.DEBUG if args.trace else logging.INFO)

    log.info('kaleido bridge %s starting (pid %d), log file %s', __version__, os.getpid(), log_path)
    bridge = Bridge(args.device, args.baudrate, link, args.keep_link_on_abrupt_exit, args.trace, not args.no_link_check)
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, bridge.on_signal)
    if not bridge.setup():
        bridge.teardown()
        return EXIT_SETUP
    if bridge.link_check:
        threading.Thread(target=watch_link, args=(bridge,), daemon=True).start()
    log.info('waiting for Artisan. Stop the bridge with Ctrl-C (turn Artisan OFF first).')
    return bridge.run()


if __name__ == '__main__':
    sys.exit(main())
