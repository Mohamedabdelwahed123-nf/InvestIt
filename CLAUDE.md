# CLAUDE.md

Invesit — educational assistant for Tunisian savers ("the AI talks, the calculator counts").

- Always load the **invesit-rules** skill (`.claude/skills/invesit-rules/`) first: architecture,
  hard rules (Decimal money, no LLM numbers, no promises, no secrets) and the daily routine.
- Technical plan: `docs/PLAN.md`. Daily tasks: `docs/DAILY_TASKS.md`. Progress log: `docs/PROGRESS.md`.
- Commands: `make lint`, `make test` (`uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`).
