"""What the menu of the status item contains, as plain data. The AppKit code only draws it."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass

from .controller import State, Status

# SF Symbols for the menu bar, by state. All exist since macOS 11.
SYMBOLS = {
    State.STOPPED: 'stop.circle',
    State.FAILED: 'exclamationmark.octagon.fill',
    State.WAITING_BLUETOOTH: 'antenna.radiowaves.left.and.right',
    State.WAITING_ARTISAN: 'hourglass',
    State.ARTISAN_ATTACHED: 'ellipsis.circle',
    State.RECEIVING: 'arrow.left.arrow.right.circle.fill',
    State.NO_REPLIES: 'exclamationmark.triangle.fill',
}


@dataclass(frozen=True)
class Entry:
    key: str            # '' for a separator
    title: str = ''
    enabled: bool = True


def menu_entries(status: Status, version: str) -> list[Entry]:
    detail = textwrap.wrap(status.detail, 62)[:3]
    return [
        Entry('headline', status.headline, enabled=False),
        *[Entry(f'detail{index}', line, enabled=False) for index, line in enumerate(detail)],
        Entry(''),
        Entry('start', 'Start Bridge', enabled=not status.running),
        Entry('stop', 'Stop Bridge…', enabled=status.running),
        Entry(''),
        Entry('copy', 'Copy Virtual Port Path'),
        Entry('log', 'Open Log'),
        Entry(''),
        Entry('settings', 'Settings…'),
        Entry('guide', 'Setup Guide…'),
        Entry('help', 'Troubleshooting…'),
        Entry('updates', 'Check for Updates…'),
        Entry(''),
        Entry('about', f'About Kaleido Serial Bridge {version}'),
        Entry('quit', 'Quit'),
    ]
