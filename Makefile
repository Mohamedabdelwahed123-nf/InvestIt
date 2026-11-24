.PHONY: install lint format test up down

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
