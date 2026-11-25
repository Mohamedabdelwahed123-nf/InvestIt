"""Postgres-only checks: migrations, pgvector, DB constraints and the loader CLI."""

from datetime import date

import pytest
from alembic import command
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from backend.data.load_csv import main
from backend.db.repository import SqlFundRepository

from .conftest import alembic_config

pytestmark = pytest.mark.db


def test_migration_creates_schema_and_pgvector(pg_engine: Engine) -> None:
    tables = set(inspect(pg_engine).get_table_names())
    assert {"funds", "nav_prices", "data_flags", "alembic_version"} <= tables
    with pg_engine.connect() as conn:
        ext = conn.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'"))
        assert ext.scalar_one() == "vector"


def test_downgrade_then_upgrade(pg_url: str, pg_engine: Engine) -> None:
    cfg = alembic_config(pg_url)
    command.downgrade(cfg, "base")
    assert "funds" not in inspect(pg_engine).get_table_names()
    command.upgrade(cfg, "head")
    assert "funds" in inspect(pg_engine).get_table_names()


def test_db_rejects_bad_category_and_non_positive_nav(
    pg_engine: Engine, sql_repo: SqlFundRepository
) -> None:
    insert_fund = "INSERT INTO funds (code, name, manager, category) VALUES ('X', 'X', 'X', :c)"
    with pytest.raises(IntegrityError), pg_engine.begin() as conn:
        conn.execute(text(insert_fund), {"c": "crypto"})
    with pg_engine.begin() as conn:
        fund_id = conn.execute(text(insert_fund + " RETURNING id"), {"c": "mixed_sicav"}).scalar()
    with pytest.raises(IntegrityError), pg_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO nav_prices (fund_id, date, nav, source) VALUES (:f, :d, 0, 'S')"),
            {"f": fund_id, "d": date(2024, 1, 1)},
        )


def test_cli_loads_sample(pg_url: str, sql_repo: SqlFundRepository, capsys) -> None:
    assert main(["--db-url", pg_url]) == 0
    assert "Loaded 10 funds" in capsys.readouterr().out
    assert len(sql_repo.list_funds()) == 10
