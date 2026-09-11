"""Regression checks for HTTP rejection, cache provenance, and offline inspection."""

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import URLError

import pytest

from macro_event_telegram_alerts.providers.bea_transport import BeaScheduleTransport
from macro_event_telegram_alerts.providers.bls_transport import BlsCalendarTransport
from macro_event_telegram_alerts.providers.cached_http import (
    CachedDocumentError,
    FailureCategory,
    HttpResult,
)
from macro_event_telegram_alerts.providers.fed_transport import FomcCalendarTransport

NOW = datetime(2026, 9, 10, 10, tzinfo=UTC)
UA = "macro-alerts-test (+https://github.com/bockuden/macro-event-telegram-alerts)"


@pytest.mark.parametrize(
    "factory",
    [
        BlsCalendarTransport,
        BeaScheduleTransport,
        FomcCalendarTransport,
    ],
)
def test_http_rejection_survives_every_wrapper(
    tmp_path: Path,
    factory: type[BlsCalendarTransport]
    | type[BeaScheduleTransport]
    | type[FomcCalendarTransport],
) -> None:
    transport = factory(
        cache_dir=tmp_path,
        user_agent=UA,
        clock=lambda: NOW,
        http_get=lambda *_: HttpResult(403, b"secret-body", {}),
    )
    with pytest.raises(CachedDocumentError) as caught:
        transport.fetch()
    assert caught.value.http_status == 403
    assert caught.value.category == FailureCategory.HTTP
    assert "secret-body" not in str(caught.value)
    assert transport.diagnostics().http_status == 403


@pytest.mark.parametrize(
    "error,category",
    [
        (TimeoutError("secret"), FailureCategory.TIMEOUT),
        (URLError(TimeoutError("secret")), FailureCategory.TIMEOUT),
        (URLError("secret"), FailureCategory.NETWORK),
    ],
)
def test_network_error_classification(
    tmp_path: Path, error: OSError, category: FailureCategory
) -> None:
    def fail(url: str, headers: Mapping[str, str], timeout: float) -> HttpResult:
        raise error

    transport = BlsCalendarTransport(
        cache_dir=tmp_path,
        user_agent=UA,
        clock=lambda: NOW,
        http_get=fail,
    )
    with pytest.raises(CachedDocumentError) as caught:
        transport.fetch()
    assert caught.value.category == category
    assert "secret" not in str(caught.value)


def test_stale_fallback_does_not_refresh_validation_time(tmp_path: Path) -> None:
    now = NOW
    responses = iter(
        [
            HttpResult(200, b"calendar", {"Content-Type": "text/calendar"}),
            HttpResult(503, b"private upstream error", {"Retry-After": "30000"}),
            HttpResult(304, b"", {}),
        ]
    )
    transport = BlsCalendarTransport(
        cache_dir=tmp_path,
        user_agent=UA,
        clock=lambda: now,
        http_get=lambda *_: next(responses),
    )
    transport.fetch()
    now += timedelta(hours=7)
    transport.fetch()
    diagnostic = transport.diagnostics()
    assert diagnostic.validated_at == NOW
    assert diagnostic.retrieved_at == NOW
    assert diagnostic.next_request_at == now + timedelta(seconds=30000)
    assert diagnostic.stale
    assert diagnostic.category == FailureCategory.HTTP

    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    offline = BlsCalendarTransport(
        cache_dir=tmp_path,
        user_agent=UA,
        clock=lambda: now,
        allow_network=False,
        http_get=lambda *_: pytest.fail("offline inspection made an HTTP request"),
    )
    offline.fetch()
    assert offline.diagnostics().stale
    assert offline.diagnostics().validated_at == NOW
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    now += timedelta(hours=9)
    transport.fetch()
    assert transport.diagnostics().validated_at == now
    assert transport.diagnostics().retrieved_at == NOW
    assert not transport.diagnostics().stale


@pytest.mark.parametrize("retry", [None, "2026-09-11T10:00:00+00:00"])
def test_legacy_cache_does_not_invent_validation_after_retry(
    tmp_path: Path,
    retry: str | None,
) -> None:
    (tmp_path / "bls.ics").write_text("calendar", encoding="utf-8")
    (tmp_path / "bls-cache.json").write_text(
        json.dumps(
            {
                "retrieved_at": NOW.isoformat(),
                "checked_at": NOW.isoformat(),
                "retry_not_before": retry,
            }
        ),
        encoding="utf-8",
    )
    transport = BlsCalendarTransport(
        cache_dir=tmp_path,
        user_agent=UA,
        clock=lambda: NOW,
        allow_network=False,
    )
    transport.fetch()
    assert transport.diagnostics().validated_at == (NOW if retry is None else None)


def test_incomplete_cache_has_cache_category(tmp_path: Path) -> None:
    (tmp_path / "bls.ics").write_text("calendar", encoding="utf-8")
    transport = BlsCalendarTransport(
        cache_dir=tmp_path,
        user_agent=UA,
        clock=lambda: NOW,
        allow_network=False,
    )
    with pytest.raises(CachedDocumentError) as caught:
        transport.fetch()
    assert caught.value.category == FailureCategory.CACHE
