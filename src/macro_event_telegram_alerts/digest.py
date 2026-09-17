"""Daily upcoming-event digest formatting and durable once-per-day delivery."""

import sqlite3
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta, tzinfo
from pathlib import Path

from macro_event_telegram_alerts.domain import MacroEvent

type DeliverDigest = Callable[[str], None]


class DailyDigestService:
    """Send one chronological digest per local calendar day after its schedule time."""

    def __init__(
        self, database_path: Path, *, hour: int, minute: int, horizon_days: int
    ) -> None:
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("digest time is outside the day")
        if horizon_days < 1:
            raise ValueError("horizon_days must be positive")
        self._database_path = database_path
        self._hour = hour
        self._minute = minute
        self._horizon_days = horizon_days
        self._initialize()

    def run(
        self,
        events: Iterable[MacroEvent],
        now_utc: datetime,
        timezone: tzinfo | None,
        deliver: DeliverDigest,
    ) -> bool:
        """Deliver today's digest when due; failed sends remain eligible for retry."""
        now_utc = _require_utc(now_utc)
        if timezone is None:
            raise ValueError("digest timezone must be configured")
        local_now = now_utc.astimezone(timezone)
        if (local_now.hour, local_now.minute) < (self._hour, self._minute):
            return False
        digest_date = local_now.date()
        if self._was_sent(digest_date):
            return False
        horizon_end = local_now + timedelta(days=self._horizon_days)
        upcoming = sorted(
            (event for event in events if _is_upcoming(event, now_utc, horizon_end)),
            key=lambda event: (
                event.starts_at_utc or datetime.max.replace(tzinfo=UTC),
                event.title,
            ),
        )
        deliver(format_digest(upcoming, self._horizon_days))
        self._mark_sent(digest_date, now_utc)
        return True

    def _was_sent(self, digest_date: date) -> bool:
        with self._connection() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM daily_digests WHERE digest_date = ?",
                    (digest_date.isoformat(),),
                ).fetchone()
                is not None
            )

    def _mark_sent(self, digest_date: date, sent_at: datetime) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO daily_digests(digest_date, sent_at) "
                "VALUES (?, ?)",
                (digest_date.isoformat(), sent_at.isoformat()),
            )

    def _initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS daily_digests ("
                "digest_date TEXT PRIMARY KEY, sent_at TEXT NOT NULL)"
            )

    def _connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database_path)


def format_digest(events: Iterable[MacroEvent], horizon_days: int) -> str:
    """Render a compact digest, retaining date-only events without inventing a time."""
    lines = [f"Macro digest - next {horizon_days} days"]
    rendered = sorted(
        events,
        key=lambda event: (
            event.starts_at_utc
            or datetime.combine(event.scheduled_date, datetime.min.time(), tzinfo=UTC),
            event.title,
        ),
    )
    if not rendered:
        lines.append("No upcoming events found.")
    for event in rendered:
        if event.starts_at_utc is None:
            when = event.scheduled_date.isoformat()
        else:
            local = (
                event.starts_at_local.strftime("%Y-%m-%d %H:%M %Z")
                if event.starts_at_local
                else ""
            )
            when = f"{event.starts_at_utc.strftime('%Y-%m-%d %H:%M UTC')} ({local})"
        lines.append(
            f"{when} - {event.title} [{event.institution}; {event.source_url}]"
        )
    return "\n".join(lines)


def _is_upcoming(event: MacroEvent, now_utc: datetime, horizon_end: datetime) -> bool:
    if event.starts_at_utc is not None:
        return now_utc <= event.starts_at_utc <= horizon_end
    return now_utc.date() <= event.scheduled_date <= horizon_end.date()


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("now must use UTC")
    return value.astimezone(UTC)
