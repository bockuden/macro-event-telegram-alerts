"""Tests for safe, inspectable reminder rendering."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from macro_event_telegram_alerts import (
    EventSignificance,
    MacroEvent,
    SignificancePolicy,
    TimingPrecision,
)
from macro_event_telegram_alerts.notifications import (
    DryRunNotifier,
    format_reminder_message,
)
from macro_event_telegram_alerts.reminders import Reminder


def _reminder() -> Reminder:
    local_time = datetime(2026, 9, 15, 8, 30, tzinfo=ZoneInfo("America/New_York"))
    event = MacroEvent(
        source_id="bls:cpi:2026-09-15",
        title="Consumer Price Index",
        institution="U.S. Bureau of Labor Statistics",
        source_url="https://www.bls.gov/news.release/cpi.nr0.htm",
        scheduled_date=date(2026, 9, 15),
        timing_precision=TimingPrecision.EXACT,
        policy=SignificancePolicy(EventSignificance.SIGNIFICANT, "us-major-events-v1"),
        retrieved_at=datetime(2026, 9, 1, 12, tzinfo=UTC),
        starts_at_local=local_time,
        starts_at_utc=local_time.astimezone(UTC),
    )
    return Reminder(event=event, lead_time=timedelta(minutes=15))


def test_message_includes_required_source_facts_and_policy_disclaimer() -> None:
    message = format_reminder_message(_reminder())

    assert "15 minutes remaining" in message
    assert "Consumer Price Index" in message
    assert "U.S. Bureau of Labor Statistics" in message
    assert "2026-09-15 08:30 EDT (America/New_York)" in message
    assert "exact time published by the source" in message
    assert "https://www.bls.gov/news.release/cpi.nr0.htm" in message
    assert "not an official institution rating" in message


def test_dry_run_writes_the_same_message_without_credentials() -> None:
    messages: list[str] = []

    DryRunNotifier(messages.append).deliver(_reminder())

    assert messages == [format_reminder_message(_reminder())]
