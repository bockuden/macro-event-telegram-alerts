from datetime import UTC, datetime
from pathlib import Path

import pytest

from macro_event_telegram_alerts.domain import MacroEvent
from macro_event_telegram_alerts.policy import EventSignificance
from macro_event_telegram_alerts.providers.bea_schedule import (
    BeaScheduleError,
    parse_bea_schedule,
)
from macro_event_telegram_alerts.providers.bea_transport import BEA_SCHEDULE_URL

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "bea-schedule-minimal.html"
RETRIEVED_AT = datetime(2026, 8, 30, 12, tzinfo=UTC)


def _events() -> tuple[MacroEvent, ...]:
    return parse_bea_schedule(
        FIXTURE_PATH.read_text(encoding="utf-8"),
        RETRIEVED_AT,
    )


def test_fixture_selects_only_reviewed_gdp_and_pce_news_releases() -> None:
    events = _events()

    assert [event.title for event in events] == [
        "Gross Domestic Product (GDP)",
        "Personal Income and Outlays (PCE)",
        "Gross Domestic Product (GDP)",
        "Personal Income and Outlays (PCE)",
        "Gross Domestic Product (GDP)",
        "Personal Income and Outlays (PCE)",
    ]
    assert all(
        event.institution == "U.S. Bureau of Economic Analysis" for event in events
    )
    assert all(
        event.policy.significance is EventSignificance.SIGNIFICANT
        and event.policy.revision == "bea-significant-releases-v1"
        for event in events
    )


def test_fixture_normalizes_eastern_time_across_daylight_saving() -> None:
    events = _events()

    assert events[0].starts_at_utc == datetime(2026, 8, 26, 12, 30, tzinfo=UTC)
    assert events[4].starts_at_utc == datetime(2026, 11, 25, 13, 30, tzinfo=UTC)


def test_fixture_preserves_release_links_and_uses_schedule_fallback() -> None:
    events = _events()

    assert events[0].source_url == (
        "https://www.bea.gov/news/2026/"
        "gdp-second-estimate-and-corporate-profits-2nd-quarter-2026"
    )
    assert events[1].source_url == (
        "https://www.bea.gov/news/2026/personal-income-and-outlays-july-2026"
    )
    assert all(event.source_url == BEA_SCHEDULE_URL for event in events[2:])


def test_source_identity_survives_a_schedule_date_change() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    original = parse_bea_schedule(html, RETRIEVED_AT)
    rescheduled = parse_bea_schedule(
        html.replace("August 26", "August 27"),
        RETRIEVED_AT,
    )

    assert [event.source_id for event in rescheduled] == [
        event.source_id for event in original
    ]
    assert rescheduled[0].scheduled_date != original[0].scheduled_date


def test_selected_release_without_time_fails_visibly() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8").replace(
        '<small class="text-muted">8:30 AM</small>',
        "",
        1,
    )

    with pytest.raises(BeaScheduleError, match="has no scheduled release time"):
        parse_bea_schedule(html, RETRIEVED_AT)


def test_external_release_link_is_rejected() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8").replace(
        "/news/2026/gdp-second-estimate-and-corporate-profits-2nd-quarter-2026",
        "https://example.com/gdp",
    )

    with pytest.raises(BeaScheduleError, match=r"must use HTTPS on bea\.gov"):
        parse_bea_schedule(html, RETRIEVED_AT)


def test_alias_drift_cannot_silently_remove_a_family() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8").replace(
        "Personal Income and Outlays,",
        "Renamed Household Release,",
    )

    with pytest.raises(BeaScheduleError, match="missing reviewed families"):
        parse_bea_schedule(html, RETRIEVED_AT)
