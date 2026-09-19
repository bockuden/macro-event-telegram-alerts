from datetime import UTC, datetime

from macro_event_telegram_alerts.providers.census_schedule import (
    CENSUS_SIGNIFICANCE_POLICY,
    parse_census_schedule,
)

HTML = """
<tr><td>Advance Monthly Sales for Retail and Food Services</td>
<td>October 15, 2026</td><td>8:30 AM</td></tr>
"""


def test_parse_census_retail_schedule_normalizes_eastern_time() -> None:
    events = parse_census_schedule(HTML, datetime(2026, 9, 19, tzinfo=UTC))
    assert len(events) == 1
    event = events[0]
    assert event.title == "Advance Monthly Sales for Retail and Food Services"
    assert event.starts_at_utc is not None
    assert event.starts_at_utc.isoformat() == "2026-10-15T12:30:00+00:00"
    assert event.policy == CENSUS_SIGNIFICANCE_POLICY


def test_parse_census_requires_reviewed_family() -> None:
    try:
        parse_census_schedule("<html>empty</html>", datetime(2026, 9, 19, tzinfo=UTC))
    except ValueError as error:
        assert "no reviewed retail releases" in str(error)
    else:
        raise AssertionError("expected missing-family validation")
