"""Durable recent-success health state for a single service process."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path


class HealthStateError(RuntimeError):
    """The service health state is missing, stale, or invalid."""


class HealthReporter:
    """Atomically retain the most recent fully successful service-loop time."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def record_success(self, completed_at: datetime) -> None:
        """Write one UTC success timestamp after a healthy service loop."""
        completed_at_utc = _require_utc(completed_at)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(self._path.suffix + ".tmp")
            temporary.write_text(
                json.dumps({"last_success_at": completed_at_utc.isoformat()}) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            temporary.replace(self._path)
        except OSError as error:
            raise HealthStateError("health state could not be written") from error


def require_recent_success(path: Path, *, now: datetime, max_age: timedelta) -> None:
    """Raise unless the last successful loop is recent enough for health checks."""
    now_utc = _require_utc(now)
    if max_age <= timedelta(0):
        raise ValueError("max_age must be positive")
    try:
        document: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HealthStateError("health state is unavailable") from error
    if not isinstance(document, dict) or not isinstance(
        value := document.get("last_success_at"), str
    ):
        raise HealthStateError("health state is invalid")
    try:
        completed_at = _require_utc(datetime.fromisoformat(value))
    except ValueError as error:
        raise HealthStateError("health state is invalid") from error
    age = now_utc - completed_at
    if age < timedelta(0) or age > max_age:
        raise HealthStateError("health state is stale")


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("health timestamp must be timezone-aware")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("health timestamp must use UTC")
    return value.astimezone(UTC)
