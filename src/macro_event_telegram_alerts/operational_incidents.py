"""Durable, bounded source-incident state kept separate from reminders."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypedDict, cast

from macro_event_telegram_alerts.delivery_errors import DeliveryError
from macro_event_telegram_alerts.source_diagnostics import SourceReport


@dataclass(frozen=True, slots=True)
class IncidentChange:
    source: str
    kind: str


class _IncidentEntry(TypedDict):
    failures: int
    notified: bool
    attempts: int
    retry_at: str | None
    last_notified_at: str | None
    active_source: str | None


class OperationalIncidentStore:
    """Persist incident notification state without sharing the reminder ledger."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def observe(
        self,
        source: str,
        *,
        degraded: bool,
        now: datetime,
        failure_threshold: int = 1,
        followup_interval: timedelta = timedelta(hours=24),
        active_source: str | None = None,
    ) -> IncidentChange | None:
        now = _utc(now)
        if failure_threshold <= 0 or followup_interval <= timedelta(0):
            raise ValueError("incident notification policy must be positive")
        state = self._read()
        entry = state.get(source, _empty_entry())
        changed_active_source = entry["active_source"] != active_source
        entry["active_source"] = active_source
        if degraded:
            entry["failures"] += 1
            state[source] = entry
            self._write(state)
            if (_due(entry, now) or changed_active_source) and entry[
                "failures"
            ] >= failure_threshold:
                return IncidentChange(
                    source, "opened" if not entry["notified"] else "follow_up"
                )
            return None
        if entry["notified"]:
            return IncidentChange(source, "recovered")
        if source in state:
            del state[source]
            self._write(state)
        return None

    def record_delivery(
        self,
        change: IncidentChange,
        *,
        now: datetime,
        retryable: bool | None,
        followup_interval: timedelta = timedelta(hours=24),
    ) -> None:
        """Record a delivery result; failed notices back off rather than storm."""
        now = _utc(now)
        state = self._read()
        entry = state.get(change.source)
        if entry is None:
            return
        if retryable is None:
            if change.kind == "recovered":
                del state[change.source]
            else:
                entry["notified"] = True
                entry["attempts"] = 0
                entry["last_notified_at"] = now.isoformat()
                entry["retry_at"] = (now + followup_interval).isoformat()
        else:
            entry["attempts"] += 1
            delay = _retry_delay(entry["attempts"], retryable)
            entry["retry_at"] = (now + delay).isoformat()
        self._write(state)

    def _read(self) -> dict[str, _IncidentEntry]:
        if not self._path.exists():
            return {}
        try:
            raw: object = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ValueError("operational incident state is invalid") from error
        if not isinstance(raw, dict):
            raise ValueError("operational incident state is invalid")
        normalized: dict[str, _IncidentEntry] = {}
        for key, value in raw.items():
            if not isinstance(key, str) or not _valid_entry(value):
                raise ValueError("operational incident state is invalid")
            entry = dict(value)
            entry.setdefault("active_source", None)
            normalized[key] = cast(_IncidentEntry, entry)
        return normalized

    def _write(self, state: dict[str, _IncidentEntry]) -> None:
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(state, sort_keys=True) + "\n", encoding="utf-8"
            )
            temporary.replace(self._path)
        except OSError as error:
            raise ValueError(
                "operational incident state could not be written"
            ) from error


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("now must be timezone-aware UTC")
    return value.astimezone(UTC)


def _empty_entry() -> _IncidentEntry:
    return {
        "failures": 0,
        "notified": False,
        "attempts": 0,
        "retry_at": None,
        "last_notified_at": None,
        "active_source": None,
    }


def _valid_entry(value: object) -> bool:
    if not isinstance(value, dict) or not set(value).issubset(set(_empty_entry())):
        return False
    return (
        isinstance(value["failures"], int)
        and not isinstance(value["failures"], bool)
        and value["failures"] >= 0
        and isinstance(value["notified"], bool)
        and isinstance(value["attempts"], int)
        and not isinstance(value["attempts"], bool)
        and value["attempts"] >= 0
        and all(
            value[name] is None or isinstance(value[name], str)
            for name in ("retry_at", "last_notified_at")
        )
        and (
            value.get("active_source") is None
            or isinstance(value.get("active_source"), str)
        )
    )


def _due(entry: _IncidentEntry, now: datetime) -> bool:
    raw = entry["retry_at"]
    if raw is None:
        return True
    try:
        retry_at = _utc(datetime.fromisoformat(str(raw)))
    except ValueError as error:
        raise ValueError("operational incident state is invalid") from error
    return now >= retry_at


def _retry_delay(attempts: int, retryable: bool) -> timedelta:
    count = attempts
    if not retryable or count >= 3:
        return timedelta(hours=24)
    return timedelta(minutes=5 * (2 ** (count - 1)))


class OperationalIncidentReporter:
    """Turn safe source reports into bounded Telegram operational notices."""

    def __init__(
        self,
        store: OperationalIncidentStore,
        deliver: Callable[[str], None],
        *,
        failure_threshold: int,
        followup_interval: timedelta,
    ) -> None:
        self._store = store
        self._deliver = deliver
        self._failure_threshold = failure_threshold
        self._followup_interval = followup_interval

    def observe(self, report: SourceReport, now: datetime) -> None:
        change = self._store.observe(
            report.source,
            degraded=report.status != "healthy",
            now=now,
            failure_threshold=self._failure_threshold,
            followup_interval=self._followup_interval,
            active_source=report.transport.active_source,
        )
        if change is None:
            return
        try:
            self._deliver(format_operational_message(change, report))
        except DeliveryError as error:
            self._store.record_delivery(
                change,
                now=now,
                retryable=error.retryable,
                followup_interval=self._followup_interval,
            )
        except Exception:
            self._store.record_delivery(
                change,
                now=now,
                retryable=False,
                followup_interval=self._followup_interval,
            )
        else:
            self._store.record_delivery(
                change,
                now=now,
                retryable=None,
                followup_interval=self._followup_interval,
            )


def format_operational_message(change: IncidentChange, report: SourceReport) -> str:
    """Render only locally-derived diagnostics, never URLs or external text."""
    heading = {
        "opened": "⚠️ Source coverage degraded",
        "follow_up": "⚠️ Source coverage still degraded",
        "recovered": "✅ Source coverage recovered",
    }[change.kind]
    facts = [f"Source: {report.source}", f"Status: {report.status}"]
    if report.transport.active_source:
        facts.append(f"Fallback coverage active: {report.transport.active_source}")
    if report.transport.category:
        facts.append(f"Reason: {report.transport.category.value}")
    if report.transport.http_status is not None:
        facts.append(f"HTTP status: {report.transport.http_status}")
    if report.future_events is not None:
        facts.append(f"Future events: {report.future_events}")
    if report.transport.next_request_at:
        facts.append(
            f"Next source retry: {report.transport.next_request_at.isoformat()}"
        )
    return "\n".join([heading, *facts])
