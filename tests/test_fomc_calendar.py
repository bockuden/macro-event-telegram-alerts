from datetime import UTC, datetime
from pathlib import Path

import pytest

from macro_event_telegram_alerts.domain import MacroEvent, TimingPrecision
from macro_event_telegram_alerts.policy import EventSignificance
from macro_event_telegram_alerts.providers.fed_transport import FOMC_CALENDAR_URL
from macro_event_telegram_alerts.providers.fomc_calendar import (
    FomcCalendarError,
    parse_fomc_calendar,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fomc-calendar-minimal.html"
RETRIEVED_AT = datetime(2026, 9, 3, 12, tzinfo=UTC)


def _fixture() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def _events(html: str | None = None) -> tuple[MacroEvent, ...]:
    return parse_fomc_calendar(html or _fixture(), RETRIEVED_AT)


def test_fixture_creates_statement_and_press_conference_for_each_meeting() -> None:
    events = _events()

    assert len(events) == 16
    assert [event.title for event in events[:4]] == [
        "FOMC Policy Statement",
        "FOMC Chair Press Conference",
        "FOMC Policy Statement",
        "FOMC Chair Press Conference",
    ]
    assert all(event.institution == "Federal Open Market Committee" for event in events)
    assert all(
        event.policy.significance is EventSignificance.SIGNIFICANT
        and event.policy.revision == "fomc-scheduled-communications-v1"
        for event in events
    )


def test_eastern_time_conversion_covers_est_and_edt() -> None:
    events = _events()

    assert events[0].starts_at_utc == datetime(2026, 1, 28, 19, 0, tzinfo=UTC)
    assert events[1].starts_at_utc == datetime(2026, 1, 28, 19, 30, tzinfo=UTC)
    assert events[2].starts_at_utc == datetime(2026, 3, 18, 18, 0, tzinfo=UTC)
    assert events[3].starts_at_utc == datetime(2026, 3, 18, 18, 30, tzinfo=UTC)
    assert events[-2].starts_at_utc == datetime(2026, 12, 9, 19, 0, tzinfo=UTC)
    assert events[-1].starts_at_utc == datetime(2026, 12, 9, 19, 30, tzinfo=UTC)


def test_past_is_exact_and_future_calendar_dates_remain_tentative() -> None:
    events = _events()

    assert all(event.timing_precision is TimingPrecision.EXACT for event in events[:10])
    assert all(
        event.timing_precision is TimingPrecision.TENTATIVE for event in events[10:]
    )


def test_published_links_are_preserved_and_future_events_use_calendar() -> None:
    events = _events()

    assert events[0].source_url == (
        "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260128a.htm"
    )
    assert events[1].source_url == (
        "https://www.federalreserve.gov/monetarypolicy/fomcpressconf20260128.htm"
    )
    assert all(event.source_url == FOMC_CALENDAR_URL for event in events[10:])


def test_source_identity_survives_a_tentative_date_change() -> None:
    original = _events()
    rescheduled = _events(_fixture().replace("15-16*", "22-23*"))

    assert [event.source_id for event in rescheduled] == [
        event.source_id for event in original
    ]
    assert rescheduled[10].scheduled_date != original[10].scheduled_date


def test_missing_regular_meeting_fails_instead_of_returning_partial_year() -> None:
    changed = _fixture().replace("8-9*", "9 (unscheduled)")

    with pytest.raises(FomcCalendarError, match="exactly 8 regular meetings"):
        _events(changed)


def test_past_meeting_requires_published_source_links() -> None:
    changed = _fixture().replace(
        '<a href="/newsevents/pressreleases/monetary20260128a.htm">HTML</a>',
        "",
    )

    with pytest.raises(FomcCalendarError, match="no official statement link"):
        _events(changed)


def test_source_link_date_must_match_decision_date() -> None:
    changed = _fixture().replace("monetary20260128a.htm", "monetary20260129a.htm")

    with pytest.raises(FomcCalendarError, match="date does not match"):
        _events(changed)


def test_invalid_first_meeting_day_is_rejected() -> None:
    changed = _fixture().replace("15-16*", "99-16*", 1)

    with pytest.raises(FomcCalendarError, match="invalid FOMC decision date"):
        _events(changed)
