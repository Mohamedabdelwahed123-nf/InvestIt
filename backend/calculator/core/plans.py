"""Cautious vs Growth plans — deterministic allocation rules, Decimal only, no DB, no AI.

Rules (documented in docs/PLAN.md, "Calculator plans"):
1. No emergency fund -> EMERGENCY_RESERVE_PERCENT of the amount is kept in bond SICAV as an
   emergency reserve first; the profile weights apply to the rest (the investable part).
2. Horizon bands give the base weights (percent of the investable part):
   < 12 months: bond SICAV only (no mixed, no equity) for both profiles.
   12-35, 36-59 and >= 60 months: see BASE_WEIGHTS.
3. Equity exposure = equity + half of mixed (a mixed SICAV is about half shares). It is capped by
   the risk tolerance (EXPOSURE_CAPS); the cautious profile gets CAUTIOUS_CAP_FACTOR of that cap.
   Over the cap, equity is moved to bond SICAV first, then mixed (2 points of mixed per point).
4. National bond loan: only if months >= NATIONAL_BOND_MIN_MONTHS and a tranche is open; it then
   takes half of the investment bond share. Emergency money is never locked in it.
5. Individual stocks are never allocated. Amounts are split with `allocate` (exact millimes).
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from backend.calculator.core.money import DecimalLike, allocate, parse_amount


class PlanError(ValueError):
    """The plan inputs are invalid (months out of range, unknown profile...)."""


class Profile(StrEnum):
    CAUTIOUS = "cautious"
    GROWTH = "growth"


class RiskTolerance(StrEnum):
    """How the saver feels about a 10% drop: LOW = very worried, MEDIUM = a bit, HIGH = not much."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AssetCategory(StrEnum):
    """Categories a plan may use (same values as the DB). Individual stocks are never here."""

    BOND_SICAV = "bond_sicav"
    NATIONAL_BOND = "national_bond"
    MIXED_SICAV = "mixed_sicav"
    EQUITY_SICAV = "equity_sicav"


class Purpose(StrEnum):
    EMERGENCY = "emergency"
    INVESTMENT = "investment"


_BOND, _NATIONAL = AssetCategory.BOND_SICAV, AssetCategory.NATIONAL_BOND
_MIXED, _EQUITY = AssetCategory.MIXED_SICAV, AssetCategory.EQUITY_SICAV
_ZERO, _HUNDRED, _HALF = Decimal(0), Decimal(100), Decimal("0.5")

SHORT_HORIZON_MONTHS = 12
NATIONAL_BOND_MIN_MONTHS = 60
MAX_MONTHS = 600
EMERGENCY_RESERVE_PERCENT = Decimal(30)
CAUTIOUS_CAP_FACTOR = _HALF
EXPOSURE_CAPS: dict[RiskTolerance, Decimal] = {
    RiskTolerance.LOW: Decimal(15),
    RiskTolerance.MEDIUM: Decimal(35),
    RiskTolerance.HIGH: Decimal(65),
}

type Weights = tuple[Decimal, Decimal, Decimal]  # bond SICAV, mixed SICAV, equity SICAV


def _w(bond: int, mixed: int, equity: int) -> Weights:
    return Decimal(bond), Decimal(mixed), Decimal(equity)


# (minimum months, cautious weights, growth weights), longest band first
BASE_WEIGHTS: tuple[tuple[int, Weights, Weights], ...] = (
    (60, _w(50, 30, 20), _w(20, 30, 50)),
    (36, _w(60, 30, 10), _w(30, 40, 30)),
    (12, _w(80, 20, 0), _w(50, 40, 10)),
    (0, _w(100, 0, 0), _w(100, 0, 0)),
)


@dataclass(frozen=True, slots=True)
class Allocation:
    category: AssetCategory
    purpose: Purpose
    percent: Decimal  # of the whole amount, exact
    amount: Decimal  # TND, millimes


@dataclass(frozen=True, slots=True)
class Plan:
    profile: Profile
    amount: Decimal
    months: int
    risk_tolerance: RiskTolerance
    has_emergency_fund: bool
    national_bond_open: bool
    allocations: tuple[Allocation, ...]
    equity_exposure_percent: Decimal  # equity + half of mixed, percent of the whole amount
    notes: tuple[str, ...]

    def amount_for(self, category: AssetCategory) -> Decimal:
        total = sum((a.amount for a in self.allocations if a.category is category), _ZERO)
        return total.quantize(Decimal("0.001"))


def _enum[E: StrEnum](kind: type[E], value: object, name: str) -> E:
    try:
        return kind(value)
    except ValueError:
        allowed = ", ".join(m.value for m in kind)
        raise PlanError(f"{name} must be one of: {allowed}") from None


