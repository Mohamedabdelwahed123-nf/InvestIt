"""Engine and session factory helpers."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import get_settings


def make_engine(url: str | None = None) -> Engine:
    """Create an engine for `url` (defaults to DATABASE_URL from settings)."""
    return create_engine(url or get_settings().database_url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory bound to `engine` (objects stay usable after commit)."""
    return sessionmaker(bind=engine, expire_on_commit=False)
