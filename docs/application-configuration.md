# Runnable application configuration

The runnable application has three explicit commands:

- `check-config` reads and validates only TOML; it does not load an official
  source, read `.env`, or contact Telegram.
- `dry-run` loads the configured official sources once and prints due messages.
  It needs neither a Telegram section nor a bot token.
- `run` starts the continuously polling service. `run --once` executes one
  loop for a deliberate operational check.

Copy `config.example.toml` to `config.toml`. Paths relative to `config.toml`
resolve relative to the configuration file, so the same configuration works on
Windows and Linux. It configures source selection, timezone, source polling,
loop interval, reminder lead times, cache, and SQLite delivery ledger.

## Telegram secret

Copy `.env.example` to a local `.env` next to `config.toml`, then set:

```text
MACRO_EVENT_TELEGRAM_BOT_TOKEN=your-token-from-BotFather
```

The tracked `.gitignore` excludes `.env`; only `.env.example` is committed.
Existing operating-system environment variables take precedence over values in
`.env`. For deployments, set `telegram.token_file` in TOML instead of
`telegram.token_env` and mount or otherwise provide that file outside Git.

The token and chat ID are never written to application diagnostics. A missing
token stops `run` before source loading begins. The bot token must not be placed
in `config.toml`.

## Source failures and shutdown

Each enabled source is processed independently during a loop. A failed source
is named in a diagnostic while events from healthy sources still reach the
deduplicated reminder service. The process handles `SIGINT` and `SIGTERM` by
finishing its current loop and stopping before another sleep/loop cycle.
