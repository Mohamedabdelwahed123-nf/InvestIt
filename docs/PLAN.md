# Invesit — Technical Plan

## Goal
An educational assistant for Tunisian savers. It explains and compares two investment plans
(Cautious vs Growth) for a given amount and horizon. It never recommends, never promises returns,
and never handles money — the user invests on their own at a licensed CMF provider.

## Core principle
**The AI talks, the calculator counts.** Every number shown to the user comes from plain Python
with `Decimal`. Language models only explain and argue using tool outputs.

## What users can invest in (the app's menu, safest to riskiest)
1. Bond SICAV (obligataire) — stable, withdraw anytime, emergency money / under 1 year
2. National bond loan (emprunt obligataire national) — fixed interest, locked for years, only when a tranche is open
3. Mixed SICAV (mixte) — half bonds, half shares, 1–5 years
4. Equity SICAV / FCP (actions) — mostly Tunisian shares, 5+ years
5. Individual stocks (Bourse de Tunis) — explained only, never allocated in plans

Not covered: ETFs (none in Tunisia), crypto, foreign markets.

## Architecture
```
Client (CLI / Swagger now, Next.js last)
        │  POST /chat (SSE)
        ▼
FastAPI  ──►  LangGraph
               intake (moderator, strong model) ──interrupt──► asks missing questions
               calculate ──MCP──► calculator server (no AI)
               cautious_agent ┐ parallel (cheap model)
               growth_agent   ┘
               moderator_summary (trade-off, no verdict)
               safety_check (rules → LLM judge) ── fail → rewrite (max 2)
                                                   │
Calculator MCP server: make_plan · simulate · fund_stats · get_nav_history
        ▼
Postgres 16: funds, nav_prices, data_flags, LangGraph checkpoints
pgvector:   prospectus chunks (RAG with citations)
Langfuse:   traces, cost, evals
```

## Stack
Python 3.12 · uv · ruff · pytest + hypothesis · FastAPI · LangGraph · MCP Python SDK (FastMCP)
· langchain-mcp-adapters · SQLAlchemy 2.0 + Alembic · Postgres 16 + pgvector · Langfuse
· Docker Compose · GitHub Actions. Frontend: Next.js (last).
LLM provider: not chosen yet — configured through `LLM_PROVIDER` / `LLM_MODEL`.

## Repository layout
```
backend/
  calculator/core/   money.py, stats.py, plans.py, simulate.py   (pure, no DB, no AI)
  calculator/        repository adapter, mcp_server.py
  agents/            llm.py, state.py, graph.py, nodes/, prompts/, cli.py
  safety/            rules.py, llm_judge.py
  api/               main.py, routes/, schemas.py
  data/              sample/, load_csv.py, cmf_parser.py, raw/, prospectuses/
  db/                models.py, repository.py, migrations/
  tests/             unit/, integration/, evals/
frontend/            Next.js (last)
docs/                PLAN.md, DAILY_TASKS.md, PROGRESS.md, EVALS.md
docker-compose.yml
```

## Data model
- `funds(id, code UNIQUE, name, manager, category, currency DEFAULT 'TND')`
  category ∈ bond_sicav | national_bond | mixed_sicav | equity_sicav | equity_fcp
- `nav_prices(fund_id, date, nav NUMERIC(18,6), source)` UNIQUE(fund_id, date)
- `data_flags(fund_id, date, issue, created_at)`

## Calculator rules (first version — exact rules in "Calculator plans" below)
- No emergency fund → that part goes to bond SICAV first.
- Horizon < 12 months → no equity.
- National bond loan only when the horizon is long enough to lock the money.
- Growth profile shifts towards mixed/equity within the user's risk tolerance.
- Individual stocks are never allocated.
- Allocations always sum exactly to the amount; no negative parts.
- Simulation: p10 / p50 / p90 over historical rolling windows of the horizon (deterministic).

## Calculator statistics (Day 3, `calculator/core/stats.py`)
- Money: `Decimal` only (floats refused), TND rounded half-up to 3 decimals; rates are fractions
  rounded half-up to 6 decimals. `allocate()` splits by weights with largest remainder so the
  parts always sum exactly to the amount.
- A NAV series holds trading days only; weekends/holidays are absent and returns are taken
  between consecutive observations. Duplicate dates or NAV <= 0 are errors.
- Time is calendar time, 1 year = 365.25 days.
- Annualised return = (last/first)^(365.25/days) - 1.
- Annualised volatility = sample std of observation returns x sqrt(returns / (days/365.25)).
- Max drawdown = worst fall from the running peak (<= 0).
- Worst 12-month return = min over observations >= 12 months after start of NAV / (last NAV on
  or before the same day 12 months earlier) - 1; `None` if the series is shorter than 12 months.
