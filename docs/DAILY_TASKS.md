# Invesit — Daily scheduled tasks (Days 1–10, backend only)

Copy one prompt per day into the scheduled Claude Code task.
Merge each day's PR before the next run starts.

## Day 1 — Foundation
```
Use the invesit-rules skill. Day 1 task: project foundation.
- Create the layout from docs/PLAN.md: backend/{calculator/core, agents, safety, api, data, db,
  tests/{unit,integration,evals}}, frontend/ (empty placeholder with a README).
- pyproject.toml with uv; ruff + pytest + pytest-cov + hypothesis configured; a Makefile or justfile
  with lint / test / up commands.
- docker-compose.yml: Postgres 16 with pgvector (pgvector/pgvector:pg16) and self-hosted Langfuse.
- backend/config.py with pydantic-settings (DATABASE_URL, LLM_PROVIDER, LLM_MODEL,
  LLM_MODEL_CHEAP, Langfuse keys); .env.example; make sure .env is gitignored.
- GitHub Actions CI: ruff + pytest on every PR.
- Create docs/PROGRESS.md and CLAUDE.md (short: points to the invesit-rules skill and docs/PLAN.md).
  docs/PLAN.md already exists: keep it, only update it if something changed.
- Real README (short FR + EN): what Invesit is, the "AI talks, calculator counts" principle, how to run.
- A smoke test that imports config and passes.
Done when: `uv run pytest` passes, ruff is clean, CI file is valid.
```

## Day 2 — Database and data layer
```
Use the invesit-rules, postgres-patterns and database-migrations skills. Day 2 task: database,
migrations, data loading, repository.
- SQLAlchemy 2.0 models exactly as in docs/PLAN.md (funds, nav_prices, data_flags).
- Alembic set up; first migration also enables the pgvector extension.
- backend/data/sample/: a SAMPLE CSV (clearly labelled synthetic; at least 2 funds per category,
  2+ years of daily NAV generated plausibly) + a README saying it must be replaced by real CMF data.
- backend/data/load_csv.py: validated loader (positive NAV, no duplicate dates, known category,
  parsable dates), clear error messages for bad rows, idempotent upserts.
- backend/db/repository.py: FundRepository (list_funds, get_fund, get_nav_history(fund_id, start, end),
  get_category_funds) behind an interface, plus an in-memory fake for tests.
- Unit tests for validation; integration tests for loader + repository.
Done when: migrations run, sample data loads, tests pass.
```

## Day 3 — Calculator part 1: money and statistics
```
Use the invesit-rules, tdd-workflow and python-testing skills. Day 3 task: the no-AI calculator
core, part 1. Strict TDD: write the tests first, see them fail, then implement.
- calculator/core/money.py: Decimal helpers, TND rounding to 3 decimals, safe percentage operations.
- calculator/core/stats.py: from a NAV series compute period returns, annualised return,
  annualised volatility, max drawdown, worst 12-month return; and the same aggregated per category.
  Handle gaps, too-short series (clear error), non-trading days.
- Frozen output models (FundStats, CategoryStats).
- No DB or AI imports inside calculator/core: data in, results out.
Done when: coverage of calculator/core >= 90%, edge cases tested.
```

## Day 4 — Calculator part 2: plans and simulation
```
Use the invesit-rules, tdd-workflow and python-testing skills. Day 4 task: the no-AI calculator
core, part 2. Strict TDD.
- calculator/core/plans.py: make_plan(amount, months, risk_tolerance, has_emergency_fund,
  profile: cautious|growth) -> Plan with allocations per category, following the rules in
  docs/PLAN.md. Document the exact rules you implement back into docs/PLAN.md.
- calculator/core/simulate.py: simulate(plan, months, history) -> bad/average/good outcomes
  (p10/p50/p90 over historical rolling windows of that length). Deterministic, no randomness.
- Property-based tests with hypothesis: allocations always sum exactly to amount, no negative
  parts, all rules respected.
- Scenario test: 1,000 TND, 12 months, "a bit" worried by a 10% drop -> two different valid plans.
Done when: all invariants pass, coverage >= 90%.
```

## Day 5 — MCP server
```
Use the invesit-rules and mcp-builder skills. Day 5 task: expose the calculator as an MCP server.
- backend/calculator/mcp_server.py with the official MCP Python SDK (FastMCP), 4 tools:
  make_plan, simulate, fund_stats, get_nav_history.
- Pydantic input schemas with validation (amount > 0 with a sane max, months 1–360, known enums);
  Decimal values serialised as strings; clear tool errors, no stack traces.
- Tools use the Day 2 repository through dependency injection (fake repository in tests).
- Integration tests that start the server and call every tool through an MCP client.
- README section: how to run the server and connect an MCP client.
Done when: all 4 tools work end to end against the sample data.
```