def _check_inputs(months: object, has_emergency_fund: object, national_bond_open: object) -> int:
    if not isinstance(months, int) or isinstance(months, bool):
        raise PlanError("months must be a whole number")
    if not 1 <= months <= MAX_MONTHS:
        raise PlanError(f"months must be between 1 and {MAX_MONTHS}")
    for name, flag in (
        ("has_emergency_fund", has_emergency_fund),
        ("national_bond_open", national_bond_open),
    ):
        if not isinstance(flag, bool):
            raise PlanError(f"{name} must be true or false")
    return months


def _base_weights(months: int, profile: Profile) -> Weights:
    for min_months, cautious, growth in BASE_WEIGHTS:
        if months >= min_months:
            return cautious if profile is Profile.CAUTIOUS else growth
    raise PlanError("months must be positive")  # pragma: no cover - guarded by _check_inputs


def exposure(weights: Weights) -> Decimal:
    """Equity exposure of (bond, mixed, equity) weights: equity + half of mixed."""
    return weights[2] + weights[1] * _HALF


def _cap(weights: Weights, cap: Decimal) -> Weights:
    """Move equity, then mixed, to bond SICAV until exposure <= cap."""
    bond, mixed, equity = weights
    excess = exposure(weights) - cap
    if excess <= 0:
        return weights
    cut = min(equity, excess)
    bond, equity, excess = bond + cut, equity - cut, excess - cut
    cut = min(mixed, excess * 2)
    return bond + cut, mixed - cut, equity


def _investment_lines(
    weights: Weights, months: int, national_bond_open: bool
) -> list[tuple[AssetCategory, Decimal]]:
    bond, mixed, equity = weights
    lines = [(_BOND, bond), (_MIXED, mixed), (_EQUITY, equity)]
    if national_bond_open and months >= NATIONAL_BOND_MIN_MONTHS and bond > 0:
        lines[0:1] = [(_BOND, bond * _HALF), (_NATIONAL, bond * _HALF)]
    return lines


def _notes(months: int, has_emergency: bool, national_open: bool, capped: bool) -> list[str]:
    notes = ["individual stocks are never allocated"]
    if not has_emergency:
        notes.append("no emergency fund: part of the amount is kept in bond SICAV as a reserve")
    if months < SHORT_HORIZON_MONTHS:
        notes.append("horizon under 12 months: bond SICAV only, no mixed or equity funds")
    if months >= NATIONAL_BOND_MIN_MONTHS and not national_open:
        notes.append("national bond loan not included: no open tranche was given")
    if capped:
        notes.append("risk tolerance limited the equity exposure")
    return notes


def make_plan(
    amount: DecimalLike,
    months: int,
    risk_tolerance: RiskTolerance | str,
    has_emergency_fund: bool,
    profile: Profile | str,
    *,
    national_bond_open: bool = False,
) -> Plan:
    """Build the allocation for one profile. Same inputs always give the same plan."""
    total = parse_amount(amount)
    months = _check_inputs(months, has_emergency_fund, national_bond_open)
    tolerance = _enum(RiskTolerance, risk_tolerance, "risk_tolerance")
    chosen = _enum(Profile, profile, "profile")
    cap = EXPOSURE_CAPS[tolerance] * (CAUTIOUS_CAP_FACTOR if chosen is Profile.CAUTIOUS else 1)
    base = _base_weights(months, chosen)
    weights = _cap(base, cap)
    share = _HUNDRED if has_emergency_fund else _HUNDRED - EMERGENCY_RESERVE_PERCENT
    lines = [
        (c, Purpose.INVESTMENT, w * share / _HUNDRED)
        for c, w in _investment_lines(weights, months, national_bond_open)
    ]
    if not has_emergency_fund:
        lines.insert(0, (_BOND, Purpose.EMERGENCY, EMERGENCY_RESERVE_PERCENT))
    lines = [line for line in lines if line[2] > 0]
    amounts = allocate(total, [line[2] for line in lines])
    return Plan(
        profile=chosen,
        amount=total,
        months=months,
        risk_tolerance=tolerance,
        has_emergency_fund=has_emergency_fund,
        national_bond_open=national_bond_open,
        allocations=tuple(
            Allocation(c, p, pct, amt) for (c, p, pct), amt in zip(lines, amounts, strict=True)
        ),
        equity_exposure_percent=exposure(weights) * share / _HUNDRED,
        notes=tuple(_notes(months, has_emergency_fund, national_bond_open, weights != base)),
    )
