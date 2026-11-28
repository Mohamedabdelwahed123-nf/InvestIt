"""Tests for calculator/core/plans.py — Cautious vs Growth allocations (no AI, Decimal only)."""

import dataclasses
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from backend.calculator.core.money import MoneyError
from backend.calculator.core.plans import (
    CAUTIOUS_CAP_FACTOR,
    EMERGENCY_RESERVE_PERCENT,
    EXPOSURE_CAPS,
    MAX_MONTHS,
    NATIONAL_BOND_MIN_MONTHS,
    SHORT_HORIZON_MONTHS,
    AssetCategory,
    Plan,
    PlanError,
    Profile,
    Purpose,
    RiskTolerance,
    make_plan,
)
from backend.db.domain import Category

D = Decimal
BOND = AssetCategory.BOND_SICAV
NATIONAL = AssetCategory.NATIONAL_BOND
MIXED = AssetCategory.MIXED_SICAV
EQUITY = AssetCategory.EQUITY_SICAV


def by_line(plan: Plan) -> dict[tuple[str, str], Decimal]:
    return {(a.category.value, a.purpose.value): a.amount for a in plan.allocations}


# --- scenario: 1,000 TND, 12 months, "a bit" worried by a 10% drop -------------------------


def test_scenario_1000_tnd_12_months_with_emergency_fund() -> None:
    args = dict(amount="1000", months=12, risk_tolerance="medium", has_emergency_fund=True)
    cautious = make_plan(**args, profile="cautious")
    growth = make_plan(**args, profile="growth")

    assert by_line(cautious) == {
        ("bond_sicav", "investment"): D("800.000"),
        ("mixed_sicav", "investment"): D("200.000"),
    }
    assert by_line(growth) == {
        ("bond_sicav", "investment"): D("500.000"),
        ("mixed_sicav", "investment"): D("400.000"),
        ("equity_sicav", "investment"): D("100.000"),
    }
    assert cautious.allocations != growth.allocations
    assert cautious.equity_exposure_percent == D(10)
    assert growth.equity_exposure_percent == D(30)
    for plan in (cautious, growth):
        assert sum(a.amount for a in plan.allocations) == D("1000.000")
        assert sum(a.percent for a in plan.allocations) == D(100)


def test_scenario_1000_tnd_12_months_without_emergency_fund() -> None:
    args = dict(amount=1000, months=12, risk_tolerance=RiskTolerance.MEDIUM)
    cautious = make_plan(**args, has_emergency_fund=False, profile=Profile.CAUTIOUS)
    growth = make_plan(**args, has_emergency_fund=False, profile=Profile.GROWTH)

    assert by_line(cautious) == {
        ("bond_sicav", "emergency"): D("300.000"),
        ("bond_sicav", "investment"): D("560.000"),
        ("mixed_sicav", "investment"): D("140.000"),
    }
    assert by_line(growth) == {
        ("bond_sicav", "emergency"): D("300.000"),
        ("bond_sicav", "investment"): D("350.000"),
        ("mixed_sicav", "investment"): D("280.000"),
        ("equity_sicav", "investment"): D("70.000"),
    }
    assert growth.allocations[0].purpose is Purpose.EMERGENCY
    assert any("emergency" in note for note in growth.notes)


# --- rules -----------------------------------------------------------------------------------


@pytest.mark.parametrize("months", [1, 6, 11])
@pytest.mark.parametrize("profile", list(Profile))
def test_short_horizon_is_bond_sicav_only(months: int, profile: Profile) -> None:
    plan = make_plan("500", months, "high", True, profile)
    assert {a.category for a in plan.allocations} == {BOND}
    assert plan.equity_exposure_percent == 0
    assert any("12 months" in note for note in plan.notes)


@pytest.mark.parametrize(
    ("months", "profile", "expected"),
    [
        (12, "cautious", {BOND: 80, MIXED: 20}),
        (35, "growth", {BOND: 50, MIXED: 40, EQUITY: 10}),
        (36, "cautious", {BOND: 60, MIXED: 30, EQUITY: 10}),
        (59, "growth", {BOND: 30, MIXED: 40, EQUITY: 30}),
        # cautious cap at high tolerance is 65 x 0.5 = 32.5: 2.5 points of equity go to bond
        (60, "cautious", {BOND: D("52.5"), MIXED: 30, EQUITY: D("17.5")}),
        (120, "growth", {BOND: 20, MIXED: 30, EQUITY: 50}),
    ],
)
def test_horizon_bands_with_high_tolerance(
    months: int, profile: str, expected: dict[AssetCategory, int | Decimal]
) -> None:
    plan = make_plan("1000", months, "high", True, profile)
    assert {a.category: a.percent for a in plan.allocations} == {
        k: D(v) for k, v in expected.items()
    }


def test_low_tolerance_caps_exposure_and_keeps_plans_different() -> None:
    cautious = make_plan("1000", 120, "low", True, "cautious")
    growth = make_plan("1000", 120, "low", True, "growth")
    assert {a.category: a.percent for a in growth.allocations} == {BOND: 70, MIXED: 30}
    assert {a.category: a.percent for a in cautious.allocations} == {BOND: 85, MIXED: 15}
    assert growth.equity_exposure_percent == EXPOSURE_CAPS[RiskTolerance.LOW]
    assert any("risk tolerance" in note for note in growth.notes)


