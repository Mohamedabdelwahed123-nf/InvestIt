"""Validated CSV loader for funds and NAV prices (idempotent upserts).

Validation happens before any write: if one row is bad, nothing is loaded and every bad row is
reported with its file and line number.

Usage: uv run python -m backend.data.load_csv [--funds PATH] [--navs PATH] [--db-url URL]
"""

import argparse
import csv
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.exc import SQLAlchemyError

from backend.db.domain import Category, FundRecord, NavRecord
from backend.db.repository import FundWriter, SqlFundRepository, UnknownFundError
from backend.db.session import make_engine, make_session_factory

SAMPLE_DIR = Path(__file__).parent / "sample"
FUND_COLUMNS = ("code", "name", "manager", "category", "currency")
NAV_COLUMNS = ("fund_code", "date", "nav", "source")
MAX_REPORTED_ERRORS = 50
_CATEGORIES = ", ".join(c.value for c in Category)

Text = Annotated[str, Field(min_length=1, max_length=200)]


class CsvValidationError(ValueError):
    """One or more CSV rows are invalid. `errors` holds one readable message per problem."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = list(errors)
        shown = self.errors[:MAX_REPORTED_ERRORS]
        more = len(self.errors) - len(shown)
        tail = [f"... and {more} more"] if more else []
        super().__init__("\n".join([f"{len(self.errors)} invalid row(s):", *shown, *tail]))


class _FundCsvRow(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    code: Annotated[str, Field(min_length=1, max_length=32)]
    name: Text
    manager: Text
    category: str
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] = "TND"

    @field_validator("category")
    @classmethod
    def _known_category(cls, v: str) -> str:
        if v not in {c.value for c in Category}:
            raise ValueError(f"unknown category {v!r} (expected one of: {_CATEGORIES})")
        return v


class _NavCsvRow(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    fund_code: Annotated[str, Field(min_length=1, max_length=32)]
    date: date
    nav: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6, allow_inf_nan=False)]
    source: Annotated[str, Field(min_length=1, max_length=64)]

    @field_validator("date", mode="before")
    @classmethod
    def _iso_date(cls, v: object) -> date:
        try:
            return date.fromisoformat(str(v))
        except ValueError:
            raise ValueError(f"unparsable date {v!r} (expected YYYY-MM-DD)") from None

    @field_validator("nav", mode="before")
    @classmethod
    def _nav_is_text(cls, v: object) -> object:
        if isinstance(v, float):  # money is never float
            raise ValueError("NAV must be given as text, not float")
        return v


@dataclass(frozen=True, slots=True)
class LoadReport:
    funds: int
    navs: int


def _read_rows(path: Path, columns: Sequence[str]) -> Iterator[tuple[int, dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in columns if c not in (reader.fieldnames or [])]
        if missing:
            raise CsvValidationError([f"{path.name}: missing column(s): {', '.join(missing)}"])
        for row in reader:
            yield reader.line_num, {c: row[c] or "" for c in columns}


def _describe(err: ValidationError) -> str:
    parts = []
    for e in err.errors():
        field = ".".join(str(p) for p in e["loc"]) or "row"
        parts.append(f"{field}: {e['msg'].removeprefix('Value error, ')}")
    return "; ".join(parts)


def parse_funds(path: Path) -> list[FundRecord]:
    """Parse and validate a funds CSV. Raises CsvValidationError listing every bad row."""
    errors: list[str] = []
    funds: dict[str, FundRecord] = {}
    for line, raw in _read_rows(path, FUND_COLUMNS):
        try:
            row = _FundCsvRow.model_validate(raw)
        except ValidationError as e:
            errors.append(f"{path.name} line {line}: {_describe(e)}")
            continue
        if row.code in funds:
            errors.append(f"{path.name} line {line}: duplicate fund code {row.code!r}")
            continue
        funds[row.code] = FundRecord(
            row.code, row.name, row.manager, Category(row.category), row.currency
        )
    if errors:
        raise CsvValidationError(errors)
    return list(funds.values())


def parse_navs(path: Path, known_codes: set[str]) -> list[NavRecord]:
    """Parse and validate a NAV CSV against the known fund codes."""
    errors: list[str] = []
    seen: set[tuple[str, date]] = set()
    navs: list[NavRecord] = []
    for line, raw in _read_rows(path, NAV_COLUMNS):
        where = f"{path.name} line {line}"
        try:
            row = _NavCsvRow.model_validate(raw)
        except ValidationError as e:
            errors.append(f"{where}: {_describe(e)}")
            continue
        if row.fund_code not in known_codes:
            errors.append(f"{where}: unknown fund code {row.fund_code!r}")
        elif (row.fund_code, row.date) in seen:
            errors.append(f"{where}: duplicate date {row.date} for fund {row.fund_code!r}")
        else:
            seen.add((row.fund_code, row.date))
            navs.append(NavRecord(row.fund_code, row.date, row.nav, row.source))
    if errors:
        raise CsvValidationError(errors)
    return navs


def load(writer: FundWriter, funds_path: Path, navs_path: Path) -> LoadReport:
    """Validate both files fully, then upsert funds and NAVs. Safe to run again."""
    funds = parse_funds(funds_path)
    navs = parse_navs(navs_path, {f.code for f in funds})
    return LoadReport(writer.upsert_funds(funds), writer.upsert_nav_prices(navs))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load funds and NAV prices from CSV.")
    parser.add_argument("--funds", type=Path, default=SAMPLE_DIR / "funds.csv")
    parser.add_argument("--navs", type=Path, default=SAMPLE_DIR / "nav_prices.csv")
    parser.add_argument("--db-url", default=None, help="defaults to DATABASE_URL")
    args = parser.parse_args(argv)

    engine = make_engine(args.db_url)
    try:
        report = load(SqlFundRepository(make_session_factory(engine)), args.funds, args.navs)
    except (CsvValidationError, OSError, UnknownFundError) as e:
        print(f"Load failed: {e}", file=sys.stderr)
        return 1
    except SQLAlchemyError as e:
        print(
            f"Load failed: database error ({type(e).__name__}); check DATABASE_URL and run "
            "`uv run alembic upgrade head`.",
            file=sys.stderr,
        )
        return 1
    finally:
        engine.dispose()
    print(f"Loaded {report.funds} funds and {report.navs} NAV rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
