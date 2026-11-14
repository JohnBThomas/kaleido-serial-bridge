"""Check for Updates: asks GitHub, once per click, for the latest published release and compares versions.

Nothing here runs by itself, downloads anything or touches the bridge. The answer is one of three:
a newer version is available, the installed version is up to date, or the check could not be
completed. The user downloads and installs a newer disk image themselves, from the release page on
the official repository.

The request goes to api.github.com only when the user clicks, with the app's name and version as
its User-Agent and nothing else about the user or the Mac. It uses macOS's own networking
(NSURLSession: the system's certificates and proxy settings), with a time limit.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from . import __version__

LATEST_RELEASE_API = 'https://api.github.com/repos/JohnBThomas/kaleido-serial-bridge/releases/latest'
RELEASE_PAGE_PREFIX = 'https://github.com/JohnBThomas/kaleido-serial-bridge/releases/'
TIMEOUT = 10.0              # seconds for the whole request
MAX_RESPONSE = 1_000_000    # bytes; a release description is far smaller

NEWER = 'newer'
CURRENT = 'current'
FAILED = 'failed'

_VERSION = re.compile(r'^v?(\d{1,6}(?:\.\d{1,6}){0,3})$')


def parse_version(text: str) -> tuple[int, ...] | None:
    """'v0.2.10' -> (0, 2, 10). None for anything that is not a plain dotted version (e.g. '0.2.1-rc1', 'latest')."""
    match = _VERSION.match(text.strip()) if isinstance(text, str) else None
    if match is None:
        return None
    return tuple(int(part) for part in match.group(1).split('.'))


def compare_versions(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    """-1, 0 or 1, numerically per part, missing parts counting as 0: (0, 2, 10) > (0, 2, 9) and (0, 2) == (0, 2, 0)."""
    length = max(len(left), len(right))
    a = left + (0,) * (length - len(left))
    b = right + (0,) * (length - len(right))
    return (a > b) - (a < b)


@dataclass(frozen=True)
class Result:
    kind: str                 # NEWER, CURRENT or FAILED
    installed: str
    latest: str = ''          # the release's version, without a leading 'v'
    url: str = ''             # the release page on the official repository, for NEWER
    reason: str = ''          # for FAILED


Fetch = Callable[[str, float], tuple[int, bytes]]  # (url, timeout) -> (HTTP status, body); raises OSError on failure


def evaluate(status: int, body: bytes, installed: str = __version__) -> Result:
    """Turns GitHub's answer into a Result. Anything unexpected is a failed check, never a guess."""
    if status != 200:
        hint = ' (GitHub limits how often it can be asked; try again later)' if status in (403, 429) else ''
        return Result(FAILED, installed, reason=f'GitHub answered with HTTP status {status}{hint}.')
    if len(body) > MAX_RESPONSE:
        return Result(FAILED, installed, reason='GitHub sent an unexpectedly large answer.')
    try:
        data = json.loads(body.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        return Result(FAILED, installed, reason='GitHub sent an answer that is not valid JSON.')
    if not isinstance(data, dict):
        return Result(FAILED, installed, reason='GitHub sent an answer in an unexpected form.')
    tag, url = data.get('tag_name'), data.get('html_url')
    if data.get('draft') is True or data.get('prerelease') is True:
        return Result(FAILED, installed, reason='The release GitHub named is not a published stable release.')
    latest = parse_version(tag) if isinstance(tag, str) else None
    if latest is None:
        return Result(FAILED, installed, reason=f'The latest release has a tag that is not a version number: {str(tag)[:40]!r}.')
    if not isinstance(url, str) or not url.startswith(RELEASE_PAGE_PREFIX) or any(c.isspace() for c in url):
        return Result(FAILED, installed, reason='The release does not point to the official repository.')
    mine = parse_version(installed)
    if mine is None:
        return Result(FAILED, installed, reason=f'The installed version {installed!r} is not a version number.')
    shown = '.'.join(map(str, latest))
    if compare_versions(latest, mine) > 0:
        return Result(NEWER, installed, shown, url)
    return Result(CURRENT, installed, shown)


def check(fetch: Fetch, installed: str = __version__, url: str = LATEST_RELEASE_API, timeout: float = TIMEOUT) -> Result:
    try:
        status, body = fetch(url, timeout)
    except TimeoutError:
        return Result(FAILED, installed, reason=f'GitHub did not answer within {timeout:.0f} s.')
    except OSError as e:
        return Result(FAILED, installed, reason=f'GitHub could not be reached: {e}')
    return evaluate(status, body, installed)


class UpdateCheck:
    """One check at a time, in the background. begin() from the main thread; take() from the app's timer."""

    def __init__(self, fetch: Fetch | None = None) -> None:
        self.fetch: Fetch = fetch if fetch is not None else fetch_with_foundation
        self._lock = threading.Lock()
        self._running = False
        self._result: Result | None = None

    @property
    def in_progress(self) -> bool:
        with self._lock:
            return self._running

    def begin(self) -> bool:
        """Starts a check. Returns False, and starts nothing, while one is in progress."""
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._result = None
        threading.Thread(target=self._run, name='update-check', daemon=True).start()
        return True

    def _run(self) -> None:
        try:
            result = check(self.fetch)
        except Exception as e:  # noqa: BLE001  # whatever happens, the check ends with an answer
            result = Result(FAILED, __version__, reason=f'Unexpected error: {e}')
        with self._lock:
            self._result = result
            self._running = False

    def take(self) -> Result | None:
        """The result of the finished check, once."""
        with self._lock:
            result, self._result = self._result, None
            return result


def fetch_with_foundation(url: str, timeout: float) -> tuple[int, bytes]:
    """One GET with NSURLSession, waited for with a limit. Raises TimeoutError or OSError."""
    from Foundation import NSURL, NSMutableURLRequest, NSURLSession  # pylint: disable=import-outside-toplevel
    request = NSMutableURLRequest.requestWithURL_(NSURL.URLWithString_(url))
    request.setTimeoutInterval_(timeout)
    request.setValue_forHTTPHeaderField_('application/vnd.github+json', 'Accept')
    request.setValue_forHTTPHeaderField_('2022-11-28', 'X-GitHub-Api-Version')
    request.setValue_forHTTPHeaderField_(f'KaleidoSerialBridge/{__version__}', 'User-Agent')
    done = threading.Event()
    answer: dict[str, Any] = {}

    def completion(data: Any, response: Any, error: Any) -> None:
        answer['data'], answer['response'], answer['error'] = data, response, error
        done.set()

    task = NSURLSession.sharedSession().dataTaskWithRequest_completionHandler_(request, completion)
    task.resume()
    if not done.wait(timeout + 2.0):
        task.cancel()
        raise TimeoutError('no answer')
    error = answer.get('error')
    if error is not None:
        if int(error.code()) == -1001:  # NSURLErrorTimedOut
            raise TimeoutError(str(error.localizedDescription()))
        raise OSError(str(error.localizedDescription()))
    response, data = answer.get('response'), answer.get('data')
    status = int(response.statusCode()) if response is not None and hasattr(response, 'statusCode') else 0
    return status, bytes(data) if data is not None else b''
