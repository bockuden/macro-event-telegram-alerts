"""Command-line entry point for the configured reminder application."""

import argparse
import json
import logging
import os
import signal
import sys
import time
from collections.abc import Callable, MutableMapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import FrameType
from typing import Any, Protocol, TextIO, cast

from macro_event_telegram_alerts.app_config import (
    AppConfig,
    ConfigError,
    SourceName,
    load_config,
)
from macro_event_telegram_alerts.app_runtime import (
    ApplicationRunner,
    build_official_providers,
    build_runner,
    inspect_source,
    utc_now,
)
from macro_event_telegram_alerts.delivery_errors import DeliveryError
from macro_event_telegram_alerts.domain import MacroEvent
from macro_event_telegram_alerts.notifications import DryRunNotifier
from macro_event_telegram_alerts.operational_incidents import (
    OperationalIncidentReporter,
    OperationalIncidentStore,
)
from macro_event_telegram_alerts.policy import importance_at_least
from macro_event_telegram_alerts.reminders import Reminder
from macro_event_telegram_alerts.secrets import (
    load_dotenv,
    resolve_telegram_credentials,
)
from macro_event_telegram_alerts.source_diagnostics import SourceReport
from macro_event_telegram_alerts.telegram_notifier import TelegramNotifier


class _RunResult(Protocol):
    @property
    def failed_sources(self) -> tuple[SourceName, ...]:
        """Return source names that failed during the loop."""


class _Runner(Protocol):
    def run_once(self, *args: Any, **kwargs: Any) -> _RunResult:
        """Run one loop for CLI testability."""


class _Notifier(Protocol):
    def deliver(self, reminder: Reminder) -> None:
        """Deliver one reminder."""


type RunnerBuilder = Callable[..., _Runner]


def main(
    argv: Sequence[str] | None = None,
    *,
    runner_builder: RunnerBuilder = build_runner,
    environment: MutableMapping[str, str] | None = None,
    output: TextIO | None = None,
    error_output: TextIO | None = None,
) -> int:
    """Run `check-config`, `dry-run`, or live Telegram delivery."""
    _configure_logging()
    parsed = _parser().parse_args(argv)
    output = output or sys.stdout
    error_output = error_output or sys.stderr
    environment = environment if environment is not None else os.environ
    try:
        config = load_config(parsed.config)
        if parsed.command == "check-config":
            print("Configuration is valid.", file=output)
            return 0
        if parsed.command == "diagnose-sources":
            reports = [
                inspect_source(provider, utc_now())[1]
                for provider in build_official_providers(
                    config, clock=utc_now, allow_network=parsed.live
                )
            ]
            print(
                json.dumps(
                    {
                        "mode": "live" if parsed.live else "cache-only",
                        "sources": [report.to_dict() for report in reports],
                    },
                    indent=2,
                ),
                file=output,
            )
            return 1 if any(report.status != "healthy" for report in reports) else 0
        if parsed.command == "preview":
            return _preview(config, parsed.days, output, error_output)
        if parsed.command == "status":
            return _status(config, output, error_output, environment)
        if parsed.command == "send-test":
            load_dotenv(parsed.config.parent / ".env", environment)
            credentials = resolve_telegram_credentials(config.telegram, environment)
            test_notifier = TelegramNotifier(credentials.token, credentials.chat_id)
            try:
                test_notifier.deliver_text(
                    "Macro Event Telegram Alerts test message\n"
                    "Telegram credentials and chat delivery are working."
                )
            except DeliveryError as error:
                print(
                    f"Telegram test message failed (retryable={error.retryable}).",
                    file=error_output,
                )
                return 1
            print("Telegram test message sent successfully.", file=output)
            return 0
        if parsed.command == "dry-run":
            notifier: _Notifier = DryRunNotifier(
                lambda message: print(message, file=output)
            )
            operational_deliver: Callable[[str], None] | None = None

            digest_deliver: Callable[[str], None] = _digest_sink(output)
        else:
            load_dotenv(parsed.config.parent / ".env", environment)
            credentials = resolve_telegram_credentials(config.telegram, environment)
            notifier = TelegramNotifier(credentials.token, credentials.chat_id)
            operational_deliver = notifier.deliver_text
            digest_deliver = notifier.deliver_text
        operational_reporter = (
            OperationalIncidentReporter(
                OperationalIncidentStore(
                    config.ledger_path.parent / "source-incidents.json"
                ),
                operational_deliver,
                failure_threshold=config.operations.failure_threshold,
                followup_interval=config.operations.followup_interval,
            )
            if parsed.command == "run"
            and config.operations.enabled
            and operational_deliver is not None
            else None
        )
        runner = runner_builder(config, clock=utc_now)
        if parsed.command == "dry-run" or parsed.once:
            if operational_reporter is None:
                if config.digest.enabled:
                    result = runner.run_once(
                        utc_now(), notifier.deliver, deliver_digest=digest_deliver
                    )
                else:
                    result = runner.run_once(utc_now(), notifier.deliver)
            else:
                if config.digest.enabled:
                    result = runner.run_once(
                        utc_now(),
                        notifier.deliver,
                        operational_reporter.observe,
                        digest_deliver,
                    )
                else:
                    result = runner.run_once(
                        utc_now(), notifier.deliver, operational_reporter.observe
                    )
            _print_result(result.failed_sources, error_output)
            return 1 if result.failed_sources else 0
        return _run_forever(
            cast(ApplicationRunner, runner),
            config.loop_interval.total_seconds(),
            notifier.deliver,
            error_output,
            operational_reporter.observe if operational_reporter else None,
            digest_deliver if config.digest.enabled else None,
        )
    except ConfigError as error:
        print(f"Configuration error: {error}", file=error_output)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="macro-event-telegram-alerts")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in (
        "check-config",
        "dry-run",
        "run",
        "diagnose-sources",
        "preview",
        "status",
        "send-test",
    ):
        subparser = subcommands.add_parser(command)
        subparser.add_argument(
            "--config",
            type=Path,
            default=Path("config.toml"),
            help="path to the non-secret TOML configuration file",
        )
        if command == "diagnose-sources":
            subparser.add_argument(
                "--live",
                action="store_true",
                help="allow bounded calendar requests under existing cache/poll rules",
            )
        if command == "run":
            subparser.add_argument(
                "--once",
                action="store_true",
                help="run one service loop, then exit",
            )
        if command == "preview":
            subparser.add_argument(
                "--days",
                type=_positive_days,
                default=7,
                help="number of upcoming days to display (default: 7)",
            )
    return parser


