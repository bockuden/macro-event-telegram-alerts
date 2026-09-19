# ADR 0003: Official Census retail calendar

The first Census integration uses the official [Economic Indicator Release
Schedule](https://www.census.gov/economic-indicators/calendar-listview.html),
not a third-party calendar or API. It selects only **Advance Monthly Sales for
Retail and Food Services**, which the Census schedule publishes with a date and
8:30 a.m. Eastern release time. The adapter stores the official calendar URL,
normalizes Eastern time to UTC, and assigns the project policy revision
`census-retail-v1`.

The HTML schedule is cached with the same poll interval, rejection cooldown,
backoff, and stale-cache limits as the other official sources. The parser is
fixture-tested because live government pages are not used in CI. Additional
Census families remain out of scope until their timing and provenance are
reviewed separately.
