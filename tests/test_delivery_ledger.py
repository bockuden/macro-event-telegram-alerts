"""Tests for durable delivery claims and reminder identities."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from macro_event_telegram_alerts import (
    EventSignificance,
    MacroEvent,
    SignificancePolicy,
    TimingPrecision,
)
from macro_event_telegram_alerts.delivery_ledger import DeliveryStatus, ReminderLedger
from macro_event_telegram_alerts.reminders import Reminder


def _reminder(
    *, occurrence_at: datetime = datetime(2026, 9, 15, 12, 30, tzinfo=UTC)
) -> Reminder:
    event = MacroEvent(
        source_id="bls:cpi:2026-09-15",
        title="Consumer Price Index",
        institution="U.S. Bureau of Labor Statistics",
        source_url="https://www.bls.gov/news.release/cpi.nr0.htm",
        scheduled_date=date(2026, 9, 15),
        timing_precision=TimingPrecision.EXACT,
        policy=SignificancePolicy(EventSignificance.SIGNIFICANT, "us-major-events-v1"),
        retrieved_at=datetime(2026, 9, 1, 12, tzinfo=UTC),
        starts_at_local=occurrence_at.astimezone(ZoneInfo("America/New_York")),
        starts_at_utc=occurrence_at,
    )
    return Reminder(event=event, lead_time=timedelta(minutes=15))


def test_sent_reminder_is_not_claimed_after_ledger_restart(tmp_path: Path) -> None:
    path = tmp_path / "state" / "reminders.sqlite3"
    reminder = _reminder()
    now = datetime(2026, 9, 15, 12, 15, tzinfo=UTC)
    ledger = ReminderLedger(path)
    lease = ledger.claim(reminder, now)

    assert lease is not None
    ledger.mark_sent(lease, now)

    restarted = ReminderLedger(path)
    assert restarted.claim(reminder, now + timedelta(minutes=1)) is None
    assert restarted.record_for(reminder).status is DeliveryStatus.SENT  # type: ignore[union-attr]


def test_failed_delivery_can_be_claimed_again(tmp_path: Path) -> None:
    ledger = ReminderLedger(tmp_path / "reminders.sqlite3")
    reminder = _reminder()
    now = datetime(2026, 9, 15, 12, 15, tzinfo=UTC)
    first = ledger.claim(reminder, now)

    assert first is not None
    ledger.mark_failed(first, now, "temporary transport failure", retryable=True)
    second = ledger.claim(reminder, now + timedelta(minutes=1))

    assert second is not None
    assert second.attempt_id != first.attempt_id
    assert ledger.record_for(reminder).attempts == 2  # type: ignore[union-attr]


def test_expired_delivery_lease_can_be_recovered_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "reminders.sqlite3"
    reminder = _reminder()
    now = datetime(2026, 9, 15, 12, 15, tzinfo=UTC)
    first = ReminderLedger(path).claim(
        reminder, now, lease_duration=timedelta(minutes=1)
    )

    assert first is not None
    recovered = ReminderLedger(path).claim(reminder, now + timedelta(minutes=2))

    assert recovered is not None
    assert recovered.attempt_id != first.attempt_id


def test_rescheduled_occurrence_has_a_distinct_delivery_identity(
    tmp_path: Path,
) -> None:
    ledger = ReminderLedger(tmp_path / "reminders.sqlite3")
    original = _reminder()
    rescheduled = _reminder(occurrence_at=datetime(2026, 9, 15, 13, 30, tzinfo=UTC))
    now = datetime(2026, 9, 15, 12, 15, tzinfo=UTC)

    original_lease = ledger.claim(original, now)
    rescheduled_lease = ledger.claim(rescheduled, now)

    assert original_lease is not None
    assert rescheduled_lease is not None
    assert ledger.record_for(original) is not None
    assert ledger.record_for(rescheduled) is not None
