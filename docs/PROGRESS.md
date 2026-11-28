# Invesit — Progress log

## Day 1 — Foundation (2026-11-24) ✅
**Branch:** `day-1`

### Done
- Repository layout from `docs/PLAN.md`: `backend/{calculator/core, agents, safety, api, data, db,
  tests/{unit,integration,evals}}` as Python packages; `frontend/` placeholder with a README.
- `pyproject.toml` managed by uv (Python 3.12, `uv.lock` committed); ruff (lint + format, `.claude/`
  excluded), pytest + pytest-cov (fail under 80%) + hypothesis; `db` and `llm` test markers.
- `Makefile` with `install`, `lint`, `format`, `test`, `up`, `down`.
- `docker-compose.yml`: `pgvector/pgvector:pg16` and self-hosted Langfuse v2 (own Postgres).
  All passwords/secrets come from `.env` (compose fails fast if they are missing).
- `backend/config.py` (pydantic-settings, frozen): `DATABASE_URL`, `LLM_PROVIDER` (default `fake`),
  `LLM_MODEL`, `LLM_MODEL_CHEAP`, `LLM_API_KEY`, Langfuse host/keys (`langfuse_enabled` only when
  both keys are set). Secrets are `SecretStr`. `.env.example` added; `.env` is gitignored.
- GitHub Actions CI (`.github/workflows/ci.yml`): `uv sync --locked`, ruff check, ruff format
  check, pytest on every PR and on pushes to `main`.
- `CLAUDE.md`, bilingual `README.md`, this file. `docs/PLAN.md` unchanged.

### Test results
- `uv run ruff check .` → all checks passed; `uv run ruff format --check .` → clean.
- `uv run pytest` → 4 passed, coverage 100% (`backend/config.py`).
- `docker compose --env-file .env.example config` → valid.
- Docker daemon is **not** available in the build environment, so the stack was not started.
  No DB tests exist yet; from Day 2 they will skip cleanly when Postgres is unreachable.

### What is left
- Day 2: SQLAlchemy models, Alembic + pgvector migration, SAMPLE data, loader, repository.

### Decisions for the owner
1. **LLM provider** — still open (`LLM_PROVIDER` accepts fake/anthropic/openai/mistral/google/ollama).
2. **Langfuse version** — compose uses Langfuse v2 (one container + Postgres) for simplicity.
   Langfuse v3 needs ClickHouse, Redis and S3/MinIO; say if you want v3 or Langfuse Cloud instead.
3. **Branch protection** — consider requiring the CI check on `main` before merging.

## Day 2 — Database and data layer (2026-11-25) ✅
**Branch:** `day-2`

### Done
- `backend/db/models.py`: SQLAlchemy 2.0 models for `funds` (code UNIQUE, category CHECK,
  currency default `TND`), `nav_prices` (`NUMERIC(18,6)`, UNIQUE(fund_id, date), CHECK nav > 0)
  and `data_flags` (fund_id, date, issue, created_at). Plain frozen domain types in
  `backend/db/domain.py` (`Category`, `Fund`, `FundRecord`, `NavRecord`, `NavPoint`).
- Alembic (`alembic.ini`, `backend/db/migrations/`): migration `0001` enables `vector` (pgvector)
  and creates the three tables; URL comes from `-x db_url=…` or `DATABASE_URL`, never from the ini.
  `alembic check` reports no drift between models and migration. `make migrate`.
- `backend/data/sample/`: SAMPLE synthetic data — 10 invented funds (2 per category, codes `SMP-`,
  names `SAMPLE …`), daily NAV Mon–Fri 2023-01-02 → 2025-12-31 (7,830 rows, `source = SAMPLE`),
  deterministic generator `generate.py`, README saying it must be replaced by real CMF data.
- `backend/data/load_csv.py`: pydantic-validated loader (positive NAV, Decimal from text only,
  max 6 decimals, ISO dates, known category, known fund code, no duplicate codes/dates, required
  columns). All bad rows reported as `file line N: reason`; nothing is written if any row fails.
  Idempotent upserts (`ON CONFLICT DO UPDATE`). CLI prints friendly errors, no tracebacks.
  `make load-sample`.
- `backend/db/repository.py`: `FundRepository` (list_funds, get_fund, get_nav_history(fund_id,
  start, end), get_category_funds) + `FundWriter` (upsert_funds, upsert_nav_prices) protocols;
  `SqlFundRepository` and `InMemoryFundRepository` (fake). Returns domain types, NAV as Decimal.
- Tests: unit (validation, sample data, models, CLI errors); integration contract tests that run
  the same cases against the fake and against Postgres; Postgres-only tests (migration + pgvector,
  downgrade/upgrade, DB constraints, CLI load).
