# Official source catalog

This catalog is the review gate for live adapters. A source is not eligible for
release merely because its page is publicly accessible.

## U.S. Bureau of Labor Statistics

- **Planned events:** CPI, Employment Situation, PPI, JOLTS
- **Schedule:** https://www.bls.gov/schedule/news_release/
- **ICS feed:** https://www.bls.gov/schedule/news_release/bls.ics
- **Authentication:** none
- **Planned adapter:** iCalendar
- **Reuse note:** BLS states that its published material is public domain, with
  limited exceptions for previously copyrighted media, and asks users to cite BLS.
- **Operational note:** BLS prohibits excessive automated retrieval. The adapter
  must poll conservatively, cache responses, and use a contactable User-Agent.

References:

- https://www.bls.gov/opub/copyright-information.htm
- https://www.bls.gov/bls/blsterms.htm

## U.S. Bureau of Economic Analysis

- **Planned events:** GDP releases; Personal Income and Outlays/PCE
- **Schedule:** https://www.bea.gov/news/schedule
- **Authentication:** none for the public release schedule
- **Planned adapter:** HTML schedule parser
- **Reuse note:** retain BEA attribution and the official release URL. Recheck
  applicable BEA website policies before a production or commercial release.
- **Operational note:** the live parser must use bounded polling and a recorded
  fixture; a layout change must fail visibly rather than emit guessed events.

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

