"""Strict structural parser for the official FOMC meeting calendar."""

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

MEETING_CLASS = "fomc-meeting"
MONTH_CLASS = "fomc-meeting__month"
DATE_CLASS = "fomc-meeting__date"
YEAR_HEADING = re.compile(r"^(20\d{2}) FOMC Meetings$")


class FomcCalendarParseError(ValueError):
    """The FOMC calendar HTML no longer satisfies its reviewed contract."""


@dataclass(frozen=True, slots=True)
class FomcCalendarLink:
    """One link retained from a meeting row."""

    text: str
    href: str


@dataclass(frozen=True, slots=True)
class FomcMeetingRow:
    """One structurally validated meeting row."""

    year: int
    month_label: str
    date_label: str
    links: tuple[FomcCalendarLink, ...]


@dataclass(frozen=True, slots=True)
class FomcCalendarDocument:
    """Meeting years and rows parsed from the official calendar."""

    years: tuple[int, ...]
    meetings: tuple[FomcMeetingRow, ...]


@dataclass(slots=True)
class _MeetingBuilder:
    year: int
    month_parts: list[str] = field(default_factory=list)
    date_parts: list[str] = field(default_factory=list)
    links: list[FomcCalendarLink] = field(default_factory=list)


@dataclass(slots=True)
class _Capture:
    name: str
    closing_tag: str
    parts: list[str]
    href: str | None = None


class _FomcCalendarHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.years: list[int] = []
        self.meetings: list[FomcMeetingRow] = []
        self.current_year: int | None = None
        self.current_meeting: _MeetingBuilder | None = None
        self.meeting_div_depth = 0
        self.capture: _Capture | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        classes = _class_tokens(attributes.get("class"))

        if self.current_meeting is not None and tag == "div":
            self.meeting_div_depth += 1

        if tag == "h4" and self.current_meeting is None:
            self._begin_capture("heading", tag, [])
            return

        if tag == "div" and MEETING_CLASS in classes:
            self._begin_meeting()
            return
        if self.current_meeting is None:
            return
        if tag == "div" and MONTH_CLASS in classes:
            self._begin_capture("month", tag, self.current_meeting.month_parts)
        elif tag == "div" and DATE_CLASS in classes:
            self._begin_capture("date", tag, self.current_meeting.date_parts)
        elif tag == "a":
            href = attributes.get("href")
            if href is None or not href.strip():
                raise FomcCalendarParseError("FOMC meeting link has no href")
            self._begin_capture("link", tag, [], href=href.strip())

    def handle_endtag(self, tag: str) -> None:
        if self.capture is not None and tag == self.capture.closing_tag:
            self._finish_capture()

        if self.current_meeting is not None and tag == "div":
            self.meeting_div_depth -= 1
            if self.meeting_div_depth < 0:
                raise FomcCalendarParseError("unexpected div end in FOMC meeting")
            if self.meeting_div_depth == 0:
                self._finish_meeting()

    def handle_data(self, data: str) -> None:
        if self.capture is not None:
            self.capture.parts.append(data)

    def _begin_capture(
        self,
        name: str,
        closing_tag: str,
        parts: list[str],
        *,
        href: str | None = None,
    ) -> None:
        if self.capture is not None:
            if self.capture.name == "heading":
                return
            raise FomcCalendarParseError(
                f"overlapping {self.capture.name} and {name} fields in FOMC calendar"
            )
        self.capture = _Capture(
            name=name,
            closing_tag=closing_tag,
            parts=parts,
            href=href,
        )

    def _finish_capture(self) -> None:
        assert self.capture is not None
        capture = self.capture
        self.capture = None
        text = _normalized_text(capture.parts)
        if capture.name == "heading":
            match = YEAR_HEADING.fullmatch(text)
            if match is not None:
                year = int(match.group(1))
                if year in self.years:
                    raise FomcCalendarParseError(
                        f"FOMC calendar repeats the {year} meeting section"
                    )
                self.years.append(year)
                self.current_year = year
        elif capture.name == "link":
            assert self.current_meeting is not None
            assert capture.href is not None
            if not text:
                raise FomcCalendarParseError("FOMC meeting link has no text")
            self.current_meeting.links.append(
                FomcCalendarLink(text=text, href=capture.href)
            )

    def _begin_meeting(self) -> None:
        if self.current_meeting is not None:
            raise FomcCalendarParseError("FOMC meeting rows cannot be nested")
        if self.current_year is None:
            raise FomcCalendarParseError(
                "FOMC meeting appears before a YYYY FOMC Meetings heading"
            )
        if self.capture is not None:
            raise FomcCalendarParseError("FOMC meeting starts inside another field")
        self.current_meeting = _MeetingBuilder(year=self.current_year)
        self.meeting_div_depth = 1

    def _finish_meeting(self) -> None:
        assert self.current_meeting is not None
        if self.capture is not None:
            raise FomcCalendarParseError("FOMC meeting ended inside a field")
        month = _normalized_text(self.current_meeting.month_parts)
        dates = _normalized_text(self.current_meeting.date_parts)
        if not month:
            raise FomcCalendarParseError("FOMC meeting has no month field")
        if not dates:
            raise FomcCalendarParseError("FOMC meeting has no date field")
        self.meetings.append(
            FomcMeetingRow(
                year=self.current_meeting.year,
                month_label=month,
                date_label=dates,
                links=tuple(self.current_meeting.links),
            )
        )
        self.current_meeting = None


def parse_fomc_calendar_html(html: str) -> FomcCalendarDocument:
    """Parse the reviewed FOMC layout, rejecting structural drift."""
    parser = _FomcCalendarHtmlParser()
    try:
        parser.feed(html)
        parser.close()
    except FomcCalendarParseError:
        raise
    except Exception as error:
        raise FomcCalendarParseError(
            "FOMC calendar HTML could not be parsed"
        ) from error

    if parser.current_meeting is not None or parser.meeting_div_depth != 0:
        raise FomcCalendarParseError("FOMC calendar ended inside a meeting row")
    if parser.capture is not None:
        raise FomcCalendarParseError("FOMC calendar ended inside a field")
    if not parser.years:
        raise FomcCalendarParseError("FOMC calendar has no year sections")
    if not parser.meetings:
        raise FomcCalendarParseError("FOMC calendar has no meeting rows")
    return FomcCalendarDocument(
        years=tuple(parser.years),
        meetings=tuple(parser.meetings),
    )


def _class_tokens(value: str | None) -> set[str]:
    return set(value.split()) if value else set()


def _normalized_text(parts: list[str]) -> str:
    return " ".join("".join(parts).split())
