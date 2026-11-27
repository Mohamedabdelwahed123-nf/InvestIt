"""Tests for calculator/core/stats.py — returns, volatility, drawdown, per-category aggregates."""

import dataclasses
import math
from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.calculator.core.money import MoneyError
from backend.calculator.core.stats import (
    DAYS_PER_YEAR,
    MAX_GAP_DAYS,
    MIN_OBSERVATIONS,
    CategoryStats,
    Frequency,
    FundStats,
    InsufficientDataError,
    PricePoint,
    StatsError,
    annualised_return,
    annualised_volatility,
    category_stats,
    find_gaps,
    fund_stats,
    max_drawdown,
    period_returns,
    total_return,
    validate_series,
    worst_rolling_return,
)
from backend.db.domain import NavPoint

D = Decimal


def pts(*pairs: tuple[str, str]) -> list[PricePoint]:
    return [PricePoint(date.fromisoformat(d), D(v)) for d, v in pairs]


def business_days(start: date, navs: list[str]) -> list[PricePoint]:
    """One point per Mon–Fri trading day starting at `start`."""
    out: list[PricePoint] = []
    day = start
    for nav in navs:
        while day.weekday() >= 5:
            day += timedelta(days=1)
        out.append(PricePoint(day, D(nav)))
        day += timedelta(days=1)
    return out


def steady_series(days: int, start: str = "2023-01-02", daily: str = "1.0002") -> list[PricePoint]:
    nav = D(100)
    navs = []
    for _ in range(days):
        navs.append(str(nav))
        nav = (nav * D(daily)).quantize(D("0.000001"))
    return business_days(date.fromisoformat(start), navs)


class TestValidateSeries:
    def test_sorts_by_date(self) -> None:
        series = validate_series(pts(("2024-01-03", "2"), ("2024-01-02", "1")))
        assert [p.date for p in series] == [date(2024, 1, 2), date(2024, 1, 3)]
        assert isinstance(series, tuple)

    def test_accepts_repository_nav_points(self) -> None:
        series = validate_series([NavPoint(date(2024, 1, 2), D("10.5"), "SAMPLE")])
        assert series == (PricePoint(date(2024, 1, 2), D("10.5")),)

    def test_duplicate_dates_rejected(self) -> None:
        with pytest.raises(StatsError, match="duplicate date 2024-01-02"):
            validate_series(pts(("2024-01-02", "1"), ("2024-01-02", "2")))

    @pytest.mark.parametrize("nav", ["0", "-1"])
    def test_non_positive_nav_rejected(self, nav) -> None:
        with pytest.raises(StatsError, match="must be positive"):
            validate_series(pts(("2024-01-02", nav)))

    def test_float_nav_rejected(self) -> None:
        with pytest.raises(MoneyError, match="float"):
            validate_series([PricePoint(date(2024, 1, 2), 1.5)])  # type: ignore[arg-type]

    def test_empty_series_is_insufficient(self) -> None:
        with pytest.raises(InsufficientDataError, match="at least 1"):
            validate_series([])

    def test_custom_minimum(self) -> None:
        with pytest.raises(InsufficientDataError, match="at least 3 NAV observations, got 2"):
            validate_series(pts(("2024-01-02", "1"), ("2024-01-03", "1")), min_points=3)

    def test_insufficient_is_a_stats_error_and_value_error(self) -> None:
        assert issubclass(InsufficientDataError, StatsError)
        assert issubclass(StatsError, ValueError)


class TestPeriodReturns:
    def test_observation_returns_skip_weekends_and_holidays(self) -> None:
        # Fri -> Mon is one period, a missing Tuesday (holiday) is just a longer period.
        series = pts(("2024-01-05", "100"), ("2024-01-08", "110"), ("2024-01-10", "99"))
        returns = period_returns(series)
        assert [(r.start, r.end, r.value) for r in returns] == [
            (date(2024, 1, 5), date(2024, 1, 8), D("0.1")),
            (date(2024, 1, 8), date(2024, 1, 10), D("-0.1")),
        ]

    def test_monthly_uses_last_nav_of_each_month(self) -> None:
        series = pts(
            ("2024-01-02", "100"),
            ("2024-01-31", "102"),
            ("2024-02-15", "999"),
            ("2024-02-29", "104.04"),
            ("2024-03-01", "104.04"),
        )
        returns = period_returns(series, Frequency.MONTHLY)
        assert [(r.end, r.value) for r in returns] == [
            (date(2024, 1, 31), D("0.02")),
            (date(2024, 2, 29), D("0.02")),
            (date(2024, 3, 1), D("0")),
        ]

    def test_yearly(self) -> None:
        series = pts(("2023-01-02", "100"), ("2023-12-29", "110"), ("2024-12-31", "121"))
        returns = period_returns(series, Frequency.YEARLY)
        assert [r.value for r in returns] == [D("0.1"), D("0.1")]

    def test_single_point_needs_two(self) -> None:
        with pytest.raises(InsufficientDataError, match="at least 2"):
            period_returns(pts(("2024-01-02", "1")))


