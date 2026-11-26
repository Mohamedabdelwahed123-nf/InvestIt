"""Postgres fixtures. Every DB test is skipped (with a reason) when no test database is reachable.

Point TEST_DATABASE_URL at a throwaway database: tables are migrated and wiped by these tests.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError

from backend.config import Settings
from backend.db.repository import InMemoryFundRepository, SqlFundRepository
from backend.db.session import make_engine, make_session_factory

ROOT = Path(__file__).resolve().parents[3]


def alembic_config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def pg_url() -> str:
    url = Settings().test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set: Postgres integration tests skipped")
    engine = make_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as e:
        pytest.skip(f"Postgres not reachable at TEST_DATABASE_URL ({type(e).__name__})")
    finally:
        engine.dispose()
    return url


@pytest.fixture(scope="session")
def pg_engine(pg_url: str) -> Iterator[Engine]:
    command.upgrade(alembic_config(pg_url), "head")
    engine = make_engine(pg_url)
    yield engine
    engine.dispose()


@pytest.fixture
def sql_repo(pg_engine: Engine) -> Iterator[SqlFundRepository]:
    yield SqlFundRepository(make_session_factory(pg_engine))
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE data_flags, nav_prices, funds RESTART IDENTITY CASCADE"))


@pytest.fixture(params=["memory", pytest.param("sql", marks=pytest.mark.db)])
def repo(request: pytest.FixtureRequest):
    """The same contract tests run against the fake and against Postgres."""
    if request.param == "memory":
        return InMemoryFundRepository()
    return request.getfixturevalue("sql_repo")
