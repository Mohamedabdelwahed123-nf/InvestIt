"""Generate the SAMPLE (synthetic) fund and NAV CSVs in this folder.

THIS IS NOT REAL MARKET DATA. Every fund is invented, every NAV is a seeded random walk.
Re-run with `uv run python -m backend.data.sample.generate`; output is deterministic.
"""

import csv
import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).parent
SEED = 20261125
START = date(2023, 1, 2)
END = date(2025, 12, 31)
TRADING_DAYS = 252
NAV_STEP = Decimal("0.001")
SOURCE = "SAMPLE"


@dataclass(frozen=True)
class SampleFund:
    code: str
    name: str
    category: str
    start_nav: Decimal
    annual_drift: Decimal
    annual_vol: float  # only drives the synthetic noise, never a money amount


FUNDS = (
    SampleFund(
        "SMP-BOND-1",
        "SAMPLE Bond SICAV Alpha",
        "bond_sicav",
        Decimal("104.250"),
        Decimal("0.068"),
        0.003,
    ),
    SampleFund(
        "SMP-BOND-2",
        "SAMPLE Bond SICAV Beta",
        "bond_sicav",
        Decimal("112.800"),
        Decimal("0.072"),
        0.004,
    ),
    SampleFund(
        "SMP-NAT-1",
        "SAMPLE National Bond Tranche A",
        "national_bond",
        Decimal("100.000"),
        Decimal("0.080"),
        0.005,
    ),
    SampleFund(
        "SMP-NAT-2",
        "SAMPLE National Bond Tranche B",
        "national_bond",
        Decimal("100.000"),
        Decimal("0.0875"),
        0.006,
    ),
    SampleFund(
        "SMP-MIX-1",
        "SAMPLE Mixed SICAV Gamma",
        "mixed_sicav",
        Decimal("58.400"),
        Decimal("0.065"),
        0.055,
    ),
    SampleFund(
        "SMP-MIX-2",
        "SAMPLE Mixed SICAV Delta",
        "mixed_sicav",
        Decimal("131.900"),
        Decimal("0.070"),
        0.070,
    ),
    SampleFund(
        "SMP-EQ-1",
        "SAMPLE Equity SICAV Epsilon",
        "equity_sicav",
        Decimal("87.150"),
        Decimal("0.085"),
        0.120,
    ),
    SampleFund(
        "SMP-EQ-2",
        "SAMPLE Equity SICAV Zeta",
        "equity_sicav",
        Decimal("15.320"),
        Decimal("0.075"),
        0.140,
    ),
    SampleFund(
        "SMP-FCP-1",
        "SAMPLE Equity FCP Eta",
        "equity_fcp",
        Decimal("1020.500"),
        Decimal("0.095"),
        0.150,
    ),
    SampleFund(
        "SMP-FCP-2",
        "SAMPLE Equity FCP Theta",
        "equity_fcp",
        Decimal("245.700"),
        Decimal("0.080"),
        0.170,
    ),
)


def business_days(start: date, end: date) -> list[date]:
    """Monday-Friday dates between start and end (inclusive). Holidays are ignored."""
    days = (end - start).days + 1
    all_days = (start + timedelta(days=i) for i in range(days))
    return [d for d in all_days if d.weekday() < 5]


def nav_path(fund: SampleFund, days: list[date], rng: random.Random) -> list[Decimal]:
    """Seeded random walk with drift; NAV stays positive and is rounded to millimes."""
    drift = fund.annual_drift / TRADING_DAYS
    daily_vol = fund.annual_vol / math.sqrt(TRADING_DAYS)
    nav = fund.start_nav
    path = []
    for _ in days:
        shock = Decimal(str(round(rng.gauss(0.0, daily_vol), 8)))
        nav = max(NAV_STEP, (nav * (1 + drift + shock)).quantize(NAV_STEP))
        path.append(nav)
    return path


def write_csvs(out_dir: Path = HERE) -> None:
    rng = random.Random(SEED)  # noqa: S311 - synthetic sample data, not security related
    days = business_days(START, END)
    with (out_dir / "funds.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["code", "name", "manager", "category", "currency"])
        for f in FUNDS:
            w.writerow([f.code, f.name, "SAMPLE Asset Manager (synthetic)", f.category, "TND"])
    with (out_dir / "nav_prices.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["fund_code", "date", "nav", "source"])
        for f in FUNDS:
            for d, nav in zip(days, nav_path(f, days, rng), strict=True):
                w.writerow([f.code, d.isoformat(), f"{nav}", SOURCE])


if __name__ == "__main__":
    write_csvs()
