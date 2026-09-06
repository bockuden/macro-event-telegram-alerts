"""Reminder selection for normalized macroeconomic events."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from macro_event_telegram_alerts.domain import MacroEvent

DEFAULT_LEAD_TIMES = (
    timedelta(hours=24),
    timedelta(hours=1),
    timedelta(minutes=15),
)


@dataclass(frozen=True, slots=True)
class Reminder:
    """One notification due before one immutable event occurrence."""

    event: MacroEvent
    lead_time: timedelta

    def __post_init__(self) -> None:
        if self.event.starts_at_utc is None:
            raise ValueError("a reminder requires an event with a UTC instant")
        if self.lead_time <= timedelta(0):
            raise ValueError("reminder lead_time must be positive")
        if self.lead_time != timedelta(seconds=int(self.lead_time.total_seconds())):
            raise ValueError("reminder lead_time must have whole-second precision")

    @property
    def due_at(self) -> datetime:
        """Return the UTC instant at which this reminder becomes due."""
        assert self.event.starts_at_utc is not None
        return self.event.starts_at_utc - self.lead_time

    @property
    def occurrence_at(self) -> datetime:
        """Return the event instant used to distinguish a rescheduled occurrence."""
        assert self.event.starts_at_utc is not None
        return self.event.starts_at_utc

    @property
    def lead_seconds(self) -> int:
        """Return the durable, whole-second lead-time representation."""
        return int(self.lead_time.total_seconds())


@dataclass(frozen=True, slots=True)
class ReminderPolicy:
    """Configurable lead times and late-discovery selection semantics."""

    lead_times: tuple[timedelta, ...] = DEFAULT_LEAD_TIMES

    def __post_init__(self) -> None:
        if not self.lead_times:
            raise ValueError("reminder lead_times must not be empty")
        if any(lead_time <= timedelta(0) for lead_time in self.lead_times):
            raise ValueError("reminder lead_times must be positive")
        if any(
            lead_time != timedelta(seconds=int(lead_time.total_seconds()))
            for lead_time in self.lead_times
        ):
            raise ValueError("reminder lead_times must have whole-second precision")
        if len(set(self.lead_times)) != len(self.lead_times):
            raise ValueError("reminder lead_times must be unique")

    def due_reminders(
        self,
        events: Iterable[MacroEvent],
        now: datetime,
    ) -> tuple[Reminder, ...]:
        """Return at most one useful due reminder for each future occurrence."""
        now_utc = _require_utc(now, "now")
        reminders: list[Reminder] = []
        for event in events:
            if event.starts_at_utc is None or event.starts_at_utc <= now_utc:
                continue
            due = [
                Reminder(event=event, lead_time=lead_time)
                for lead_time in self.lead_times
                if event.starts_at_utc - lead_time <= now_utc
            ]
            if due:
                reminders.append(max(due, key=lambda reminder: reminder.due_at))
        return tuple(sorted(reminders, key=lambda reminder: reminder.due_at))


def _require_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must use UTC")
    return value.astimezone(UTC)
