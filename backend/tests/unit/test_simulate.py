"""Tests for calculator/core/simulate.py — bad/average/good outcomes over historical windows."""

import dataclasses
from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.calculator.core.plans import AssetCategory, make_plan
from backend.calculator.core.simulate import (
    MIN_WINDOWS,
    InsufficientHistoryError,
    SimulationError,
    equal_weight_index,
    percentile,
    simulate,
)
from backend.calculator.core.stats import PricePoint
from backend.db.domain import NavPoint

D = Decimal
START = date(2020, 1, 1)


def daily(values: list[Decimal], start: date = START) -> list[PricePoint]:
    return [PricePoint(start + timedelta(days=i), v) for i, v in enumerate(values)]


def flat(days: int, nav: str = "100") -> list[PricePoint]:
    return daily([D(nav)] * days)


def growing(days: int, step: str) -> list[PricePoint]:
    return daily([D(100) + D(step) * i for i in range(days)])


def bond_only_plan(amount: str = "1000"):
    return make_plan(amount, 6, "medium", True, "cautious")


# --- percentile ------------------------------------------------------------------------------


def test_percentile_linear_interpolation() -> None:
    values = [D(v) for v in ("4", "1", "3", "2", "5")]
    assert percentile(values, 0) == D(1)
    assert percentile(values, 50) == D(3)
    assert percentile(values, 100) == D(5)
    assert percentile(values, 10) == D("1.4")
    assert percentile([D(7)], 90) == D(7)


@pytest.mark.parametrize("p", [-1, 101])
def test_percentile_rejects_bad_p(p: int) -> None:
    with pytest.raises(SimulationError, match="percentile"):
        percentile([D(1)], p)


def test_percentile_rejects_empty() -> None:
    with pytest.raises(SimulationError, match="at least one"):
        percentile([], 50)


# --- simulate --------------------------------------------------------------------------------


def test_flat_history_returns_the_amount() -> None:
    result = simulate(bond_only_plan(), 1, {"bond_sicav": flat(120)})
    for outcome in result.outcomes:
        assert outcome.final_value == D("1000.000")
        assert outcome.gain == D("0.000")
        assert outcome.return_rate == D("0.000000")
    assert [o.label for o in result.outcomes] == ["bad", "average", "good"]
    assert [o.percentile for o in result.outcomes] == [10, 50, 90]


def test_known_windows_give_known_percentiles() -> None:
    # NAV 100, 101, ..., each 1-month window gains a different amount: smaller later on.
    history = {"bond_sicav": growing(100, "1")}
    result = simulate(bond_only_plan(), 1, history)
    # windows end on day 31 .. day 99 (base = same day one month earlier)
    assert result.window_count == 69
    assert result.first_window_end == date(2020, 2, 1)
    assert result.last_window_end == START + timedelta(days=99)
    assert result.bad.final_value < result.average.final_value < result.good.final_value
    assert result.bad.gain == result.bad.final_value - D(1000)


def test_mixed_plan_uses_each_category_on_the_same_windows() -> None:
    plan = make_plan("1000", 12, "medium", True, "growth")  # 500 bond / 400 mixed / 100 equity
    days = 800
    history = {
        "bond_sicav": flat(days),
        "mixed_sicav": flat(days),
        "equity_sicav": daily([D(100) if i < 500 else D(50) for i in range(days)]),
    }
    result = simulate(plan, 12, history)
    # equity halves for windows ending on/after day 500 whose base is before day 500
    assert result.bad.final_value == D("950.000")
    assert result.good.final_value == D("1000.000")
    assert result.bad.return_rate == D("-0.050000")


def test_accepts_repository_navpoints_and_ignores_unused_categories() -> None:
    points = [NavPoint(p.date, p.nav, "SAMPLE") for p in growing(60, "0.5")]
    result = simulate(bond_only_plan(), 1, {"bond_sicav": points, "equity_sicav": flat(3)})
    assert result.window_count > 0
    assert result.amount == D("1000.000")


