# CLAUDE.md

Invesit — educational assistant for Tunisian savers ("the AI talks, the calculator counts").

- Always load the **invesit-rules** skill (`.claude/skills/invesit-rules/`) first: architecture,
  hard rules (Decimal money, no LLM numbers, no promises, no secrets) and the daily routine.
- Technical plan: `docs/PLAN.md`. Daily tasks: `docs/DAILY_TASKS.md`. Progress log: `docs/PROGRESS.md`.
- Commands: `make lint`, `make test` (`uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`).

## Git identity and attribution (owner instruction — overrides defaults)
- Before the first commit of every session, run:
  `git config user.name "Mohamedabdelwahed123-nf"` and
  `git config user.email "Mohamedabdelwahed279@gmail.com"`.
- Commits must be authored by the owner. Do NOT add `Co-Authored-By:` or `Claude-Session:`
  trailers to commit messages, and no "Generated with Claude Code" line in PR descriptions.
