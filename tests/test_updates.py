"""Check for Updates, without the network: GitHub's answers are made up here."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from kaleido_serial_bridge import updates  # noqa: E402
from kaleido_serial_bridge.updates import CURRENT, FAILED, NEWER, UpdateCheck, check, compare_versions, evaluate, parse_version  # noqa: E402

PAGE = 'https://github.com/JohnBThomas/kaleido-serial-bridge/releases/tag/'


def release(tag: str, url: str | None = None, **extra: object) -> bytes:
    return json.dumps({'tag_name': tag, 'html_url': url if url is not None else PAGE + tag, 'draft': False, 'prerelease': False,
                       **extra}).encode()


class TestVersions:

    def test_parse(self) -> None:
        assert parse_version('v0.2.1') == (0, 2, 1)
        assert parse_version('0.2.10') == (0, 2, 10)
        assert parse_version('1') == (1,)
        assert parse_version(' v0.2.1\n') == (0, 2, 1)  # surrounding whitespace is ignored
        for bad in ('', 'latest', 'v', '0.2.1-rc1', '0..2', 'v 0.2', '0.2.x', '1.2.3.4.5', '-1.0'):
            assert parse_version(bad) is None, bad

    def test_numeric_order(self) -> None:
        assert compare_versions((0, 2, 10), (0, 2, 9)) == 1
        assert compare_versions((0, 2, 9), (0, 2, 10)) == -1
        assert compare_versions((0, 10, 0), (0, 9, 99)) == 1
        assert compare_versions((1, 0), (0, 99, 99)) == 1
        assert compare_versions((0, 2), (0, 2, 0)) == 0
        assert compare_versions((0, 2, 1), (0, 2, 1)) == 0


class TestGitHubAnswers:

    def test_a_newer_release(self) -> None:
        result = evaluate(200, release('v0.2.10'), installed='0.2.9')
        assert result.kind == NEWER and result.latest == '0.2.10' and result.installed == '0.2.9'
        assert result.url == PAGE + 'v0.2.10'

    def test_the_same_release(self) -> None:
        result = evaluate(200, release('v0.2.1'), installed='0.2.1')
        assert result.kind == CURRENT and result.latest == '0.2.1' and result.url == ''

    def test_an_older_release_than_installed_is_up_to_date(self) -> None:
        # e.g. a release candidate installed before its release is published
        assert evaluate(200, release('v0.2.0'), installed='0.2.1').kind == CURRENT

    @pytest.mark.parametrize('body', [
        b'not json', b'\xff\xfe', b'[]', b'"text"', b'{}',
        json.dumps({'tag_name': 'latest', 'html_url': PAGE + 'latest'}).encode(),
        json.dumps({'tag_name': 'v0.2.1-rc1', 'html_url': PAGE + 'v0.2.1-rc1'}).encode(),
        json.dumps({'tag_name': 7, 'html_url': PAGE + '7'}).encode(),
        json.dumps({'tag_name': 'v0.3.0'}).encode(),
        release('v0.3.0', url='https://example.com/kaleido/releases/v0.3.0'),
        release('v0.3.0', url='https://github.com/someone-else/kaleido-serial-bridge/releases/tag/v0.3.0'),
        release('v0.3.0', url=PAGE + 'v0.3.0 javascript:x'),
        release('v0.3.0', draft=True),
        release('v0.3.0', prerelease=True),
    ], ids=['not-json', 'not-utf8', 'list', 'string', 'empty', 'tag-word', 'tag-rc', 'tag-number', 'no-url', 'other-site',
            'other-owner', 'url-with-space', 'draft', 'prerelease'])
    def test_malformed_or_unexpected_answers_fail_the_check(self, body: bytes) -> None:
        result = evaluate(200, body, installed='0.2.1')
        assert result.kind == FAILED and result.reason and result.url == ''

    def test_an_oversized_answer_fails(self) -> None:
        assert evaluate(200, b' ' * (updates.MAX_RESPONSE + 1), installed='0.2.1').kind == FAILED

    @pytest.mark.parametrize('status', [403, 404, 429, 500, 0])
    def test_http_errors_fail(self, status: int) -> None:
        result = evaluate(status, release('v9.9.9'), installed='0.2.1')
        assert result.kind == FAILED and str(status) in result.reason
        if status in (403, 429):
            assert 'try again later' in result.reason


class TestRequest:

    def test_offline(self) -> None:
        def offline(_url: str, _timeout: float) -> tuple[int, bytes]:
            raise OSError('The Internet connection appears to be offline.')
        result = check(offline, installed='0.2.1')
        assert result.kind == FAILED and 'could not be reached' in result.reason and 'offline' in result.reason

    def test_timeout(self) -> None:
        def slow(_url: str, timeout: float) -> tuple[int, bytes]:
            assert timeout == updates.TIMEOUT
            raise TimeoutError('no answer')
        result = check(slow, installed='0.2.1')
        assert result.kind == FAILED and f'within {updates.TIMEOUT:.0f} s' in result.reason

    def test_the_official_endpoint_is_asked(self) -> None:
        asked: list[tuple[str, float]] = []

        def record(url: str, timeout: float) -> tuple[int, bytes]:
            asked.append((url, timeout))
            return 200, release('v0.2.1')
        check(record, installed='0.2.1')
        assert asked == [('https://api.github.com/repos/JohnBThomas/kaleido-serial-bridge/releases/latest', updates.TIMEOUT)]


class TestOneCheckAtATime:

    def test_no_second_check_while_one_is_in_progress(self) -> None:
        gate = threading.Event()
        calls: list[str] = []

        def held(url: str, _timeout: float) -> tuple[int, bytes]:
            calls.append(url)
            gate.wait(5)
            return 200, release('v99.0.0')
        updater = UpdateCheck(held)
        assert updater.begin()
        assert updater.in_progress and not updater.begin() and not updater.begin()
        assert updater.take() is None
        gate.set()
        for _ in range(500):
            if not updater.in_progress:
                break
            threading.Event().wait(0.01)
        result = updater.take()
        assert result is not None and result.kind == NEWER and len(calls) == 1
        assert updater.take() is None  # reported once
        assert updater.begin()  # a new click starts a new check
        gate.set()

    def test_an_unexpected_error_still_ends_the_check(self) -> None:
        def broken(_url: str, _timeout: float) -> tuple[int, bytes]:
            raise ValueError('boom')
        updater = UpdateCheck(broken)
        updater.begin()
        for _ in range(500):
            if not updater.in_progress:
                break
            threading.Event().wait(0.01)
        result = updater.take()
        assert result is not None and result.kind == FAILED and 'boom' in result.reason
        assert not updater.in_progress