- CI now runs a `pgvector/pgvector:pg16` service and sets `TEST_DATABASE_URL`, so DB tests run in CI.

### Test results
- `uv run ruff check .` → all checks passed; `uv run ruff format --check .` → clean.
- Without a DB: `uv run pytest` → 39 passed, 10 skipped ("TEST_DATABASE_URL is not set"), coverage 88%.
- With a local Postgres 16 + pgvector 0.6 (`TEST_DATABASE_URL` set) → 49 passed, coverage 97.8%.
  Docker containers could not be used here, so a local Postgres 16 cluster (+ apt pgvector) was
  started instead; `alembic upgrade/downgrade` and `load_csv` were run against it (loading twice
  keeps 10 funds / 7,830 NAV rows — idempotent).

### What is left
- Day 3: calculator core part 1 — `money.py` and `stats.py` (TDD, coverage ≥ 90%).
- `data_flags` table exists but nothing writes to it yet (Day 9 second-source check).

### Decisions for the owner
1. **Test database** — DB tests only run when `TEST_DATABASE_URL` points to a throwaway DB
   (tables are wiped). Locally: create e.g. `invesit_test` in the compose Postgres and set it in `.env`.
2. **Sample parameters** — synthetic yearly drift/volatility per category are invented
   (bond ≈ 7% / 0.3%, equity ≈ 8–9% / 12–17%). They only shape test data; tell me if you want
   other ranges. Real CMF data replaces them on Day 9.
3. Earlier open items still stand: LLM provider, Langfuse v2 vs v3, branch protection on `main`.

## Day 3 — Calculator part 1: money and statistics (2026-11-27) ✅
**Branch:** `day-3`

### Done
- Strict TDD: tests committed first (RED: collection failed on missing modules), then the
  implementation (GREEN). Commits show both steps.
- `backend/calculator/core/money.py`: `to_decimal` (refuses float, bool, NaN/Inf, bad text),
  `round_tnd` (half-up, 3 decimals), `round_rate` (6 decimals), `parse_amount` (> 0, ≤ 3 decimals),
  `percent_of`, `percent_to_fraction`, `fraction_to_percent`, `apply_rate` (refuses < -100%),
  `safe_divide`, and `allocate(amount, weights)` — largest-remainder split in millimes that always
  sums exactly to the amount (hypothesis property test). Ready for Day 4 plans.
- `backend/calculator/core/stats.py`: `validate_series`, `period_returns` (per observation,
  monthly, yearly), `total_return`, `annualised_return`, `annualised_volatility`, `max_drawdown`,
  `worst_rolling_return` (12 months by default, month-end clamping), `find_gaps`, `fund_stats`,
  `category_stats`. Frozen output models `FundStats`, `CategoryStats` (+ `PricePoint`,
  `PeriodReturn`, `Gap`). Accepts any object with `.date`/`.nav`, so the repository's `NavPoint`
  works without the core importing the DB. Exact formulas written into `docs/PLAN.md`.
- Edge cases tested: weekends/holidays, long gaps, duplicate dates, NAV ≤ 0, float NAV, empty /
  too-short series (`InsufficientDataError` with "needs at least N NAV observations, got M"),
  series shorter than 12 months (worst 12m = None), Feb 29, mixed categories, empty category.
- `test_calculator_purity.py`: AST check that `calculator/core` imports nothing from DB, agents,
  API, SQLAlchemy, LLM SDKs, HTTP or `random`, and never builds a float.

### Test results
- `uv run ruff check .` → all checks passed; `uv run ruff format --check .` → clean.
- `uv run pytest` → 134 passed, 10 skipped (Postgres tests: "TEST_DATABASE_URL is not set" —
  no Docker/Postgres in this build environment; they run in CI). Total coverage 92.9%;
  `calculator/core/money.py` 100%, `calculator/core/stats.py` 100%.
- Sanity run on SAMPLE data: bond SICAV ≈ 7.5%/yr with 0.4% volatility; equity SICAV ≈ -0.8%/yr
  with 13.9% volatility and -24.7% worst drawdown (synthetic numbers, not real funds).

### What is left
- Day 4: `plans.py` (make_plan) and `simulate.py` (p10/p50/p90 over rolling windows), property
  tests, 1,000 TND / 12 months scenario.

### Decisions for the owner
1. **Statistic conventions** — 365.25-day year, sample std, volatility annualised by the observed
   frequency, gap threshold 7 days, minimum 20 observations per fund, category = equal-weight mean
   + worst case. Say if you prefer e.g. 252 trading days or a category index series instead.
