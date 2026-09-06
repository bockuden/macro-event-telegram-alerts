"""Tests for reminder lead times and late-discovery behavior."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from macro_event_telegram_alerts import (
    EventSignificance,
    MacroEvent,
    SignificancePolicy,
    TimingPrecision,
)
from macro_event_telegram_alerts.reminders import ReminderPolicy


def _event(
    *,
    starts_at_utc: datetime | None = datetime(2026, 9, 15, 12, 30, tzinfo=UTC),
    precision: TimingPrecision = TimingPrecision.EXACT,
) -> MacroEvent:
    starts_at_local = (
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
        policy=SignificancePolicy(
            significance=EventSignificance.SIGNIFICANT,
            revision="us-major-events-v1",
        ),
        retrieved_at=datetime(2026, 9, 1, 12, tzinfo=UTC),
        starts_at_local=starts_at_local,
        starts_at_utc=starts_at_utc,
    )


def test_default_policy_selects_the_closest_due_lead_time() -> None:
    policy = ReminderPolicy()

    (reminder,) = policy.due_reminders(
        [_event()],
        datetime(2026, 9, 15, 11, 45, tzinfo=UTC),
    )

    assert reminder.lead_time == timedelta(minutes=60)
    assert reminder.due_at == datetime(2026, 9, 15, 11, 30, tzinfo=UTC)


def test_late_discovery_never_backfills_multiple_messages() -> None:
    policy = ReminderPolicy()

    (reminder,) = policy.due_reminders(
        [_event()],
        datetime(2026, 9, 15, 12, 20, tzinfo=UTC),
    )

    assert reminder.lead_time == timedelta(minutes=15)


def test_date_only_and_tba_events_are_not_scheduled() -> None:
    policy = ReminderPolicy()
    date_only = _event(starts_at_utc=None, precision=TimingPrecision.DATE_ONLY)
    tba = _event(starts_at_utc=None, precision=TimingPrecision.TBA)

    assert (
        policy.due_reminders([date_only, tba], datetime(2026, 9, 15, 12, tzinfo=UTC))
        == ()
    )


def test_policy_rejects_duplicate_or_nonpositive_lead_times() -> None:
    with pytest.raises(ValueError, match="unique"):
        ReminderPolicy((timedelta(minutes=15), timedelta(minutes=15)))
    with pytest.raises(ValueError, match="positive"):
        ReminderPolicy((timedelta(0),))