## Day 6 — Agents part 1: state, intake, calculation
```
Use the invesit-rules, langchain-build-agent and ai-regression-testing skills. Day 6 task:
LangGraph agents, part 1.
- agents/llm.py: provider-agnostic model factory reading LLM_PROVIDER / LLM_MODEL / LLM_MODEL_CHEAP
  (strong model for the moderator, cheap model for the debaters). The provider is not chosen yet.
- agents/state.py: TypedDict state (amount, months, has_emergency_fund, risk_tolerance,
  plan_cautious, plan_growth, sims, arguments, draft, final_answer, rewrites, messages).
- intake node: the moderator extracts fields with structured output (pydantic); if any is missing it
  asks ONE clear question via LangGraph interrupt(). Handles French and English.
- calculate node: calls the MCP tools via langchain-mcp-adapters, stores plans + simulations in state.
- agents/graph.py wiring; prompts as separate files in agents/prompts/.
- agents/cli.py to chat in the terminal.
- Tests with a fake LLM (no API key): missing info -> question asked; complete info -> calculator called.
Done when: the graph runs up to the calculation step in tests.
```

## Day 7 — Agents part 2: debate, moderator, safety
```
Use the invesit-rules, langchain-build-agent and ai-regression-testing skills. Day 7 task:
LangGraph agents, part 2.
- cautious_agent and growth_agent nodes in parallel (fan-out / fan-in); each sees ONLY the tool
  outputs and must argue using only those numbers.
- moderator_summary node: explains the trade-off simply, gives NO recommendation or verdict.
- backend/safety/rules.py: every number in the draft must appear in the tool outputs (normalise
  formats); block promise words in EN/FR (guaranteed, garanti, sans risque, sure profit...);
  disclaimer always appended. On failure loop back to moderator_summary, max 2 rewrites, then a
  safe template answer.
- Langfuse callback on every node (no-op when keys are absent).
- End-to-end tests with a fake LLM: happy path, invented-number rejection, promise rejection,
  rewrite limit.
Done when: the 1,000 TND scenario runs fully in tests; document how to run the CLI with a real key.
```

## Day 8 — HTTP API
```
Use the invesit-rules, fastapi-patterns and api-design skills. Day 8 task: FastAPI backend API.
- backend/api/main.py: POST /chat {session_id, message} streaming via SSE (node progress + final
  answer), GET /funds, GET /funds/{id}/stats, GET /health.
- Conversation memory with the LangGraph Postgres checkpointer keyed by session_id.
- Consistent response envelope {success, data, error}; pydantic request validation; CORS config;
  simple rate limiting; no stack traces or secrets in errors.
- OpenAPI docs usable as a demo before the frontend exists.
- API tests with httpx and a fake LLM, including the multi-turn question/answer flow.
Done when: the full flow works through the API and Swagger.
```

## Day 9 — Real data and RAG
```
Use the invesit-rules, pdf, langchain-build-agent and postgres-patterns skills. Day 9 task:
real data ingestion and RAG.
- backend/data/cmf_parser.py: parse a CMF fund bulletin PDF placed in backend/data/raw/ into NAV rows.
  If no PDF is present, build the parser against a documented expected format and leave a clear TODO.
- Second-source check: compare overlapping NAVs from two sources; write gaps > 1% to data_flags.
- RAG: ingest prospectus PDFs from backend/data/prospectuses/ into pgvector (chunking + a
  provider-agnostic embedding factory); a retrieve tool that returns passages WITH citations
  (document, page).
- The moderator can call retrieve for definitions and must cite sources; the safety check accepts
  cited text.
- Tests: parser (fixtures), flagging logic, chunking, retrieval (fake embeddings).
Done when: ingestion + retrieval are tested; PROGRESS.md lists the real files the owner must provide.
```

## Day 10 — LLM judge, evals and hardening
```
Use the invesit-rules, security-review and verification-loop skills. Day 10 task: quality, evals,
hardening.
- backend/safety/llm_judge.py: second-layer judge after the rules, checking for advice/verdicts,
  promises and unsupported claims; configurable on/off.
- backend/tests/evals/: 30 YAML scenarios (amounts, horizons, FR/EN, missing info, users pushing
  for "what should I buy", trick prompts asking for guarantees). Metrics: invented numbers = 0,
  promises = 0, verdicts = 0, question asked when info is missing. Runner in pytest, optional upload
  to a Langfuse dataset.
- Full backend review: dead code, error handling, input validation, secrets, function size;
  fix CRITICAL/HIGH issues.
- Update README (FR/EN) and docs/PLAN.md ("Next: frontend"). Write docs/EVALS.md with results.
Done when: evals run, report written, all tests and CI green.
```

## After Day 10
Frontend tasks (Next.js chat streaming from /chat, the 2 plans, bad/average/good chart) using the
frontend-design and webapp-testing skills, then the demo video and README polish.
