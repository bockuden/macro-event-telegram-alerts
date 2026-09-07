# Security policy

## Supported versions

Security fixes are applied to the current `main` branch and the latest release.
This is an early project; no older release lines are maintained.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability and do not include a
Telegram bot token, chat ID, local configuration, cache, or SQLite ledger in a
report. Use GitHub's private vulnerability reporting for this repository. If it
is unavailable, contact the maintainer through their GitHub profile and share
only the minimum sanitized reproduction needed to understand the problem.

Include the affected revision, a concise impact description, reproduction steps,
and any safe mitigation. The maintainer will acknowledge the report, assess the
scope, and coordinate a fix before public disclosure.

## Secret handling

The bot token and recipient chat ID belong only in the local `.env` file or an
equivalent secret store. Both are excluded from Git and Docker build context.
Rotate a token with BotFather if it is ever pasted into a commit, issue, log, or
chat. Treat a copied SQLite delivery ledger as sensitive operational metadata:
it records event identifiers and delivery outcomes.
