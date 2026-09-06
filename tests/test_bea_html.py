import pytest

from macro_event_telegram_alerts.providers.bea_html import (
    BeaScheduleParseError,
    BeaScheduleRow,
    parse_bea_schedule_html,
)

MINIMAL_SCHEDULE = """<!doctype html>
<html><body>
<table class="table" id="release-schedule-table">
  <thead><tr><th>Year 2026</th><th></th><th>Release</th></tr></thead>
  <tbody>
    <tr class="scheduled-releases-type-press">
      <td class="scheduled-date"><div class="release-date">September 30</div>
        <small class="text-muted">8:30 AM</small></td>
      <td>News</td>
      <td class="release-title">Personal Income <em>and</em> Outlays, August 2026</td>
      <td><a href="/news/2026/personal-income-and-outlays-august-2026">View</a></td>
    </tr>
    <tr class="scheduled-releases-type-data">
      <td class="scheduled-date"><div class="release-date">October 6</div></td>
      <td>Data</td>
      <td class="release-title">Some future data release</td>
      <td></td>
    </tr>
  </tbody>
</table>
</body></html>
"""


def test_parser_extracts_reviewed_table_structure() -> None:
    document = parse_bea_schedule_html(MINIMAL_SCHEDULE)

    assert document.year == 2026
    assert document.rows == (
        BeaScheduleRow(
            release_date="September 30",
            release_time="8:30 AM",
            release_kind="press",
            title="Personal Income and Outlays, August 2026",
            href="/news/2026/personal-income-and-outlays-august-2026",
        ),
        BeaScheduleRow(
            release_date="October 6",
            release_time=None,
            release_kind="data",
            title="Some future data release",
            href=None,
        ),
    )


def test_parser_keeps_unselected_to_be_announced_rows() -> None:
    html = MINIMAL_SCHEDULE.replace(
        "</tbody>",
        """    <tr class=\"scheduled-releases-type-press\">
      <td class=\"scheduled-date\">
        <div class=\"release-date\">To Be Announced 2026</div>
      </td>
      <td>News</td>
      <td class=\"release-title\">Outdoor Recreation Economic Statistics</td>
      <td></td>
    </tr>
  </tbody>""",
    )

    document = parse_bea_schedule_html(html)

    assert document.rows[-1].release_date == "To Be Announced 2026"


@pytest.mark.parametrize(
    ("original", "replacement", "message"),
    [
        ("release-schedule-table", "changed-table", "exactly one"),
        ("Year 2026", "Schedule 2026", "year header"),
        ("scheduled-releases-type-press", "release-row", "type class"),
        ("release-title", "changed-title", "no release title"),
        ("</table>", "", "not closed"),
    ],
)
def test_parser_rejects_layout_drift(
    original: str,
    replacement: str,
    message: str,
) -> None:
    changed = MINIMAL_SCHEDULE.replace(original, replacement, 1)

    with pytest.raises(BeaScheduleParseError, match=message):
        parse_bea_schedule_html(changed)


def test_parser_rejects_duplicate_official_tables() -> None:
    duplicate = MINIMAL_SCHEDULE.replace(
        "</body>",
        '<table id="release-schedule-table"></table></body>',
    )

    with pytest.raises(BeaScheduleParseError, match="exactly one"):
        parse_bea_schedule_html(duplicate)
