"""Respectful, cached transport for the official BEA release schedule."""

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

BEA_SCHEDULE_URL = "https://www.bea.gov/news/schedule/full"
DEFAULT_MIN_POLL_INTERVAL = timedelta(hours=6)
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class BeaTransportError(CachedDocumentError):
    """The official BEA schedule could not be retrieved or cached safely."""


@dataclass(frozen=True, slots=True)
class BeaSchedulePayload:
    """Schedule HTML plus provenance about when it was retrieved."""

    text: str
    retrieved_at: datetime
    from_cache: bool


class BeaScheduleTransport:
    """Fetch only the official BEA full schedule with conditional requests."""

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
            source_name="BEA schedule",
            url=BEA_SCHEDULE_URL,
            cache_dir=cache_dir,
            document_filename="bea-schedule.html",
            metadata_filename="bea-schedule-cache.json",
            user_agent=user_agent,
            clock=clock,
            accept="text/html",
            expected_content_type="text/html",
            min_poll_interval=min_poll_interval,
            max_response_bytes=MAX_RESPONSE_BYTES,
            timeout_seconds=timeout_seconds,
            http_get=http_get,
            allow_network=allow_network,
        )

    def diagnostics(self) -> TransportDiagnostics:
        """Return the shared transport's safe diagnostics."""
        return self._transport.diagnostics()

    def fetch(self) -> BeaSchedulePayload:
        """Return a fresh or conditionally validated official schedule."""
        try:
            payload = self._transport.fetch()
        except CachedDocumentError as error:
            raise BeaTransportError(
                str(error), category=error.category, http_status=error.http_status
            ) from error
        return BeaSchedulePayload(
            text=payload.text,
            retrieved_at=payload.retrieved_at,
            from_cache=payload.from_cache,
        )


__all__ = [
    "BEA_SCHEDULE_URL",
    "BeaSchedulePayload",
    "BeaScheduleTransport",
    "BeaTransportError",
    "HttpResult",
]
