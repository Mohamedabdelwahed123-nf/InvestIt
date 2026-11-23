---
name: invesit-rules
description: Project rules, architecture and daily routine for Invesit (InvestIt repo). Use at the start of every task in this repo, especially scheduled daily build tasks.
---

# Invesit rules

## What the project is
Educational assistant for Tunisian savers. A user says "I have 1,000 TND", Invesit asks the
missing questions, a no-AI calculator builds 2 plans (Cautious vs Growth) with bad/average/good
simulations, two AI agents debate them, a moderator explains the trade-off, a safety check filters
the answer. It never gives a verdict and never handles money. Tunisia only.

Build order: backend first (Python), frontend (Next.js) last. Full plan: docs/PLAN.md.
Daily tasks: docs/DAILY_TASKS.md. Progress log: docs/PROGRESS.md.

## Architecture (do not break)
- backend/calculator/ : plain Python + Decimal, NO AI, NO DB imports in core/. Exposed as an
  MCP server with 4 tools: make_plan, simulate, fund_stats, get_nav_history.
- backend/agents/ : LangGraph graph — moderator (strong model), cautious + growth agents
  (cheap model, parallel), safety check with max 2 rewrites.
- backend/safety/ : rules first (numbers must come from tool outputs, no promise words), LLM judge later.
- backend/api/ : FastAPI (POST /chat with SSE, GET /funds, GET /funds/{id}/stats, GET /health).
- backend/db/ : Postgres 16 + pgvector, SQLAlchemy 2.0 + Alembic. Langfuse for traces.
- LLM provider is NOT chosen yet: read LLM_PROVIDER / LLM_MODEL from config; tests use a fake LLM.

## Hard rules
1. Money is Decimal, never float. TND rounded to 3 decimals (millimes).
2. The LLM never produces numbers; only calculator tools do. Agents may only quote tool outputs.
3. No promises ("guaranteed", "garanti", "sans risque"); every answer ends with a disclaimer
   ("estimate, not advice").
4. Never invent real fund data. Sample data lives in backend/data/sample/ and is labelled SAMPLE.
5. No secrets in code; config via .env (keep .env.example updated).
6. Tests first for the calculator. Coverage >= 90% for calculator/core, >= 80% overall.
7. Validate every input at boundaries (MCP tools, API) with pydantic; no stack traces to users.
8. Functions < 50 lines, files < 400 lines typical, no deep nesting, immutable data where practical.

## Tooling
Python 3.12, uv, ruff, pytest (+ pytest-cov, hypothesis), Docker Compose.
- Lint: `uv run ruff check .` and `uv run ruff format --check .`
- Tests: `uv run pytest`
- If Docker/Postgres is unavailable in this environment, DB tests must skip cleanly with a reason.

## Useful skills in this repo
- mcp-builder: building the calculator MCP server.
- langchain-build-agent: LangGraph agents, interrupts, checkpointers, RAG.
- pdf: parsing CMF bulletins and fund prospectuses.
- tdd-workflow, python-testing: calculator (tests first).
- postgres-patterns, database-migrations: schema, Alembic, pgvector.
- fastapi-patterns, api-design: the HTTP API.
- ai-regression-testing: testing the agents with a fake LLM.
- security-review, verification-loop: final review before a PR.

## Daily routine
1. Read docs/PLAN.md, docs/PROGRESS.md and today's section of docs/DAILY_TASKS.md.
2. If the previous day's work is unfinished or its tests fail, fix that first.
3. Create branch day-<N> from main. Commit in logical steps with conventional commits
   (feat:, fix:, test:, chore:, docs:, refactor:).
4. Before finishing: ruff clean and pytest green (or skips explained).
5. Push the branch and open a PR describing what changed and how it was tested.
6. Append to docs/PROGRESS.md: day, what was done, test results, what is left,
   decisions the owner must make.
