"""Offline contract tests for the approved New York Fed BLS fallback."""

from datetime import UTC, datetime

from macro_event_telegram_alerts.providers.bls_calendar import parse_bls_calendar
from macro_event_telegram_alerts.providers.nyfed_bls_calendar import (
    parse_new_york_fed_bls_calendar,
)

RETRIEVED_AT = datetime(2026, 9, 12, 10, tzinfo=UTC)

CALENDAR = """<table><tr>
<td><div>04<br/><a>Employment Situation</a><br/>(08:30)</div></td>
<td><div>10<br/><a>Producer Price Index (PPI)</a><br/>(08:30)</div></td>
<td><div>11<br/><a>Consumer Price Index</a><br/>(08:30)</div></td>
<td><div>29<br/><a>JOLTS</a><br/>(10:00)</div></td>
</tr></table>"""


def test_fallback_normalizes_all_reviewed_families_as_eastern_instants() -> None:
    events = parse_new_york_fed_bls_calendar(CALENDAR, RETRIEVED_AT, year=2026, month=9)

    assert [event.title for event in events] == [
        "Employment Situation",
        "Producer Price Index",
        "Consumer Price Index",
        "Job Openings and Labor Turnover Survey",
    ]
    assert events[0].starts_at_utc == datetime(2026, 9, 4, 12, 30, tzinfo=UTC)
    assert events[-1].starts_at_utc == datetime(2026, 9, 29, 14, tzinfo=UTC)
    assert all(event.source_url.startswith("https://www.bls.gov/") for event in events)


def test_primary_and_fallback_share_the_same_logical_event_identity() -> None:
    primary = parse_bls_calendar(
        """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:unrelated-primary-uid
DTSTART:20260911T083000
SUMMARY:Consumer Price Index
END:VEVENT
END:VCALENDAR
""",
        RETRIEVED_AT,
    )
    fallback = parse_new_york_fed_bls_calendar(
        "<td><div>11<a>Consumer Price Index</a>(08:30)</div></td>",
        RETRIEVED_AT,
        year=2026,
        month=9,
    )

    assert primary[0].source_id == fallback[0].source_id
