"""Container-friendly command that checks recent successful service state."""

import argparse
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

from macro_event_telegram_alerts.app_runtime import utc_now
from macro_event_telegram_alerts.health import HealthStateError, require_recent_success


def main(argv: Sequence[str] | None = None) -> int:
    """Return a shell-friendly health status without exposing configuration values."""
    parser = argparse.ArgumentParser(prog="macro-event-telegram-alerts-healthcheck")
    parser.add_argument("path", type=Path)
    parser.add_argument("--max-age-seconds", type=int, required=True)
    parsed = parser.parse_args(argv)
    try:
        require_recent_success(
            parsed.path,
            now=utc_now(),
            max_age=timedelta(seconds=parsed.max_age_seconds),
        )
    except (HealthStateError, ValueError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