class TestTotalAndAnnualisedReturn:
    def test_total_return(self) -> None:
        assert total_return(pts(("2024-01-02", "100"), ("2024-06-28", "107.5"))) == D("0.075")

    def test_annualised_return_exact_four_years(self) -> None:
        # 2021-01-01 -> 2025-01-01 is 1461 days = exactly 4 * 365.25.
        series = pts(("2021-01-01", "100"), ("2025-01-01", "146.41"))
        assert annualised_return(series) == D("0.1")

    def test_annualised_return_matches_formula(self) -> None:
        series = pts(("2023-01-02", "100"), ("2024-07-01", "112"))
        days = (date(2024, 7, 1) - date(2023, 1, 2)).days
        expected = 1.12 ** (365.25 / days) - 1
        assert float(annualised_return(series)) == pytest.approx(expected, abs=1e-6)

    def test_annualised_loss(self) -> None:
        series = pts(("2021-01-01", "100"), ("2025-01-01", "65.61"))
        assert annualised_return(series) == D("-0.1")

    def test_days_per_year(self) -> None:
        assert D("365.25") == DAYS_PER_YEAR

    def test_same_day_span_rejected(self) -> None:
        with pytest.raises(InsufficientDataError, match="at least 2"):
            annualised_return(pts(("2024-01-02", "1")))


class TestVolatility:
    def test_constant_nav_has_zero_volatility(self) -> None:
        series = business_days(date(2024, 1, 1), ["100"] * 10)
        assert annualised_volatility(series) == D(0)

    def test_matches_sample_std_times_sqrt_periods_per_year(self) -> None:
        series = pts(
            ("2024-01-01", "100"),
            ("2024-01-02", "110"),
            ("2024-01-03", "99"),
            ("2024-01-04", "108.9"),
        )
        r = [0.1, -0.1, 0.1]
        mean = sum(r) / 3
        std = math.sqrt(sum((x - mean) ** 2 for x in r) / 2)
        periods_per_year = 3 / (3 / 365.25)
        expected = std * math.sqrt(periods_per_year)
        assert float(annualised_volatility(series)) == pytest.approx(expected, abs=1e-6)

    def test_needs_three_points(self) -> None:
        with pytest.raises(InsufficientDataError, match="at least 3"):
            annualised_volatility(pts(("2024-01-01", "1"), ("2024-01-02", "2")))


class TestMaxDrawdown:
    def test_peak_to_trough(self) -> None:
        series = pts(
            ("2024-01-01", "100"),
            ("2024-01-02", "120"),
            ("2024-01-03", "90"),
            ("2024-01-04", "130"),
            ("2024-01-05", "110"),
        )
        assert max_drawdown(series) == D("-0.25")

    def test_only_rising_is_zero(self) -> None:
        assert max_drawdown(pts(("2024-01-01", "1"), ("2024-01-02", "2"))) == D(0)

    def test_single_point_is_zero(self) -> None:
        assert max_drawdown(pts(("2024-01-01", "1"))) == D(0)


class TestWorstRollingReturn:
    def test_worst_twelve_months(self) -> None:
        series = pts(
            ("2023-01-02", "100"),
            ("2023-06-30", "120"),
            ("2024-01-02", "110"),  # +10% vs 2023-01-02
            ("2024-06-28", "96"),  # base = 2023-06-28 or earlier -> 2023-01-02 (100) -> -4%
            ("2024-07-01", "90"),  # base = 2023-06-30 (120) -> -25%
        )
        assert worst_rolling_return(series, months=12) == D("-0.25")

    def test_shorter_than_window_is_none(self) -> None:
        assert worst_rolling_return(pts(("2024-01-02", "1"), ("2024-12-31", "2"))) is None

    def test_month_end_clamping(self) -> None:
        # 2024-02-29 minus 12 months -> 2023-02-28.
        series = pts(("2023-02-28", "100"), ("2024-02-29", "105"))
        assert worst_rolling_return(series, months=12) == D("0.05")

    def test_invalid_window(self) -> None:
        with pytest.raises(StatsError, match="months"):
            worst_rolling_return(pts(("2024-01-02", "1")), months=0)


class TestGaps:
    def test_weekend_is_not_a_gap(self) -> None:
        assert find_gaps(steady_series(30)) == ()

    def test_long_gap_reported(self) -> None:
        series = pts(("2024-01-02", "1"), ("2024-01-03", "1"), ("2024-01-20", "1"))
        gaps = find_gaps(series)
        assert len(gaps) == 1
        assert (gaps[0].start, gaps[0].end, gaps[0].days) == (
            date(2024, 1, 3),
            date(2024, 1, 20),
            17,
        )

    def test_threshold(self) -> None:
        assert MAX_GAP_DAYS == 7
        series = pts(("2024-01-01", "1"), ("2024-01-08", "1"), ("2024-01-16", "1"))
        assert [g.days for g in find_gaps(series)] == [8]


