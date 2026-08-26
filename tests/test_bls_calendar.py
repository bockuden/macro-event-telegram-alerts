from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from macro_event_telegram_alerts.domain import TimingPrecision
from macro_event_telegram_alerts.policy import EventSignificance
from macro_event_telegram_alerts.providers.bls_calendar import (
    BlsCalendarError,
    parse_bls_calendar,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "bls-minimal.ics"
RETRIEVED_AT = datetime(2026, 8, 21, 19, 30, tzinfo=UTC)


def test_fixture_selects_only_reviewed_significant_releases() -> None:
    events = parse_bls_calendar(
        FIXTURE_PATH.read_text(encoding="utf-8"),
        RETRIEVED_AT,
    )

    assert [event.title for event in events] == [
        "Consumer Price Index",
        "Employment Situation",
        "Producer Price Index",
        "Job Openings and Labor Turnover Survey",
    ]
    assert all(
        event.policy.significance is EventSignificance.SIGNIFICANT
        and event.policy.revision == "bls-significant-releases-v1"
        for event in events
    )
    assert all(
        event.institution == "U.S. Bureau of Labor Statistics" for event in events
    )


def test_fixture_normalizes_eastern_floating_utc_and_date_only_times() -> None:
    events = parse_bls_calendar(
        FIXTURE_PATH.read_text(encoding="utf-8"),
        RETRIEVED_AT,
    )
    cpi, employment, ppi, jolts = events

    assert cpi.starts_at_utc == datetime(2026, 9, 11, 12, 30, tzinfo=UTC)
    assert employment.starts_at_utc == datetime(2026, 9, 4, 12, 30, tzinfo=UTC)
    assert ppi.starts_at_local is not None
    assert ppi.starts_at_local.hour == 8
    assert ppi.starts_at_local.tzinfo is not None
    assert jolts.timing_precision is TimingPrecision.DATE_ONLY
    assert jolts.scheduled_date == date(2026, 9, 2)
    assert jolts.starts_at_local is None
    assert jolts.starts_at_utc is None


def test_event_url_falls_back_to_reviewed_official_release_page() -> None:
    events = parse_bls_calendar(
        FIXTURE_PATH.read_text(encoding="utf-8"),
        RETRIEVED_AT,
    )

    assert events[2].source_url == "https://www.bls.gov/news.release/ppi.nr0.htm"
    assert all(event.source_url.startswith("https://www.bls.gov/") for event in events)


def test_unknown_summary_is_ignored_before_other_fields_are_required() -> None:
    calendar = """BEGIN:VCALENDAR
BEGIN:VEVENT
SUMMARY:Unselected release
END:VEVENT
END:VCALENDAR
"""

    assert parse_bls_calendar(calendar, RETRIEVED_AT) == ()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("UID", "", "empty UID"),
        ("DTSTART", "not-a-date", "local DTSTART is invalid"),
        ("URL", "https://example.com/cpi", "must use HTTPS on bls.gov"),
    ],
)
def test_selected_event_fails_visibly_on_invalid_required_data(
    field: str,
    value: str,
    message: str,
) -> None:
    fields = {
        "UID": "event-1",
        "DTSTART": "20260911T083000",
        "URL": "https://www.bls.gov/news.release/cpi.nr0.htm",
    }
    fields[field] = value
    calendar = f"""BEGIN:VCALENDAR
BEGIN:VEVENT
UID:{fields["UID"]}
DTSTART:{fields["DTSTART"]}
SUMMARY:Consumer Price Index
URL:{fields["URL"]}
END:VEVENT
END:VCALENDAR
"""

    with pytest.raises(BlsCalendarError, match=message):
        parse_bls_calendar(calendar, RETRIEVED_AT)


def test_duplicate_selected_uids_are_rejected() -> None:
    event = """BEGIN:VEVENT
UID:duplicate
DTSTART:20260911T083000
SUMMARY:Consumer Price Index
END:VEVENT
"""
    calendar = f"BEGIN:VCALENDAR\n{event}{event}END:VCALENDAR\n"

    with pytest.raises(BlsCalendarError, match="duplicate UIDs"):
        parse_bls_calendar(calendar, RETRIEVED_AT)
