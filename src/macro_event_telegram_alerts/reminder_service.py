"""Coordinate due reminder selection with durable delivery claims."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from macro_event_telegram_alerts.delivery_ledger import ReminderLedger
from macro_event_telegram_alerts.domain import MacroEvent
from macro_event_telegram_alerts.reminders import Reminder, ReminderPolicy

type DeliverReminder = Callable[[Reminder], None]


@dataclass(frozen=True, slots=True)
class ReminderRunResult:
    """Outcome of one deterministic reminder service loop."""

    delivered: tuple[Reminder, ...]
    failed: tuple[Reminder, ...]


class ReminderService:
    """Attempt each due reminder once while delegating transport to a caller."""

    def __init__(self, policy: ReminderPolicy, ledger: ReminderLedger) -> None:
        self._policy = policy
        self._ledger = ledger

    def run(
        self,
        events: Iterable[MacroEvent],
        now: datetime,
        deliver: DeliverReminder,
    ) -> ReminderRunResult:
        """Deliver due reminders and retain enough state for a later retry."""
        now_utc = _require_utc(now)
        delivered: list[Reminder] = []
        failed: list[Reminder] = []
        for reminder in self._policy.due_reminders(events, now_utc):
            lease = self._ledger.claim(reminder, now_utc)
            if lease is None:
                continue
            try:
                deliver(reminder)
            except Exception as error:
                self._ledger.mark_failed(lease, now_utc, type(error).__name__)
                failed.append(reminder)
            else:
                self._ledger.mark_sent(lease, now_utc)
                delivered.append(reminder)
        return ReminderRunResult(tuple(delivered), tuple(failed))


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise ValueError("now must use UTC")
    return value.astimezone(UTC)