def test_national_bond_only_when_long_and_open() -> None:
    closed = make_plan("1000", 60, "medium", True, "cautious")
    assert NATIONAL not in {a.category for a in closed.allocations}
    assert any("tranche" in note for note in closed.notes)

    too_short = make_plan("1000", 59, "medium", True, "cautious", national_bond_open=True)
    assert NATIONAL not in {a.category for a in too_short.allocations}

    opened = make_plan("1000", 60, "medium", False, "cautious", national_bond_open=True)
    lines = by_line(opened)
    assert lines[("national_bond", "investment")] == lines[("bond_sicav", "investment")]
    assert lines[("bond_sicav", "emergency")] == D("300.000")


def test_amount_for_sums_lines_of_a_category() -> None:
    plan = make_plan("1000", 12, "medium", False, "cautious")
    assert plan.amount_for(BOND) == D("860.000")
    assert plan.amount_for(EQUITY) == D("0.000")


def test_plan_is_frozen_and_records_inputs() -> None:
    plan = make_plan("1000.5", 24, "medium", True, "growth")
    assert plan.amount == D("1000.500")
    assert (plan.months, plan.profile, plan.risk_tolerance) == (24, Profile.GROWTH, "medium")
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.months = 3  # type: ignore[misc]


def test_categories_match_the_database_and_exclude_stocks() -> None:
    assert {c.value for c in AssetCategory} <= {c.value for c in Category}
    assert not any("stock" in c.value for c in AssetCategory)


def test_millimes_are_split_exactly() -> None:
    plan = make_plan("0.007", 24, "medium", False, "growth")
    assert sum(a.amount for a in plan.allocations) == D("0.007")
    assert all(a.amount >= 0 for a in plan.allocations)


# --- validation ------------------------------------------------------------------------------


@pytest.mark.parametrize("months", [0, -1, MAX_MONTHS + 1])
def test_bad_months_rejected(months: int) -> None:
    with pytest.raises(PlanError, match="months"):
        make_plan("1000", months, "medium", True, "cautious")


@pytest.mark.parametrize("months", [True, "12", 12.0])
def test_months_must_be_an_int(months: object) -> None:
    with pytest.raises(PlanError, match="months"):
        make_plan("1000", months, "medium", True, "cautious")  # type: ignore[arg-type]


@pytest.mark.parametrize("amount", ["0", "-5", "1.0001", 1.5, "abc"])
def test_bad_amount_rejected(amount: object) -> None:
    with pytest.raises(MoneyError):
        make_plan(amount, 12, "medium", True, "cautious")  # type: ignore[arg-type]


def test_bad_enums_rejected() -> None:
    with pytest.raises(PlanError, match="risk_tolerance"):
        make_plan("1000", 12, "extreme", True, "cautious")
    with pytest.raises(PlanError, match="profile"):
        make_plan("1000", 12, "medium", True, "yolo")
    with pytest.raises(PlanError, match="has_emergency_fund"):
        make_plan("1000", 12, "medium", "yes", "cautious")  # type: ignore[arg-type]
    with pytest.raises(PlanError, match="national_bond_open"):
        make_plan("1000", 12, "medium", True, "cautious", national_bond_open=1)  # type: ignore[arg-type]


# --- properties ------------------------------------------------------------------------------

amounts = st.integers(min_value=1, max_value=10**12).map(lambda m: D(m) / 1000)
inputs = st.fixed_dictionaries(
    {
        "amount": amounts,
        "months": st.integers(min_value=1, max_value=MAX_MONTHS),
        "risk_tolerance": st.sampled_from(list(RiskTolerance)),
        "has_emergency_fund": st.booleans(),
        "national_bond_open": st.booleans(),
    }
)


@given(inputs, st.sampled_from(list(Profile)))
def test_property_allocations_are_exact_and_non_negative(kw: dict, profile: Profile) -> None:
    plan = make_plan(profile=profile, **kw)
    assert sum(a.amount for a in plan.allocations) == plan.amount
    assert sum(a.percent for a in plan.allocations) == 100
    assert all(a.amount >= 0 and a.percent > 0 for a in plan.allocations)
    assert all(a.amount == a.amount.quantize(D("0.001")) for a in plan.allocations)


@given(inputs, st.sampled_from(list(Profile)))
def test_property_rules_are_respected(kw: dict, profile: Profile) -> None:
    plan = make_plan(profile=profile, **kw)
    categories = {a.category for a in plan.allocations}
    if kw["months"] < SHORT_HORIZON_MONTHS:
        assert categories == {BOND}
    if NATIONAL in categories:
        assert kw["national_bond_open"] and kw["months"] >= NATIONAL_BOND_MIN_MONTHS
    emergency = [a for a in plan.allocations if a.purpose is Purpose.EMERGENCY]
    if kw["has_emergency_fund"]:
        assert not emergency
    else:
        assert [(a.category, a.percent) for a in emergency] == [(BOND, EMERGENCY_RESERVE_PERCENT)]
    cap = EXPOSURE_CAPS[kw["risk_tolerance"]]
    if profile is Profile.CAUTIOUS:
        cap *= CAUTIOUS_CAP_FACTOR
    assert plan.equity_exposure_percent <= cap


@given(inputs)
def test_property_cautious_never_riskier_than_growth(kw: dict) -> None:
    cautious = make_plan(profile="cautious", **kw)
    growth = make_plan(profile="growth", **kw)
    assert cautious.equity_exposure_percent <= growth.equity_exposure_percent
    if kw["months"] >= SHORT_HORIZON_MONTHS:
        assert cautious.equity_exposure_percent < growth.equity_exposure_percent
        assert cautious.allocations != growth.allocations


@given(inputs, st.sampled_from(list(Profile)))
def test_property_same_inputs_same_plan(kw: dict, profile: Profile) -> None:
    assert make_plan(profile=profile, **kw) == make_plan(profile=profile, **kw)
