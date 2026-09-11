"""Safe, serializable source status with explicit unknown and stale states."""

from dataclasses import asdict, dataclass
from datetime import datetime

from macro_event_telegram_alerts.providers.cached_http import TransportDiagnostics


@dataclass(frozen=True, slots=True)
class SourceReport:
    """Counts are unknown on failure, not misleadingly zero."""

    source: str
    status: str
    transport: TransportDiagnostics
    cache_age_seconds: float | None
    total_events: int | None
    future_events: int | None
    future_timed_events: int | None
    next_event_at: datetime | None

    def to_dict(self) -> dict[str, object]:
        """Flatten dates and transport fields for JSON and one-line logs."""
        result: dict[str, object] = asdict(self)
        result.pop("transport")
        result.update(asdict(self.transport))
        return {
            key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in result.items()
        }