class TestFundStats:
    def test_full_stats_on_steady_series(self) -> None:
        series = steady_series(300)
        stats = fund_stats("SMP-BOND-1", "bond_sicav", series)
        assert isinstance(stats, FundStats)
        assert stats.fund_code == "SMP-BOND-1"
        assert stats.category == "bond_sicav"
        assert stats.observations == 300
        assert (stats.start, stats.end) == (series[0].date, series[-1].date)
        assert stats.total_return > 0
        assert stats.annualised_return > 0
        assert stats.max_drawdown == D(0)
        assert stats.worst_12m_return is not None and stats.worst_12m_return > 0
        assert stats.gap_count == 0
        assert stats.largest_gap_days == 3
        assert stats.annualised_volatility >= 0

    def test_results_are_rounded_rates(self) -> None:
        stats = fund_stats("X", "bond_sicav", steady_series(40))
        for value in (stats.total_return, stats.annualised_return, stats.annualised_volatility):
            assert value.as_tuple().exponent >= -6

    def test_short_series_has_no_worst_12m(self) -> None:
        stats = fund_stats("X", "bond_sicav", steady_series(MIN_OBSERVATIONS))
        assert stats.worst_12m_return is None

    def test_too_short_series_is_a_clear_error(self) -> None:
        with pytest.raises(InsufficientDataError, match=f"at least {MIN_OBSERVATIONS}"):
            fund_stats("X", "bond_sicav", steady_series(MIN_OBSERVATIONS - 1))

    def test_series_with_gap(self) -> None:
        series = steady_series(30) + steady_series(30, start="2023-04-03")
        stats = fund_stats("X", "bond_sicav", series)
        assert stats.gap_count == 1
        assert stats.largest_gap_days > MAX_GAP_DAYS

    def test_frozen(self) -> None:
        stats = fund_stats("X", "bond_sicav", steady_series(30))
        with pytest.raises(dataclasses.FrozenInstanceError):
            stats.fund_code = "Y"  # type: ignore[misc]


class TestCategoryStats:
    @staticmethod
    def make(code: str, category: str = "equity_sicav", **overrides) -> FundStats:
        base = {
            "fund_code": code,
            "category": category,
            "start": date(2023, 1, 2),
            "end": date(2025, 12, 31),
            "observations": 780,
            "total_return": D("0.2"),
            "annualised_return": D("0.06"),
            "annualised_volatility": D("0.10"),
            "max_drawdown": D("-0.15"),
            "worst_12m_return": D("-0.05"),
            "gap_count": 0,
            "largest_gap_days": 3,
        }
        return FundStats(**(base | overrides))

    def test_aggregates_mean_and_worst_case(self) -> None:
        a = self.make("A", start=date(2023, 3, 1))
        b = self.make(
            "B",
            end=date(2025, 6, 30),
            annualised_return=D("0.10"),
            annualised_volatility=D("0.20"),
            max_drawdown=D("-0.30"),
            worst_12m_return=None,
        )
        result = category_stats([a, b])
        assert isinstance(result, CategoryStats)
        assert result.category == "equity_sicav"
        assert result.fund_count == 2
        assert result.fund_codes == ("A", "B")
        assert result.mean_annualised_return == D("0.08")
        assert result.mean_annualised_volatility == D("0.15")
        assert result.worst_max_drawdown == D("-0.30")
        assert result.worst_12m_return == D("-0.05")
        assert (result.start, result.end) == (date(2023, 1, 2), date(2025, 12, 31))

    def test_worst_12m_none_when_no_fund_has_it(self) -> None:
        result = category_stats([self.make("A", worst_12m_return=None)])
        assert result.worst_12m_return is None

    def test_empty_rejected(self) -> None:
        with pytest.raises(InsufficientDataError, match="at least one fund"):
            category_stats([])

    def test_mixed_categories_rejected(self) -> None:
        with pytest.raises(StatsError, match="same category"):
            category_stats([self.make("A"), self.make("B", category="bond_sicav")])

    def test_on_sample_data(self, sample_dir) -> None:
        import csv
        from collections import defaultdict

        funds = {}
        with (sample_dir / "funds.csv").open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                funds[row["code"]] = row["category"]
        series: dict[str, list[PricePoint]] = defaultdict(list)
        with (sample_dir / "nav_prices.csv").open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                point = PricePoint(date.fromisoformat(row["date"]), D(row["nav"]))
                series[row["fund_code"]].append(point)
        stats = [fund_stats(code, funds[code], series[code]) for code in sorted(funds)]
        bonds = category_stats([s for s in stats if s.category == "bond_sicav"])
        equities = category_stats([s for s in stats if s.category == "equity_sicav"])
        assert bonds.fund_count == 2
        assert bonds.mean_annualised_volatility < equities.mean_annualised_volatility
        assert bonds.worst_max_drawdown > equities.worst_max_drawdown
