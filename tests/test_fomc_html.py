from pathlib import Path

import pytest

from macro_event_telegram_alerts.providers.fomc_html import (
    FomcCalendarLink,
    FomcCalendarParseError,
    parse_fomc_calendar_html,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fomc-calendar-minimal.html"


def _fixture() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def test_parser_extracts_years_meetings_and_links() -> None:
    document = parse_fomc_calendar_html(_fixture())

    assert document.years == (2025, 2026)
    assert len(document.meetings) == 9
    assert document.meetings[0].month_label == "August"
    assert document.meetings[0].date_label == "22 (notation vote)"
    january = document.meetings[1]
    assert january.year == 2026
    assert january.month_label == "January"
    assert january.date_label == "27-28"
    assert (
        FomcCalendarLink(
            text="HTML",
            href="/newsevents/pressreleases/monetary20260128a.htm",
        )
        in january.links
    )
    assert (
        FomcCalendarLink(
            text="Press Conference",
            href="/monetarypolicy/fomcpressconf20260128.htm",
        )
        in january.links
    )


@pytest.mark.parametrize(
    ("original", "replacement", "message"),
    [
        ("2025 FOMC Meetings", "Meetings in 2025", "before a YYYY"),
        ("fomc-meeting__month", "changed-month", "no month field"),
        ("fomc-meeting__date", "changed-date", "no date field"),
        ('href="/newsevents', 'data-href="/newsevents', "no href"),
    ],
)
def test_parser_rejects_layout_drift(
    original: str,
    replacement: str,
    message: str,
) -> None:
    changed = _fixture().replace(original, replacement, 1)

    with pytest.raises(FomcCalendarParseError, match=message):
        parse_fomc_calendar_html(changed)


def test_parser_rejects_duplicate_year_sections() -> None:
    duplicate = _fixture().replace(
        "2025 FOMC Meetings",
        "2026 FOMC Meetings",
        1,
    )

    with pytest.raises(FomcCalendarParseError, match="repeats"):
        parse_fomc_calendar_html(duplicate)


def test_parser_rejects_unclosed_meeting() -> None:
    truncated = _fixture().rsplit("</div>", 2)[0] + "</body></html>"

    with pytest.raises(FomcCalendarParseError, match="ended inside"):
        parse_fomc_calendar_html(truncated)
