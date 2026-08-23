"""Tests for deterministic offline fixture loading."""

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from macro_event_telegram_alerts import TimingPrecision
from macro_event_telegram_alerts.providers import JsonFixtureProvider

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "events.json"


def test_fixture_provider_normalizes_events_with_fixed_clock() -> None:
    fixed_now = datetime(2026, 8, 23, 10, 15, tzinfo=UTC)
    provider = JsonFixtureProvider(clock=lambda: fixed_now)

    exact, date_only = provider.load(FIXTURE_PATH)

    assert exact.retrieved_at is fixed_now
    assert exact.starts_at_local == datetime(
        2026,
        9,
        15,
        8,
        30,
        tzinfo=ZoneInfo("America/New_York"),
    )
    assert exact.starts_at_utc == datetime(2026, 9, 15, 12, 30, tzinfo=UTC)
    assert exact.institution == "U.S. Bureau of Labor Statistics"
    assert exact.source_url == "https://www.bls.gov/schedule/news_release/cpi.htm"

    assert date_only.retrieved_at is fixed_now
    assert date_only.timing_precision is TimingPrecision.DATE_ONLY
    assert date_only.starts_at_local is None
    assert date_only.starts_at_utc is None


def test_fixture_clock_is_sampled_once_per_document() -> None:
    calls = 0

    def clock() -> datetime:
        nonlocal calls
        calls += 1
        return datetime(2026, 8, 23, 10, 15, tzinfo=UTC)

    events = JsonFixtureProvider(clock=clock).load(FIXTURE_PATH)

    assert len(events) == 2
    assert calls == 1
