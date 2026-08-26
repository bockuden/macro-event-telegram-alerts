"""Normalize significant releases from the official BLS iCalendar feed."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from macro_event_telegram_alerts.domain import MacroEvent, TimingPrecision
from macro_event_telegram_alerts.policy import EventSignificance, SignificancePolicy
from macro_event_telegram_alerts.providers.bls_transport import BlsCalendarTransport
from macro_event_telegram_alerts.providers.icalendar import (
    CalendarEvent,
    CalendarProperty,
    ICalendarParseError,
    parse_icalendar,
    unescape_text,
)

BLS_INSTITUTION = "U.S. Bureau of Labor Statistics"
BLS_TIMEZONE = ZoneInfo("America/New_York")
BLS_SIGNIFICANCE_POLICY = SignificancePolicy(
    significance=EventSignificance.SIGNIFICANT,
    revision="bls-significant-releases-v1",
)


class BlsCalendarError(ValueError):
    """A selected BLS event cannot be normalized safely."""


class BlsEventFamily(StrEnum):
    """Reviewed release families selected for the first BLS adapter."""

    CPI = "Consumer Price Index"
    EMPLOYMENT_SITUATION = "Employment Situation"
    PPI = "Producer Price Index"
    JOLTS = "Job Openings and Labor Turnover Survey"


@dataclass(frozen=True, slots=True)
class _AliasRule:
    family: BlsEventFamily
    aliases: tuple[str, ...]
    source_url: str


_ALIAS_RULES = (
    _AliasRule(
        family=BlsEventFamily.CPI,
        aliases=("Consumer Price Index",),
        source_url="https://www.bls.gov/news.release/cpi.nr0.htm",
    ),
    _AliasRule(
        family=BlsEventFamily.EMPLOYMENT_SITUATION,
        aliases=("Employment Situation",),
        source_url="https://www.bls.gov/news.release/empsit.nr0.htm",
    ),
    _AliasRule(
        family=BlsEventFamily.PPI,
        aliases=("Producer Price Index", "Producer Price Indexes"),
        source_url="https://www.bls.gov/news.release/ppi.nr0.htm",
    ),
    _AliasRule(
        family=BlsEventFamily.JOLTS,
        aliases=(
            "Job Openings and Labor Turnover Survey",
            "Job Openings and Labor Turnover",
        ),
        source_url="https://www.bls.gov/news.release/jolts.nr0.htm",
    ),
)


class BlsCalendarProvider:
    """Load and normalize the reviewed subset of the official BLS calendar."""

    def __init__(self, transport: BlsCalendarTransport) -> None:
        self._transport = transport

    def load(self) -> tuple[MacroEvent, ...]:
        """Fetch the cached calendar and return significant BLS releases."""
        payload = self._transport.fetch()
        return parse_bls_calendar(payload.text, payload.retrieved_at)


def parse_bls_calendar(text: str, retrieved_at: datetime) -> tuple[MacroEvent, ...]:
    """Normalize selected events without performing network access."""
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise BlsCalendarError("retrieved_at must be timezone-aware UTC")
    if retrieved_at.utcoffset() != UTC.utcoffset(retrieved_at):
        raise BlsCalendarError("retrieved_at must use UTC")

    try:
        calendar_events = parse_icalendar(text)
        normalized = tuple(
            event
            for calendar_event in calendar_events
            if (event := _normalize_event(calendar_event, retrieved_at)) is not None
        )
    except (ICalendarParseError, ValueError) as error:
        if isinstance(error, BlsCalendarError):
            raise
        raise BlsCalendarError(str(error)) from error

    source_ids = [event.source_id for event in normalized]
    if len(source_ids) != len(set(source_ids)):
        raise BlsCalendarError("selected BLS events contain duplicate UIDs")
    return normalized


def _normalize_event(
    event: CalendarEvent,
    retrieved_at: datetime,
) -> MacroEvent | None:
    summary = unescape_text(event.require_one("SUMMARY").value).strip()
    rule = _match_alias(summary)
    if rule is None:
        return None

    uid = event.require_one("UID").value.strip()
    if not uid:
        raise BlsCalendarError(f"{rule.family.value} has an empty UID")
    scheduled_date, starts_at_local, starts_at_utc, precision = _parse_start(
        event.require_one("DTSTART")
    )
    source_url = _event_source_url(event.optional_one("URL"), rule.source_url)

    return MacroEvent(
        source_id=f"bls:{uid}",
        title=rule.family.value,
        institution=BLS_INSTITUTION,
        source_url=source_url,
        scheduled_date=scheduled_date,
        timing_precision=precision,
        policy=BLS_SIGNIFICANCE_POLICY,
        retrieved_at=retrieved_at.astimezone(UTC),
        starts_at_local=starts_at_local,
        starts_at_utc=starts_at_utc,
    )


def _match_alias(summary: str) -> _AliasRule | None:
    normalized_summary = _normalized_alias(summary)
    for rule in _ALIAS_RULES:
        if normalized_summary in {_normalized_alias(alias) for alias in rule.aliases}:
            return rule
    return None


def _normalized_alias(value: str) -> str:
    return " ".join(value.split()).casefold()


def _parse_start(
    prop: CalendarProperty,
) -> tuple[date, datetime | None, datetime | None, TimingPrecision]:
    value_type = prop.parameter("VALUE")
    timezone_id = prop.parameter("TZID")

    if value_type == "DATE":
        if timezone_id is not None:
            raise BlsCalendarError("date-only DTSTART must not include TZID")
        try:
            scheduled_date = datetime.strptime(prop.value, "%Y%m%d").date()
        except ValueError as error:
            raise BlsCalendarError("BLS DTSTART date is invalid") from error
        return scheduled_date, None, None, TimingPrecision.DATE_ONLY

    if value_type not in {None, "DATE-TIME"}:
        raise BlsCalendarError(f"unsupported BLS DTSTART VALUE: {value_type}")

    if prop.value.endswith("Z"):
        if timezone_id is not None:
            raise BlsCalendarError("UTC DTSTART must not include TZID")
        try:
            starts_at_utc = datetime.strptime(prop.value, "%Y%m%dT%H%M%SZ").replace(
                tzinfo=UTC
            )
        except ValueError as error:
            raise BlsCalendarError("BLS UTC DTSTART is invalid") from error
        starts_at_local = starts_at_utc.astimezone(BLS_TIMEZONE)
    else:
        if timezone_id not in {None, BLS_TIMEZONE.key}:
            raise BlsCalendarError(f"unsupported BLS DTSTART timezone: {timezone_id}")
        try:
            naive = datetime.strptime(prop.value, "%Y%m%dT%H%M%S")
        except ValueError as error:
            raise BlsCalendarError("BLS local DTSTART is invalid") from error
        starts_at_local = _strict_eastern_time(naive)
        starts_at_utc = starts_at_local.astimezone(UTC)

    return (
        starts_at_local.date(),
        starts_at_local,
        starts_at_utc,
        TimingPrecision.EXACT,
    )


def _strict_eastern_time(value: datetime) -> datetime:
    candidates: dict[object, datetime] = {}
    for fold in (0, 1):
        candidate = value.replace(tzinfo=BLS_TIMEZONE, fold=fold)
        round_trip = candidate.astimezone(UTC).astimezone(BLS_TIMEZONE)
        if round_trip.replace(tzinfo=None) == value:
            candidates[candidate.utcoffset()] = candidate
    if not candidates:
        raise BlsCalendarError("BLS DTSTART is a nonexistent Eastern time")
    if len(candidates) > 1:
        raise BlsCalendarError("BLS DTSTART is an ambiguous Eastern time")
    return next(iter(candidates.values()))


def _event_source_url(prop: CalendarProperty | None, fallback: str) -> str:
    if prop is None:
        return fallback
    url = prop.value.strip()
    parsed = urlsplit(url)
    hostname = parsed.hostname.casefold() if parsed.hostname else ""
    if parsed.scheme != "https" or not (
        hostname == "bls.gov" or hostname.endswith(".bls.gov")
    ):
        raise BlsCalendarError("BLS event URL must use HTTPS on bls.gov")
    return url
