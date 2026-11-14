"""Open at login, through the login item service of macOS (macOS 13 and later).

The item belongs to the app bundle and is listed in System Settings > General > Login Items,
where it can also be removed. Nothing is installed anywhere else.

Asking the service anything from a copy of the app makes macOS move a registered login item to
that copy. Checks of a built app therefore set KALEIDO_BRIDGE_NO_LOGIN_ITEM=1: the service is then
never asked, and changing the registration is refused. Without the variable nothing changes.
"""

from __future__ import annotations

import os
import sys
from typing import Any

STATES = {0: 'off', 1: 'on', 2: 'needs approval in System Settings > General > Login Items', 3: 'off (not registered)'}

OPT_OUT_VARIABLE = 'KALEIDO_BRIDGE_NO_LOGIN_ITEM'  # for tests only
NOT_QUERIED = f'not queried ({OPT_OUT_VARIABLE}=1)'


def opted_out() -> bool:
    return os.environ.get(OPT_OUT_VARIABLE) == '1'


def available() -> bool:
    """Only an app bundle can be a login item, not a script run from a terminal."""
    return bool(getattr(sys, 'frozen', False)) and not opted_out()


def _service() -> Any:
    import objc
    objc.loadBundle('ServiceManagement', {}, bundle_path='/System/Library/Frameworks/ServiceManagement.framework')
    return objc.lookUpClass('SMAppService').mainAppService()


def state() -> str:
    if opted_out():
        return NOT_QUERIED
    try:
        return STATES.get(int(_service().status()), 'unknown')
    except Exception:  # noqa: BLE001  # an older macOS, or no such service
        return 'not available'


def is_enabled() -> bool:
    return state() == 'on'


def set_enabled(enabled: bool) -> tuple[bool, str]:
    """Returns (done, what macOS said if not)."""
    if opted_out():
        return False, f'The login item is not changed while {OPT_OUT_VARIABLE}=1 is set.'
    try:
        service = _service()
        done, error = service.registerAndReturnError_(None) if enabled else service.unregisterAndReturnError_(None)
    except Exception as e:  # noqa: BLE001
        return False, str(e)
    return bool(done), '' if done else str(error.localizedDescription() if error is not None else 'macOS refused')
