"""Durable, bounded source-incident state kept separate from reminders."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class IncidentChange:
    source: str
    kind: str


class OperationalIncidentStore:
    """Open each source incident once and persist recovery across restarts."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def observe(
        self, source: str, *, degraded: bool, now: datetime
    ) -> IncidentChange | None:
        now = _utc(now)
        state = self._read()
        opened = bool(state.get(source, False))
        if degraded and not opened:
            state[source] = True
            self._write(state)
            return IncidentChange(source, "opened")
        if not degraded and opened:
            state[source] = False
            self._write(state)
            return IncidentChange(source, "recovered")
        return None

    def _read(self) -> dict[str, bool]:
        if not self._path.exists():
            return {}
        try:
            raw: object = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ValueError("operational incident state is invalid") from error
        if not isinstance(raw, dict) or not all(
            isinstance(key, str) and isinstance(value, bool)
            for key, value in raw.items()
        ):
            raise ValueError("operational incident state is invalid")
        return dict(raw)

    def _write(self, state: dict[str, bool]) -> None:
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(state, sort_keys=True) + "\n", encoding="utf-8"
            )
            temporary.replace(self._path)
        except OSError as error:
            raise ValueError("operational incident state could not be written") from error


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("now must be timezone-aware UTC")
    return value.astimezone(UTC)
