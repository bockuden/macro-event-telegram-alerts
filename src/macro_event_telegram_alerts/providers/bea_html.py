"""Strict structural parser for the official BEA release schedule table."""

from dataclasses import dataclass, field
from html.parser import HTMLParser

SCHEDULE_TABLE_ID = "release-schedule-table"
ROW_CLASS_PREFIX = "scheduled-releases-type-"


class BeaScheduleParseError(ValueError):
    """The BEA schedule HTML no longer satisfies its reviewed contract."""


@dataclass(frozen=True, slots=True)
class BeaScheduleRow:
    """One structurally validated row from the BEA schedule table."""

    release_date: str
    release_time: str | None
    release_kind: str
    title: str
    href: str | None


@dataclass(frozen=True, slots=True)
class BeaScheduleDocument:
    """The schedule year and validated rows parsed from one HTML document."""

    year: int
    rows: tuple[BeaScheduleRow, ...]


@dataclass(slots=True)
class _RowBuilder:
    release_kind: str
    release_date_parts: list[str] = field(default_factory=list)
    release_time_parts: list[str] = field(default_factory=list)
    title_parts: list[str] = field(default_factory=list)
    hrefs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class _Capture:
    name: str
    closing_tag: str
    parts: list[str]


class _BeaScheduleHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.table_count = 0
        self.in_target_table = False
        self.in_table_body = False
        self.target_table_closed = False
        self.header_years: list[int] = []
        self.rows: list[BeaScheduleRow] = []
        self.current_row: _RowBuilder | None = None
        self.capture: _Capture | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        classes = _class_tokens(attributes.get("class"))

        if tag == "table" and attributes.get("id") == SCHEDULE_TABLE_ID:
            self.table_count += 1
            if self.in_target_table:
                raise BeaScheduleParseError("BEA schedule tables cannot be nested")
            self.in_target_table = True
            self.target_table_closed = False
            return

        if not self.in_target_table:
            return
        if tag == "tbody":
            if self.in_table_body:
                raise BeaScheduleParseError("BEA schedule has nested tbody elements")
            self.in_table_body = True
            return
        if tag == "th":
            self._begin_capture("header", tag, [])
            return
        if tag == "tr" and self.in_table_body:
            self._begin_row(classes)
            return
        if self.current_row is None:
            return
        if tag == "div" and "release-date" in classes:
            self._begin_capture(
                "date",
                tag,
                self.current_row.release_date_parts,
            )
        elif tag == "small" and "text-muted" in classes:
            self._begin_capture(
                "time",
                tag,
                self.current_row.release_time_parts,
            )
        elif tag == "td" and "release-title" in classes:
            self._begin_capture("title", tag, self.current_row.title_parts)
        elif tag == "a" and (href := attributes.get("href")) is not None:
            self.current_row.hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        if not self.in_target_table:
            return
        if self.capture is not None and tag == self.capture.closing_tag:
            if self.capture.name == "header":
                self._record_header_year(self.capture.parts)
            self.capture = None
        if tag == "tr" and self.current_row is not None:
            self._finish_row()
        elif tag == "tbody":
            if not self.in_table_body:
                raise BeaScheduleParseError("unexpected tbody end in BEA schedule")
            self.in_table_body = False
        elif tag == "table":
            if self.current_row is not None or self.in_table_body:
                raise BeaScheduleParseError("BEA schedule table ended inside a row")
            self.in_target_table = False
            self.target_table_closed = True

    def handle_data(self, data: str) -> None:
        if self.capture is not None:
            self.capture.parts.append(data)

    def _begin_capture(
        self,
        name: str,
        closing_tag: str,
        parts: list[str],
    ) -> None:
        if self.capture is not None:
            raise BeaScheduleParseError(
                f"overlapping {self.capture.name} and {name} fields in BEA schedule"
            )
        self.capture = _Capture(name=name, closing_tag=closing_tag, parts=parts)

    def _begin_row(self, classes: set[str]) -> None:
        if self.current_row is not None:
            raise BeaScheduleParseError("BEA schedule rows cannot be nested")
        kind_classes = sorted(
            class_name
            for class_name in classes
            if class_name.startswith(ROW_CLASS_PREFIX)
        )
        if len(kind_classes) != 1:
            raise BeaScheduleParseError(
                "BEA schedule row must have exactly one reviewed type class"
            )
        release_kind = kind_classes[0].removeprefix(ROW_CLASS_PREFIX)
        if not release_kind:
            raise BeaScheduleParseError("BEA schedule row type must not be empty")
        self.current_row = _RowBuilder(release_kind=release_kind)

    def _finish_row(self) -> None:
        assert self.current_row is not None
        if self.capture is not None:
            raise BeaScheduleParseError("BEA schedule row ended inside a field")
        release_date = _normalized_text(self.current_row.release_date_parts)
        release_time = _normalized_text(self.current_row.release_time_parts)
        title = _normalized_text(self.current_row.title_parts)
        if not title:
            raise BeaScheduleParseError("BEA schedule row has no release title")
        if len(self.current_row.hrefs) > 1:
            raise BeaScheduleParseError("BEA schedule row has multiple source links")
        href = self.current_row.hrefs[0].strip() if self.current_row.hrefs else None
        if href == "":
            raise BeaScheduleParseError("BEA schedule row has an empty source link")
        self.rows.append(
            BeaScheduleRow(
                release_date=release_date,
                release_time=release_time or None,
                release_kind=self.current_row.release_kind,
                title=title,
                href=href,
            )
        )
        self.current_row = None

    def _record_header_year(self, parts: list[str]) -> None:
        text = _normalized_text(parts)
        if not text.startswith("Year "):
            return
        raw_year = text.removeprefix("Year ")
        if len(raw_year) != 4 or not raw_year.isdecimal():
            raise BeaScheduleParseError("BEA schedule year header is invalid")
        self.header_years.append(int(raw_year))


def parse_bea_schedule_html(html: str) -> BeaScheduleDocument:
    """Parse the reviewed BEA table layout, rejecting structural drift."""
    parser = _BeaScheduleHtmlParser()
    try:
        parser.feed(html)
        parser.close()
    except BeaScheduleParseError:
        raise
    except Exception as error:
        raise BeaScheduleParseError("BEA schedule HTML could not be parsed") from error

    if parser.table_count != 1:
        raise BeaScheduleParseError(
            "BEA schedule must contain exactly one release-schedule-table"
        )
    if parser.in_target_table or not parser.target_table_closed:
        raise BeaScheduleParseError("BEA schedule table is not closed")
    if parser.current_row is not None or parser.capture is not None:
        raise BeaScheduleParseError("BEA schedule ended inside a row or field")
    if len(parser.header_years) != 1:
        raise BeaScheduleParseError("BEA schedule must contain exactly one year header")
    if not parser.rows:
        raise BeaScheduleParseError("BEA schedule table contains no release rows")
    return BeaScheduleDocument(
        year=parser.header_years[0],
        rows=tuple(parser.rows),
    )


def _class_tokens(value: str | None) -> set[str]:
    return set(value.split()) if value else set()


def _normalized_text(parts: list[str]) -> str:
    return " ".join("".join(parts).split())
