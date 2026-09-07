# Macro Event Telegram Alerts v0.1.0

First public release of a self-hosted Telegram reminder service for selected
significant U.S. macroeconomic events.

## Included

- Credential-free official schedules from BLS, BEA, and the Federal Reserve.
- BLS CPI, Employment Situation, PPI, and JOLTS; BEA GDP and Personal Income
  and Outlays/PCE; scheduled FOMC statements and Chair press conferences.
- Configurable reminders, SQLite-backed restart-safe delivery state, Telegram
  delivery or credential-free dry-run, and Docker Compose deployment.
- Secret-safe diagnostics, documented retry behaviour, and a public GHCR image.

## Limitations

- This is a calendar reminder tool, not a trading signal, forecast, actual-data
  feed, or financial-advice service.
- It covers only the listed U.S. release families; unscheduled central-bank
  decisions and international calendars are not included.
- It is designed for one SQLite-backed service replica, not high availability.

## Deploy

Use `ghcr.io/bockuden/macro-event-telegram-alerts:v0.1.0` with the tracked
`compose.release.yaml`. The README contains the complete Linux server setup;
provide your own local Telegram bot token and recipient chat ID in `.env`.
