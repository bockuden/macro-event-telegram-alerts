# Changelog

All notable changes are documented here. This project follows semantic versioning
from its first public release.

## [0.1.0] - 2026-09-07

### Added

- Official, credential-free schedule adapters for U.S. BLS, BEA, and scheduled
  Federal Reserve FOMC events.
- Configurable 24-hour, 60-minute, and 15-minute Telegram reminders with a
  SQLite delivery ledger that survives restarts.
- Secret-safe Telegram delivery, dry-run mode, structured operational logs,
  transient/permanent failure handling, Docker Compose, health checks, and
  GHCR release-image automation.

### Limitations

- Coverage is limited to CPI, Employment Situation, PPI, JOLTS, GDP,
  Personal Income and Outlays/PCE, scheduled FOMC statements, and scheduled
  Chair press conferences in the United States.
- The project sends calendar reminders, not trading signals, forecasts,
  actual-result data, or investment advice.
- One SQLite-backed service replica is supported. Multi-replica high
  availability and unscheduled central-bank decisions are outside this release.
