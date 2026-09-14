"""Cached retrieval of the public New York Fed economic indicators calendar."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

from macro_event_telegram_alerts.providers.cached_http import (
    CachedDocumentError,
    CachedDocumentTransport,
    Clock,
    HttpGet,
    TransportDiagnostics,
)

NYFED_CALENDAR_URL = (
    "https://www.newyorkfed.org/research/calendars/i-{month}{year}.html"
)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class NewYorkFedCalendarPayload:
    """One monthly calendar and enough context to interpret its day numbers."""

    text: str
    retrieved_at: datetime
    year: int
    month: int


class NewYorkFedCalendarTransport:
    """Fetch the current and next monthly pages with independent durable caches."""

    def __init__(
        self,
        *,
        cache_dir: Path,
        user_agent: str,
        clock: Clock,
        min_poll_interval: timedelta,
        rejection_cooldown: timedelta,
        max_retry_backoff: timedelta,
        max_stale_cache_age: timedelta,
        timeout_seconds: float = 20.0,
        http_get: HttpGet | None = None,
        allow_network: bool = True,
    ) -> None:
        self._cache_dir = cache_dir
        self._user_agent = user_agent
        self._clock = clock
        self._min_poll_interval = min_poll_interval
        self._rejection_cooldown = rejection_cooldown
        self._max_retry_backoff = max_retry_backoff
        self._max_stale_cache_age = max_stale_cache_age
        self._timeout_seconds = timeout_seconds
        self._http_get = http_get
        self._allow_network = allow_network
        self._transports: dict[tuple[int, int], CachedDocumentTransport] = {}
        self._diagnostics = TransportDiagnostics(active_source="new_york_fed")

    def diagnostics(self) -> TransportDiagnostics:
        """Return the last safe retrieval state without performing I/O."""
        return self._diagnostics

    def fetch(self) -> tuple[NewYorkFedCalendarPayload, ...]:
        """Load both months so a 24-hour reminder can cross a month boundary."""
        now = self._clock()
        current = (now.year, now.month)
        following = _next_month(*current)
        payloads: list[NewYorkFedCalendarPayload] = []
        for year, month in (current, following):
            transport = self._transport(year, month)
            try:
                payload = transport.fetch()
            except CachedDocumentError:
                self._diagnostics = replace(
                    transport.diagnostics(), active_source="new_york_fed"
                )
                raise
            self._diagnostics = replace(
                transport.diagnostics(), active_source="new_york_fed"
            )
            payloads.append(
                NewYorkFedCalendarPayload(
                    payload.text, payload.retrieved_at, year, month
                )
            )
        return tuple(payloads)

    def _transport(self, year: int, month: int) -> CachedDocumentTransport:
        key = (year, month)
        if key not in self._transports:
            month_name = (
                "jan",
                "feb",
                "mar",
                "apr",
                "may",
                "jun",
                "jul",
                "aug",
                "sep",
                "oct",
                "nov",
                "dec",
            )[month - 1]
            self._transports[key] = CachedDocumentTransport(
                source_name="New York Fed economic indicators calendar",
                url=NYFED_CALENDAR_URL.format(month=month_name, year=str(year)[2:]),
                cache_dir=self._cache_dir / f"{year:04}-{month:02}",
                document_filename="calendar.html",
                metadata_filename="calendar-cache.json",
                user_agent=self._user_agent,
                clock=self._clock,
                accept="text/html",
                expected_content_type="text/html",
                min_poll_interval=self._min_poll_interval,
                max_response_bytes=MAX_RESPONSE_BYTES,
                timeout_seconds=self._timeout_seconds,
                http_get=self._http_get,
                allow_network=self._allow_network,
                rejection_cooldown=self._rejection_cooldown,
                max_retry_backoff=self._max_retry_backoff,
                max_stale_cache_age=self._max_stale_cache_age,
            )
        return self._transports[key]


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)
