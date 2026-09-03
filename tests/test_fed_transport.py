"""Offline tests for respectful FOMC calendar retrieval."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from macro_event_telegram_alerts.providers.fed_transport import (
    FOMC_CALENDAR_URL,
    FomcCalendarTransport,
    HttpResult,
)

USER_AGENT = (
    "macro-event-telegram-alerts/0.0.0 "
    "(+https://github.com/bockuden/macro-event-telegram-alerts)"
)
CALENDAR = '<div class="fomc-meeting"></div>\n'


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
            "Content-Type": "text/html; charset=utf-8",
            "ETag": '"fomc-v1"',
            "Last-Modified": "Wed, 19 Aug 2026 16:00:00 GMT",
        },
    )


def _transport(
    tmp_path: Path,
    clock: _Clock,
    http: _FakeHttp,
) -> FomcCalendarTransport:
    return FomcCalendarTransport(
        cache_dir=tmp_path,
        user_agent=USER_AGENT,
        clock=clock,
        http_get=http,
    )


def test_transport_uses_only_official_calendar_and_contactable_user_agent(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 9, 3, 12, tzinfo=UTC)
    http = _FakeHttp([_ok_result()])

    payload = _transport(tmp_path, _Clock(now), http).fetch()

    assert payload.text == CALENDAR
    assert payload.retrieved_at == now
    assert payload.from_cache is False
    assert len(http.calls) == 1
    url, headers, timeout = http.calls[0]
    assert url == FOMC_CALENDAR_URL
    assert headers["User-Agent"] == USER_AGENT
    assert headers["Accept"] == "text/html"
    assert timeout == 20.0


def test_transport_reuses_and_conditionally_validates_cache(tmp_path: Path) -> None:
    now = datetime(2026, 9, 3, 12, tzinfo=UTC)
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
    assert headers["If-None-Match"] == '"fomc-v1"'
    assert headers["If-Modified-Since"] == "Wed, 19 Aug 2026 16:00:00 GMT"


def test_transport_requires_contact_information(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must include"):
        FomcCalendarTransport(
            cache_dir=tmp_path,
            user_agent="anonymous-bot/1.0",
            clock=lambda: datetime(2026, 9, 3, 12, tzinfo=UTC),
        )
