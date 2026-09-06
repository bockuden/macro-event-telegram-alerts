"""Macro Event Telegram Alerts package."""

from macro_event_telegram_alerts.domain import MacroEvent, TimingPrecision
from macro_event_telegram_alerts.policy import EventSignificance, SignificancePolicy
from macro_event_telegram_alerts.reminders import Reminder, ReminderPolicy

__version__ = "0.0.0"

__all__ = [
    "EventSignificance",
    "MacroEvent",
    "Reminder",
    "ReminderPolicy",
    "SignificancePolicy",
    "TimingPrecision",
    "__version__",
]
