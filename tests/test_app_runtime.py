"""Offline tests for independent-source application orchestration."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from macro_event_telegram_alerts import (
    EventSignificance,
    MacroEvent,
    SignificancePolicy,
    TimingPrecision,
)
from macro_event_telegram_alerts.app_config import SourceName
from macro_event_telegram_alerts.app_runtime import ApplicationRunner, NamedProvider
from macro_event_telegram_alerts.delivery_ledger import ReminderLedger
from macro_event_telegram_alerts.health import HealthReporter
from macro_event_telegram_alerts.reminder_service import ReminderService
from macro_event_telegram_alerts.reminders import ReminderPolicy


class _Provider:
    def __init__(
        self, events: tuple[MacroEvent, ...] = (), *, fails: bool = False
    ) -> None:
        self.events = events
        self.fails = fails

    def load(self) -> tuple[MacroEvent, ...]:
        if self.fails:
            raise RuntimeError("source test failure")
        return self.events


def _event() -> MacroEvent:
    starts_at_utc = datetime(2026, 9, 15, 12, 30, tzinfo=UTC)
    return MacroEvent(
        source_id="bls:cpi:2026-09-15",
        title="Consumer Price Index",
        institution="U.S. Bureau of Labor Statistics",
        source_url="https://www.bls.gov/news.release/cpi.nr0.htm",
        scheduled_date=date(2026, 9, 15),
        timing_precision=TimingPrecision.EXACT,
        policy=SignificancePolicy(EventSignificance.SIGNIFICANT, "test-v1"),
        retrieved_at=datetime(2026, 9, 1, 12, tzinfo=UTC),
        starts_at_local=starts_at_utc.astimezone(ZoneInfo("America/New_York")),
        starts_at_utc=starts_at_utc,
    )


def _runner(tmp_path: Path, providers: list[NamedProvider]) -> ApplicationRunner:
    return ApplicationRunner(
        providers,
        ReminderService(
            ReminderPolicy((timedelta(minutes=15),)),
            ReminderLedger(tmp_path / "state.sqlite3"),
        ),
    )


def test_failed_source_does_not_block_healthy_source(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        [
            NamedProvider(SourceName.BLS, _Provider(fails=True)),
            NamedProvider(SourceName.BEA, _Provider((_event(),))),
        ],
    )
    messages: list[str] = []

    result = runner.run_once(
        datetime(2026, 9, 15, 12, 20, tzinfo=UTC),
        lambda reminder: messages.append(reminder.event.title),
    )

    assert result.failed_sources == (SourceName.BLS,)
    assert result.loaded_events == 1
    assert messages == ["Consumer Price Index"]


def test_run_until_stopped_checks_stop_before_sleeping(tmp_path: Path) -> None:
    runner = _runner(tmp_path, [NamedProvider(SourceName.BLS, _Provider())])
    stops = iter((False, True))
    sleeps: list[float] = []

    results = runner.run_until_stopped(
        clock=lambda: datetime(2026, 9, 15, 12, tzinfo=UTC),
        deliver=lambda reminder: None,
        loop_interval_seconds=60,
        sleep=sleeps.append,
        stop_requested=lambda: next(stops, True),
    )

    assert len(results) == 1
    assert sleeps == []


def test_failed_source_does_not_refresh_health_state(tmp_path: Path) -> None:
    health_path = tmp_path / "health.json"
    runner = ApplicationRunner(
        [NamedProvider(SourceName.BLS, _Provider(fails=True))],
        ReminderService(
            ReminderPolicy((timedelta(minutes=15),)),
            ReminderLedger(tmp_path / "state.sqlite3"),
        ),
        HealthReporter(health_path),
    )

    runner.run_once(datetime(2026, 9, 15, 12, 20, tzinfo=UTC), lambda reminder: None)

    assert not health_path.exists()