- Gap = more than 7 calendar days between observations (reported, not an error).
- `fund_stats` needs >= 20 observations (`InsufficientDataError` otherwise).
- Category stats = equal-weight mean of annualised return and volatility, worst max drawdown and
  worst 12-month return across the category's funds.

## Calculator plans (Day 4, `calculator/core/plans.py`)
`make_plan(amount, months, risk_tolerance, has_emergency_fund, profile, *, national_bond_open=False)`
- Inputs: amount > 0 TND (≤ 3 decimals), months 1–600 (whole number), risk_tolerance
  `low` (a 10% drop would worry me a lot) | `medium` (a bit) | `high` (not much),
  profile `cautious` | `growth`, booleans for the emergency fund and an open national bond tranche.
- No emergency fund → 30% of the amount goes to bond SICAV first, as a separate `emergency` line.
  The profile weights apply to the remaining investable part.
- Base weights (bond SICAV / mixed SICAV / equity SICAV, % of the investable part):

  | Horizon | Cautious | Growth |
  |---|---|---|
  | < 12 months | 100 / 0 / 0 | 100 / 0 / 0 |
  | 12–35 months | 80 / 20 / 0 | 50 / 40 / 10 |
  | 36–59 months | 60 / 30 / 10 | 30 / 40 / 30 |
  | ≥ 60 months | 50 / 30 / 20 | 20 / 30 / 50 |
- Equity exposure = equity + ½ mixed. Cap by risk tolerance: low 15, medium 35, high 65 (% of the
  investable part); the cautious profile gets half of that cap. Over the cap, equity moves to bond
  SICAV first, then mixed (2 points of mixed per point of exposure).
- National bond loan only if months ≥ 60 **and** a tranche is open: it takes half of the
  investment bond share. The emergency reserve is never locked in it.
- Plans use bond_sicav, national_bond, mixed_sicav, equity_sicav only (equity FCPs and individual
  stocks are never allocated). Amounts are split with `allocate` (exact millimes).
- Guarantees (hypothesis-tested): parts sum exactly to the amount, no negative part, percents sum
  to 100, cautious exposure ≤ growth exposure, and for horizons ≥ 12 months the two plans differ.
- Each plan carries plain-text `notes` explaining which rules fired (for the agents to quote).

## Calculator simulation (Day 4, `calculator/core/simulate.py`)
`simulate(plan, months, history, *, min_windows=20)`
- `history` maps each category of the plan to one NAV series (`equal_weight_index` builds a
  buy-and-hold, base-100 equal-weight index of a category's funds on their common dates).
- A window ends on every observation date d (of any used series) with d ≤ the earliest series end
  and d − `months` calendar months (month-end clamped) ≥ the latest series start. Each category is
  valued at its last NAV on or before a day, so all lines share the same window.
- Window value = Σ line amount × NAV(d) / NAV(base). No rebalancing, fees or taxes.
- bad / average / good = p10 / p50 / p90 of the window values (linear interpolation), rounded to
  millimes; `return_rate` is a fraction with 6 decimals. No randomness.
- Fewer than `min_windows` windows (or none) → `InsufficientHistoryError` with a clear message.

## Phases
| Day | Phase | Done when |
|---|---|---|
| 1 | Foundation: layout, uv, ruff, pytest, Docker Compose, config, CI | pytest + ruff green |
| 2 | Database + data loader + repository | sample data loads, tests green |
| 3 | Calculator core 1: money + stats (TDD) | coverage ≥ 90% |
| 4 | Calculator core 2: plans + simulate (TDD, property tests) | invariants pass |
| 5 | MCP server with 4 tools | all tools callable end to end |
| 6 | Agents 1: LLM factory, state, intake, calculate, CLI | graph reaches calculation in tests |
| 7 | Agents 2: debate, moderator, safety rules, Langfuse | 1,000 TND scenario end to end |
| 8 | FastAPI: /chat SSE, funds, stats, health, checkpointer | full flow via API |
| 9 | Real data: CMF parser, 2nd-source check, RAG with citations | ingestion + retrieval tested |
| 10 | LLM judge, 30-scenario evals, hardening, docs | evals report, CI green |
| 11+ | Frontend (Next.js chat + charts), demo | — |

## Risks
- HIGH — CMF data is in PDFs: start with labelled sample data, real parser on Day 9.
- HIGH — LLM invents numbers: numbers-must-match-tool-outputs rule from Day 7, evals on Day 10.
- HIGH — looks like investment advice: no verdict, disclaimer always, never touches money.
- LOW — LLM cost: cheap models for debaters, tracked in Langfuse.
