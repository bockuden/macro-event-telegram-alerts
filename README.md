# Macro Event Telegram Alerts

[![CI](https://github.com/bockuden/macro-event-telegram-alerts/actions/workflows/ci.yml/badge.svg)](https://github.com/bockuden/macro-event-telegram-alerts/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/ruff-checked-D7FF64?logo=ruff&logoColor=261230)](https://docs.astral.sh/ruff/)
[![mypy: strict](https://img.shields.io/badge/mypy-strict-2A6DB2)](https://mypy-lang.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Reliable Telegram reminders before significant macroeconomic events, built from
public schedules published by the institutions that produce the releases.

> **Status:** BLS, BEA, and scheduled FOMC ingestion is implemented; reminder
> delivery and the Telegram bot are not released yet.

The project will turn a curated set of official release calendars into timely,
deduplicated Telegram notifications. It is intended for traders, researchers,
and engineers who want advance notice of scheduled macro events without keeping
a calendar tab open all day.

Version 0.1 deliberately starts with major United States events. Broader country
coverage will be added source by source only when provenance, timing semantics,
and reuse conditions are documented.

This project will be built in small, reviewable milestones. The repository is
public early so that its requirements, trade-offs, and implementation history
remain visible.

## Planned v0.1 capabilities

- no paid calendar API and no data-provider API key;
- curated coverage of BLS, BEA, and scheduled FOMC releases;
- reminders at configurable lead times, initially 24 hours, 60 minutes, and
  15 minutes;
- correct source-timezone handling, UTC normalization, and local-time display;
- explicit source, retrieval time, and timing-precision metadata;
- persistent delivery state so restarts do not duplicate notifications;
- Telegram Bot API delivery and a credential-free dry-run mode;
- a non-root Docker image, Docker Compose, health checks, and CI;
- deterministic tests that never depend on live government websites.

## Development

The project targets Python 3.12 or newer and uses a `src` package layout.
Bootstrap an isolated environment with the script for your platform.

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

Linux:

```bash
./scripts/bootstrap.sh
```

Both scripts create `.venv` and install the package with its development tools.
Run the same quality checks used by CI with the environment's Python.

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest
```

Linux:

```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy
.venv/bin/python -m pytest
```

These commands use only local fixtures and require no production integration
or secret.

## Implemented official-source ingestion

The BLS adapter reads only the official, credential-free BLS iCalendar feed and
selects CPI, Employment Situation, PPI, and JOLTS using a reviewed exact-alias
policy. It normalizes Eastern Time to UTC, retains official source links, and
keeps date-only events date-only.

Live retrieval requires a contactable `User-Agent`, validates the feed no more
than once every six hours by default, uses HTTP cache validators, and can reuse a
stale local cache during a temporary failure. Parser and transport tests are
fully offline. See the [BLS adapter policy](docs/bls-adapter.md) for source,
alias, attribution, and operational details.

The BEA adapter reads only the official full release schedule. It selects
national GDP and Personal Income and Outlays/PCE News releases using reviewed
prefix aliases, rejects layout drift, converts Eastern Time to UTC, and retains
an official BEA release or schedule link. Its transport follows the same
contactable, cached, conditional-request model. See the
[BEA adapter policy](docs/bea-adapter.md) for the exact source and contract.

The FOMC adapter reads only the official Federal Reserve meeting calendar and
creates a policy-statement event at 2:00 p.m. Eastern plus a Chair press
conference event at 2:30 p.m. Eastern for each regular meeting. Future calendar
dates stay marked as tentative, published source links are retained, and
unscheduled decisions are explicitly outside v0.1. See the
[FOMC adapter policy](docs/fomc-adapter.md) for the documented timing rule and
scope.

## Initial official sources

| Institution | Planned v0.1 coverage | Public schedule |
| --- | --- | --- |
| U.S. Bureau of Labor Statistics | CPI, Employment Situation, PPI, JOLTS | BLS online calendar and ICS feed |
| U.S. Bureau of Economic Analysis | GDP, Personal Income and Outlays/PCE | BEA release schedule |
| Federal Reserve Board | Scheduled FOMC statements and press conferences | Federal Reserve calendar and FOMC meeting calendar |

The word **significant** reflects a version-controlled project policy, not an
official rating supplied by these institutions. Every notification will link to
its source.

## Explicit non-goals

Version 0.1 will not:

- predict market direction, volatility, or the result of a release;
- generate trade entries, exits, position sizing, or execution commands;
- provide market consensus forecasts or proprietary importance scores;
- scrape third-party calendar websites;
- silently infer an exact release time from a date-only announcement;
- provide high availability across multiple replicas.

Notifications are calendar reminders, not trading signals or financial advice.

## Project documents

- [Product brief](docs/product-brief.md)
- [Normalized event model and fixture contract](docs/event-model.md)
- [BLS adapter source and retrieval policy](docs/bls-adapter.md)
- [BEA adapter source and retrieval policy](docs/bea-adapter.md)
- [Scheduled FOMC adapter policy](docs/fomc-adapter.md)
- [Official source catalog](docs/source-catalog.md)
- [Roadmap](docs/roadmap.md)
- [ADR 0001: official-source portfolio](docs/adr/0001-official-source-portfolio.md)

## Planned architecture

```text
Official source adapters
          |
          v
Normalized MacroEvent -> significance policy -> reminder policy
                                                   |
                                                   v
                                             delivery ledger
                                                   |
                                                   v
                                          Telegram notifier
```

Each institution gets a small adapter. Source payloads do not leak into domain
or scheduling code, and recorded fixtures keep tests independent of live sites.

## Development status

The public roadmap is the source of truth. Each milestone must end with a
demonstrable result and acceptance criteria; implementation details may change
as evidence appears.

## License

The project code is licensed under the MIT License. Official source material
remains subject to each institution's policies and attribution requirements.
