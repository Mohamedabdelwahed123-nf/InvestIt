"""Bad / average / good outcomes of a plan over historical rolling windows — deterministic.

Method (documented in docs/PLAN.md, "Calculator simulation"):
- `history` gives one NAV series per category used by the plan (e.g. an `equal_weight_index`).
- A window of `months` ends on any observation date d of those series such that the base day
  (d minus `months` calendar months, month-end clamped) is not before the latest series start
  and d is not after the earliest series end. Each category's value on a day is its last NAV on
  or before that day, so every line of the plan is measured on the same window (correlations kept).
- Window value = sum of each allocation amount x NAV(d) / NAV(base); no rebalancing, no fees.
- bad / average / good = p10 / p50 / p90 of the window values (linear interpolation between
  sorted values), then rounded to millimes. No randomness anywhere.
"""

from bisect import bisect_right
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.calculator.core.money import round_rate, round_tnd
from backend.calculator.core.plans import Plan, Profile
from backend.calculator.core.stats import (
    NavLike,
    PricePoint,
    Series,
    StatsError,
    months_before,
    validate_series,
)

MIN_WINDOWS = 20
INDEX_BASE = Decimal(100)
PERCENTILES = (("bad", 10), ("average", 50), ("good", 90))
_ZERO = Decimal(0)
_NAV_QUANTUM = Decimal("0.000001")


class SimulationError(ValueError):
    """The simulation cannot run (bad months, missing or invalid history...)."""


class InsufficientHistoryError(SimulationError):
    """The history is too short for the requested horizon."""


@dataclass(frozen=True, slots=True)
class Outcome:
    label: str  # bad | average | good
    percentile: int
    final_value: Decimal  # TND, millimes
    gain: Decimal  # final_value - amount
    return_rate: Decimal  # fraction, 6 decimals


@dataclass(frozen=True, slots=True)
class Simulation:
    profile: Profile
    amount: Decimal
    months: int
    window_count: int
    first_window_end: date
    last_window_end: date
    bad: Outcome
    average: Outcome
    good: Outcome

    @property
    def outcomes(self) -> tuple[Outcome, Outcome, Outcome]:
        return self.bad, self.average, self.good


def percentile(values: Sequence[Decimal], p: int) -> Decimal:
    """p-th percentile (0-100) with linear interpolation between sorted values."""
    if not 0 <= p <= 100:
        raise SimulationError("percentile must be between 0 and 100")
    if not values:
        raise SimulationError("percentile needs at least one value")
    ordered = sorted(values)
    rank = Decimal(p) * (len(ordered) - 1) / 100
    low = int(rank)
    if low == len(ordered) - 1:
        return ordered[low]
    return ordered[low] + (ordered[low + 1] - ordered[low]) * (rank - low)


def _validated(name: str, points: Iterable[NavLike]) -> Series:
    try:
        return validate_series(points, min_points=1)
    except StatsError as exc:
        raise SimulationError(f"{name}: {exc}") from exc


def _plan_series(plan: Plan, history: Mapping[str, Iterable[NavLike]]) -> dict[str, Series]:
    needed = sorted({a.category.value for a in plan.allocations})
    missing = [c for c in needed if c not in history]
    if missing:
        raise SimulationError(f"no NAV history for: {', '.join(missing)}")
    return {c: _validated(c, history[c]) for c in needed}


def _nav_on(series: Series, dates: list[date], day: date) -> Decimal:
    return series[bisect_right(dates, day) - 1].nav


def _window_ends(all_series: Iterable[Series], months: int) -> list[tuple[date, date]]:
    series = list(all_series)
    first = max(s[0].date for s in series)
    last = min(s[-1].date for s in series)
    days = sorted({p.date for s in series for p in s})
    pairs = ((d, months_before(d, months)) for d in days if d <= last)
    return [(end, base) for end, base in pairs if base >= first]


def _window_values(
    plan: Plan, series: dict[str, Series], months: int
) -> list[tuple[date, Decimal]]:
    dates = {c: [p.date for p in s] for c, s in series.items()}
    values = []
    for end, base in _window_ends(series.values(), months):
        total = _ZERO
        for line in plan.allocations:
            s, d = series[line.category.value], dates[line.category.value]
            total += line.amount * _nav_on(s, d, end) / _nav_on(s, d, base)
        values.append((end, total))
    return values


def _outcome(label: str, p: int, values: Sequence[Decimal], amount: Decimal) -> Outcome:
    raw = percentile(values, p)
    final = round_tnd(raw)
    return Outcome(label, p, final, final - amount, round_rate(raw / amount - 1))


def simulate(
    plan: Plan,
    months: int,
    history: Mapping[str, Iterable[NavLike]],
    *,
    min_windows: int = MIN_WINDOWS,
) -> Simulation:
    """p10 / p50 / p90 of what the plan would have become over every past `months` window."""
    if not isinstance(months, int) or isinstance(months, bool) or months < 1:
        raise SimulationError("months must be a whole number of at least 1")
    windows = _window_values(plan, _plan_series(plan, history), months)
    if not windows:
        raise InsufficientHistoryError(f"history is too short for {months}-month windows")
    if len(windows) < min_windows:
        raise InsufficientHistoryError(
            f"needs at least {min_windows} {months}-month windows, history gives {len(windows)}"
        )
    values = [v for _, v in windows]
    bad, average, good = (_outcome(label, p, values, plan.amount) for label, p in PERCENTILES)
    return Simulation(
        profile=plan.profile,
        amount=plan.amount,
        months=months,
        window_count=len(windows),
        first_window_end=windows[0][0],
        last_window_end=windows[-1][0],
        bad=bad,
        average=average,
        good=good,
    )


def equal_weight_index(all_points: Sequence[Iterable[NavLike]]) -> tuple[PricePoint, ...]:
    """Buy-and-hold equal-weight index of several funds on their common dates, base 100."""
    if not all_points:
        raise SimulationError("an index needs at least one NAV series")
    series = [_validated(f"series {i + 1}", pts) for i, pts in enumerate(all_points)]
    common = sorted(set.intersection(*({p.date for p in s} for s in series)))
    if not common:
        raise InsufficientHistoryError("the NAV series have no common dates")
    navs = [{p.date: p.nav for p in s} for s in series]
    bases = [n[common[0]] for n in navs]
    count = Decimal(len(series))
    return tuple(
        PricePoint(
            day,
            (
                INDEX_BASE
                * sum((n[day] / b for n, b in zip(navs, bases, strict=True)), _ZERO)
                / count
            ).quantize(_NAV_QUANTUM),
        )
        for day in common
    )
