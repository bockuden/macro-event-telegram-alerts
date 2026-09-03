"""Respectful, cached transport for the official FOMC meeting calendar."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from macro_event_telegram_alerts.providers.cached_http import (
    CachedDocumentError,
    CachedDocumentTransport,
    Clock,
    HttpGet,
    HttpResult,
)

FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
DEFAULT_MIN_POLL_INTERVAL = timedelta(hours=6)
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class FedTransportError(RuntimeError):
    """The official FOMC calendar could not be retrieved or cached safely."""


@dataclass(frozen=True, slots=True)
class FomcCalendarPayload:
    """Calendar HTML plus provenance about when it was retrieved."""

    text: str
    retrieved_at: datetime
    from_cache: bool


class FomcCalendarTransport:
    """Fetch only the official Federal Reserve FOMC calendar."""

    def __init__(
        self,
        *,
        cache_dir: Path,
        user_agent: str,
        clock: Clock,
        min_poll_interval: timedelta = DEFAULT_MIN_POLL_INTERVAL,
        timeout_seconds: float = 20.0,
        http_get: HttpGet | None = None,
    ) -> None:
        self._transport = CachedDocumentTransport(
            source_name="FOMC calendar",
            url=FOMC_CALENDAR_URL,
            cache_dir=cache_dir,
            document_filename="fomc-calendar.html",
            metadata_filename="fomc-calendar-cache.json",
            user_agent=user_agent,
            clock=clock,
            accept="text/html",
            expected_content_type="text/html",
            min_poll_interval=min_poll_interval,
            max_response_bytes=MAX_RESPONSE_BYTES,
            timeout_seconds=timeout_seconds,
            http_get=http_get,
        )

    def fetch(self) -> FomcCalendarPayload:
        """Return a fresh or conditionally validated official calendar."""
        try:
            payload = self._transport.fetch()
        except CachedDocumentError as error:
            raise FedTransportError(str(error)) from error
        return FomcCalendarPayload(
            text=payload.text,
            retrieved_at=payload.retrieved_at,
            from_cache=payload.from_cache,
        )


__all__ = [
    "FOMC_CALENDAR_URL",
    "FedTransportError",
    "FomcCalendarPayload",
    "FomcCalendarTransport",
    "HttpResult",
]
