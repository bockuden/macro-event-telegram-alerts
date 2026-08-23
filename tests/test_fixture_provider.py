"""Tests for deterministic offline fixture loading."""

import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from macro_event_telegram_alerts import TimingPrecision
from macro_event_telegram_alerts.providers import FixtureError, JsonFixtureProvider

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


@pytest.mark.parametrize(
    ("timestamp", "message"),
    [
        ("not-a-timestamp", "ISO 8601 datetime"),
        (
            "2026-11-01T01:30:00",
            "ambiguous; include an explicit UTC offset",
        ),
        ("2026-03-08T02:30:00", "nonexistent source-local time"),
        ("2026-09-15T08:30:00-03:00", "offset does not match"),
    ],
)
def test_fixture_rejects_invalid_source_timestamps(
    timestamp: str,
    message: str,
) -> None:
    provider = JsonFixtureProvider(
        clock=lambda: datetime(2026, 8, 23, 10, 15, tzinfo=UTC)
    )

    with pytest.raises(FixtureError, match=message):
        provider.loads(_single_event_fixture(timestamp))


def test_explicit_offset_resolves_an_ambiguous_source_time() -> None:
    provider = JsonFixtureProvider(
        clock=lambda: datetime(2026, 8, 23, 10, 15, tzinfo=UTC)
    )

    (event,) = provider.loads(_single_event_fixture("2026-11-01T01:30:00-05:00"))

    assert event.starts_at_local is not None
    assert event.starts_at_local.fold == 1
    assert event.starts_at_utc == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)


def _single_event_fixture(timestamp: str) -> str:
    return json.dumps(
        {
            "events": [
                {
                    "source_id": "fed:fomc:2026-11-01",
                    "title": "FOMC event",
                    "institution": "Federal Reserve Board",
                    "source_url": "https://www.federalreserve.gov/",
                    "scheduled_date": "2026-11-01",
                    "timing_precision": "exact",
                    "source_timezone": "America/New_York",
                    "starts_at": timestamp,
                    "policy": {
                        "significance": "significant",
                        "revision": "us-major-events-v1",
                    },
                }
            ]
        }
    )
