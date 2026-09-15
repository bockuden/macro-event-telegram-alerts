# Changelog

All notable changes are documented here. This project follows semantic versioning
from its first public release.

## [0.2.1] - 2026-09-15

### Changed

- Telegram reminder messages now include the scheduled UTC time alongside the
  source-local scheduled time.

## [0.2.0] - 2026-09-15

### Added

- New York Fed economic-indicators fallback coverage for selected BLS releases
  when the primary BLS calendar endpoint is rejected.
- Bounded source retry cooldowns, detailed HTTP diagnostics, and operational
  Telegram incident notifications for degraded or failed sources.
- A 48-hour default reminder lead time in addition to the existing 24-hour,
  60-minute, and 15-minute reminders.

### Changed

- Release deployment examples now pin the GHCR image to `v0.2.0`.
- The runtime User-Agent reports the package version used by the build.

### Validation

- Live source diagnostics on 2026-09-15 confirmed FOMC coverage with the next
  timed event at `2026-09-16T18:00:00+00:00`.
- Live source diagnostics confirmed BLS fallback operation through the New York
  Fed source while the primary BLS endpoint returned HTTP 403.

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
