"""SQLite-backed reminder delivery claims for a single service replica."""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from macro_event_telegram_alerts.reminders import Reminder


class DeliveryStatus(StrEnum):
    """Durable state of one reminder identity."""

    IN_FLIGHT = "in_flight"
    SENT = "sent"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DeliveryLease:
    """Exclusive, time-bounded permission to attempt one delivery."""

    reminder: Reminder
    attempt_id: str


@dataclass(frozen=True, slots=True)
class DeliveryRecord:
    """Inspectable durable state for one reminder identity."""

    status: DeliveryStatus
    attempts: int
    claimed_at: datetime
    lease_expires_at: datetime | None
    delivered_at: datetime | None
    failure_reason: str | None
    retryable: bool


class ReminderLedger:
    """Keep delivery state durable across restarts and source reschedules."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._initialize()

    def claim(
        self,
        reminder: Reminder,
        now: datetime,
        *,
        lease_duration: timedelta = timedelta(minutes=5),
    ) -> DeliveryLease | None:
        """Claim a reminder unless it was sent or has an active delivery lease."""
        now_utc = _require_utc(now, "now")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        lease_expires_at = now_utc + lease_duration
        identity = _identity(reminder)
        attempt_id = str(uuid4())

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT status, lease_expires_at, retryable
                FROM reminder_deliveries
                WHERE source_id = ? AND occurrence_at_utc = ? AND lead_seconds = ?
                """,
                identity,
            ).fetchone()
            if row is not None:
                status = DeliveryStatus(row["status"])
                lease_expires = _from_database_time(row["lease_expires_at"])
                if status is DeliveryStatus.SENT:
                    return None
                if status is DeliveryStatus.FAILED and not bool(row["retryable"]):
                    return None
                if (
                    status is DeliveryStatus.IN_FLIGHT
                    and lease_expires is not None
                    and now_utc < lease_expires
                ):
                    return None

            connection.execute(
                """
                INSERT INTO reminder_deliveries (
                    source_id, occurrence_at_utc, lead_seconds, status, attempts,
                    attempt_id, claimed_at, lease_expires_at, delivered_at,
                    failure_reason, retryable
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, NULL, NULL, 1)
                ON CONFLICT(source_id, occurrence_at_utc, lead_seconds) DO UPDATE SET
                    status = excluded.status,
                    attempts = reminder_deliveries.attempts + 1,
                    attempt_id = excluded.attempt_id,
                    claimed_at = excluded.claimed_at,
                    lease_expires_at = excluded.lease_expires_at,
                    failure_reason = NULL,
                    retryable = 1
                """,
                (
                    *identity,
                    DeliveryStatus.IN_FLIGHT.value,
                    attempt_id,
                    now_utc.isoformat(),
                    lease_expires_at.isoformat(),
                ),
            )
        return DeliveryLease(reminder=reminder, attempt_id=attempt_id)

    def mark_sent(self, lease: DeliveryLease, delivered_at: datetime) -> None:
        """Record successful delivery for an active claim."""
        self._complete(lease, delivered_at, DeliveryStatus.SENT, None)

    def mark_failed(
        self,
        lease: DeliveryLease,
        failed_at: datetime,
        reason: str,
        *,
        retryable: bool,
    ) -> None:
        """Record a failed attempt so a later service loop can retry it."""
        if not reason.strip():
            raise ValueError("failure reason must not be empty")
        self._complete(
            lease,
            failed_at,
            DeliveryStatus.FAILED,
            reason,
            retryable=retryable,
        )

    def record_for(self, reminder: Reminder) -> DeliveryRecord | None:
        """Return durable state for a reminder identity, if it exists."""
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT status, attempts, claimed_at, lease_expires_at, delivered_at,
                       failure_reason, retryable
                FROM reminder_deliveries
                WHERE source_id = ? AND occurrence_at_utc = ? AND lead_seconds = ?
                """,
                _identity(reminder),
            ).fetchone()
        if row is None:
            return None
        return DeliveryRecord(
            status=DeliveryStatus(row["status"]),
            attempts=row["attempts"],
            claimed_at=_required_database_time(row["claimed_at"]),
            lease_expires_at=_from_database_time(row["lease_expires_at"]),
            delivered_at=_from_database_time(row["delivered_at"]),
            failure_reason=row["failure_reason"],
            retryable=bool(row["retryable"]),
        )

    def _complete(
        self,
        lease: DeliveryLease,
        completed_at: datetime,
        status: DeliveryStatus,
        failure_reason: str | None,
        *,
        retryable: bool = False,
    ) -> None:
        completed_at_utc = _require_utc(completed_at, "completed_at")
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE reminder_deliveries
                SET status = ?, delivered_at = ?, lease_expires_at = NULL,
                    failure_reason = ?, retryable = ?
                WHERE source_id = ? AND occurrence_at_utc = ? AND lead_seconds = ?
                    AND status = ? AND attempt_id = ?
                """,
                (
                    status.value,
                    completed_at_utc.isoformat()
                    if status is DeliveryStatus.SENT
                    else None,
                    failure_reason,
                    int(retryable),
                    *_identity(lease.reminder),
                    DeliveryStatus.IN_FLIGHT.value,
                    lease.attempt_id,
                ),
            )
        if cursor.rowcount != 1:
            raise ValueError("delivery lease is no longer active")

    def _initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reminder_deliveries (
                    source_id TEXT NOT NULL,
                    occurrence_at_utc TEXT NOT NULL,
                    lead_seconds INTEGER NOT NULL CHECK (lead_seconds > 0),
                    status TEXT NOT NULL CHECK (
                        status IN ('in_flight', 'sent', 'failed')
                    ),
                    attempts INTEGER NOT NULL CHECK (attempts > 0),
                    attempt_id TEXT NOT NULL,
                    claimed_at TEXT NOT NULL,
                    lease_expires_at TEXT,
                    delivered_at TEXT,
                    failure_reason TEXT,
                    retryable INTEGER NOT NULL DEFAULT 1 CHECK (retryable IN (0, 1)),
                    PRIMARY KEY (source_id, occurrence_at_utc, lead_seconds)
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(reminder_deliveries)")
            }
            if "retryable" not in columns:
                connection.execute(
                    "ALTER TABLE reminder_deliveries "
                    "ADD COLUMN retryable INTEGER NOT NULL DEFAULT 1 "
                    "CHECK (retryable IN (0, 1))"
                )

    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection


def _identity(reminder: Reminder) -> tuple[str, str, int]:
    return (
        reminder.event.source_id,
        reminder.occurrence_at.isoformat(),
        reminder.lead_seconds,
    )


def _require_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must use UTC")
    return value.astimezone(UTC)


def _from_database_time(value: object) -> datetime | None:
    if value is None:
        return None
    return _required_database_time(value)


def _required_database_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise RuntimeError("delivery ledger contains an invalid timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise RuntimeError("delivery ledger contains an invalid timestamp") from error
    return _require_utc(parsed, "delivery ledger timestamp")
