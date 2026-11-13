"""Where the app keeps its files, and the few things it remembers."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

HOME_VARIABLE = 'KALEIDO_BRIDGE_HOME'  # for tests and development: use another folder than ~/.kaleido-bridge
LINK_NAME = 'cu.Roaster_bridge'        # the same name the command line prototype used


def home() -> Path:
    override = os.environ.get(HOME_VARIABLE)
    return Path(override).expanduser().resolve() if override else Path.home() / '.kaleido-bridge'


@dataclass(frozen=True)
class Paths:
    home: Path

    @property
    def settings(self) -> Path:
        return self.home / 'settings.json'

    @property
    def link(self) -> Path:
        """The virtual port: what goes into Artisan's Comm Port."""
        return self.home / LINK_NAME

    @property
    def log(self) -> Path:
        return self.home / 'bridge.log'

    @property
    def status(self) -> Path:
        return self.home / 'status.json'


@dataclass
class Settings:
    device: str = ''          # the physical serial port of the roaster, as chosen by the user
    auto_start: bool = False  # start the bridge when the app opens; off unless the user turns it on
    setup_done: bool = False  # the setup guide has been completed once

    @classmethod
    def load(cls, path: Path) -> Settings:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError):
            # unreadable: start over, but keep the file for a look
            try:
                path.replace(path.with_suffix('.json.unreadable'))
            except OSError:
                pass
            return cls()
        if not isinstance(data, dict):
            return cls()
        return cls(device=str(data.get('device') or ''), auto_start=data.get('auto_start') is True, setup_done=data.get('setup_done') is True)

    def save(self, path: Path) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = path.with_suffix(f'.json.{os.getpid()}')
        temporary.write_text(json.dumps({'version': 1, **asdict(self)}, indent=2) + '\n', encoding='utf-8')
        temporary.replace(path)
