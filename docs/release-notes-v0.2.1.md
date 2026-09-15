# Macro Event Telegram Alerts v0.2.1

Small usability release for reminder message timestamps.

## Changed

- Telegram reminder messages now include both:
  - `Scheduled local time`, using the institution/source timezone.
  - `Scheduled UTC time`, for operators who reason from UTC.

Example:

```text
Scheduled local time: 2026-09-16 14:00 EDT (America/New_York)
Scheduled UTC time: 2026-09-16 18:00 UTC
```

## Deploy

Use `ghcr.io/bockuden/macro-event-telegram-alerts:v0.2.1` with the tracked
`compose.release.yaml`. Preserve the existing Compose volume during upgrade so
the SQLite reminder ledger, source cache, and operational incident state remain
available.
