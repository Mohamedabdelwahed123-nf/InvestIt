"""Decimal money helpers: parsing, TND rounding (millimes) and safe percentage operations.

Rules: money is always `Decimal`, never `float`. TND amounts are rounded half-up to 3 decimals
(1 TND = 1000 millimes). Rates (returns, volatility) are plain fractions (0.1 = 10%).
"""

from collections.abc import Sequence
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation

type DecimalLike = Decimal | int | str

TND_QUANTUM = Decimal("0.001")
RATE_PLACES = 6
_ZERO = Decimal(0)
_HUNDRED = Decimal(100)


class MoneyError(ValueError):
    """A money value or operation is invalid (bad type, non-finite, division by zero...)."""


def to_decimal(value: DecimalLike) -> Decimal:
    """Convert to a finite Decimal. Floats and bools are refused (they hide rounding errors)."""
    if isinstance(value, bool):
        raise MoneyError("bool is not a number")
    if isinstance(value, float):
        raise MoneyError("float is not allowed for money; pass a Decimal, int or text")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int | str):
        try:
            result = Decimal(value.strip() if isinstance(value, str) else value)
        except InvalidOperation as exc:
            raise MoneyError(f"not a number: {value!r}") from exc
    else:
        raise MoneyError(f"unsupported type {type(value).__name__}")
    if not result.is_finite():
        raise MoneyError(f"not a finite number: {value!r}")
    return result


def round_tnd(value: DecimalLike) -> Decimal:
    """Round to millimes (3 decimals), half-up."""
    return to_decimal(value).quantize(TND_QUANTUM, rounding=ROUND_HALF_UP)


def round_rate(value: DecimalLike, places: int = RATE_PLACES) -> Decimal:
    """Round a rate/fraction to `places` decimals, half-up."""
    if places < 0:
        raise MoneyError("places must be >= 0")
    return to_decimal(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _has_millimes_only(value: Decimal) -> bool:
    return value == value.quantize(TND_QUANTUM, rounding=ROUND_DOWN)


def parse_amount(value: DecimalLike, *, allow_zero: bool = False) -> Decimal:
    """Validate a user amount in TND: finite, not negative, at most 3 decimals."""
    amount = to_decimal(value)
    if amount < 0:
        raise MoneyError("amount cannot be negative")
    if amount == 0 and not allow_zero:
        raise MoneyError("amount must be greater than zero")
    if not _has_millimes_only(amount):
        raise MoneyError("amount can have at most 3 decimals (millimes)")
    return round_tnd(amount)


def percent_to_fraction(percent: DecimalLike) -> Decimal:
    """10 -> 0.1"""
    return to_decimal(percent) / _HUNDRED


def fraction_to_percent(fraction: DecimalLike) -> Decimal:
    """0.1 -> 10"""
    return to_decimal(fraction) * _HUNDRED


def percent_of(amount: DecimalLike, percent: DecimalLike) -> Decimal:
    """`percent`% of `amount`, rounded to millimes."""
    return round_tnd(to_decimal(amount) * percent_to_fraction(percent))


def apply_rate(amount: DecimalLike, rate: DecimalLike) -> Decimal:
    """amount * (1 + rate), rounded to millimes. A rate below -100% is impossible."""
    fraction = to_decimal(rate)
    if fraction < -1:
        raise MoneyError("a rate cannot lose more than -100%")
    return round_tnd(to_decimal(amount) * (1 + fraction))


def safe_divide(numerator: DecimalLike, denominator: DecimalLike) -> Decimal:
    """Exact Decimal division with a clear error instead of DivisionByZero."""
    den = to_decimal(denominator)
    if den == 0:
        raise MoneyError("cannot divide by zero")
    return to_decimal(numerator) / den


def _check_weights(weights: Sequence[DecimalLike]) -> tuple[Decimal, ...]:
    if not weights:
        raise MoneyError("need at least one weight")
    values = tuple(to_decimal(w) for w in weights)
    if any(w < 0 for w in values):
        raise MoneyError("weights cannot be negative")
    if sum(values, _ZERO) == 0:
        raise MoneyError("weights must sum to more than zero")
    return values


def allocate(amount: DecimalLike, weights: Sequence[DecimalLike]) -> tuple[Decimal, ...]:
    """Split `amount` by `weights` into millime parts that sum exactly to `amount`.

    Largest-remainder method: every part is first rounded down to millimes, then the leftover
    millimes go one by one to the largest remainders (ties: earlier position first).
    """
    total = parse_amount(amount, allow_zero=True)
    values = _check_weights(weights)
    weight_sum = sum(values, _ZERO)
    millimes = int(total / TND_QUANTUM)
    exact = [Decimal(millimes) * w / weight_sum for w in values]
    floors = [int(x) for x in exact]  # int() truncates toward zero; all values are >= 0
    leftover = millimes - sum(floors)
    order = sorted(range(len(values)), key=lambda i: (-(exact[i] - floors[i]), i))
    for i in order[:leftover]:
        floors[i] += 1
    return tuple((Decimal(f) * TND_QUANTUM).quantize(TND_QUANTUM) for f in floors)
