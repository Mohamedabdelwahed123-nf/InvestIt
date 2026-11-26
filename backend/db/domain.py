"""Plain domain types shared by the data layer (no SQLAlchemy, no AI).

These are what the repository returns, so callers (calculator adapter, API) never touch ORM rows.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class Category(StrEnum):
    """Fund categories, safest to riskiest (see docs/PLAN.md)."""

    BOND_SICAV = "bond_sicav"
    NATIONAL_BOND = "national_bond"
    MIXED_SICAV = "mixed_sicav"
    EQUITY_SICAV = "equity_sicav"
    EQUITY_FCP = "equity_fcp"


@dataclass(frozen=True, slots=True)
class FundRecord:
    """A fund as stored in the `funds` table (without its surrogate id)."""

    code: str
    name: str
    manager: str
    category: Category
    currency: str = "TND"


@dataclass(frozen=True, slots=True)
class Fund:
    """A stored fund, with its database id."""

    id: int
    code: str
    name: str
    manager: str
    category: Category
    currency: str


@dataclass(frozen=True, slots=True)
class NavRecord:
    """One NAV observation keyed by fund code (input of the loader)."""

    fund_code: str
    date: date
    nav: Decimal
    source: str


@dataclass(frozen=True, slots=True)
class NavPoint:
    """One NAV observation of a stored fund (output of the repository)."""

    date: date
    nav: Decimal
    source: str
