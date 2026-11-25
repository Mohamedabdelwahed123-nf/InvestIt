"""FundRepository: read/write access to funds and NAV history behind an interface.

`SqlFundRepository` talks to Postgres; `InMemoryFundRepository` is a fake for tests.
Both return plain domain types from `backend.db.domain`, never ORM rows.
"""

from collections.abc import Iterable, Sequence
from datetime import date
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from backend.db.domain import Category, Fund, FundRecord, NavPoint, NavRecord
from backend.db.models import FundRow, NavPriceRow


class UnknownFundError(LookupError):
    """Raised when NAV rows reference a fund code that is not stored."""


class FundRepository(Protocol):
    """Read side used by the calculator adapter and the API."""

    def list_funds(self) -> list[Fund]: ...

    def get_fund(self, fund_id: int) -> Fund | None: ...

    def get_nav_history(
        self, fund_id: int, start: date | None = None, end: date | None = None
    ) -> list[NavPoint]: ...

    def get_category_funds(self, category: Category) -> list[Fund]: ...


class FundWriter(Protocol):
    """Write side used by the loaders. Upserts are idempotent."""

    def upsert_funds(self, funds: Iterable[FundRecord]) -> int: ...

    def upsert_nav_prices(self, navs: Iterable[NavRecord]) -> int: ...


def _in_range(d: date, start: date | None, end: date | None) -> bool:
    return (start is None or d >= start) and (end is None or d <= end)


def _to_fund(row: FundRow) -> Fund:
    return Fund(
        id=row.id,
        code=row.code,
        name=row.name,
        manager=row.manager,
        category=Category(row.category),
        currency=row.currency,
    )


class SqlFundRepository:
    """Postgres implementation (SQLAlchemy 2.0)."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_funds(self) -> list[Fund]:
        with self._session_factory() as s:
            rows = s.scalars(select(FundRow).order_by(FundRow.code))
            return [_to_fund(r) for r in rows]

    def get_fund(self, fund_id: int) -> Fund | None:
        with self._session_factory() as s:
            row = s.get(FundRow, fund_id)
            return _to_fund(row) if row else None

    def get_nav_history(
        self, fund_id: int, start: date | None = None, end: date | None = None
    ) -> list[NavPoint]:
        stmt = select(NavPriceRow.date, NavPriceRow.nav, NavPriceRow.source).where(
            NavPriceRow.fund_id == fund_id
        )
        if start is not None:
            stmt = stmt.where(NavPriceRow.date >= start)
        if end is not None:
            stmt = stmt.where(NavPriceRow.date <= end)
        with self._session_factory() as s:
            rows = s.execute(stmt.order_by(NavPriceRow.date))
            return [NavPoint(date=d, nav=n, source=src) for d, n, src in rows]

    def get_category_funds(self, category: Category) -> list[Fund]:
        stmt = select(FundRow).where(FundRow.category == category.value).order_by(FundRow.code)
        with self._session_factory() as s:
            return [_to_fund(r) for r in s.scalars(stmt)]

    def upsert_funds(self, funds: Iterable[FundRecord]) -> int:
        values = [
            {
                "code": f.code,
                "name": f.name,
                "manager": f.manager,
                "category": f.category.value,
                "currency": f.currency,
            }
            for f in funds
        ]
        if not values:
            return 0
        stmt = insert(FundRow).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[FundRow.code],
            set_={k: stmt.excluded[k] for k in ("name", "manager", "category", "currency")},
        )
        with self._session_factory.begin() as s:
            s.execute(stmt)
        return len(values)

    def upsert_nav_prices(self, navs: Iterable[NavRecord]) -> int:
        navs = list(navs)
        if not navs:
            return 0
        with self._session_factory.begin() as s:
            ids = dict(s.execute(select(FundRow.code, FundRow.id)).tuples())
            values = [_nav_values(n, ids) for n in navs]
            for chunk in _chunks(values, 2000):
                stmt = insert(NavPriceRow).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_nav_prices_fund_id_date",
                    set_={"nav": stmt.excluded.nav, "source": stmt.excluded.source},
                )
                s.execute(stmt)
        return len(navs)


def _require_id(code: str, ids: dict[str, int]) -> int:
    if code not in ids:
        raise UnknownFundError(f"unknown fund code {code!r}; load funds first")
    return ids[code]


def _nav_values(n: NavRecord, ids: dict[str, int]) -> dict[str, object]:
    fund_id = _require_id(n.fund_code, ids)
    return {"fund_id": fund_id, "date": n.date, "nav": n.nav, "source": n.source}


def _chunks(items: Sequence[dict[str, object]], size: int) -> Iterable[Sequence[dict[str, object]]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class InMemoryFundRepository:
    """In-memory fake with the same behaviour as the SQL repository (for tests)."""

    def __init__(self) -> None:
        self._funds: dict[str, Fund] = {}
        self._navs: dict[int, dict[date, NavPoint]] = {}

    def list_funds(self) -> list[Fund]:
        return sorted(self._funds.values(), key=lambda f: f.code)

    def get_fund(self, fund_id: int) -> Fund | None:
        return next((f for f in self._funds.values() if f.id == fund_id), None)

    def get_nav_history(
        self, fund_id: int, start: date | None = None, end: date | None = None
    ) -> list[NavPoint]:
        points = self._navs.get(fund_id, {})
        return [points[d] for d in sorted(points) if _in_range(d, start, end)]

    def get_category_funds(self, category: Category) -> list[Fund]:
        return [f for f in self.list_funds() if f.category == category]

    def upsert_funds(self, funds: Iterable[FundRecord]) -> int:
        count = 0
        for rec in funds:
            existing = self._funds.get(rec.code)
            fund_id = existing.id if existing else len(self._funds) + 1
            self._funds[rec.code] = Fund(
                fund_id, rec.code, rec.name, rec.manager, rec.category, rec.currency
            )
            count += 1
        return count

    def upsert_nav_prices(self, navs: Iterable[NavRecord]) -> int:
        navs = list(navs)
        ids = {code: f.id for code, f in self._funds.items()}
        staged = [(_require_id(n.fund_code, ids), n) for n in navs]  # validate all first
        for fund_id, n in staged:
            self._navs.setdefault(fund_id, {})[n.date] = NavPoint(n.date, n.nav, n.source)
        return len(navs)
