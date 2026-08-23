"""Normalized domain types shared by all official-source adapters."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from urllib.parse import urlsplit

from macro_event_telegram_alerts.policy import SignificancePolicy


class TimingPrecision(StrEnum):
    """How precisely an institution has scheduled an event."""

    EXACT = "exact"
    TENTATIVE = "tentative"
    DATE_ONLY = "date_only"
    TBA = "tba"

    @property
    def has_instant(self) -> bool:
        """Whether this precision carries a source-local and UTC instant."""
        return self in {self.EXACT, self.TENTATIVE}


@dataclass(frozen=True, slots=True)
class MacroEvent:
    """An official-source event normalized without inventing timing details."""

    source_id: str
    title: str
    institution: str
    source_url: str
    scheduled_date: date
    timing_precision: TimingPrecision
    policy: SignificancePolicy
    retrieved_at: datetime
    starts_at_local: datetime | None = None
    starts_at_utc: datetime | None = None

    def __post_init__(self) -> None:
        self._validate_text_fields()
        self._validate_source_url()
        self._validate_retrieval_time()
        self._validate_scheduled_time()

    def _validate_text_fields(self) -> None:
        for name in ("source_id", "title", "institution"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")

    def _validate_source_url(self) -> None:
        parsed = urlsplit(self.source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source_url must be an absolute HTTP(S) URL")

    def _validate_retrieval_time(self) -> None:
        _require_aware(self.retrieved_at, "retrieved_at")
        _require_utc(self.retrieved_at, "retrieved_at")

    def _validate_scheduled_time(self) -> None:
        has_local = self.starts_at_local is not None
        has_utc = self.starts_at_utc is not None

        if has_local != has_utc:
            raise ValueError(
                "starts_at_local and starts_at_utc must be provided together"
            )
        if self.timing_precision.has_instant != has_local:
            raise ValueError(
                f"{self.timing_precision.value} timing precision has an invalid instant"
            )
        if not has_local:
            return

        assert self.starts_at_local is not None
        assert self.starts_at_utc is not None
        _require_aware(self.starts_at_local, "starts_at_local")
        _require_aware(self.starts_at_utc, "starts_at_utc")
        _require_utc(self.starts_at_utc, "starts_at_utc")

        if self.starts_at_local.date() != self.scheduled_date:
            raise ValueError("scheduled_date must match the source-local date")
        normalized_utc = self.starts_at_local.astimezone(UTC)
        if normalized_utc != self.starts_at_utc:
            raise ValueError(
                "source-local and UTC timestamps must represent one instant"
            )


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_utc(value: datetime, field_name: str) -> None:
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must use UTC")
