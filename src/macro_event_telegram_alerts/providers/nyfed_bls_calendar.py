"""Fallback BLS schedule parser for the public New York Fed monthly calendar."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from html.parser import HTMLParser

from macro_event_telegram_alerts.domain import MacroEvent, TimingPrecision
from macro_event_telegram_alerts.policy import EventSignificance, SignificancePolicy
from macro_event_telegram_alerts.providers.bls_calendar import (
    BLS_INSTITUTION,
    BLS_TIMEZONE,
    BlsEventFamily,
    canonical_bls_source_id,
)

NYFED_INSTITUTION = "Federal Reserve Bank of New York"
NYFED_CALENDAR_URL = "https://www.newyorkfed.org/research/calendars/"
NYFED_SIGNIFICANCE_POLICY = SignificancePolicy(
    significance=EventSignificance.SIGNIFICANT,
    revision="bls-significant-releases-v1",
)


class NewYorkFedCalendarError(ValueError):
    """The approved fallback calendar cannot be normalized safely."""


@dataclass(frozen=True, slots=True)
class _Rule:
    label: str
    family: BlsEventFamily
    source_url: str


_RULES = (
    _Rule(
        "Consumer Price Index",
        BlsEventFamily.CPI,
        "https://www.bls.gov/news.release/cpi.nr0.htm",
    ),
    _Rule(
        "Producer Price Index (PPI)",
        BlsEventFamily.PPI,
        "https://www.bls.gov/news.release/ppi.nr0.htm",
    ),
    _Rule(
        "Employment Situation",
        BlsEventFamily.EMPLOYMENT_SITUATION,
        "https://www.bls.gov/news.release/empsit.nr0.htm",
    ),
    _Rule(
        "JOLTS",
        BlsEventFamily.JOLTS,
        "https://www.bls.gov/news.release/jolts.nr0.htm",
    ),
)


class _MonthlyCalendarParser(HTMLParser):
    """Extract reviewed anchor/time pairs from one NY Fed calendar month."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[tuple[int, _Rule, str]] = []
        self._cell_depth = 0
        self._day: int | None = None
        self._anchor_parts: list[str] | None = None
        self._pending_rule: _Rule | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "td":
            self._cell_depth += 1
            if self._cell_depth == 1:
                self._day = None
                self._pending_rule = None
        elif tag == "a" and self._cell_depth:
            self._anchor_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor_parts is not None:
            label = " ".join("".join(self._anchor_parts).split())
            self._pending_rule = next(
                (rule for rule in _RULES if rule.label == label), None
            )
            self._anchor_parts = None
        elif tag == "td" and self._cell_depth:
            self._cell_depth -= 1
            if self._cell_depth == 0:
                self._day = None
                self._pending_rule = None

    def handle_data(self, data: str) -> None:
        if not self._cell_depth:
            return
        if self._anchor_parts is not None:
            self._anchor_parts.append(data)
            return
        value = " ".join(data.split())
        if not value:
            return
        if self._day is None and value.isdigit() and 1 <= int(value) <= 31:
            self._day = int(value)
            return
        if (
            self._pending_rule is not None
            and self._day is not None
            and len(value) == 7
            and value.startswith("(")
            and value.endswith(")")
        ):
            self.events.append((self._day, self._pending_rule, value[1:-1]))
            self._pending_rule = None


def parse_new_york_fed_bls_calendar(
    text: str,
    retrieved_at: datetime,
    *,
    year: int,
    month: int,
) -> tuple[MacroEvent, ...]:
    """Normalize exact-time BLS events without performing network access."""
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() != UTC.utcoffset(
        retrieved_at
    ):
        raise NewYorkFedCalendarError("retrieved_at must be timezone-aware UTC")
    parser = _MonthlyCalendarParser()
    parser.feed(text)
    parser.close()
    events = tuple(
        _event(day, rule, time_text, retrieved_at, year, month)
        for day, rule, time_text in parser.events
    )
    source_ids = [event.source_id for event in events]
    if len(source_ids) != len(set(source_ids)):
        raise NewYorkFedCalendarError("selected fallback events are duplicated")
    return events


def _event(
    day: int,
    rule: _Rule,
    time_text: str,
    retrieved_at: datetime,
    year: int,
    month: int,
) -> MacroEvent:
    try:
        local = datetime.strptime(
            f"{year:04}-{month:02}-{day:02} {time_text}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=BLS_TIMEZONE)
    except ValueError as error:
        raise NewYorkFedCalendarError(
            "fallback event date or time is invalid"
        ) from error
    scheduled_date = date(year, month, day)
    starts_at_utc = local.astimezone(UTC)
    return MacroEvent(
        source_id=canonical_bls_source_id(rule.family, scheduled_date, starts_at_utc),
        title=rule.family.value,
        institution=BLS_INSTITUTION,
        source_url=rule.source_url,
        scheduled_date=scheduled_date,
        timing_precision=TimingPrecision.EXACT,
        policy=NYFED_SIGNIFICANCE_POLICY,
        retrieved_at=retrieved_at.astimezone(UTC),
        starts_at_local=local,
        starts_at_utc=starts_at_utc,
    )


__all__ = [
    "NYFED_CALENDAR_URL",
    "NYFED_INSTITUTION",
    "NewYorkFedCalendarError",
    "parse_new_york_fed_bls_calendar",
]
