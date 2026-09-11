"""Source assembly and one-loop application orchestration."""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol

from macro_event_telegram_alerts.app_config import AppConfig, SourceName
from macro_event_telegram_alerts.delivery_ledger import ReminderLedger
from macro_event_telegram_alerts.domain import MacroEvent
from macro_event_telegram_alerts.health import HealthReporter
from macro_event_telegram_alerts.providers.bea_schedule import BeaScheduleProvider
from macro_event_telegram_alerts.providers.bea_transport import BeaScheduleTransport
from macro_event_telegram_alerts.providers.bls_calendar import BlsCalendarProvider
from macro_event_telegram_alerts.providers.bls_transport import BlsCalendarTransport
from macro_event_telegram_alerts.providers.cached_http import (
    CachedDocumentError,
    FailureCategory,
    TransportDiagnostics,
)
from macro_event_telegram_alerts.providers.fed_transport import FomcCalendarTransport
from macro_event_telegram_alerts.providers.fomc_calendar import FomcCalendarProvider
from macro_event_telegram_alerts.reminder_service import (
    ReminderRunResult,
    ReminderService,
)
from macro_event_telegram_alerts.reminders import Reminder
from macro_event_telegram_alerts.source_diagnostics import SourceReport

type Clock = Callable[[], datetime]
type DeliverReminder = Callable[[Reminder], None]
type Sleep = Callable[[float], None]
type StopRequested = Callable[[], bool]


LOGGER = logging.getLogger(__name__)


class EventProvider(Protocol):
    """One official source adapter available to the application loop."""

    def load(self) -> tuple[MacroEvent, ...]:
        """Load normalized events from one source."""


@dataclass(frozen=True, slots=True)
class NamedProvider:
    """An adapter paired with its safe diagnostic name."""

    name: SourceName
    provider: EventProvider
    diagnostics: Callable[[], TransportDiagnostics] | None = None


@dataclass(frozen=True, slots=True)
class ApplicationRunResult:
    """Secret-safe facts about one completed application loop."""

    loaded_events: int
    failed_sources: tuple[SourceName, ...]
    reminder_result: ReminderRunResult


class ApplicationRunner:
    """Run all sources independently and pass healthy events to reminders."""

    def __init__(
        self,
        providers: Iterable[NamedProvider],
        reminder_service: ReminderService,
        health_reporter: HealthReporter | None = None,
    ) -> None:
        self._providers = tuple(providers)
        self._reminder_service = reminder_service
        self._health_reporter = health_reporter

    def run_once(
        self,
        now: datetime,
        deliver: DeliverReminder,
    ) -> ApplicationRunResult:
        """Load healthy sources even if another source fails."""
        now_utc = _require_utc(now)
        events: list[MacroEvent] = []
        failures: list[SourceName] = []
        for named_provider in self._providers:
            source_events, report = inspect_source(named_provider, now_utc)
            if report.status != "healthy":
                failures.append(named_provider.name)
            events.extend(source_events)
            log = LOGGER.warning if report.status != "healthy" else LOGGER.info
            log(
                "Official source status: %s",
                " ".join(f"{key}={value}" for key, value in report.to_dict().items()),
            )
        reminder_result = self._reminder_service.run(events, now_utc, deliver)
        result = ApplicationRunResult(
            loaded_events=len(events),
            failed_sources=tuple(failures),
            reminder_result=reminder_result,
        )
        if (
            self._health_reporter is not None
            and not result.failed_sources
            and not result.reminder_result.failed
        ):
            self._health_reporter.record_success(now_utc)
        LOGGER.info(
            "Application loop completed: loaded_events=%s failed_sources=%s "
            "delivered_reminders=%s failed_reminders=%s",
            result.loaded_events,
            len(result.failed_sources),
            len(result.reminder_result.delivered),
            len(result.reminder_result.failed),
        )
        return result

    def run_until_stopped(
        self,
        *,
        clock: Clock,
        deliver: DeliverReminder,
        loop_interval_seconds: float,
        sleep: Sleep,
        stop_requested: StopRequested,
    ) -> tuple[ApplicationRunResult, ...]:
        """Run service loops until a caller requests a graceful stop."""
        if loop_interval_seconds <= 0:
            raise ValueError("loop_interval_seconds must be positive")
        results: list[ApplicationRunResult] = []
        while not stop_requested():
            results.append(self.run_once(clock(), deliver))
            if not stop_requested():
                sleep(loop_interval_seconds)
        return tuple(results)


