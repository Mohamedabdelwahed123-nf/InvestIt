"""Initial schema: pgvector extension, funds, nav_prices, data_flags.

Revision ID: 0001
Revises:
Create Date: 2026-11-25 06:04:20.894299
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector is needed later for prospectus chunks (RAG, Day 9).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "funds",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("manager", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="TND", nullable=False),
        sa.CheckConstraint(
            "category IN ('bond_sicav', 'national_bond', 'mixed_sicav', "
            "'equity_sicav', 'equity_fcp')",
            name="ck_funds_category",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_funds_category"), "funds", ["category"], unique=False)
    op.create_table(
        "data_flags",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("fund_id", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("issue", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["fund_id"], ["funds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_flags_fund_id_date", "data_flags", ["fund_id", "date"], unique=False)
    op.create_table(
        "nav_prices",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("fund_id", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("nav", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.CheckConstraint("nav > 0", name="ck_nav_prices_nav_positive"),
        sa.ForeignKeyConstraint(["fund_id"], ["funds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fund_id", "date", name="uq_nav_prices_fund_id_date"),
    )


def downgrade() -> None:
    op.drop_table("nav_prices")
    op.drop_index("ix_data_flags_fund_id_date", table_name="data_flags")
    op.drop_table("data_flags")
    op.drop_index(op.f("ix_funds_category"), table_name="funds")
    op.drop_table("funds")
    op.execute("DROP EXTENSION IF EXISTS vector")