def test_is_deterministic() -> None:
    plan = make_plan("1000", 12, "medium", False, "growth")
    history = {
        c: growing(900, step)
        for c, step in zip(
            ("bond_sicav", "mixed_sicav", "equity_sicav"), ("0.01", "0.03", "-0.02"), strict=True
        )
    }
    assert simulate(plan, 12, history) == simulate(plan, 12, history)


def test_result_is_frozen() -> None:
    result = simulate(bond_only_plan(), 1, {"bond_sicav": flat(60)})
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.months = 2  # type: ignore[misc]


def test_missing_category_history_is_an_error() -> None:
    plan = make_plan("1000", 12, "medium", True, "growth")
    with pytest.raises(SimulationError, match="mixed_sicav"):
        simulate(plan, 12, {"bond_sicav": flat(800)})


def test_history_too_short_for_the_horizon() -> None:
    with pytest.raises(InsufficientHistoryError, match="12-month"):
        simulate(bond_only_plan(), 12, {"bond_sicav": flat(300)})


def test_too_few_windows() -> None:
    # 1-month windows on 40 days of history: only ~9 windows < MIN_WINDOWS
    assert MIN_WINDOWS == 20
    with pytest.raises(InsufficientHistoryError, match="windows"):
        simulate(bond_only_plan(), 1, {"bond_sicav": flat(40)})
    assert simulate(bond_only_plan(), 1, {"bond_sicav": flat(40)}, min_windows=1).window_count == 9


def test_categories_must_overlap_in_time() -> None:
    plan = make_plan("1000", 12, "medium", True, "cautious")
    history = {
        "bond_sicav": flat(400),
        "mixed_sicav": daily([D(100)] * 400, start=date(2023, 1, 1)),
    }
    with pytest.raises(InsufficientHistoryError):
        simulate(plan, 12, history)


@pytest.mark.parametrize("months", [0, -3, True])
def test_bad_months(months: int) -> None:
    with pytest.raises(SimulationError, match="months"):
        simulate(bond_only_plan(), months, {"bond_sicav": flat(60)})


def test_bad_nav_series_is_reported() -> None:
    bad = flat(60)
    bad[5] = PricePoint(bad[5].date, D(0))
    with pytest.raises(SimulationError, match="positive"):
        simulate(bond_only_plan(), 1, {"bond_sicav": bad})


# --- equal-weight category index -------------------------------------------------------------


def test_equal_weight_index_on_common_dates() -> None:
    a = daily([D(10), D(11), D(12)])
    b = daily([D(200), D(200), D(100), D(50)])
    index = equal_weight_index([a, b])
    assert [p.nav for p in index] == [D(100), D(105), D(85)]
    assert [p.date for p in index] == [p.date for p in a]


def test_equal_weight_index_errors() -> None:
    with pytest.raises(SimulationError, match="at least one"):
        equal_weight_index([])
    with pytest.raises(InsufficientHistoryError, match="common"):
        equal_weight_index([flat(3), daily([D(1)], start=date(2030, 1, 1))])


# --- properties ------------------------------------------------------------------------------

navs = st.lists(
    st.integers(min_value=1, max_value=10**6).map(lambda n: D(n) / 100), min_size=70, max_size=200
)


@settings(max_examples=50, deadline=None)
@given(
    bond=navs,
    mixed=navs,
    equity=navs,
    amount=st.integers(min_value=1, max_value=10**9).map(lambda m: D(m) / 1000),
    months=st.integers(min_value=12, max_value=24),
)
def test_property_outcomes_are_ordered_and_rounded(bond, mixed, equity, amount, months) -> None:
    plan = make_plan(amount, months, "high", False, "growth")
    history = {
        "bond_sicav": daily(bond),
        "mixed_sicav": daily(mixed),
        "equity_sicav": daily(equity),
    }
    result = simulate(plan, 2, history, min_windows=1)
    assert result.bad.final_value <= result.average.final_value <= result.good.final_value
    for o in result.outcomes:
        assert o.final_value >= 0
        assert o.final_value == o.final_value.quantize(D("0.001"))
        assert o.gain == o.final_value - plan.amount
    assert {a.category for a in plan.allocations} <= set(AssetCategory)
