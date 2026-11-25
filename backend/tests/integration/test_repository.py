"""FundRepository contract + loader, run against the in-memory fake and Postgres."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.data.load_csv import load
from backend.db.domain import Category, FundRecord, NavRecord
from backend.db.repository import UnknownFundError


def _seed(repo) -> int:
    repo.upsert_funds(
        [
            FundRecord("B1", "Bond One", "M", Category.BOND_SICAV),
            FundRecord("E1", "Equity One", "M", Category.EQUITY_SICAV),
            FundRecord("B2", "Bond Two", "M", Category.BOND_SICAV),
        ]
    )
    repo.upsert_nav_prices(
        [
            NavRecord("B1", date(2024, 1, 3), Decimal("100.300000"), "SAMPLE"),
            NavRecord("B1", date(2024, 1, 1), Decimal("100.100000"), "SAMPLE"),
            NavRecord("B1", date(2024, 1, 2), Decimal("100.200000"), "SAMPLE"),
        ]
    )
    return next(f.id for f in repo.list_funds() if f.code == "B1")


def test_list_get_and_category(repo) -> None:
    b1 = _seed(repo)
    assert [f.code for f in repo.list_funds()] == ["B1", "B2", "E1"]
    fund = repo.get_fund(b1)
    assert fund is not None
    assert (fund.code, fund.category, fund.currency) == ("B1", Category.BOND_SICAV, "TND")
    assert repo.get_fund(999_999) is None
    assert [f.code for f in repo.get_category_funds(Category.BOND_SICAV)] == ["B1", "B2"]
    assert repo.get_category_funds(Category.EQUITY_FCP) == []


def test_nav_history_sorted_ranged_and_decimal(repo) -> None:
    b1 = _seed(repo)
    history = repo.get_nav_history(b1)
    assert [p.date.day for p in history] == [1, 2, 3]
    assert all(isinstance(p.nav, Decimal) for p in history)
    assert history[0].nav == Decimal("100.1")
    ranged = repo.get_nav_history(b1, start=date(2024, 1, 2), end=date(2024, 1, 2))
    assert [p.nav for p in ranged] == [Decimal("100.2")]
    assert [p.date.day for p in repo.get_nav_history(b1, start=date(2024, 1, 2))] == [2, 3]
    assert [p.date.day for p in repo.get_nav_history(b1, end=date(2024, 1, 2))] == [1, 2]
    assert repo.get_nav_history(999_999) == []


def test_upserts_are_idempotent_and_update(repo) -> None:
    b1 = _seed(repo)
    _seed(repo)
    assert len(repo.list_funds()) == 3
    assert len(repo.get_nav_history(b1)) == 3

    repo.upsert_funds([FundRecord("B1", "Bond One renamed", "M2", Category.BOND_SICAV)])
    repo.upsert_nav_prices([NavRecord("B1", date(2024, 1, 1), Decimal("99.5"), "FIX")])
    fund = repo.get_fund(b1)
    assert fund is not None
    assert (fund.id, fund.name, fund.manager) == (b1, "Bond One renamed", "M2")
    first = repo.get_nav_history(b1)[0]
    assert (first.nav, first.source) == (Decimal("99.5"), "FIX")


def test_empty_upserts(repo) -> None:
    assert repo.upsert_funds([]) == 0
    assert repo.upsert_nav_prices([]) == 0


def test_unknown_fund_code_rejected_atomically(repo) -> None:
    b1 = _seed(repo)
    with pytest.raises(UnknownFundError, match="ZZ"):
        repo.upsert_nav_prices(
            [
                NavRecord("B1", date(2024, 1, 9), Decimal("101"), "S"),
                NavRecord("ZZ", date(2024, 1, 9), Decimal("1"), "S"),
            ]
        )
    assert len(repo.get_nav_history(b1)) == 3


def test_sample_data_loads_twice(repo, sample_dir: Path) -> None:
    funds, navs = sample_dir / "funds.csv", sample_dir / "nav_prices.csv"
    first = load(repo, funds, navs)
    second = load(repo, funds, navs)
    assert first == second
    assert first.funds == 10
    stored = repo.list_funds()
    assert len(stored) == 10
    total = sum(len(repo.get_nav_history(f.id)) for f in stored)
    assert total == first.navs
    for category in Category:
        assert len(repo.get_category_funds(category)) >= 2