def inspect_source(
    named: NamedProvider, now: datetime
) -> tuple[tuple[MacroEvent, ...], SourceReport]:
    """Load one source without constructing a reminder ledger or notifier."""
    now = _require_utc(now)
    error_category: FailureCategory | None = None
    http_status: int | None = None
    try:
        events = named.provider.load()
    except CachedDocumentError as error:
        error_category, http_status = error.category, error.http_status
        events = ()
    except ValueError:
        error_category = FailureCategory.PARSE
        events = ()
    except Exception:
        error_category = FailureCategory.UNKNOWN
        events = ()
    diagnostic = named.diagnostics() if named.diagnostics else TransportDiagnostics()
    if error_category is not None:
        diagnostic = replace(
            diagnostic,
            category=error_category,
            http_status=http_status
            if http_status is not None
            else diagnostic.http_status,
        )
    failed = error_category is not None
    future = [
        event
        for event in events
        if (event.starts_at_utc is not None and event.starts_at_utc > now)
        or (event.starts_at_utc is None and event.scheduled_date >= now.date())
    ]
    timed = [event.starts_at_utc for event in future if event.starts_at_utc is not None]
    return events, SourceReport(
        source=named.name.value,
        status="failed"
        if failed
        else "degraded"
        if diagnostic.stale or diagnostic.category
        else "healthy",
        transport=diagnostic,
        cache_age_seconds=(
            max(0.0, (now - diagnostic.retrieved_at).total_seconds())
            if diagnostic.retrieved_at
            else None
        ),
        total_events=None if failed else len(events),
        future_events=None if failed else len(future),
        future_timed_events=None if failed else len(timed),
        next_event_at=min(timed) if timed else None,
    )


def build_official_providers(
    config: AppConfig, *, clock: Clock, allow_network: bool = True
) -> tuple[NamedProvider, ...]:
    """Build configured official-source adapters without fetching their data."""
    user_agent = "macro-event-telegram-alerts/0.1.0 (+https://github.com/bockuden/macro-event-telegram-alerts)"
    providers: list[NamedProvider] = []
    for source in config.sources:
        cache_dir = config.cache_dir / source.value
        if source is SourceName.BLS:
            bls_transport = BlsCalendarTransport(
                cache_dir=cache_dir,
                user_agent=user_agent,
                clock=clock,
                min_poll_interval=config.source_poll_interval,
                rejection_cooldown=config.source_rejection_cooldown,
                max_retry_backoff=config.source_retry_max_backoff,
                max_stale_cache_age=config.source_max_stale_cache_age,
                allow_network=allow_network,
            )
            providers.append(
                NamedProvider(
                    source,
                    BlsCalendarProvider(bls_transport),
                    bls_transport.diagnostics,
                )
            )
        elif source is SourceName.BEA:
            bea_transport = BeaScheduleTransport(
                cache_dir=cache_dir,
                user_agent=user_agent,
                clock=clock,
                min_poll_interval=config.source_poll_interval,
                rejection_cooldown=config.source_rejection_cooldown,
                max_retry_backoff=config.source_retry_max_backoff,
                max_stale_cache_age=config.source_max_stale_cache_age,
                allow_network=allow_network,
            )
            providers.append(
                NamedProvider(
                    source,
                    BeaScheduleProvider(bea_transport),
                    bea_transport.diagnostics,
                )
            )
        elif source is SourceName.FOMC:
            fomc_transport = FomcCalendarTransport(
                cache_dir=cache_dir,
                user_agent=user_agent,
                clock=clock,
                min_poll_interval=config.source_poll_interval,
                rejection_cooldown=config.source_rejection_cooldown,
                max_retry_backoff=config.source_retry_max_backoff,
                max_stale_cache_age=config.source_max_stale_cache_age,
                allow_network=allow_network,
            )
            providers.append(
                NamedProvider(
                    source,
                    FomcCalendarProvider(fomc_transport),
                    fomc_transport.diagnostics,
                )
            )
    return tuple(providers)


def build_runner(config: AppConfig, *, clock: Clock) -> ApplicationRunner:
    """Construct a durable application runner without loading sources yet."""
    return ApplicationRunner(
        build_official_providers(config, clock=clock),
        ReminderService(config.reminder_policy, ReminderLedger(config.ledger_path)),
        HealthReporter(config.health_path),
    )


def utc_now() -> datetime:
    """Return the current application clock time in UTC."""
    return datetime.now(UTC)


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("now must use UTC")
    return value.astimezone(UTC)
