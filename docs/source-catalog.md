# Official source catalog

This catalog is the review gate for live adapters. A source is not eligible for
release merely because its page is publicly accessible.

## U.S. Bureau of Labor Statistics

- **Implemented events:** CPI, Employment Situation, PPI, JOLTS
- **Schedule:** https://www.bls.gov/schedule/news_release/
- **ICS feed:** https://www.bls.gov/schedule/news_release/bls.ics
- **Authentication:** none
- **Adapter:** iCalendar, implemented with strict parsing and offline contract
  tests
- **Reuse note:** BLS states that its published material is public domain, with
  limited exceptions for previously copyrighted media, and asks users to cite BLS.
- **Operational note:** BLS prohibits excessive automated retrieval. The adapter
  requires a contactable User-Agent, validates no more than once every six hours
  by default, uses conditional requests, and persists a local cache.
- **Timing note:** floating calendar times are interpreted in
  `America/New_York`, matching the BLS calendar's Eastern Time convention;
  explicit UTC and date-only values remain distinguishable.

References:

- https://www.bls.gov/opub/copyright-information.htm
- https://www.bls.gov/bls/blsterms.htm
- https://www.bls.gov/help/hlpiCAL.htm
- [Detailed adapter policy](bls-adapter.md)

## U.S. Bureau of Economic Analysis

- **Implemented events:** national GDP releases; Personal Income and Outlays/PCE
- **Schedule:** https://www.bea.gov/news/schedule/full
- **Authentication:** none for the public release schedule
- **Adapter:** strict HTML schedule parser with offline contract tests
- **Reuse note:** BEA describes its information as public domain unless stated
  otherwise and appreciates attribution. Retain BEA attribution and the official
  release or schedule URL; do not imply agency endorsement.
- **Operational note:** the adapter requires a contactable User-Agent, validates
  no more than once every six hours by default, uses conditional requests, and
  persists a local cache. Reviewed table, row, and field structure must match.
- **Timing note:** schedule times are interpreted in `America/New_York`, following
  BEA's published Eastern Time release convention.

References:

- https://www.bea.gov/help/faq/147
- https://www.bea.gov/about/policies-and-information/linking
- [Detailed adapter policy](bea-adapter.md)

## Federal Reserve Board

- **Planned events:** scheduled FOMC statements and press conferences
- **Calendar:** https://www.federalreserve.gov/newsevents/calendar.htm
- **Meeting schedule:** https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
- **Authentication:** none
- **Planned adapter:** HTML calendar parser
- **Timing note:** the Federal Reserve states that scheduled policy statements
  are released at 2:00 p.m. Eastern Time on the second meeting day and the Chair's
  press conference starts at 2:30 p.m. The live calendar remains authoritative.
- **Operational note:** unscheduled or emergency decisions are outside v0.1.

Reference:

- https://www.federalreserve.gov/newsevents/pressreleases/monetary20240809a.htm

## Project significance policy

Official sources do not provide a uniform market-impact rating. Version 0.1 uses
a reviewed allowlist of event families and labels them `significant` as a project
classification. The label must be traceable to a configuration revision and must
not appear as a statement made by BLS, BEA, or the Federal Reserve.

## Adapter acceptance checklist

Before adding an institution, document:

- canonical source and event-detail URLs;
- access method and whether authentication is required;
- timezone and daylight-saving behavior;
- exact, tentative, date-only, and TBA representations;
- update frequency and rescheduling behavior;
- attribution and reuse requirements;
- respectful polling and caching policy;
- minimal sanitized fixtures and parser failure behavior.
