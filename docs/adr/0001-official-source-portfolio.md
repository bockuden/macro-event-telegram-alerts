# ADR 0001: Build a curated portfolio of official schedule adapters

- **Status:** Accepted for the initial implementation
- **Date:** 2026-08-18

## Context

The service needs future macroeconomic events with trustworthy release times and
clear provenance. A commercial aggregate calendar provides broad coverage and a
uniform schema, but production redistribution can require a costly license and
creates a single-vendor dependency.

Official institutions publish the schedules needed for a useful smaller product,
but in different formats and without a common importance rating or consensus
forecast. The project must choose between broad convenient coverage and narrow
auditable coverage that does not require a paid calendar API.

## Decision

Build version 0.1 from a curated portfolio of public official schedules. Do not
use Trading Economics or another paid aggregate calendar in the initial release.

Initial adapters will cover:

1. BLS online calendar/ICS for CPI, Employment Situation, PPI, and JOLTS;
2. BEA release schedule for GDP and Personal Income and Outlays/PCE;
3. Federal Reserve calendars for scheduled FOMC statements and press conferences.

Every adapter will map into a provider-neutral `MacroEvent` and preserve:

- institution and canonical source URL;
- source-local timestamp and normalized UTC timestamp;
- retrieval timestamp;
- timing precision such as exact, tentative, date-only, or TBA;
- a source-derived stable identity where possible.

The project will maintain its own version-controlled significance allowlist.
This classification is product policy, not institution-provided data.

## Responsible retrieval policy

- prefer machine-readable official feeds such as BLS iCalendar;
- poll slowly because release schedules change infrequently;
- use conditional requests and local caching when supported;
- identify the application with a contactable User-Agent where appropriate;
- test parsers against recorded minimal fixtures, never live sites in CI;
- fail visibly on unknown layouts or ambiguous times;
- link and attribute every official source in user-facing messages;
- review current source terms again before each public release.

## Why this option

- no paid calendar subscription or data-provider API key is required for v0.1;
- event provenance is visible and independently verifiable;
- source-specific timing quality can be represented honestly;
- the architecture remains useful for a future hosted commercial service;
- narrow United States coverage is sufficient to validate reminder reliability
  before investing in broader international adapters.

## Consequences

### Positive

- no aggregate-provider redistribution dependency in the first release;
- strong provenance and source links;
- public schedules can be tested through small recorded fixtures;
- each new institution becomes a reviewable, incremental contribution.

### Negative

- narrower initial coverage and more adapter maintenance;
- HTML pages can change without schema versioning;
- official sources do not provide market consensus forecasts;
- significance is a project judgment that requires transparent governance;
- commercial reuse still requires a source-by-source policy review.

## Alternatives considered

### Trading Economics calendar API

Rejected for v0.1. It has a convenient schema, importance fields, and broad
coverage, but live access requires a paid plan and client redistribution is a
separate commercial licensing concern.

### Scrape a third-party public calendar

Rejected because provenance, markup stability, and automated-use rights are
weaker than official schedules.

### Maintain all dates manually

Useful as a deterministic fixture and emergency override only. Manual entry
cannot safely track schedule revisions as the primary live source.

## Review trigger

Revisit this decision if official formats become operationally unreliable,
users demonstrate demand for broader country coverage, or a commercial provider
offers explicit redistribution rights with sustainable unit economics.

