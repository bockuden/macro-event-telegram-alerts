# Contributing

Thanks for considering a contribution. The project favours small, reviewable
changes with deterministic tests over broad source coverage.

## Before opening a pull request

1. Discuss a substantial feature or new data source in an issue first.
2. Never commit `.env`, `config.toml`, a bot token, recipient chat ID, cache, or
   SQLite ledger.
3. Add focused tests using sanitized fixtures; tests must not call live sources
   or Telegram.
4. Run the local checks documented in the README: Ruff, mypy, and pytest.

## Adding an official source

Do not add a public web page merely because it is easy to scrape. An adapter
must use an official source and update the source catalog with provenance,
timezone semantics, polling/cache policy, reuse terms, fixture coverage, and
parser failure behaviour. Preserve the boundary between source parsing,
normalized events, reminder scheduling, and notification delivery.

## Pull requests

Keep each pull request narrowly scoped, explain user-visible behaviour and
limitations, and update operational documentation when commands, configuration,
or failure handling change. Maintainers may ask for a smaller follow-up PR when
a change combines unrelated concerns.