2. **Rounding** — TND half-up (not banker's rounding). Confirm this matches how you want amounts shown.
3. **Sample data** — by chance the SAMPLE equity funds end the 3 years slightly negative, so Day 4
   growth plans will look poor on sample data. Fine for tests; regenerate with other seeds if you
   want nicer demos (real CMF data replaces it on Day 9).
4. Earlier open items still stand: LLM provider, Langfuse v2 vs v3, branch protection on `main`.

## Day 4 — Calculator part 2: plans and simulation (2026-11-28) ✅
**Branch:** `day-4`

### Done
- Strict TDD: tests committed first (RED: collection failed on missing `plans`/`simulate`), then
  the implementation (GREEN), one commit per module.
- `backend/calculator/core/plans.py`: `make_plan(amount, months, risk_tolerance,
  has_emergency_fund, profile, *, national_bond_open=False)` → frozen `Plan` with `Allocation`
  lines (category, purpose `emergency`/`investment`, exact percent, TND amount), equity exposure
  and plain-text `notes` saying which rules fired. Rules: 30% emergency reserve in bond SICAV when
  there is no emergency fund; horizon bands (< 12 months bond only; 12–35 / 36–59 / ≥ 60 months
  tables); exposure (equity + ½ mixed) capped by risk tolerance (15 / 35 / 65, cautious gets half);
  national bond only for ≥ 60 months and an open tranche; individual stocks never allocated.
  Exact rules and tables written into `docs/PLAN.md` ("Calculator plans").
- `backend/calculator/core/simulate.py`: `simulate(plan, months, history)` → frozen `Simulation`
  with bad/average/good = p10/p50/p90 over every historical rolling window of `months` (same
  windows for all categories, linear-interpolation percentiles, no randomness);
  `equal_weight_index` builds one base-100 series per category from its funds; `percentile`.
  Clear `InsufficientHistoryError` when the history is too short. Method in `docs/PLAN.md`.
- Hypothesis properties: parts sum exactly to the amount, no negative part, percents sum to 100,
  every rule respected, cautious never riskier than growth (strictly less from 12 months), same
  inputs → same plan; simulation outcomes ordered (bad ≤ average ≤ good) and rounded to millimes.
- Scenario test: 1,000 TND, 12 months, "a bit" worried (medium) → Cautious 800 bond / 200 mixed,
  Growth 500 bond / 400 mixed / 100 equity (with an emergency fund); without one, 300 TND reserve
  first, then 560/140 vs 350/280/70.
- Purity test now also covers `plans.py` and `simulate.py` (no DB/AI/random/float).

### Test results
- `uv run ruff check .` → all checks passed; `uv run ruff format --check .` → clean.
- `uv run pytest` → 195 passed, 10 skipped (Postgres tests: "TEST_DATABASE_URL is not set" —
  no Docker/Postgres in this build environment; they run in CI). Total coverage 94.8%;
  `calculator/core` money, stats, plans, simulate all 100%.
- Sanity run on SAMPLE data (1,000 TND, 12 months, medium, with emergency fund, 522 windows):
  Cautious bad/average/good ≈ 1,057 / 1,067 / 1,080 TND; Growth ≈ 1,028 / 1,046 / 1,077 TND
  (synthetic data, not real funds).

### What is left
- Day 5: MCP server exposing make_plan, simulate, fund_stats, get_nav_history (pydantic inputs,
  repository injected). It must build the per-category history (e.g. `equal_weight_index`).
- Long horizons (e.g. 60 months) cannot be simulated on the 3-year SAMPLE history: `simulate`
  raises `InsufficientHistoryError`. Day 5/6 must handle this (say so to the user, or fall back).

### Decisions for the owner
1. **Plan rules** — the weight tables, 30% emergency reserve, exposure caps (15/35/65, cautious
   half) and the 60-month national bond threshold are my first proposal (see `docs/PLAN.md`).
   Please review; they are constants at the top of `plans.py` and easy to change.
2. **Short horizons** — under 12 months both profiles are 100% bond SICAV, so Cautious and Growth
   are identical. Alternative: allow a small mixed share for Growth from 6 months.
3. **National bond tranche** — the calculator cannot know if a tranche is open, so I added a
   `national_bond_open` flag (default false). Who sets it: the user, or a config/data value?
4. **Equity FCP** — plans only use equity SICAV (FCPs are often less liquid). Say if FCPs should
   share the equity part.
5. **Long-horizon simulation** — with < 5 years of history, choose: refuse with a message (current),
   chain shorter windows, or wait for longer real CMF data (Day 9).
6. Earlier open items still stand: LLM provider, Langfuse v2 vs v3, branch protection on `main`,
   statistic conventions and TND half-up rounding (Day 3).
