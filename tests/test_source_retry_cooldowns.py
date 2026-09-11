"""Persistent, source-local cooldown behaviour for official HTTP documents."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from macro_event_telegram_alerts.providers.bls_transport import BlsCalendarTransport
from macro_event_telegram_alerts.providers.cached_http import (
    CachedDocumentError,
    FailureCategory,
    HttpResult,
)

NOW = datetime(2026, 9, 11, 10, tzinfo=UTC)
UA = "macro-alerts-test (+https://github.com/bockuden/macro-event-telegram-alerts)"


class _Clock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


class _Http:
    def __init__(self, results: list[HttpResult]) -> None:
        self._results = iter(results)
        self.calls = 0

    def __call__(
        self, url: str, headers: Mapping[str, str], timeout_seconds: float
    ) -> HttpResult:
        del url, headers, timeout_seconds
        self.calls += 1
        return next(self._results)


def _transport(tmp_path: Path, clock: _Clock, http: _Http) -> BlsCalendarTransport:
    return BlsCalendarTransport(
        cache_dir=tmp_path,
        user_agent=UA,
        clock=clock,
        http_get=http,
        min_poll_interval=timedelta(minutes=1),
        rejection_cooldown=timedelta(hours=6),
        max_retry_backoff=timedelta(hours=1),
        max_stale_cache_age=timedelta(days=2),
    )


def _calendar() -> HttpResult:
    return HttpResult(200, b"BEGIN:VCALENDAR\nEND:VCALENDAR\n", {"Content-Type": "text/calendar"})


def test_403_without_cache_is_persistently_cooled_down(tmp_path: Path) -> None:
    clock = _Clock(NOW)
    http = _Http([HttpResult(403, b"", {}), _calendar()])
    first = _transport(tmp_path, clock, http)

    with pytest.raises(CachedDocumentError, match="HTTP 403"):
        first.fetch()
    assert http.calls == 1
    assert first.diagnostics().next_request_at == NOW + timedelta(hours=6)

    with pytest.raises(CachedDocumentError, match="cooldown"):
        first.fetch()
    restarted = _transport(tmp_path, clock, http)
    with pytest.raises(CachedDocumentError, match="cooldown"):
        restarted.fetch()
    assert http.calls == 1
    assert restarted.diagnostics().http_status == 403
    assert restarted.diagnostics().category == FailureCategory.HTTP

    clock.current += timedelta(hours=6)
    payload = restarted.fetch()
    assert payload.from_cache is False
    assert http.calls == 2
    assert not (tmp_path / "bls-cache-retry.json").exists()


def test_retry_after_overrides_bounded_temporary_backoff(tmp_path: Path) -> None:
    clock = _Clock(NOW)
    http = _Http(
        [
            HttpResult(429, b"", {"Retry-After": "7200"}),
            _calendar(),
        ]
    )
    transport = _transport(tmp_path, clock, http)

    with pytest.raises(CachedDocumentError, match="HTTP 429"):
        transport.fetch()
    assert transport.diagnostics().next_request_at == NOW + timedelta(hours=2)

    clock.current += timedelta(minutes=30)
    with pytest.raises(CachedDocumentError, match="cooldown"):
        transport.fetch()
    assert http.calls == 1

    clock.current = NOW + timedelta(hours=2)
    transport.fetch()
    assert http.calls == 2


def test_temporary_failures_back_off_without_masking_old_cache(tmp_path: Path) -> None:
    clock = _Clock(NOW)
    http = _Http([_calendar(), HttpResult(503, b"", {}), HttpResult(503, b"", {})])
    transport = _transport(tmp_path, clock, http)
    transport.fetch()

    clock.current += timedelta(minutes=1)
    cached = transport.fetch()
    assert cached.from_cache
    assert transport.diagnostics().validated_at == NOW
    assert transport.diagnostics().next_request_at == NOW + timedelta(minutes=2)

    clock.current += timedelta(minutes=1)
    transport.fetch()
    assert transport.diagnostics().next_request_at == NOW + timedelta(minutes=4)
    assert transport.diagnostics().stale
    assert http.calls == 3


def test_cache_older_than_configured_limit_is_not_used_as_fallback(tmp_path: Path) -> None:
    clock = _Clock(NOW)
    http = _Http([_calendar(), HttpResult(403, b"", {})])
    transport = _transport(tmp_path, clock, http)
    transport.fetch()

    clock.current += timedelta(days=3)
    with pytest.raises(CachedDocumentError, match="HTTP 403"):
        transport.fetch()
    assert transport.diagnostics().retrieved_at == NOW
    assert transport.diagnostics().stale
    assert http.calls == 2


def test_cooldown_for_one_source_does_not_block_a_healthy_source(tmp_path: Path) -> None:
    clock = _Clock(NOW)
    denied = _transport(tmp_path / "denied", clock, _Http([HttpResult(403, b"", {})]))
    healthy_http = _Http([_calendar()])
    healthy = _transport(tmp_path / "healthy", clock, healthy_http)

    with pytest.raises(CachedDocumentError):
        denied.fetch()
    payload = healthy.fetch()

    assert payload.text.startswith("BEGIN:VCALENDAR")
    assert healthy_http.calls == 1
