"""Validation rules of the CSV loader (no database)."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.data.load_csv import (
    CsvValidationError,
    _NavCsvRow,
    load,
    main,
    parse_funds,
    parse_navs,
)
from backend.db.domain import Category
from backend.db.repository import InMemoryFundRepository

FUND_HEADER = "code,name,manager,category,currency"
NAV_HEADER = "fund_code,date,nav,source"
GOOD_FUND = "F1,Fund One,Manager,bond_sicav,TND"


def _errors(exc: pytest.ExceptionInfo[CsvValidationError]) -> str:
    return "\n".join(exc.value.errors)


def test_parse_valid_funds(write_csv) -> None:
    path = write_csv("funds.csv", FUND_HEADER, GOOD_FUND, " F2 , Two ,M,equity_fcp,TND")
    funds = parse_funds(path)
    assert [f.code for f in funds] == ["F1", "F2"]
    assert funds[1].name == "Two"
    assert funds[1].category is Category.EQUITY_FCP


def test_unknown_category_is_reported_with_line(write_csv) -> None:
    path = write_csv("funds.csv", FUND_HEADER, GOOD_FUND, "F2,Two,M,crypto,TND")
    with pytest.raises(CsvValidationError) as exc:
        parse_funds(path)
    assert "funds.csv line 3" in _errors(exc)
    assert "unknown category 'crypto'" in _errors(exc)


@pytest.mark.parametrize(
    ("row", "needle"),
    [
        ("F1,Dup,M,bond_sicav,TND", "duplicate fund code 'F1'"),
        (",Name,M,bond_sicav,TND", "code"),
        ("F3,Name,M,bond_sicav,tnd", "currency"),
    ],
)
def test_bad_fund_rows(write_csv, row: str, needle: str) -> None:
    path = write_csv("funds.csv", FUND_HEADER, GOOD_FUND, row)
    with pytest.raises(CsvValidationError) as exc:
        parse_funds(path)
    assert needle in _errors(exc)


def test_missing_column(write_csv) -> None:
    path = write_csv("funds.csv", "code,name,category", "F1,One,bond_sicav")
    with pytest.raises(CsvValidationError, match="missing column"):
        parse_funds(path)


def test_parse_valid_navs_keeps_decimal_exact(write_csv) -> None:
    path = write_csv("navs.csv", NAV_HEADER, "F1,2024-01-02,104.123456,SAMPLE")
    [nav] = parse_navs(path, {"F1"})
    assert nav.date == date(2024, 1, 2)
    assert nav.nav == Decimal("104.123456")
    assert isinstance(nav.nav, Decimal)


@pytest.mark.parametrize(
    ("row", "needle"),
    [
        ("F1,2024-01-02,-1.5,S", "greater than 0"),
        ("F1,2024-01-02,0,S", "greater than 0"),
        ("F1,2024-01-02,abc,S", "nav"),
        ("F1,2024-01-02,NaN,S", "nav"),
        ("F1,2024-01-02,1.1234567,S", "decimal places"),
        ("F1,02/01/2024,100,S", "unparsable date '02/01/2024'"),
        ("F1,2024-02-30,100,S", "unparsable date"),
        ("F1,,100,S", "unparsable date"),
        ("F1,2024-01-02,100,", "source"),
        ("ZZ,2024-01-02,100,S", "unknown fund code 'ZZ'"),
        ("F1,2024-01-01,100,S", "duplicate date 2024-01-01 for fund 'F1'"),
    ],
)
def test_bad_nav_rows(write_csv, row: str, needle: str) -> None:
    path = write_csv("navs.csv", NAV_HEADER, "F1,2024-01-01,100,S", row)
    with pytest.raises(CsvValidationError) as exc:
        parse_navs(path, {"F1"})
    assert "navs.csv line 3" in _errors(exc)
    assert needle in _errors(exc)


def test_all_bad_rows_reported_and_message_is_capped(write_csv) -> None:
    rows = [f"F1,2024-01-02,-{i},S" for i in range(1, 61)]
    path = write_csv("navs.csv", NAV_HEADER, *rows)
    with pytest.raises(CsvValidationError) as exc:
        parse_navs(path, {"F1"})
    assert len(exc.value.errors) == 60
    assert "60 invalid row(s)" in str(exc.value)
    assert "... and 10 more" in str(exc.value)


def test_float_nav_rejected() -> None:
    with pytest.raises(ValueError, match="not float"):
        _NavCsvRow.model_validate(
            {"fund_code": "F1", "date": "2024-01-02", "nav": 1.5, "source": "S"}
        )


def test_load_is_idempotent_and_writes_nothing_on_error(write_csv) -> None:
    funds = write_csv("funds.csv", FUND_HEADER, GOOD_FUND)
    navs = write_csv("navs.csv", NAV_HEADER, "F1,2024-01-02,100,S", "F1,2024-01-03,101,S")
    repo = InMemoryFundRepository()
    first = load(repo, funds, navs)
    second = load(repo, funds, navs)
    assert first == second
    assert (first.funds, first.navs) == (1, 2)
    assert len(repo.get_nav_history(repo.list_funds()[0].id)) == 2

    bad_navs = write_csv("bad.csv", NAV_HEADER, "F1,2024-01-04,-1,S")
    empty = InMemoryFundRepository()
    with pytest.raises(CsvValidationError):
        load(empty, funds, bad_navs)
    assert empty.list_funds() == []


def test_main_reports_errors_without_traceback(
    write_csv, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    funds = write_csv("funds.csv", FUND_HEADER, "F1,One,M,unknown,TND")
    code = main(["--funds", str(funds), "--navs", str(tmp_path / "x.csv"), "--db-url", "sqlite://"])
    assert code == 1
    err = capsys.readouterr().err
    assert err.startswith("Load failed:")
    assert "unknown category" in err
    assert "Traceback" not in err


def test_main_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--funds", str(tmp_path / "nope.csv"), "--db-url", "sqlite://"])
    assert code == 1
    assert "Load failed" in capsys.readouterr().err


def test_cli_database_error_is_friendly(capsys) -> None:
    assert main(["--db-url", "postgresql+psycopg://nobody:x@127.0.0.1:1/none"]) == 1
    err = capsys.readouterr().err
    assert "database error" in err
    assert "Traceback" not in err
