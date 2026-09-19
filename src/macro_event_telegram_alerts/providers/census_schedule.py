"""Normalize Advance Monthly Retail Sales from the official Census calendar."""

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from macro_event_telegram_alerts.domain import MacroEvent, TimingPrecision
from macro_event_telegram_alerts.policy import EventSignificance, SignificancePolicy
from macro_event_telegram_alerts.providers.census_transport import (
    CENSUS_CALENDAR_URL,
    CensusScheduleTransport,
)

CENSUS_INSTITUTION = "U.S. Census Bureau"
CENSUS_TIMEZONE = ZoneInfo("America/New_York")
CENSUS_SIGNIFICANCE_POLICY = SignificancePolicy(
    EventSignificance.SIGNIFICANT, "census-retail-v1"
)


class CensusScheduleProvider:
    def __init__(self, transport: CensusScheduleTransport) -> None:
        self._transport = transport

    def load(self) -> tuple[MacroEvent, ...]:
        payload = self._transport.fetch()
        return parse_census_schedule(payload.text, payload.retrieved_at)


def parse_census_schedule(html: str, retrieved_at: datetime) -> tuple[MacroEvent, ...]:
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() != UTC.utcoffset(
        retrieved_at
    ):
        raise ValueError("retrieved_at must use UTC")
    events: list[MacroEvent] = []
    pattern = re.compile(
        r"Advance Monthly Sales for Retail and Food Services.*?"
        r"(?P<date>[A-Z][a-z]+ \d{1,2}, \d{4}).*?"
        r"(?P<time>\d{1,2}:\d{2} [AP]M)",
        re.I | re.S,
    )
    for match in pattern.finditer(html):
        try:
            local = datetime.strptime(
                f"{match.group('date')} {match.group('time')}", "%B %d, %Y %I:%M %p"
            ).replace(tzinfo=CENSUS_TIMEZONE)
        except ValueError as error:
            raise ValueError("Census release date or time is invalid") from error
        events.append(
            MacroEvent(
                source_id=f"census:retail:{local.date().isoformat()}",
                title="Advance Monthly Sales for Retail and Food Services",
                institution=CENSUS_INSTITUTION,
                source_url=CENSUS_CALENDAR_URL,
                scheduled_date=local.date(),
                timing_precision=TimingPrecision.EXACT,
                policy=CENSUS_SIGNIFICANCE_POLICY,
                retrieved_at=retrieved_at.astimezone(UTC),
                starts_at_local=local,
                starts_at_utc=local.astimezone(UTC),
            )
        )
    if not events:
        raise ValueError("Census calendar contains no reviewed retail releases")
    return tuple(dict((event.source_id, event) for event in events).values())
