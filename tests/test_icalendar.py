import pytest

from macro_event_telegram_alerts.providers.icalendar import (
    CalendarProperty,
    ICalendarParseError,
    parse_icalendar,
    unescape_text,
)


def test_parser_unfolds_lines_and_normalizes_names() -> None:
    calendar = """BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VEVENT\r
uid:event-1\r
SUMMARY:Consumer Price\r
 Index\r
DTSTART;TZID=America/New_York:20260915T083000\r
END:VEVENT\r
END:VCALENDAR\r
"""

    (event,) = parse_icalendar(calendar)

    assert event.require_one("uid").value == "event-1"
    assert event.require_one("summary").value == "Consumer PriceIndex"
    assert event.require_one("dtstart") == CalendarProperty(
        name="DTSTART",
        value="20260915T083000",
        parameters=(("TZID", "America/New_York"),),
    )
    assert event.optional_one("url") is None


def test_parser_ignores_properties_outside_events() -> None:
    calendar = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VTIMEZONE
TZID:America/New_York
END:VTIMEZONE
BEGIN:VEVENT
UID:event-1
END:VEVENT
END:VCALENDAR
"""

    (event,) = parse_icalendar(calendar)

    assert event.properties == (CalendarProperty(name="UID", value="event-1"),)


@pytest.mark.parametrize(
    "calendar",
    [
        "",
        "BEGIN:VEVENT\nEND:VEVENT",
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nEND:VCALENDAR",
        "BEGIN:VCALENDAR\nBROKEN\nEND:VCALENDAR",
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nBEGIN:VEVENT\nEND:VEVENT\nEND:VEVENT\nEND:VCALENDAR",
    ],
)
def test_parser_rejects_invalid_structure(calendar: str) -> None:
    with pytest.raises(ICalendarParseError):
        parse_icalendar(calendar)


def test_event_accessors_reject_duplicate_properties() -> None:
    calendar = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:first
UID:second
END:VEVENT
END:VCALENDAR
"""
    (event,) = parse_icalendar(calendar)

    with pytest.raises(ICalendarParseError, match="exactly one UID"):
        event.require_one("uid")


def test_text_unescaping_is_explicit() -> None:
    assert unescape_text(r"one\, two\; three\\four\nnext") == (
        "one, two; three\\four\nnext"
    )
    with pytest.raises(ICalendarParseError, match="unsupported TEXT escape"):
        unescape_text(r"unsupported\tvalue")
