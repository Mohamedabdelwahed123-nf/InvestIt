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
