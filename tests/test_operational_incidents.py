from datetime import UTC, datetime, timedelta
from pathlib import Path

from macro_event_telegram_alerts.delivery_errors import DeliveryError
from macro_event_telegram_alerts.operational_incidents import (
    OperationalIncidentReporter,
    OperationalIncidentStore,
)
from macro_event_telegram_alerts.providers.cached_http import (
    FailureCategory,
    TransportDiagnostics,
)
from macro_event_telegram_alerts.source_diagnostics import SourceReport


def test_incident_is_opened_once_persisted_and_then_recovered(tmp_path: Path) -> None:
    path = tmp_path / "incidents.json"
    now = datetime(2026, 9, 12, 12, tzinfo=UTC)
    store = OperationalIncidentStore(path)

    opened = store.observe("bls", degraded=True, now=now)
    assert opened is not None
    assert opened.kind == "opened"
    store.record_delivery(opened, now=now, retryable=None)
    assert store.observe("bls", degraded=True, now=now) is None
    restarted = OperationalIncidentStore(path)
    assert restarted.observe("bls", degraded=True, now=now) is None
    recovered = restarted.observe("bls", degraded=False, now=now)
    assert recovered is not None
    assert recovered.kind == "recovered"


def _report(status: str = "failed") -> SourceReport:
    return SourceReport(
        source="bls",
        status=status,
        transport=TransportDiagnostics(
            category=FailureCategory.HTTP if status != "healthy" else None,
            http_status=403 if status != "healthy" else None,
        ),
        cache_age_seconds=None,
        total_events=None,
        future_events=None,
        future_timed_events=None,
        next_event_at=None,
    )


def test_reporter_sends_once_then_recovers_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "incidents.json"
    messages: list[str] = []
    now = datetime(2026, 9, 10, 12, tzinfo=UTC)
    reporter = OperationalIncidentReporter(
        OperationalIncidentStore(path),
        messages.append,
        failure_threshold=2,
        followup_interval=timedelta(hours=24),
    )

    reporter.observe(_report(), now)
    reporter.observe(_report(), now + timedelta(minutes=1))
    reporter.observe(_report(), now + timedelta(minutes=2))
    restarted = OperationalIncidentReporter(
        OperationalIncidentStore(path),
        messages.append,
        failure_threshold=2,
        followup_interval=timedelta(hours=24),
    )
    restarted.observe(_report("healthy"), now + timedelta(minutes=3))

    assert len(messages) == 2
    assert "HTTP status: 403" in messages[0]
    assert "recovered" in messages[1]


def test_reporter_retries_transient_delivery_without_each_loop(tmp_path: Path) -> None:
    calls = 0

    def fail(_: str) -> None:
        nonlocal calls
        calls += 1
        raise DeliveryError("temporary", retryable=True)

    now = datetime(2026, 9, 10, 12, tzinfo=UTC)
    reporter = OperationalIncidentReporter(
        OperationalIncidentStore(tmp_path / "incidents.json"),
        fail,
        failure_threshold=1,
        followup_interval=timedelta(hours=24),
    )

    reporter.observe(_report(), now)
    reporter.observe(_report(), now + timedelta(minutes=1))
    reporter.observe(_report(), now + timedelta(minutes=5))

    assert calls == 2
