"""Fund statistics from a NAV series — plain Decimal maths, no DB, no AI.

Conventions (see docs/PLAN.md, "Calculator statistics"):
- A series is NAV observations on trading days only; weekends/holidays are simply absent.
  Returns are measured between consecutive observations, whatever the calendar distance.
- Time is calendar time: a year is 365.25 days.
- Annualised return: (last / first) ** (365.25 / days) - 1.
- Annualised volatility: sample standard deviation of observation-to-observation returns,
  times sqrt(observed periods per year), where periods per year = returns / (days / 365.25).
- Max drawdown: worst fall from a running peak (<= 0).
- Worst 12-month return: for every observation at least 12 calendar months after the start,
  NAV vs the last NAV on or before the same day 12 months earlier; the minimum (None if the
  series is shorter than 12 months).
- A gap is a distance between consecutive observations longer than MAX_GAP_DAYS calendar days.
All rates are fractions (0.1 = 10%) rounded half-up to 6 decimals in the output models.
"""

import calendar
from bisect import bisect_right
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import StrEnum
from itertools import pairwise
from typing import Protocol

from backend.calculator.core.money import DecimalLike, round_rate, to_decimal

DAYS_PER_YEAR = Decimal("365.25")
MAX_GAP_DAYS = 7
MIN_OBSERVATIONS = 20
_ZERO = Decimal(0)
_PRECISION = 28


class StatsError(ValueError):
    """The NAV series cannot be used (duplicates, non-positive NAV, mixed categories...)."""


class InsufficientDataError(StatsError):
    """The series is too short for the requested statistic."""


class NavLike(Protocol):
    """Anything with a date and a Decimal NAV (e.g. the repository's NavPoint)."""

    @property
    def date(self) -> date: ...

    @property
    def nav(self) -> DecimalLike: ...


class Frequency(StrEnum):
    OBSERVATION = "observation"
    MONTHLY = "monthly"
    YEARLY = "yearly"


@dataclass(frozen=True, slots=True)
class PricePoint:
    date: date
    nav: Decimal


@dataclass(frozen=True, slots=True)
class PeriodReturn:
    start: date
    end: date
    value: Decimal


@dataclass(frozen=True, slots=True)
class Gap:
    start: date
    end: date
    days: int


@dataclass(frozen=True, slots=True)
class FundStats:
    fund_code: str
    category: str
    start: date
    end: date
    observations: int
    total_return: Decimal
    annualised_return: Decimal
    annualised_volatility: Decimal
    max_drawdown: Decimal
    worst_12m_return: Decimal | None
    gap_count: int
    largest_gap_days: int


@dataclass(frozen=True, slots=True)
class CategoryStats:
    """Equal-weight mean of the funds' return/volatility plus worst-case risk figures."""

    category: str
    fund_count: int
    fund_codes: tuple[str, ...]
    start: date
    end: date
    mean_annualised_return: Decimal
    mean_annualised_volatility: Decimal
    worst_max_drawdown: Decimal
    worst_12m_return: Decimal | None


type Series = tuple[PricePoint, ...]


def _require(series: Sequence[object], min_points: int) -> None:
    if len(series) < min_points:
        raise InsufficientDataError(
            f"needs at least {min_points} NAV observations, got {len(series)}"
        )


def validate_series(points: Iterable[NavLike], *, min_points: int = 1) -> Series:
    """Sort by date and check: no duplicate dates, every NAV a positive Decimal."""
    series = tuple(sorted((PricePoint(p.date, to_decimal(p.nav)) for p in points), key=_by_date))
    _require(series, min_points)
    for previous, current in pairwise(series):
        if previous.date == current.date:
            raise StatsError(f"duplicate date {current.date.isoformat()} in NAV series")
    for point in series:
        if point.nav <= 0:
            raise StatsError(f"NAV on {point.date.isoformat()} must be positive")
    return series


def _by_date(point: PricePoint) -> date:
    return point.date


def _span_days(series: Series) -> int:
    return (series[-1].date - series[0].date).days


def _resample(series: Series, frequency: Frequency) -> Series:
    """First observation, then the last observation of each month/year."""
    if frequency is Frequency.OBSERVATION:
        return series

    def key(point: PricePoint) -> tuple[int, ...]:
        d = point.date
        return (d.year, d.month) if frequency is Frequency.MONTHLY else (d.year,)

    closes = [a for a, b in pairwise(series) if key(a) != key(b)]
    closes.append(series[-1])
    return series[:1] + tuple(p for p in closes if p != series[0])


def period_returns(
    points: Iterable[NavLike], frequency: Frequency = Frequency.OBSERVATION
) -> tuple[PeriodReturn, ...]:
    series = _resample(validate_series(points, min_points=2), frequency)
    return tuple(
        PeriodReturn(a.date, b.date, round_rate(b.nav / a.nav - 1)) for a, b in pairwise(series)
    )


