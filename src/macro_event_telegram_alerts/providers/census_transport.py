"""Cached transport for the official Census economic indicator calendar."""

from datetime import timedelta
from pathlib import Path

from macro_event_telegram_alerts.providers.cached_http import (
    CachedDocumentPayload,
    CachedDocumentTransport,
    Clock,
    HttpGet,
    TransportDiagnostics,
)

CENSUS_CALENDAR_URL = (
    "https://www.census.gov/economic-indicators/calendar-listview.html"
)


class CensusScheduleTransport:
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
        allow_network: bool = True,
        http_get: HttpGet | None = None,
    ) -> None:
        self._transport = CachedDocumentTransport(
            source_name="Census economic indicator calendar",
            url=CENSUS_CALENDAR_URL,
            cache_dir=cache_dir,
            document_filename="census-calendar.html",
            metadata_filename="census-calendar-cache.json",
            user_agent=user_agent,
            clock=clock,
            accept="text/html",
            expected_content_type="text/html",
            min_poll_interval=min_poll_interval,
            max_response_bytes=4 * 1024 * 1024,
            timeout_seconds=20,
            http_get=http_get,
            allow_network=allow_network,
            rejection_cooldown=rejection_cooldown,
            max_retry_backoff=max_retry_backoff,
            max_stale_cache_age=max_stale_cache_age,
        )

    def diagnostics(self) -> TransportDiagnostics:
        return self._transport.diagnostics()

    def fetch(self) -> CachedDocumentPayload:
        return self._transport.fetch()
