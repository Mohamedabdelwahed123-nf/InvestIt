"""Tests for calculator/core/money.py — Decimal helpers, TND rounding, safe percentages."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from backend.calculator.core.money import (
    TND_QUANTUM,
    MoneyError,
    allocate,
    apply_rate,
    fraction_to_percent,
    parse_amount,
    percent_of,
    percent_to_fraction,
    round_rate,
    round_tnd,
    safe_divide,
    to_decimal,
)

D = Decimal


class TestToDecimal:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(D("1.5"), D("1.5")), (7, D("7")), ("1000.250", D("1000.250")), (" 12 ", D("12"))],
    )
    def test_accepts_decimal_int_and_text(self, value, expected) -> None:
        assert to_decimal(value) == expected

    def test_rejects_float(self) -> None:
        with pytest.raises(MoneyError, match="float"):
            to_decimal(0.1)

    def test_rejects_bool(self) -> None:
        with pytest.raises(MoneyError, match="bool"):
            to_decimal(True)

    @pytest.mark.parametrize("value", ["abc", "", "1,5", "NaN", "Infinity", D("NaN"), D("-Inf")])
    def test_rejects_non_numbers_and_non_finite(self, value) -> None:
        with pytest.raises(MoneyError):
            to_decimal(value)

    def test_rejects_other_types(self) -> None:
        with pytest.raises(MoneyError, match="list"):
            to_decimal([1])  # type: ignore[arg-type]


class TestRoundTnd:
    def test_quantum_is_one_millime(self) -> None:
        assert TND_QUANTUM == D("0.001")

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (D("1.0004"), D("1.000")),
            (D("1.0005"), D("1.001")),  # half-up, not banker's rounding
            (D("2.0025"), D("2.003")),
            (D("-1.0005"), D("-1.001")),
            (D("10"), D("10.000")),
        ],
    )
    def test_rounds_half_up_to_three_decimals(self, value, expected) -> None:
        result = round_tnd(value)
        assert result == expected
        assert result.as_tuple().exponent == -3

    def test_accepts_text(self) -> None:
        assert round_tnd("3.14159") == D("3.142")


class TestRoundRate:
    def test_default_six_places(self) -> None:
        assert round_rate(D("0.12345675")) == D("0.123457")

    def test_custom_places(self) -> None:
        assert round_rate(D("0.125"), places=2) == D("0.13")

    def test_negative_places_rejected(self) -> None:
        with pytest.raises(MoneyError, match="places"):
            round_rate(D("1"), places=-1)


class TestParseAmount:
    def test_valid_amount_is_quantized(self) -> None:
        assert parse_amount("1000") == D("1000.000")

    def test_rejects_negative(self) -> None:
        with pytest.raises(MoneyError, match="negative"):
            parse_amount("-5")

    def test_rejects_zero_by_default(self) -> None:
        with pytest.raises(MoneyError, match="greater than zero"):
            parse_amount(0)

    def test_allows_zero_when_asked(self) -> None:
        assert parse_amount(0, allow_zero=True) == D("0.000")

    def test_rejects_more_than_millimes(self) -> None:
        with pytest.raises(MoneyError, match="3 decimals"):
            parse_amount("1.0005")


class TestPercentages:
    def test_percent_to_fraction(self) -> None:
        assert percent_to_fraction(10) == D("0.1")

    def test_fraction_to_percent(self) -> None:
        assert fraction_to_percent(D("0.075")) == D("7.5")

    def test_percent_of_rounds_to_millimes(self) -> None:
        assert percent_of(D("1000"), D("33.3333")) == D("333.333")
        assert percent_of(D("0.010"), 50) == D("0.005")

    def test_apply_rate(self) -> None:
        assert apply_rate(D("1000"), D("-0.1")) == D("900.000")
        assert apply_rate(D("1000"), D("0.0712345")) == D("1071.235")

    def test_apply_rate_below_minus_one_rejected(self) -> None:
        with pytest.raises(MoneyError, match="-100%"):
            apply_rate(D("1000"), D("-1.5"))


class TestSafeDivide:
    def test_divides(self) -> None:
        assert safe_divide(D("1"), D("4")) == D("0.25")

    def test_zero_denominator_is_a_clear_error(self) -> None:
        with pytest.raises(MoneyError, match="zero"):
            safe_divide(D("1"), D("0"))


class TestAllocate:
    def test_even_split_with_remainder_goes_to_first(self) -> None:
        assert allocate(D("100"), [1, 1, 1]) == (D("33.334"), D("33.333"), D("33.333"))

    def test_weighted_split(self) -> None:
        assert allocate(D("1000"), [D("0.6"), D("0.4")]) == (D("600.000"), D("400.000"))

    def test_zero_weight_gets_nothing(self) -> None:
        assert allocate(D("10"), [0, 1]) == (D("0.000"), D("10.000"))

    def test_zero_amount(self) -> None:
        assert allocate(D("0"), [1, 2]) == (D("0.000"), D("0.000"))

    @pytest.mark.parametrize(
        ("weights", "message"),
        [([], "at least one"), ([1, -1], "negative"), ([0, 0], "sum")],
    )
    def test_bad_weights(self, weights, message) -> None:
        with pytest.raises(MoneyError, match=message):
            allocate(D("10"), weights)

    def test_amount_must_be_millimes(self) -> None:
        with pytest.raises(MoneyError, match="3 decimals"):
            allocate(D("10.0001"), [1])

    @given(
        amount=st.decimals(min_value=0, max_value=10**9, places=3, allow_nan=False),
        weights=st.lists(st.integers(min_value=0, max_value=1000), min_size=1, max_size=8).filter(
            lambda w: sum(w) > 0
        ),
    )
    def test_parts_sum_exactly_and_are_never_negative(self, amount, weights) -> None:
        parts = allocate(amount, weights)
        assert sum(parts, D(0)) == amount
        assert all(p >= 0 for p in parts)
        assert all(p.as_tuple().exponent == -3 for p in parts)
        assert all(p == 0 for p, w in zip(parts, weights, strict=True) if w == 0)