def total_return(points: Iterable[NavLike]) -> Decimal:
    series = validate_series(points, min_points=2)
    return round_rate(series[-1].nav / series[0].nav - 1)


def _annualised(series: Series) -> Decimal:
    days = _span_days(series)
    growth = series[-1].nav / series[0].nav
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        return growth ** (DAYS_PER_YEAR / Decimal(days)) - 1


def annualised_return(points: Iterable[NavLike]) -> Decimal:
    return round_rate(_annualised(validate_series(points, min_points=2)))


def _volatility(series: Series) -> Decimal:
    returns = [b.nav / a.nav - 1 for a, b in pairwise(series)]
    count = Decimal(len(returns))
    mean = sum(returns, _ZERO) / count
    variance = sum(((r - mean) ** 2 for r in returns), _ZERO) / (count - 1)
    periods_per_year = count * DAYS_PER_YEAR / Decimal(_span_days(series))
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        return (variance * periods_per_year).sqrt()


def annualised_volatility(points: Iterable[NavLike]) -> Decimal:
    return round_rate(_volatility(validate_series(points, min_points=3)))


def _drawdown(series: Series) -> Decimal:
    peak = series[0].nav
    worst = _ZERO
    for point in series:
        peak = max(peak, point.nav)
        worst = min(worst, point.nav / peak - 1)
    return worst


def max_drawdown(points: Iterable[NavLike]) -> Decimal:
    return round_rate(_drawdown(validate_series(points)))


def months_before(day: date, months: int) -> date:
    """Same day `months` calendar months earlier, clamped to the month end (Feb 29 -> Feb 28)."""
    index = day.year * 12 + day.month - 1 - months
    year, month = divmod(index, 12)
    last_day = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(day.day, last_day))


def _worst_rolling(series: Series, months: int) -> Decimal | None:
    dates = [p.date for p in series]
    worst: Decimal | None = None
    for point in series:
        base_day = months_before(point.date, months)
        if base_day < series[0].date:
            continue
        base = series[bisect_right(dates, base_day) - 1]
        change = point.nav / base.nav - 1
        worst = change if worst is None else min(worst, change)
    return worst


def worst_rolling_return(points: Iterable[NavLike], months: int = 12) -> Decimal | None:
    if months < 1:
        raise StatsError("months must be at least 1")
    worst = _worst_rolling(validate_series(points), months)
    return None if worst is None else round_rate(worst)


def _gaps(series: Series, max_gap_days: int) -> tuple[Gap, ...]:
    pairs = pairwise(series)
    spans = (Gap(a.date, b.date, (b.date - a.date).days) for a, b in pairs)
    return tuple(g for g in spans if g.days > max_gap_days)


def find_gaps(points: Iterable[NavLike], max_gap_days: int = MAX_GAP_DAYS) -> tuple[Gap, ...]:
    return _gaps(validate_series(points), max_gap_days)


def fund_stats(
    fund_code: str,
    category: str,
    points: Iterable[NavLike],
    *,
    min_observations: int = MIN_OBSERVATIONS,
) -> FundStats:
    """All statistics for one fund. Raises InsufficientDataError for too-short series."""
    series = validate_series(points, min_points=max(min_observations, 3))
    worst_12m = _worst_rolling(series, 12)
    steps = [(b.date - a.date).days for a, b in pairwise(series)]
    return FundStats(
        fund_code=fund_code,
        category=category,
        start=series[0].date,
        end=series[-1].date,
        observations=len(series),
        total_return=round_rate(series[-1].nav / series[0].nav - 1),
        annualised_return=round_rate(_annualised(series)),
        annualised_volatility=round_rate(_volatility(series)),
        max_drawdown=round_rate(_drawdown(series)),
        worst_12m_return=None if worst_12m is None else round_rate(worst_12m),
        gap_count=len(_gaps(series, MAX_GAP_DAYS)),
        largest_gap_days=max(steps),
    )


def _mean(values: Sequence[Decimal]) -> Decimal:
    return round_rate(sum(values, _ZERO) / Decimal(len(values)))


def category_stats(funds: Sequence[FundStats]) -> CategoryStats:
    """Aggregate funds of one category: equal-weight means and worst-case risk."""
    if not funds:
        raise InsufficientDataError("needs at least one fund to aggregate a category")
    categories = {f.category for f in funds}
    if len(categories) != 1:
        raise StatsError(f"funds must share the same category, got {sorted(categories)}")
    worst_12m = [f.worst_12m_return for f in funds if f.worst_12m_return is not None]
    return CategoryStats(
        category=funds[0].category,
        fund_count=len(funds),
        fund_codes=tuple(f.fund_code for f in funds),
        start=min(f.start for f in funds),
        end=max(f.end for f in funds),
        mean_annualised_return=_mean([f.annualised_return for f in funds]),
        mean_annualised_volatility=_mean([f.annualised_volatility for f in funds]),
        worst_max_drawdown=min(f.max_drawdown for f in funds),
        worst_12m_return=min(worst_12m) if worst_12m else None,
    )
