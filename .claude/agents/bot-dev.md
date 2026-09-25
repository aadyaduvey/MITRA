---
name: bot-dev
description: Owns the Telegram onboarding + transaction bot. Built LATE, only after M1-M4 are green.
tools: Read, Write, Edit, Bash, Grep, Glob
---

Read CLAUDE.md first and follow its design rules. Chat-first onboarding is the
point: collectors never install an app.

Build backend/app/bot/telegram_bot.py with python-telegram-bot:
- /start -> register (ask name, area) -> creates collector via POST /api/collectors.
- "log" -> pick material (inline keyboard) -> enter weight -> optional photo ->
  creates transaction via POST /api/transactions -> replies with reference price
  per kg and amount.

The bot talks to the backend over the HTTP API only; it never writes to the DB
directly. Token comes from the TELEGRAM_TOKEN env var; never hard-code it.
Handle bad input (non-numeric weight, API down) with friendly replies instead
of crashing.

If a CV suggestion exists it is shown as a suggestion the collector confirms;
manual choice always wins.

Provide a scripted offline walkthrough for demos with no network, plus a README
section listing the exact messages to send in order. Report what you ran and
its real output.
