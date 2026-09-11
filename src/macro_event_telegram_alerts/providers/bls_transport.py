"""Respectful, cached transport for the official BLS iCalendar feed."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from macro_event_telegram_alerts.providers.cached_http import (
    CachedDocumentError,
    CachedDocumentTransport,
    Clock,
    HttpGet,
    HttpResult,
    TransportDiagnostics,
)

BLS_CALENDAR_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
DEFAULT_MIN_POLL_INTERVAL = timedelta(hours=6)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class BlsTransportError(CachedDocumentError):
    """The official BLS calendar could not be retrieved or cached safely."""


@dataclass(frozen=True, slots=True)
class BlsCalendarPayload:
    """Calendar text plus provenance about when it was retrieved."""

    text: str
    retrieved_at: datetime
    from_cache: bool


class BlsCalendarTransport:
    """Fetch only the official BLS ICS feed with conditional requests."""

    def __init__(
        self,
        *,
        cache_dir: Path,
        user_agent: str,
        clock: Clock,
        min_poll_interval: timedelta = DEFAULT_MIN_POLL_INTERVAL,
        timeout_seconds: float = 20.0,
        http_get: HttpGet | None = None,
        allow_network: bool = True,
    ) -> None:
        self._transport = CachedDocumentTransport(
            source_name="BLS calendar",
            url=BLS_CALENDAR_URL,
            cache_dir=cache_dir,
            document_filename="bls.ics",
            metadata_filename="bls-cache.json",
            user_agent=user_agent,
            clock=clock,
            accept="text/calendar",
            expected_content_type="text/calendar",
            min_poll_interval=min_poll_interval,
            max_response_bytes=MAX_RESPONSE_BYTES,
            timeout_seconds=timeout_seconds,
            http_get=http_get,
            allow_network=allow_network,
        )

    def diagnostics(self) -> TransportDiagnostics:
        """Return the shared transport's safe diagnostics."""
        return self._transport.diagnostics()

    def fetch(self) -> BlsCalendarPayload:
        """Return a fresh or conditionally validated official calendar."""
        try:
            payload = self._transport.fetch()
        except CachedDocumentError as error:
            raise BlsTransportError(
                str(error), category=error.category, http_status=error.http_status
            ) from error
        return BlsCalendarPayload(
            text=payload.text,
            retrieved_at=payload.retrieved_at,
            from_cache=payload.from_cache,
        )


__all__ = [
    "BLS_CALENDAR_URL",
    "BlsCalendarPayload",
    "BlsCalendarTransport",
    "BlsTransportError",
    "HttpResult",
]
