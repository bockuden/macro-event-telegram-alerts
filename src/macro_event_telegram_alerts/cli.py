"""Command-line entry point for the configured reminder application."""

import argparse
import logging
import os
import signal
import sys
import time
from collections.abc import Callable, MutableMapping, Sequence
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import Protocol, TextIO, cast

from macro_event_telegram_alerts.app_config import ConfigError, SourceName, load_config
from macro_event_telegram_alerts.app_runtime import (
    ApplicationRunner,
    build_runner,
    utc_now,
)
from macro_event_telegram_alerts.notifications import DryRunNotifier
from macro_event_telegram_alerts.reminders import Reminder
from macro_event_telegram_alerts.secrets import (
    load_dotenv,
    resolve_telegram_credentials,
)
from macro_event_telegram_alerts.telegram_notifier import TelegramNotifier


class _RunResult(Protocol):
    @property
    def failed_sources(self) -> tuple[SourceName, ...]:
        """Return source names that failed during the loop."""


class _Runner(Protocol):
    def run_once(
        self, now: datetime, deliver: Callable[[Reminder], None]
    ) -> _RunResult:
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
        if parsed.command == "dry-run":
            notifier: _Notifier = DryRunNotifier(
                lambda message: print(message, file=output)
            )
        else:
            load_dotenv(parsed.config.parent / ".env", environment)
            credentials = resolve_telegram_credentials(config.telegram, environment)
            notifier = TelegramNotifier(credentials.token, credentials.chat_id)
        runner = runner_builder(config, clock=utc_now)
        if parsed.command == "dry-run" or parsed.once:
            result = runner.run_once(utc_now(), notifier.deliver)
            _print_result(result.failed_sources, error_output)
            return 1 if result.failed_sources else 0
        return _run_forever(
            cast(ApplicationRunner, runner),
            config.loop_interval.total_seconds(),
            notifier.deliver,
            error_output,
        )
    except ConfigError as error:
        print(f"Configuration error: {error}", file=error_output)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="macro-event-telegram-alerts")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in ("check-config", "dry-run", "run"):
        subparser = subcommands.add_parser(command)
        subparser.add_argument(
            "--config",
            type=Path,
            default=Path("config.toml"),
            help="path to the non-secret TOML configuration file",
        )
        if command == "run":
            subparser.add_argument(
                "--once",
                action="store_true",
                help="run one service loop, then exit",
            )
    return parser


def _run_forever(
    runner: ApplicationRunner,
    loop_interval_seconds: float,
    deliver: Callable[[Reminder], None],
    error_output: TextIO,
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


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


if __name__ == "__main__":
    raise SystemExit(main())
