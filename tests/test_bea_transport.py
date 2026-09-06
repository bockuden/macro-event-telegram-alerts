"""Offline tests for respectful BEA schedule retrieval."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from macro_event_telegram_alerts.providers.bea_transport import (
    BEA_SCHEDULE_URL,
    BeaScheduleTransport,
    HttpResult,
)

USER_AGENT = (
    "macro-event-telegram-alerts/0.0.0 "
    "(+https://github.com/bockuden/macro-event-telegram-alerts)"
)
SCHEDULE = '<table id="release-schedule-table"></table>\n'


class _Clock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


class _FakeHttp:
    def __init__(self, results: list[HttpResult]) -> None:
        self._results = iter(results)
        self.calls: list[tuple[str, Mapping[str, str], float]] = []

    def __call__(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResult:
        self.calls.append((url, headers, timeout_seconds))
        return next(self._results)


def _ok_result() -> HttpResult:
    return HttpResult(
        status=200,
        body=SCHEDULE.encode(),
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "ETag": '"schedule-v1"',
            "Last-Modified": "Sun, 30 Aug 2026 12:00:00 GMT",
        },
    )


def _transport(
    tmp_path: Path,
    clock: _Clock,
    http: _FakeHttp,
) -> BeaScheduleTransport:
    return BeaScheduleTransport(
        cache_dir=tmp_path,
        user_agent=USER_AGENT,
        clock=clock,
        http_get=http,
    )


def test_transport_uses_only_official_schedule_and_contactable_user_agent(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    http = _FakeHttp([_ok_result()])

    payload = _transport(tmp_path, _Clock(now), http).fetch()

    assert payload.text == SCHEDULE
    assert payload.retrieved_at == now
    assert payload.from_cache is False
    assert len(http.calls) == 1
    url, headers, timeout = http.calls[0]
    assert url == BEA_SCHEDULE_URL
    assert headers["User-Agent"] == USER_AGENT
    assert headers["Accept"] == "text/html"
    assert timeout == 20.0


def test_transport_reuses_and_conditionally_validates_cache(tmp_path: Path) -> None:
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    clock = _Clock(now)
    http = _FakeHttp(
        [
            _ok_result(),
            HttpResult(status=304, body=b"", headers={}),
        ]
    )
    transport = _transport(tmp_path, clock, http)
    transport.fetch()

    clock.current += timedelta(hours=5)
    assert transport.fetch().from_cache is True
    assert len(http.calls) == 1

    clock.current += timedelta(hours=1)
    cached = transport.fetch()

    assert cached.from_cache is True
    assert cached.retrieved_at == now
    _, headers, _ = http.calls[1]
    assert headers["If-None-Match"] == '"schedule-v1"'
    assert headers["If-Modified-Since"] == "Sun, 30 Aug 2026 12:00:00 GMT"


def test_transport_uses_stale_cache_when_rate_limited(tmp_path: Path) -> None:
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    clock = _Clock(now)
    http = _FakeHttp(
        [
            _ok_result(),
            HttpResult(status=429, body=b"", headers={}),
        ]
    )
    transport = _transport(tmp_path, clock, http)
    transport.fetch()
    clock.current += timedelta(days=1)

    payload = transport.fetch()

    assert payload.from_cache is True
    assert payload.retrieved_at == now


def test_rate_limit_defers_retries_until_retry_after(tmp_path: Path) -> None:
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    clock = _Clock(now)
    http = _FakeHttp(
        [
            _ok_result(),
            HttpResult(status=429, body=b"", headers={"Retry-After": "3600"}),
        ]
    )
    transport = _transport(tmp_path, clock, http)
    transport.fetch()
    clock.current += timedelta(days=1)

    assert transport.fetch().from_cache is True
    assert transport.fetch().from_cache is True
    assert len(http.calls) == 2


def test_transport_requires_contact_information(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must include"):
        BeaScheduleTransport(
            cache_dir=tmp_path,
            user_agent="anonymous-bot/1.0",
            clock=lambda: datetime(2026, 8, 30, 12, tzinfo=UTC),
        )
