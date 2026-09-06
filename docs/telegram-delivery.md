# Telegram delivery and dry-run

Issue #7 supplies delivery components; the service entry point and configuration
file will be added in a later milestone. The components deliberately have no
global configuration, logging, or environment-variable access.

`DryRunNotifier` accepts a local string sink and needs neither a Telegram token
nor a chat ID. It renders the exact message that `TelegramNotifier` sends, so it
is suitable for local inspection and deterministic tests.

`TelegramNotifier` sends UTF-8 JSON to Telegram's HTTPS `sendMessage` endpoint.
Its timeout defaults to 10 seconds and may not exceed 30 seconds. It considers a
delivery successful only when Telegram returns HTTP 200 and a JSON response with
`ok: true`.

The notifier intentionally never logs request URLs, payloads, bot tokens, or
chat IDs. Its raised errors are generic and safe to record in the delivery
ledger. The supplied `ReminderService` receives a notifier's `deliver` method
as a callback, so no Telegram dependency leaks into scheduling or source code.

Each message includes the event name, institution, source-local scheduled time,
timing quality, source URL, and a clear statement that project significance is
not an official institution rating.
