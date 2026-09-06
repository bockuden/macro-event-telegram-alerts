"""Macro Event Telegram Alerts package."""

from macro_event_telegram_alerts.domain import MacroEvent, TimingPrecision
from macro_event_telegram_alerts.notifications import (
    DryRunNotifier,
    format_reminder_message,
)
from macro_event_telegram_alerts.policy import EventSignificance, SignificancePolicy
from macro_event_telegram_alerts.reminders import Reminder, ReminderPolicy
from macro_event_telegram_alerts.telegram_notifier import (
    TelegramDeliveryError,
    TelegramNotifier,
)

__version__ = "0.0.0"

__all__ = [
    "DryRunNotifier",
    "EventSignificance",
    "MacroEvent",
    "Reminder",
    "ReminderPolicy",
    "SignificancePolicy",
    "TelegramDeliveryError",
    "TelegramNotifier",
    "TimingPrecision",
    "__version__",
    "format_reminder_message",
]
