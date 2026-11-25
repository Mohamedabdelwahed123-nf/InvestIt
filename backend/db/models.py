"""SQLAlchemy 2.0 models: funds, nav_prices, data_flags (exactly as in docs/PLAN.md)."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.db.domain import Category

CATEGORY_VALUES = tuple(c.value for c in Category)
_CATEGORY_SQL = ", ".join(f"'{v}'" for v in CATEGORY_VALUES)


class Base(DeclarativeBase):
    """Declarative base for all Invesit tables."""


class FundRow(Base):
    __tablename__ = "funds"
    __table_args__ = (CheckConstraint(f"category IN ({_CATEGORY_SQL})", name="ck_funds_category"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    manager: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="TND")


class NavPriceRow(Base):
    __tablename__ = "nav_prices"
    __table_args__ = (
        UniqueConstraint("fund_id", "date", name="uq_nav_prices_fund_id_date"),
        CheckConstraint("nav > 0", name="ck_nav_prices_nav_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    fund_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("funds.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    nav: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)


class DataFlagRow(Base):
    __tablename__ = "data_flags"
    __table_args__ = (Index("ix_data_flags_fund_id_date", "fund_id", "date"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    fund_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("funds.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    issue: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
