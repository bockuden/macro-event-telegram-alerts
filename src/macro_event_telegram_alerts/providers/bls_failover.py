"""Explicit BLS primary/fallback selection with safe active-source diagnostics."""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Protocol

from macro_event_telegram_alerts.domain import MacroEvent
from macro_event_telegram_alerts.providers.cached_http import (
    CachedDocumentError,
    TransportDiagnostics,
)
from macro_event_telegram_alerts.providers.nyfed_bls_calendar import (
    parse_new_york_fed_bls_calendar,
)
from macro_event_telegram_alerts.providers.nyfed_transport import (
    NewYorkFedCalendarTransport,
)


class _EventProvider(Protocol):
    def load(self) -> tuple[MacroEvent, ...]: ...


class NewYorkFedBlsFallbackProvider:
    """Normalize the approved fallback while preserving BLS event identity."""

    def __init__(self, transport: NewYorkFedCalendarTransport) -> None:
        self._transport = transport

    def load(self) -> tuple[MacroEvent, ...]:
        events = tuple(
            event
            for payload in self._transport.fetch()
            for event in parse_new_york_fed_bls_calendar(
                payload.text,
                payload.retrieved_at,
                year=payload.year,
                month=payload.month,
            )
        )
        source_ids = [event.source_id for event in events]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("fallback BLS event identities are duplicated")
        return events


@dataclass(slots=True)
class FailoverBlsProvider:
    """Prefer BLS ICS and use the approved calendar only after primary failure."""

    primary: _EventProvider
    primary_diagnostics: Callable[[], TransportDiagnostics]
    fallback: _EventProvider
    fallback_diagnostics: Callable[[], TransportDiagnostics]
    _diagnostics: TransportDiagnostics = field(
        default_factory=lambda: TransportDiagnostics(active_source="bls_ics")
    )

    def load(self) -> tuple[MacroEvent, ...]:
        try:
            events = self.primary.load()
        except (CachedDocumentError, ValueError) as primary_error:
            primary_diagnostic = self.primary_diagnostics()
            try:
                events = self.fallback.load()
            except (CachedDocumentError, ValueError) as fallback_error:
                if isinstance(fallback_error, CachedDocumentError):
                    raise fallback_error from primary_error
                raise
            fallback_diagnostic = self.fallback_diagnostics()
            self._diagnostics = replace(
                fallback_diagnostic,
                active_source="new_york_fed",
                category=(
                    primary_error.category
                    if isinstance(primary_error, CachedDocumentError)
                    else primary_diagnostic.category
                ),
                http_status=(
                    primary_error.http_status
                    if isinstance(primary_error, CachedDocumentError)
                    else primary_diagnostic.http_status
                ),
            )
            return events
        self._diagnostics = replace(self.primary_diagnostics(), active_source="bls_ics")
        return events

    def diagnostics(self) -> TransportDiagnostics:
        return self._diagnostics
