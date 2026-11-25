"""The ORM schema matches docs/PLAN.md."""

from sqlalchemy import Numeric, UniqueConstraint

from backend.db.models import Base


def test_tables_and_columns() -> None:
    tables = Base.metadata.tables
    assert set(tables) == {"funds", "nav_prices", "data_flags"}
    assert set(tables["funds"].c.keys()) == {
        "id",
        "code",
        "name",
        "manager",
        "category",
        "currency",
    }
    assert {"fund_id", "date", "nav", "source"} <= set(tables["nav_prices"].c.keys())
    assert {"fund_id", "date", "issue", "created_at"} <= set(tables["data_flags"].c.keys())


def test_nav_is_exact_numeric_and_unique_per_day() -> None:
    nav_prices = Base.metadata.tables["nav_prices"]
    nav_type = nav_prices.c.nav.type
    assert isinstance(nav_type, Numeric)
    assert (nav_type.precision, nav_type.scale, nav_type.asdecimal) == (18, 6, True)
    uniques = [
        {c.name for c in con.columns}
        for con in nav_prices.constraints
        if isinstance(con, UniqueConstraint)
    ]
    assert {"fund_id", "date"} in uniques
    assert Base.metadata.tables["funds"].c.code.unique
