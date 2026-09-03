"""Normalize scheduled FOMC statements and press conferences."""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from enum import StrEnum
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from macro_event_telegram_alerts.domain import MacroEvent, TimingPrecision
from macro_event_telegram_alerts.policy import EventSignificance, SignificancePolicy
from macro_event_telegram_alerts.providers.fed_transport import (
    FOMC_CALENDAR_URL,
    FomcCalendarTransport,
)
from macro_event_telegram_alerts.providers.fomc_html import (
    FomcCalendarLink,
    FomcCalendarParseError,
    FomcMeetingRow,
    parse_fomc_calendar_html,
)

FOMC_INSTITUTION = "Federal Open Market Committee"
FOMC_TIMEZONE = ZoneInfo("America/New_York")
FOMC_STATEMENT_TIME = time(14, 0)
FOMC_PRESS_CONFERENCE_TIME = time(14, 30)
FOMC_TIME_POLICY_URL = (
    "https://www.federalreserve.gov/newsevents/pressreleases/monetary20240809a.htm"
)
FOMC_SIGNIFICANCE_POLICY = SignificancePolicy(
    significance=EventSignificance.SIGNIFICANT,
    revision="fomc-scheduled-communications-v1",
)

_REGULAR_DATES = re.compile(r"^(\d{1,2})-(\d{1,2})(?:\*)?$")
_STATEMENT_PATH = re.compile(
    r"^/newsevents/pressreleases/monetary(\d{8})a\.htm$",
    re.IGNORECASE,
)
_PRESS_PATH = re.compile(
    r"^/monetarypolicy/fomc(?:press|pres)conf(\d{8})\.htm$",
    re.IGNORECASE,
)
_MONTH_NUMBERS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


class FomcCalendarError(ValueError):
    """A scheduled FOMC communication cannot be normalized safely."""


class FomcEventKind(StrEnum):
    """Scheduled post-meeting communications represented by the adapter."""

    STATEMENT = "FOMC Policy Statement"
    PRESS_CONFERENCE = "FOMC Chair Press Conference"


@dataclass(frozen=True, slots=True)
class _RegularMeeting:
    year: int
    ordinal: int
    decision_date: date
    row: FomcMeetingRow


class FomcCalendarProvider:
    """Load scheduled FOMC communications from the official calendar."""

    def __init__(self, transport: FomcCalendarTransport) -> None:
        self._transport = transport

    def load(self) -> tuple[MacroEvent, ...]:
        """Fetch the cached calendar and return scheduled communications."""
        payload = self._transport.fetch()
        return parse_fomc_calendar(payload.text, payload.retrieved_at)


def parse_fomc_calendar(html: str, retrieved_at: datetime) -> tuple[MacroEvent, ...]:
    """Normalize current and future calendar years without network access."""
    _require_utc(retrieved_at)
    try:
        document = parse_fomc_calendar_html(html)
    except FomcCalendarParseError as error:
        raise FomcCalendarError(str(error)) from error

    retrieved_eastern = retrieved_at.astimezone(FOMC_TIMEZONE)
    target_years = tuple(
        year for year in document.years if year >= retrieved_eastern.year
    )
    if not target_years:
        raise FomcCalendarError("FOMC calendar has no current or future year")

    meetings = _regular_meetings(document.meetings, target_years)
    events: list[MacroEvent] = []
    for meeting in meetings:
        events.extend(_meeting_events(meeting, retrieved_at, retrieved_eastern.date()))
    return tuple(events)


def _regular_meetings(
    rows: tuple[FomcMeetingRow, ...],
    target_years: tuple[int, ...],
) -> tuple[_RegularMeeting, ...]:
    meetings: list[_RegularMeeting] = []
    for year in target_years:
        year_rows: list[tuple[date, FomcMeetingRow]] = []
        for row in (candidate for candidate in rows if candidate.year == year):
            if _is_out_of_scope(row.date_label):
                continue
            if _REGULAR_DATES.fullmatch(row.date_label) is None:
                raise FomcCalendarError(
                    f"unsupported FOMC meeting date label: {row.date_label}"
                )
            year_rows.append((_decision_date(row), row))

        if len(year_rows) != 8:
            raise FomcCalendarError(
                f"FOMC {year} calendar must contain exactly 8 regular meetings"
            )
        dates = [meeting_date for meeting_date, _ in year_rows]
        if dates != sorted(dates) or len(dates) != len(set(dates)):
            raise FomcCalendarError(
                f"FOMC {year} regular meetings must be unique and chronological"
            )
        meetings.extend(
            _RegularMeeting(
                year=year,
                ordinal=index,
                decision_date=meeting_date,
                row=row,
            )
            for index, (meeting_date, row) in enumerate(year_rows, start=1)
        )
    return tuple(meetings)


