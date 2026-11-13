"""Open at login, through the login item service of macOS (macOS 13 and later).

The item belongs to the app bundle and is listed in System Settings > General > Login Items,
where it can also be removed. Nothing is installed anywhere else.
"""

from __future__ import annotations

import sys
from typing import Any

STATES = {0: 'off', 1: 'on', 2: 'needs approval in System Settings > General > Login Items', 3: 'off (not registered)'}


def available() -> bool:
    """Only an app bundle can be a login item, not a script run from a terminal."""
    return bool(getattr(sys, 'frozen', False))


def _service() -> Any:
    import objc
    objc.loadBundle('ServiceManagement', {}, bundle_path='/System/Library/Frameworks/ServiceManagement.framework')
    return objc.lookUpClass('SMAppService').mainAppService()


def state() -> str:
    try:
        return STATES.get(int(_service().status()), 'unknown')
    except Exception:  # noqa: BLE001  # an older macOS, or no such service
        return 'not available'


def is_enabled() -> bool:
    return state() == 'on'


def set_enabled(enabled: bool) -> tuple[bool, str]:
    """Returns (done, what macOS said if not)."""
    try:
        service = _service()
        done, error = service.registerAndReturnError_(None) if enabled else service.unregisterAndReturnError_(None)
    except Exception as e:  # noqa: BLE001
        return False, str(e)
    return bool(done), '' if done else str(error.localizedDescription() if error is not None else 'macOS refused')
