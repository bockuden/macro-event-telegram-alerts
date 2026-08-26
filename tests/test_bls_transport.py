"""Offline tests for respectful BLS calendar retrieval."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from macro_event_telegram_alerts.providers.bls_transport import (
    BLS_CALENDAR_URL,
    BlsCalendarTransport,
    HttpResult,
)

USER_AGENT = (
    "macro-event-telegram-alerts/0.0.0 "
    "(+https://github.com/bockuden/macro-event-telegram-alerts)"
)
CALENDAR = "BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR\n"


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
        body=CALENDAR.encode(),
        headers={
            "Content-Type": "text/calendar; charset=utf-8",
            "ETag": '"calendar-v1"',
            "Last-Modified": "Fri, 21 Aug 2026 19:30:00 GMT",
        },
    )


def _transport(
    tmp_path: Path,
    clock: _Clock,
    http: _FakeHttp,
) -> BlsCalendarTransport:
    return BlsCalendarTransport(
        cache_dir=tmp_path,
        user_agent=USER_AGENT,
        clock=clock,
        http_get=http,
    )


def test_transport_uses_only_official_feed_and_contactable_user_agent(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 26, 8, tzinfo=UTC)
    http = _FakeHttp([_ok_result()])

    payload = _transport(tmp_path, _Clock(now), http).fetch()

    assert payload.text == CALENDAR
    assert payload.retrieved_at == now
    assert payload.from_cache is False
    assert len(http.calls) == 1
    url, headers, timeout = http.calls[0]
    assert url == BLS_CALENDAR_URL
    assert headers["User-Agent"] == USER_AGENT
    assert headers["Accept"] == "text/calendar"
    assert timeout == 20.0


def test_transport_reuses_fresh_cache_without_http(tmp_path: Path) -> None:
    now = datetime(2026, 8, 26, 8, tzinfo=UTC)
    clock = _Clock(now)
    http = _FakeHttp([_ok_result()])
    transport = _transport(tmp_path, clock, http)
    transport.fetch()

    clock.current += timedelta(hours=5)
    cached = transport.fetch()

    assert cached.from_cache is True
    assert cached.retrieved_at == now
    assert len(http.calls) == 1


def test_transport_conditionally_validates_stale_cache(tmp_path: Path) -> None:
    now = datetime(2026, 8, 26, 8, tzinfo=UTC)
    clock = _Clock(now)
    http = _FakeHttp(
        [
            _ok_result(),
            HttpResult(status=304, body=b"", headers={}),
        ]
    )
    transport = _transport(tmp_path, clock, http)
    transport.fetch()

    clock.current += timedelta(hours=6)
    cached = transport.fetch()

    assert cached.text == CALENDAR
    assert cached.retrieved_at == now
    assert cached.from_cache is True
    _, conditional_headers, _ = http.calls[1]
    assert conditional_headers["If-None-Match"] == '"calendar-v1"'
    assert conditional_headers["If-Modified-Since"] == ("Fri, 21 Aug 2026 19:30:00 GMT")


def test_transport_uses_stale_cache_after_network_failure(tmp_path: Path) -> None:
    now = datetime(2026, 8, 26, 8, tzinfo=UTC)
    clock = _Clock(now)

    def failing_http(
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResult:
        del url, headers, timeout_seconds
        raise OSError("offline")

    seed = _transport(tmp_path, clock, _FakeHttp([_ok_result()]))
    seed.fetch()
    clock.current += timedelta(days=1)
    transport = BlsCalendarTransport(
        cache_dir=tmp_path,
        user_agent=USER_AGENT,
        clock=clock,
        http_get=failing_http,
    )

    payload = transport.fetch()

    assert payload.from_cache is True
    assert payload.retrieved_at == now


def test_transport_requires_contact_information(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must include"):
        BlsCalendarTransport(
            cache_dir=tmp_path,
            user_agent="anonymous-bot/1.0",
            clock=lambda: datetime(2026, 8, 26, 8, tzinfo=UTC),
        )
