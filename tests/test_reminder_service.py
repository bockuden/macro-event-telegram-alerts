"""End-to-end tests for reminder selection, deduplication, and retry state."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from macro_event_telegram_alerts import (
    EventSignificance,
    MacroEvent,
    SignificancePolicy,
    TimingPrecision,
)
from macro_event_telegram_alerts.delivery_errors import DeliveryError
from macro_event_telegram_alerts.delivery_ledger import DeliveryStatus, ReminderLedger
from macro_event_telegram_alerts.notifications import DryRunNotifier
from macro_event_telegram_alerts.reminder_service import ReminderService
from macro_event_telegram_alerts.reminders import ReminderPolicy


def _event(
    *,
    starts_at_utc: datetime | None = datetime(2026, 9, 15, 12, 30, tzinfo=UTC),
    precision: TimingPrecision = TimingPrecision.EXACT,
) -> MacroEvent:
    local_time = (
        starts_at_utc.astimezone(ZoneInfo("America/New_York"))
        if starts_at_utc is not None
        else None
    )
    return MacroEvent(
        source_id="bls:cpi:2026-09-15",
        title="Consumer Price Index",
        institution="U.S. Bureau of Labor Statistics",
        source_url="https://www.bls.gov/news.release/cpi.nr0.htm",
        scheduled_date=date(2026, 9, 15),
        timing_precision=precision,
        policy=SignificancePolicy(EventSignificance.SIGNIFICANT, "us-major-events-v1"),
        retrieved_at=datetime(2026, 9, 1, 12, tzinfo=UTC),
        starts_at_local=local_time,
        starts_at_utc=starts_at_utc,
    )


def _service(database_path: Path) -> ReminderService:
    return ReminderService(ReminderPolicy(), ReminderLedger(database_path))


def test_late_discovery_delivers_only_the_closest_due_reminder(tmp_path: Path) -> None:
    delivered: list[timedelta] = []

    result = _service(tmp_path / "state.sqlite3").run(
        [_event()],
        datetime(2026, 9, 15, 11, 45, tzinfo=UTC),
        lambda reminder: delivered.append(reminder.lead_time),
    )

    assert delivered == [timedelta(hours=1)]
    assert len(result.delivered) == 1


def test_restart_does_not_redeliver_a_sent_reminder(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    now = datetime(2026, 9, 15, 12, 20, tzinfo=UTC)
    first: list[str] = []
    second: list[str] = []

    _service(path).run(
        [_event()], now, lambda reminder: first.append(reminder.event.source_id)
    )
    _service(path).run(
        [_event()], now, lambda reminder: second.append(reminder.event.source_id)
    )

    assert first == ["bls:cpi:2026-09-15"]
    assert second == []


def test_failed_delivery_is_recorded_and_retried(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    service = _service(path)
    event = _event()
    now = datetime(2026, 9, 15, 12, 20, tzinfo=UTC)

    failed = service.run([event], now, lambda reminder: _raise_transport_error())
    retried = service.run([event], now + timedelta(minutes=1), lambda reminder: None)
    reminder = ReminderPolicy().due_reminders([event], now)[0]

    assert len(failed.failed) == 1
    assert len(retried.delivered) == 1
    assert ReminderLedger(path).record_for(reminder).status is DeliveryStatus.SENT  # type: ignore[union-attr]


def test_permanent_delivery_failure_is_not_retried(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    service = _service(path)
    event = _event()
    now = datetime(2026, 9, 15, 12, 20, tzinfo=UTC)
    attempts: list[object] = []

    first = service.run(
        [event],
        now,
        lambda _: _raise_permanent_delivery_error(attempts),
    )
    second = service.run([event], now + timedelta(minutes=1), attempts.append)
    reminder = ReminderPolicy().due_reminders([event], now)[0]
    record = ReminderLedger(path).record_for(reminder)

    assert len(first.failed) == 1
    assert second.delivered == ()
    assert len(attempts) == 1
    assert record is not None
    assert record.status is DeliveryStatus.FAILED
    assert not record.retryable


def test_tba_event_never_enters_the_delivery_ledger(tmp_path: Path) -> None:
    delivered: list[object] = []

    result = _service(tmp_path / "state.sqlite3").run(
        [_event(starts_at_utc=None, precision=TimingPrecision.TBA)],
        datetime(2026, 9, 15, 12, tzinfo=UTC),
        delivered.append,
    )

    assert result.delivered == ()
    assert delivered == []


def test_service_can_deliver_to_a_credential_free_dry_run_sink(tmp_path: Path) -> None:
    messages: list[str] = []
    notifier = DryRunNotifier(messages.append)

    result = _service(tmp_path / "state.sqlite3").run(
        [_event()],
        datetime(2026, 9, 15, 12, 20, tzinfo=UTC),
        notifier.deliver,
    )

    assert len(result.delivered) == 1
    assert len(messages) == 1
    assert "Consumer Price Index" in messages[0]


def _raise_transport_error() -> None:
    raise RuntimeError("simulated transport failure")


def _raise_permanent_delivery_error(attempts: list[object]) -> None:
    attempts.append(object())
    raise DeliveryError("simulated permanent delivery failure", retryable=False)
