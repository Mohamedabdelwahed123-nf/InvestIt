.PHONY: install lint format test up down migrate load-sample

install:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

test:
	uv run pytest

up:
	docker compose up -d

down:
	docker compose down

migrate:
	uv run alembic upgrade head

load-sample:
	uv run python -m backend.data.load_csv
