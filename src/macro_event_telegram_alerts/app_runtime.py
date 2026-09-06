"""Source assembly and one-loop application orchestration."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from macro_event_telegram_alerts.app_config import AppConfig, SourceName
from macro_event_telegram_alerts.delivery_ledger import ReminderLedger
from macro_event_telegram_alerts.domain import MacroEvent
from macro_event_telegram_alerts.providers.bea_schedule import BeaScheduleProvider
from macro_event_telegram_alerts.providers.bea_transport import BeaScheduleTransport
from macro_event_telegram_alerts.providers.bls_calendar import BlsCalendarProvider
from macro_event_telegram_alerts.providers.bls_transport import BlsCalendarTransport
from macro_event_telegram_alerts.providers.fed_transport import FomcCalendarTransport
from macro_event_telegram_alerts.providers.fomc_calendar import FomcCalendarProvider
from macro_event_telegram_alerts.reminder_service import (
    ReminderRunResult,
    ReminderService,
)
from macro_event_telegram_alerts.reminders import Reminder

type Clock = Callable[[], datetime]
type DeliverReminder = Callable[[Reminder], None]
type Sleep = Callable[[float], None]
type StopRequested = Callable[[], bool]


class EventProvider(Protocol):
    """One official source adapter available to the application loop."""

    def load(self) -> tuple[MacroEvent, ...]:
        """Load normalized events from one source."""


@dataclass(frozen=True, slots=True)
class NamedProvider:
    """An adapter paired with its safe diagnostic name."""

    name: SourceName
    provider: EventProvider


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
    ) -> None:
        self._providers = tuple(providers)
        self._reminder_service = reminder_service

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
            try:
                events.extend(named_provider.provider.load())
            except Exception:
                failures.append(named_provider.name)
        reminder_result = self._reminder_service.run(events, now_utc, deliver)
        return ApplicationRunResult(
            loaded_events=len(events),
            failed_sources=tuple(failures),
            reminder_result=reminder_result,
        )

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


def build_official_providers(
    config: AppConfig, *, clock: Clock
) -> tuple[NamedProvider, ...]:
    """Build configured official-source adapters without fetching their data."""
    user_agent = "macro-event-telegram-alerts/0.0.0 (+https://github.com/bockuden/macro-event-telegram-alerts)"
    providers: list[NamedProvider] = []
    for source in config.sources:
        cache_dir = config.cache_dir / source.value
        if source is SourceName.BLS:
            providers.append(
                NamedProvider(
                    source,
                    BlsCalendarProvider(
                        BlsCalendarTransport(
                            cache_dir=cache_dir,
                            user_agent=user_agent,
                            clock=clock,
                            min_poll_interval=config.source_poll_interval,
                        )
                    ),
                )
            )
        elif source is SourceName.BEA:
            providers.append(
                NamedProvider(
                    source,
                    BeaScheduleProvider(
                        BeaScheduleTransport(
                            cache_dir=cache_dir,
                            user_agent=user_agent,
                            clock=clock,
                            min_poll_interval=config.source_poll_interval,
                        )
                    ),
                )
            )
        elif source is SourceName.FOMC:
            providers.append(
                NamedProvider(
                    source,
                    FomcCalendarProvider(
                        FomcCalendarTransport(
                            cache_dir=cache_dir,
                            user_agent=user_agent,
                            clock=clock,
                            min_poll_interval=config.source_poll_interval,
                        )
                    ),
                )
            )
    return tuple(providers)


def build_runner(config: AppConfig, *, clock: Clock) -> ApplicationRunner:
    """Construct a durable application runner without loading sources yet."""
    return ApplicationRunner(
        build_official_providers(config, clock=clock),
        ReminderService(config.reminder_policy, ReminderLedger(config.ledger_path)),
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
