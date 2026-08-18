# Product brief

## Problem

Scheduled macroeconomic releases can cause abrupt changes in volatility, but
calendar monitoring is easy to forget. Generic calendars often hide provenance,
and simple reminder scripts do not retain delivery state across restarts.

A useful personal alerting service should be small enough to self-host, explicit
about where every event came from, honest about timing precision, and predictable
about which notification was or was not sent.

## Target user

The initial user is a technically capable trader, quantitative researcher, or
engineer who:

- follows major United States macro events;
- cares about a small, transparent set of significant scheduled releases;
- already uses Telegram;
- can run a Docker container;
- values provenance, reliability, and auditability over a broad opaque calendar.

## Value proposition

Run one container, choose reminder lead times, and receive useful Telegram
notifications sourced from the institutions that publish the schedules. No paid
calendar subscription or calendar-provider API key is required for v0.1.

## Version 0.1 user story

> As a market participant, I want advance Telegram reminders for significant
> scheduled macro events in my local timezone so I can review risk before the
> release and verify every event against its official source.

## Version 0.1 source scope

The first release targets a curated United States event set:

- BLS: CPI, Employment Situation, PPI, and JOLTS;
- BEA: GDP and Personal Income and Outlays/PCE;
- Federal Reserve: scheduled FOMC statements and press conferences.

Coverage is intentionally narrower than a commercial global calendar. New
institutions are accepted only with documented source URLs, update behavior,
timezone semantics, attribution requirements, and deterministic fixtures.

## Functional requirements

1. Read upcoming events through institution-specific official-source adapters.
2. Normalize source timestamps to timezone-aware UTC values at the boundary.
3. Preserve source URL, retrieval time, and timing precision for every event.
4. Apply a version-controlled significance allowlist owned by the project.
5. Schedule configurable reminder lead times.
6. Persist delivery decisions and avoid duplicates after restart.
7. Send messages through the Telegram Bot API.
8. Provide fixture and dry-run modes without data or Telegram credentials.
9. Run continuously in Docker and expose a meaningful health check.

## Quality requirements

- **Provenance:** every event retains its institution and official source URL.
- **Determinism:** scheduling and parser tests use a supplied clock and fixtures.
- **Idempotency:** a source event occurrence has a stable identity.
- **Honest timing:** exact, date-only, tentative, and TBA times are distinct.
- **Responsible retrieval:** adapters cache responses, use bounded polling, and
  identify the application with a contactable User-Agent where appropriate.
- **Secret hygiene:** Telegram tokens are read from the environment and never logged.
- **Recoverability:** failed delivery is retried; successful delivery is not.
- **Operability:** logs explain fetch, filtering, delivery, and failure outcomes.

## Success criteria for v0.1

- a new user can complete the documented fixture dry run in under ten minutes;
- no paid data account or data API key is required;
- the official-source catalog describes all shipped adapters;
- an end-to-end live reminder can be delivered from the container;
- restarting the container does not resend an acknowledged reminder;
- all scheduling and parser contract tests pass in CI without network access;
- messages distinguish project significance from official source facts.

## Monetization compatibility

The architecture may later support a hosted subscription, but v0.1 remains a
free validation release. Billing, advertising, multi-tenancy, and proprietary
analytics are not part of the initial implementation.

Using official public schedules reduces dependence on a calendar-redistribution
license. It does not remove the obligation to review each source's current terms,
attribute it correctly, and comply with local law before a commercial launch.

## Risks and open questions

- official pages and ICS structures can change without versioned schemas;
- schedules can be revised after an earlier reminder;
- some announcements publish only a date or tentative time far in advance;
- official sources do not supply market consensus forecasts;
- project-assigned significance must never be represented as an official rating;
- Telegram can accept a request while downstream delivery is delayed;
- SQLite is appropriate for one replica but not distributed claiming.

