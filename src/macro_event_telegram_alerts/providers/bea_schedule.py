"""Normalize significant releases from the official BEA schedule."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from macro_event_telegram_alerts.domain import MacroEvent, TimingPrecision
from macro_event_telegram_alerts.policy import EventSignificance, SignificancePolicy
from macro_event_telegram_alerts.providers.bea_html import (
    BeaScheduleParseError,
    BeaScheduleRow,
    parse_bea_schedule_html,
)
from macro_event_telegram_alerts.providers.bea_transport import (
    BEA_SCHEDULE_URL,
    BeaScheduleTransport,
)

BEA_INSTITUTION = "U.S. Bureau of Economic Analysis"
BEA_TIMEZONE = ZoneInfo("America/New_York")
BEA_SIGNIFICANCE_POLICY = SignificancePolicy(
    significance=EventSignificance.SIGNIFICANT,
    revision="bea-significant-releases-v1",
)


class BeaScheduleError(ValueError):
    """A selected BEA release cannot be normalized safely."""


class BeaEventFamily(StrEnum):
    """Reviewed release families selected for the first BEA adapter."""

    GDP = "Gross Domestic Product (GDP)"
    PERSONAL_INCOME_AND_OUTLAYS = "Personal Income and Outlays (PCE)"


@dataclass(frozen=True, slots=True)
class _AliasRule:
    family: BeaEventFamily
    prefixes: tuple[str, ...]


_ALIAS_RULES = (
    _AliasRule(
        family=BeaEventFamily.GDP,
        prefixes=(
            "GDP (Advance Estimate)",
            "GDP (Second Estimate)",
            "GDP (Third Estimate)",
            "GDP (Updated Estimate)",
            "Gross Domestic Product,",
        ),
    ),
    _AliasRule(
        family=BeaEventFamily.PERSONAL_INCOME_AND_OUTLAYS,
        prefixes=("Personal Income and Outlays,",),
    ),
)


class BeaScheduleProvider:
    """Load and normalize GDP and PCE-family releases from BEA."""

    def __init__(self, transport: BeaScheduleTransport) -> None:
        self._transport = transport

    def load(self) -> tuple[MacroEvent, ...]:
        """Fetch the cached schedule and return reviewed BEA releases."""
        payload = self._transport.fetch()
        return parse_bea_schedule(payload.text, payload.retrieved_at)


def parse_bea_schedule(html: str, retrieved_at: datetime) -> tuple[MacroEvent, ...]:
    """Normalize selected BEA rows without performing network access."""
    _require_utc(retrieved_at)
    try:
        document = parse_bea_schedule_html(html)
        events = tuple(
            event
            for row in document.rows
            if (event := _normalize_row(row, document.year, retrieved_at)) is not None
        )
    except (BeaScheduleParseError, BeaScheduleError) as error:
        if isinstance(error, BeaScheduleError):
            raise
        raise BeaScheduleError(str(error)) from error

    families = {event.title for event in events}
    expected_families = {family.value for family in BeaEventFamily}
    missing_families = expected_families - families
    if missing_families:
        missing = ", ".join(sorted(missing_families))
        raise BeaScheduleError(f"BEA schedule is missing reviewed families: {missing}")

    source_ids = [event.source_id for event in events]
    if len(source_ids) != len(set(source_ids)):
        raise BeaScheduleError("selected BEA releases contain duplicate identities")
    return events


def _normalize_row(
    row: BeaScheduleRow,
    schedule_year: int,
    retrieved_at: datetime,
) -> MacroEvent | None:
    if row.release_kind != "press":
        return None
    rule = _match_alias(row.title)
    if rule is None:
        return None
    if row.release_time is None:
        raise BeaScheduleError(f"{rule.family.value} has no scheduled release time")

    starts_at_local = _parse_eastern_time(
        schedule_year,
        row.release_date,
        row.release_time,
    )
    source_url = _source_url(row.href)
    return MacroEvent(
        source_id=_source_id(rule.family, row.title),
        title=rule.family.value,
        institution=BEA_INSTITUTION,
        source_url=source_url,
        scheduled_date=starts_at_local.date(),
        timing_precision=TimingPrecision.EXACT,
        policy=BEA_SIGNIFICANCE_POLICY,
        retrieved_at=retrieved_at.astimezone(UTC),
        starts_at_local=starts_at_local,
        starts_at_utc=starts_at_local.astimezone(UTC),
    )


def _match_alias(title: str) -> _AliasRule | None:
    normalized_title = _normalized_title(title)
    for rule in _ALIAS_RULES:
        if any(_matches_prefix(normalized_title, prefix) for prefix in rule.prefixes):
            return rule
    return None


def _matches_prefix(normalized_title: str, prefix: str) -> bool:
    normalized_prefix = _normalized_title(prefix)
    if normalized_prefix.endswith(","):
        return normalized_title.startswith(f"{normalized_prefix} ")
    return normalized_title == normalized_prefix or normalized_title.startswith(
        (f"{normalized_prefix}, ", f"{normalized_prefix} and ")
    )


def _normalized_title(value: str) -> str:
    return " ".join(value.split()).casefold()


def _parse_eastern_time(year: int, release_date: str, release_time: str) -> datetime:
    try:
        naive = datetime.strptime(
            f"{year} {release_date} {release_time}",
            "%Y %B %d %I:%M %p",
        )
    except ValueError as error:
        raise BeaScheduleError("BEA release date or time is invalid") from error

    candidates: dict[object, datetime] = {}
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=BEA_TIMEZONE, fold=fold)
        round_trip = candidate.astimezone(UTC).astimezone(BEA_TIMEZONE)
        if round_trip.replace(tzinfo=None) == naive:
            candidates[candidate.utcoffset()] = candidate
    if not candidates:
        raise BeaScheduleError("BEA release uses a nonexistent Eastern time")
    if len(candidates) > 1:
        raise BeaScheduleError("BEA release uses an ambiguous Eastern time")
    return next(iter(candidates.values()))


def _source_url(href: str | None) -> str:
    if href is None:
        return BEA_SCHEDULE_URL
    url = urljoin(BEA_SCHEDULE_URL, href)
    parsed = urlsplit(url)
    hostname = parsed.hostname.casefold() if parsed.hostname else ""
    if parsed.scheme != "https" or not (
        hostname == "bea.gov" or hostname.endswith(".bea.gov")
    ):
        raise BeaScheduleError("BEA release URL must use HTTPS on bea.gov")
    return url


def _source_id(family: BeaEventFamily, source_title: str) -> str:
    identity = _normalized_title(source_title).encode()
    digest = sha256(identity).hexdigest()[:20]
    return f"bea:{family.name.lower()}:{digest}"


def _require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise BeaScheduleError("retrieved_at must be timezone-aware UTC")
    if value.utcoffset() != UTC.utcoffset(value):
        raise BeaScheduleError("retrieved_at must use UTC")
