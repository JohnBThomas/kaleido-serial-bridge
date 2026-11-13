#!/usr/bin/env python3
"""Writes a copy of an Artisan settings file (.aset) that differs only in the Comm Port.

    python make_bridge_aset.py direct.aset bridge.aset

'direct.aset' is a file saved by Artisan (Help >> Save Settings...) or a machine preset.
'bridge.aset' gets the same content with [SerialPort] comport set to the client endpoint of
the bridge. Nothing else is changed, and the source file is never written to.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

DEFAULT_PORT = os.path.join(os.path.expanduser('~'), '.kaleido-bridge', 'cu.Roaster_bridge')
SAFE_VALUE = re.compile(r'^[A-Za-z0-9_./-]+$')  # needs no quoting in a Qt ini file


def set_comport(text: str, port: str) -> tuple[str, str | None]:
    """Returns the text with [SerialPort] comport set to port, and the previous value (None if there was none)."""
    newline = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines(keepends=True)
    section = None
    header_at = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            section = stripped[1:-1]
            if section == 'SerialPort':
                header_at = index
        elif section == 'SerialPort' and stripped.startswith('comport='):
            previous = stripped[len('comport='):]
            lines[index] = f'comport={port}{newline}'
            return ''.join(lines), previous
    if header_at is not None:
        lines.insert(header_at + 1, f'comport={port}{newline}')
        return ''.join(lines), None
    if lines and not lines[-1].endswith(('\n', '\r')):
        lines[-1] += newline
    lines.extend([newline, f'[SerialPort]{newline}', f'comport={port}{newline}'])
    return ''.join(lines), None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Copy an Artisan .aset, changing only the Comm Port.')
    parser.add_argument('source', help='settings file saved by Artisan, or a machine preset')
    parser.add_argument('target', help='the copy to write')
    parser.add_argument('--port', default=DEFAULT_PORT, help=f'the Comm Port to set (default: {DEFAULT_PORT})')
    args = parser.parse_args(argv)

    port = os.path.abspath(os.path.expanduser(args.port))
    if not SAFE_VALUE.match(port):
        print(f'error: {port!r} contains characters that would need quoting in a settings file; choose a simpler path', file=sys.stderr)
        return 2
    if os.path.exists(args.target) and os.path.samefile(args.source, args.target):
        print('error: source and target are the same file', file=sys.stderr)
        return 2
    with open(args.source, encoding='utf-8', newline='') as f:
        text = f.read()
    changed, previous = set_comport(text, port)
    with open(args.target, 'w', encoding='utf-8', newline='') as f:
        f.write(changed)
    print(f'{args.target}: Comm Port {previous if previous is not None else "(not set)"} -> {port}')
    print('everything else is identical to', args.source)
    return 0


if __name__ == '__main__':
    sys.exit(main())