def _positive_days(value: str) -> int:
    days = int(value)
    if not 1 <= days <= 31:
        raise argparse.ArgumentTypeError("days must be between 1 and 31")
    return days


def _preview(config: AppConfig, days: int, output: TextIO, error_output: TextIO) -> int:
    now = utc_now()
    horizon = now + timedelta(days=days)
    events: list[MacroEvent] = []
    failed = False
    for provider in build_official_providers(config, clock=utc_now, allow_network=True):
        loaded, report = inspect_source(provider, now)
        events.extend(loaded)
        if report.status != "healthy":
            failed = True
            print(f"Source {report.source} status: {report.status}", file=error_output)
    upcoming = sorted(
        (
            event
            for event in events
            if importance_at_least(event.policy, config.minimum_importance)
            and (
                (
                    event.starts_at_utc is not None
                    and now <= event.starts_at_utc <= horizon
                )
                or (
                    event.starts_at_utc is None
                    and now.date() <= event.scheduled_date <= horizon.date()
                )
            )
        ),
        key=lambda event: (
            event.starts_at_utc
            or datetime.combine(event.scheduled_date, datetime.min.time(), tzinfo=UTC),
            event.title,
        ),
    )
    print(f"Macro event preview - next {days} days", file=output)
    if not upcoming:
        print("No upcoming events found.", file=output)
    for event in upcoming:
        local = (
            event.starts_at_local.strftime("%Y-%m-%d %H:%M %Z")
            if event.starts_at_local
            else event.scheduled_date.isoformat()
        )
        utc = (
            event.starts_at_utc.strftime("%Y-%m-%d %H:%M UTC")
            if event.starts_at_utc
            else "date-only"
        )
        print(
            f"{utc} | local: {local} | {event.title} | "
            f"{event.institution} | source: {event.source_id} | {event.source_url}",
            file=output,
        )
    return 1 if failed else 0


def _status(
    config: AppConfig,
    output: TextIO,
    error_output: TextIO,
    environment: MutableMapping[str, str],
) -> int:
    """Print read-only source and configuration health without secrets."""
    now = utc_now()
    failed = False
    for provider in build_official_providers(config, clock=utc_now, allow_network=True):
        events, report = inspect_source(provider, now)
        selected = [
            event
            for event in events
            if importance_at_least(event.policy, config.minimum_importance)
        ]
        if report.status != "healthy":
            failed = True
        print(f"Source {report.source}: {report.status}", file=output)
        if report.transport.active_source:
            print(f"  Fallback coverage: {report.transport.active_source}", file=output)
        print(f"  Future events: {len(selected)}", file=output)
        timed = [event.starts_at_utc for event in selected if event.starts_at_utc]
        if timed:
            print(f"  Next event UTC: {min(timed).isoformat()}", file=output)
        if report.status != "healthy":
            print(f"Source {report.source} status: {report.status}", file=error_output)
    leads = ", ".join(
        f"{int(value.total_seconds() // 60)}m"
        for value in config.reminder_policy.lead_times
    )
    print(f"Reminder lead times: {leads}", file=output)
    print(f"Minimum importance: {config.minimum_importance.value}", file=output)
    telegram_configured = config.telegram is not None
    print(
        f"Telegram configuration: {'configured' if telegram_configured else 'missing'}",
        file=output,
    )
    del environment
    return 1 if failed else 0


def _run_forever(
    runner: ApplicationRunner,
    loop_interval_seconds: float,
    deliver: Callable[[Reminder], None],
    error_output: TextIO,
    report_operational: Callable[[SourceReport, datetime], None] | None,
    deliver_digest: Callable[[str], None] | None,
) -> int:
    stopping = False

    def request_stop(signum: int, frame: FrameType | None) -> None:
        del signum, frame
        nonlocal stopping
        stopping = True

    original_handlers = {
        signum: signal.signal(signum, request_stop)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        results = runner.run_until_stopped(
            clock=utc_now,
            deliver=deliver,
            report_operational=report_operational,
            deliver_digest=deliver_digest,
            loop_interval_seconds=loop_interval_seconds,
            sleep=time.sleep,
            stop_requested=lambda: stopping,
        )
    finally:
        for signum, handler in original_handlers.items():
            signal.signal(signum, handler)
    failures = tuple(source for result in results for source in result.failed_sources)
    _print_result(failures, error_output)
    return 1 if failures else 0


def _print_result(failed_sources: tuple[SourceName, ...], error_output: TextIO) -> None:
    for source in failed_sources:
        print(f"Source failed during this loop: {source.value}", file=error_output)


def _digest_sink(output: TextIO) -> Callable[[str], None]:
    def sink(message: str) -> None:
        print(message, file=output)

    return sink


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


if __name__ == "__main__":
    raise SystemExit(main())
