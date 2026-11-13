"""Finding the serial port of the roaster. Only names are looked at; no port is opened."""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass

# A paired Kaleido shows up as /dev/cu.<Bluetooth name>, e.g. /dev/cu.Roaster_SRSv6
HINTS = ('kaleido', 'roaster', 'sniper', 'srs')
# Ports macOS always has and that are never a roaster
IGNORED = ('Bluetooth-Incoming-Port', 'debug-console', 'wlan-debug')


@dataclass(frozen=True)
class Port:
    path: str
    name: str        # without /dev/cu.
    suggested: bool  # the name looks like a Kaleido

    @property
    def label(self) -> str:
        return f'{self.name}  (looks like a Kaleido)' if self.suggested else self.name


def looks_like_kaleido(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in HINTS)


def discover(pattern: str = '/dev/cu.*') -> list[Port]:
    """All serial ports matching the pattern, suggestions first."""
    ports = []
    for path in glob.glob(pattern):
        name = os.path.basename(path)
        if name.startswith('cu.'):
            name = name[3:]
        if name in IGNORED:
            continue
        ports.append(Port(path, name, looks_like_kaleido(name)))
    return sorted(ports, key=lambda port: (not port.suggested, port.name.lower()))


def best_guess(ports: list[Port]) -> Port | None:
    """The port to preselect: the only suggestion, if there is exactly one."""
    suggestions = [port for port in ports if port.suggested]
    return suggestions[0] if len(suggestions) == 1 else None
