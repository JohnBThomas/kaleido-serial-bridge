"""Entry point of the app.

    Kaleido Serial Bridge                       the menu bar app
    Kaleido Serial Bridge --version
    Kaleido Serial Bridge --selftest            checks that everything the app needs is inside it, then exits
    Kaleido Serial Bridge --render-screens DIR  draws its windows into PNG files, then exits
    Kaleido Serial Bridge --cli DEVICE [...]    the bridge without the menu bar (see cli.py)
"""

from __future__ import annotations

import sys


def selftest() -> int:
    import platform

    import objc
    import serial

    from . import BUNDLE_ID, __version__, loginitem
    from .controller import State
    from .ui import state_symbol

    from AppKit import NSApplication  # noqa: I001
    NSApplication.sharedApplication()
    print(f'Kaleido Serial Bridge {__version__} ({BUNDLE_ID})')
    print(f'bundled: {bool(getattr(sys, "frozen", False))} | python {platform.python_version()} | pyserial {serial.__version__} | pyobjc {objc.__version__}')
    print(f'macOS {platform.mac_ver()[0]} {platform.machine()}')
    print(f'executable: {sys.executable}')
    print('code loaded from:', sorted({path for path in sys.path if path})[:3])
    missing = [state.value for state in State if state_symbol(state, '') is None]
    print('menu bar symbols:', 'all available' if not missing else f'MISSING for {missing}')
    print('login item service:', loginitem.state())
    from .recovery import parts_available  # pylint: disable=import-outside-toplevel
    print('guided recovery:', parts_available())
    return 1 if missing else 0


def main() -> int:
    arguments = sys.argv[1:]
    if arguments[:1] == ['--version']:
        from . import __version__
        print(__version__)
        return 0
    if arguments[:1] == ['--selftest']:
        return selftest()
    if arguments[:1] == ['--render-screens'] and len(arguments) == 2:
        from .app import render_screens
        for path in render_screens(arguments[1]):
            print(path)
        return 0
    if arguments[:1] == ['--cli']:
        from .cli import main as cli_main
        return cli_main(arguments[1:])
    from .app import run
    return run()


if __name__ == '__main__':
    sys.exit(main())