def _meeting_events(
    meeting: _RegularMeeting,
    retrieved_at: datetime,
    retrieved_eastern_date: date,
) -> tuple[MacroEvent, MacroEvent]:
    precision = (
        TimingPrecision.EXACT
        if meeting.decision_date <= retrieved_eastern_date
        else TimingPrecision.TENTATIVE
    )
    statement_url = _statement_url(meeting, retrieved_eastern_date)
    press_url = _press_conference_url(meeting, retrieved_eastern_date)
    statement_time = _eastern_datetime(meeting.decision_date, FOMC_STATEMENT_TIME)
    press_time = _eastern_datetime(
        meeting.decision_date,
        FOMC_PRESS_CONFERENCE_TIME,
    )
    return (
        _event(
            meeting,
            FomcEventKind.STATEMENT,
            statement_url,
            statement_time,
            precision,
            retrieved_at,
        ),
        _event(
            meeting,
            FomcEventKind.PRESS_CONFERENCE,
            press_url,
            press_time,
            precision,
            retrieved_at,
        ),
    )


def _event(
    meeting: _RegularMeeting,
    kind: FomcEventKind,
    source_url: str,
    starts_at_local: datetime,
    precision: TimingPrecision,
    retrieved_at: datetime,
) -> MacroEvent:
    source_kind = kind.name.lower()
    return MacroEvent(
        source_id=f"fomc:{meeting.year}:{meeting.ordinal:02d}:{source_kind}",
        title=kind.value,
        institution=FOMC_INSTITUTION,
        source_url=source_url,
        scheduled_date=meeting.decision_date,
        timing_precision=precision,
        policy=FOMC_SIGNIFICANCE_POLICY,
        retrieved_at=retrieved_at.astimezone(UTC),
        starts_at_local=starts_at_local,
        starts_at_utc=starts_at_local.astimezone(UTC),
    )


def _decision_date(row: FomcMeetingRow) -> date:
    match = _REGULAR_DATES.fullmatch(row.date_label)
    if match is None:
        raise FomcCalendarError(f"invalid regular FOMC dates: {row.date_label}")
    month_parts = [part.strip().casefold() for part in row.month_label.split("/")]
    if len(month_parts) not in {1, 2} or any(not part for part in month_parts):
        raise FomcCalendarError(f"invalid FOMC month label: {row.month_label}")
    try:
        decision_month = _MONTH_NUMBERS[month_parts[-1]]
    except KeyError as error:
        raise FomcCalendarError(
            f"unsupported FOMC month label: {row.month_label}"
        ) from error
    try:
        return date(row.year, decision_month, int(match.group(2)))
    except ValueError as error:
        raise FomcCalendarError(
            f"invalid FOMC decision date: {row.date_label}"
        ) from error


def _statement_url(meeting: _RegularMeeting, retrieved_date: date) -> str:
    candidates = [
        (link, match)
        for link in meeting.row.links
        if (match := _STATEMENT_PATH.fullmatch(urlsplit(link.href).path)) is not None
    ]
    return _dated_source_url(candidates, meeting, retrieved_date, "statement")


def _press_conference_url(meeting: _RegularMeeting, retrieved_date: date) -> str:
    candidates = [
        (link, match)
        for link in meeting.row.links
        if link.text.casefold() == "press conference"
        and (match := _PRESS_PATH.fullmatch(urlsplit(link.href).path)) is not None
    ]
    return _dated_source_url(candidates, meeting, retrieved_date, "press conference")


def _dated_source_url(
    candidates: list[tuple[FomcCalendarLink, re.Match[str]]],
    meeting: _RegularMeeting,
    retrieved_date: date,
    source_name: str,
) -> str:
    if len(candidates) > 1:
        raise FomcCalendarError(f"FOMC meeting has multiple {source_name} links")
    if not candidates:
        if meeting.decision_date < retrieved_date:
            raise FomcCalendarError(
                f"past FOMC meeting has no official {source_name} link"
            )
        return FOMC_CALENDAR_URL

    link, match = candidates[0]
    expected_date = meeting.decision_date.strftime("%Y%m%d")
    if match.group(1) != expected_date:
        raise FomcCalendarError(f"FOMC {source_name} link date does not match meeting")
    return _official_url(link.href)


def _official_url(href: str) -> str:
    url = urljoin(FOMC_CALENDAR_URL, href)
    parsed = urlsplit(url)
    hostname = parsed.hostname.casefold() if parsed.hostname else ""
    if parsed.scheme != "https" or not (
        hostname == "federalreserve.gov" or hostname.endswith(".federalreserve.gov")
    ):
        raise FomcCalendarError("FOMC source URL must use HTTPS on federalreserve.gov")
    return url


def _eastern_datetime(day: date, scheduled_time: time) -> datetime:
    naive = datetime.combine(day, scheduled_time)
    candidates: dict[object, datetime] = {}
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=FOMC_TIMEZONE, fold=fold)
        round_trip = candidate.astimezone(UTC).astimezone(FOMC_TIMEZONE)
        if round_trip.replace(tzinfo=None) == naive:
            candidates[candidate.utcoffset()] = candidate
    if not candidates:
        raise FomcCalendarError("scheduled FOMC time does not exist in Eastern Time")
    if len(candidates) > 1:
        raise FomcCalendarError("scheduled FOMC time is ambiguous in Eastern Time")
    return next(iter(candidates.values()))


def _is_out_of_scope(date_label: str) -> bool:
    normalized = date_label.casefold()
    return "notation vote" in normalized or "unscheduled" in normalized


def _require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise FomcCalendarError("retrieved_at must be timezone-aware UTC")
    if value.utcoffset() != UTC.utcoffset(value):
        raise FomcCalendarError("retrieved_at must use UTC")
