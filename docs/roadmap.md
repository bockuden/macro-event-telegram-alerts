# Roadmap

The roadmap is organized as issue-ready milestones. After the repository is
published, each item should become a GitHub issue and be closed by a focused
pull request or documented direct commit.

Version 0.1 intentionally covers significant United States events from BLS,
BEA, and the Federal Reserve. International coverage follows after the first
release, one documented official institution at a time.

## 1. Bootstrap the Python package and quality gates

**Outcome:** an installable empty package with Python 3.12 metadata.

Acceptance criteria:

- `pyproject.toml` defines runtime and development dependencies;
- Ruff, mypy, and pytest commands are documented;
- a minimal CI workflow runs all three checks;
- no production integration or secret is required.

## 2. Define the normalized event model and fixture provider

**Outcome:** official-source events can be represented and tested offline.

Acceptance criteria:

- `MacroEvent` uses aware source-local and UTC timestamps;
- institution, source URL, retrieval time, and timing precision are retained;
- significance is a separate project policy field;
- a JSON fixture provider supports fixed-clock tests;
- malformed and ambiguous timestamp cases have tests.

## 3. Add the BLS iCalendar adapter

**Outcome:** significant BLS release schedules are ingested without credentials.

Acceptance criteria:

- the official BLS ICS feed is the only live input;
- CPI, Employment Situation, PPI, and JOLTS are selected by reviewed aliases;
- polling, caching, User-Agent, and attribution follow documented BLS policies;
- parser tests use minimal recorded fixtures and never access BLS in CI.

## 4. Add the BEA release-schedule adapter

**Outcome:** GDP and Personal Income and Outlays/PCE dates are normalized.

Acceptance criteria:

- only the official BEA release schedule is queried;
- relevant releases are selected by explicit aliases;
- layout drift fails visibly instead of producing guessed events;
- attribution and source links are preserved;
- contract tests use a recorded minimal HTML fixture.

## 5. Add the scheduled FOMC calendar adapter

**Outcome:** scheduled policy statements and press conferences are represented.

Acceptance criteria:

- meeting dates come from official Federal Reserve calendars;
- statement and press-conference times follow explicit official documentation;
- unscheduled decisions are declared outside v0.1 scope;
- Eastern Time daylight-saving conversion has boundary tests;
- source links and timing precision are preserved.

## 6. Implement reminder policy and persistent deduplication

**Outcome:** reminders remain predictable across restarts and reschedules.

Acceptance criteria:

- reminder lead times are configurable;
- SQLite records source occurrence and reminder identity;
- late discovery sends only the closest useful due reminder;
- restart, reschedule, TBA, and failed-delivery cases have tests.

## 7. Deliver Telegram messages and provide dry-run mode

**Outcome:** the same reminder can be inspected locally or sent to Telegram.

Acceptance criteria:

- Telegram Bot API calls have bounded timeouts;
- messages include local time, institution, event, source, and timing quality;
- project significance is not presented as an official institution rating;
- tokens and chat IDs never appear in logs;
- dry-run requires no credentials.

## 8. Package the service for Docker operation

**Outcome:** one documented Compose command runs the service continuously.

Acceptance criteria:

- the image uses an unprivileged user;
- SQLite state and source cache use persistent storage;
- health status reflects a recent successful service loop;
- a container smoke test runs in CI.

## 9. Harden documentation and operational behavior

**Outcome:** a new user can evaluate and operate the project responsibly.

Acceptance criteria:

- README includes setup, configuration, dry-run, sources, and troubleshooting;
- SECURITY and CONTRIBUTING documents are present;
- retry policy distinguishes transient and permanent failures;
- the source catalog matches every shipped live adapter;
- logs support diagnosis without exposing secrets.

## 10. Validate and publish v0.1.0

**Outcome:** a reproducible first release with an honest capability statement.

Acceptance criteria:

- clean-machine fixture and live end-to-end checks are recorded;
- changelog and release notes list coverage and limitations;
- Docker image and source tag reference the same version;
- no paid data credential is required;
- the profile README links to the released project.

## Post-v0.1 candidates

- ECB, Bank of England, and Bank of Japan official schedule adapters;
- post-release actual values from documented official data APIs;
- Prometheus metrics and dead-man heartbeat integration;
- hosted subscriptions only after user and source-policy validation;
- PostgreSQL claiming for intentionally multi-replica deployments.

