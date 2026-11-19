"""The Milpa Token ledger: the rules Ernestine keeps in her paper notebook.

This module is a *proof of the rules*, not software for Ernestine. She keeps a
paper notebook and numbered paper tokens. Every method here mirrors one line she
would write by hand, and every check mirrors a rule she can apply by eye.

Guarantees enforced by :class:`Ledger`:

* **Closed loop.** Only Tierra Viva issues tokens and only Tierra Viva redeems
  them. Tokens are named to one household; transfers and cash-out are refused.
* **Atomic events.** Every operation validates first and mutates second. A
  :meth:`Ledger.batch` block rolls back every change if any step fails.
* **Backed.** Tokens may only be issued while the *sale* reserve (never the
  family's food) covers every outstanding token at ``min_coverage``.
* **Capped.** No household may hold more than ``max_tokens_per_household``.
* **Expiring.** Tokens expire ``expiry_months`` after issue.
* **Seasonal.** Issue and redemption are only open in configured months.
* **No interest.** A token is worth the same basket the day it is issued and
  the day it is redeemed.
"""

from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator, Mapping

MONTHS: tuple[str, ...] = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

#: Items kept in sealed drums. They count toward backing.
DURABLE_ITEMS: frozenset[str] = frozenset({"corn", "beans", "seed_corn"})
#: Perishable items. They can be handed out only in the month they are on hand
#: and never count toward backing.
FRESH_ITEMS: frozenset[str] = frozenset({"plantain", "fresh_veg"})


class LedgerError(ValueError):
    """Base class for every rule violation. The ledger is unchanged when raised."""


class OutsideWindow(LedgerError):
    """The operation is not open in this month."""


class CapExceeded(LedgerError):
    """A household would hold more tokens than the cap allows."""


class InsufficientBacking(LedgerError):
    """Issuing would leave outstanding tokens less than fully covered."""


class InsufficientTokens(LedgerError):
    """The household does not hold enough valid tokens."""


class InsufficientReserve(LedgerError):
    """There is not enough of the item on hand."""


class TransferNotAllowed(LedgerError):
    """Tokens are named to one household and cannot move to another."""


class CashOutNotAllowed(LedgerError):
    """Tokens are never exchanged for cash."""


class FamilyFoodProtected(LedgerError):
    """The family's food is never part of the token reserve."""


@dataclass(frozen=True)
class Rules:
    """The fixed rules of the system. Every value comes from the config file.

    Attributes:
        in_kind_corn_lb: Pounds of corn one token redeems for. It also sets the
            value of every other item: ``in_kind_corn_lb * price["corn"]``.
        prices_usd: Ernestine's own selling price per unit for each item.
        max_tokens_per_household: Cap on tokens one household may hold.
        expiry_months: Tokens lapse this many months after issue.
        min_coverage: Required ratio of sale-reserve value to outstanding
            token value at the moment of issue (1.0 = fully backed).
        issue_months: Months when work can be paid in tokens.
        redeem_months: For each item, the months when it can be redeemed.
    """

    in_kind_corn_lb: float
    prices_usd: Mapping[str, float]
    max_tokens_per_household: int
    expiry_months: int
    min_coverage: float
    issue_months: frozenset[str]
    redeem_months: Mapping[str, frozenset[str]]

    def __post_init__(self) -> None:
        if self.in_kind_corn_lb <= 0:
            raise ValueError("in_kind_corn_lb must be positive")
        if "corn" not in self.prices_usd:
            raise ValueError("prices_usd must include 'corn'")
        for item, price in self.prices_usd.items():
            if price <= 0:
                raise ValueError(f"price for {item!r} must be positive")
        if self.max_tokens_per_household < 1:
            raise ValueError("max_tokens_per_household must be >= 1")
        if self.expiry_months < 1:
            raise ValueError("expiry_months must be >= 1")
        if self.min_coverage < 1.0:
            raise ValueError("min_coverage below 1.0 would allow unbacked tokens")
        bad = [m for m in self.issue_months if m not in MONTHS]
        for months in self.redeem_months.values():
            bad += [m for m in months if m not in MONTHS]
        if bad:
            raise ValueError(f"unknown month names: {sorted(set(bad))}")
        unknown = set(self.redeem_months) - set(self.prices_usd)
        if unknown:
            raise ValueError(f"redeemable items without a price: {sorted(unknown)}")

    @property
    def token_value_usd(self) -> float:
        """Retail value of what one token redeems for, at Ernestine's prices."""
        return self.in_kind_corn_lb * self.prices_usd["corn"]

    def units_per_token(self, item: str) -> float:
        """How many units (lb or each) of ``item`` one token redeems for."""
        if item not in self.prices_usd:
            raise LedgerError(f"{item!r} is not on the redemption list")
        return self.token_value_usd / self.prices_usd[item]


@dataclass
class Lot:
    """A run of paper tokens issued together, numbered ``first_serial`` onward."""

    household: str
    issued_month: int
    first_serial: int
    count: int
    remaining: int


@dataclass(frozen=True)
class Event:
    """One line in the notebook."""

    month: int
    kind: str
    household: str | None = None
    tokens: int = 0
    hours: float = 0.0
    item: str | None = None
    quantity: float = 0.0
    usd: float = 0.0
    note: str = ""


@dataclass
class Ledger:
    """State of the notebook plus the rules that guard every change.

    Months are integers counted from the start of the simulation. ``start_month``
    maps month 0 to a calendar month name, so ``month_name(0) == start_month``.
    """

    rules: Rules
    start_month: str = "Jan"
    family_reserve_lb: dict[str, float] = field(default_factory=dict)
    sale_reserve: dict[str, float] = field(default_factory=dict)
    fresh_on_hand: dict[str, float] = field(default_factory=dict)
    fresh_month: int | None = None
    lots: list[Lot] = field(default_factory=list)
    debts_usd: dict[str, float] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    next_serial: int = 1
    issued_total: int = 0
    redeemed_total: int = 0
    expired_total: int = 0

    def __post_init__(self) -> None:
        if self.start_month not in MONTHS:
            raise ValueError(f"unknown start month {self.start_month!r}")

    # ------------------------------------------------------------------ helpers
    def month_name(self, month: int) -> str:
        """Calendar name of simulation month ``month``."""
        if month < 0:
            raise ValueError("month must be >= 0")
        return MONTHS[(MONTHS.index(self.start_month) + month) % 12]

    def held_by(self, household: str, month: int | None = None) -> int:
        """Valid tokens a household holds (excluding expired lots at ``month``)."""
        return sum(
            lot.remaining for lot in self.lots
            if lot.household == household and lot.remaining > 0
            and (month is None or not self._is_expired(lot, month))
        )

    @property
    def outstanding(self) -> int:
        """Tokens issued and not yet redeemed or expired."""
        return sum(lot.remaining for lot in self.lots)

    def reserve_value_usd(self) -> float:
        """Value of the durable sale reserve at Ernestine's prices."""
        return sum(qty * self.rules.prices_usd[item] for item, qty in self.sale_reserve.items())

    def coverage_ratio(self, extra_tokens: int = 0) -> float:
        """Sale-reserve value divided by the value of outstanding tokens.

        Returns ``float('inf')`` when nothing is outstanding.
        """
        liability = (self.outstanding + extra_tokens) * self.rules.token_value_usd
        if liability == 0:
            return float("inf")
        return self.reserve_value_usd() / liability

    def backable_tokens(self) -> int:
        """How many more tokens could be issued right now under the coverage rule."""
        capacity = self.reserve_value_usd() / (self.rules.min_coverage * self.rules.token_value_usd)
        return max(0, int(capacity + 1e-9) - self.outstanding)

    def _is_expired(self, lot: Lot, month: int) -> bool:
        return month - lot.issued_month >= self.rules.expiry_months

    def _log(self, event: Event) -> None:
        self.events.append(event)

    @contextmanager
    def batch(self) -> Iterator[Ledger]:
        """Apply several operations as one: if any fails, none of them happened."""
        snapshot = copy.deepcopy(self.__dict__)
        try:
            yield self
        except Exception:
            self.__dict__.clear()
            self.__dict__.update(snapshot)
            raise

    # ----------------------------------------------------------- reserve moves
    def set_family_food(self, item: str, lb: float) -> None:
        """Record the family's own food. It is never touched by token rules."""
        if lb < 0:
            raise LedgerError("family food cannot be negative")
        self.family_reserve_lb[item] = lb

    def add_to_reserve(self, month: int, item: str, lb: float, note: str = "") -> None:
        """Put dried grain into the *sale* drums."""
        if item not in DURABLE_ITEMS:
            raise LedgerError(f"{item!r} does not keep in a drum")
        if lb <= 0:
            raise LedgerError("quantity must be positive")
        self.sale_reserve[item] = self.sale_reserve.get(item, 0.0) + lb
        self._log(Event(month, "reserve_in", item=item, quantity=lb, note=note))

    def take_from_family_food(self, *_: object, **__: object) -> None:
        """Always refused: the family's food is not a token reserve."""
        raise FamilyFoodProtected("the family's food is never part of the token reserve")

    def sell_from_reserve(self, month: int, item: str, lb: float) -> float:
        """Sell grain from the sale drums, keeping every outstanding token covered.

        Returns the sale value in USD.
        """
        if lb <= 0:
            raise LedgerError("quantity must be positive")
        on_hand = self.sale_reserve.get(item, 0.0)
        if lb > on_hand + 1e-9:
            raise InsufficientReserve(f"only {on_hand:.1f} lb of {item} in the sale drums")
        usd = lb * self.rules.prices_usd[item]
        remaining_value = self.reserve_value_usd() - usd
        needed = self.outstanding * self.rules.token_value_usd * self.rules.min_coverage
        if remaining_value + 1e-9 < needed:
            raise InsufficientBacking(
                "selling this would leave outstanding tokens uncovered"
            )
        self.sale_reserve[item] = on_hand - lb
        self._log(Event(month, "reserve_sale", item=item, quantity=lb, usd=usd))
        return usd

    def free_reserve_value_usd(self) -> float:
        """Reserve value not needed to back outstanding tokens (sellable for cash)."""
        needed = self.outstanding * self.rules.token_value_usd * self.rules.min_coverage
        return max(0.0, self.reserve_value_usd() - needed)

    def set_fresh_on_hand(self, month: int, item: str, qty: float) -> None:
        """Declare surplus fresh produce on hand this month (perishable)."""
        if item not in FRESH_ITEMS:
            raise LedgerError(f"{item!r} is not a fresh item")
        if qty < 0:
            raise LedgerError("quantity cannot be negative")
        if self.fresh_month != month:
            self.fresh_on_hand = {}
            self.fresh_month = month
        self.fresh_on_hand[item] = qty

    # ------------------------------------------------------------- credit book
    def record_credit(self, month: int, household: str, usd: float) -> None:
        """A sale on credit, written in the book and read back to the buyer."""
        if usd <= 0:
            raise LedgerError("credit amount must be positive")
        self.debts_usd[household] = self.debts_usd.get(household, 0.0) + usd
        self._log(Event(month, "credit", household, usd=usd))

    def settle_debt_with_labor(self, month: int, household: str, hours: float,
                               wage_usd_per_hour: float) -> float:
        """Pay an old balance in hands: hours of work cancel debt at the wage.

        No tokens are issued; the debt shrinks. Returns USD of debt cancelled.
        """
        if hours <= 0 or wage_usd_per_hour <= 0:
            raise LedgerError("hours and wage must be positive")
        if self.month_name(month) not in self.rules.issue_months:
            raise OutsideWindow(f"labor is only booked in work months, not {self.month_name(month)}")
        owed = self.debts_usd.get(household, 0.0)
        usd = hours * wage_usd_per_hour
        if usd > owed + 1e-9:
            raise LedgerError(f"{household} owes ${owed:.2f}; {hours} h would overpay")
        self.debts_usd[household] = owed - usd
        self._log(Event(month, "debt_labor", household, hours=hours, usd=usd))
        return usd

    # ---------------------------------------------------------------- tokens
    def issue(self, month: int, household: str, hours: int, note: str = "") -> Lot:
        """Pay ``hours`` of work with the same number of tokens (1 token = 1 hour)."""
        if not isinstance(hours, int) or isinstance(hours, bool) or hours <= 0:
            raise LedgerError("tokens are whole hours: hours must be a positive integer")
        name = self.month_name(month)
        if name not in self.rules.issue_months:
            raise OutsideWindow(f"tokens are only issued in work months, not {name}")
        if self.held_by(household, month) + hours > self.rules.max_tokens_per_household:
            raise CapExceeded(
                f"{household} would hold more than {self.rules.max_tokens_per_household} tokens"
            )
        if self.coverage_ratio(extra_tokens=hours) + 1e-9 < self.rules.min_coverage:
            raise InsufficientBacking(
                f"sale drums cover {self.backable_tokens()} more tokens, not {hours}"
            )
        lot = Lot(household, month, self.next_serial, hours, hours)
        self.lots.append(lot)
        self.next_serial += hours
        self.issued_total += hours
        self._log(Event(month, "issue", household, tokens=hours, hours=float(hours), note=note))
        return lot

    def redeem(self, month: int, household: str, tokens: int, item: str) -> float:
        """Exchange tokens for food at Tierra Viva. Returns the units handed over."""
        if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens <= 0:
            raise LedgerError("tokens must be a positive integer")
        name = self.month_name(month)
        months = self.rules.redeem_months.get(item)
        if months is None:
            raise LedgerError(f"{item!r} is not on the redemption list")
        if name not in months:
            raise OutsideWindow(f"{item} is not redeemable in {name}")
        if self.held_by(household, month) < tokens:
            raise InsufficientTokens(f"{household} holds {self.held_by(household, month)} valid tokens")
        qty = tokens * self.rules.units_per_token(item)
        if item in FRESH_ITEMS:
            on_hand = self.fresh_on_hand.get(item, 0.0) if self.fresh_month == month else 0.0
            if qty > on_hand + 1e-9:
                raise InsufficientReserve(f"only {on_hand:.1f} of {item} on hand this month")
            self.fresh_on_hand[item] = on_hand - qty
        else:
            on_hand = self.sale_reserve.get(item, 0.0)
            if qty > on_hand + 1e-9:
                raise InsufficientReserve(f"only {on_hand:.1f} lb of {item} in the sale drums")
            self.sale_reserve[item] = on_hand - qty
        self._consume(household, month, tokens)
        self.redeemed_total += tokens
        self._log(Event(month, "redeem", household, tokens=tokens, item=item, quantity=qty))
        return qty

    def redeem_grain_mix(self, month: int, household: str, tokens: int,
                         items: tuple[str, ...] = ("corn", "beans")) -> dict[str, float]:
        """Pay tokens in a mix of drum grains of the same total value.

        Coverage is measured in value, so a drum can back a token without holding
        a full 10 lb of corn or 3 lb of beans on its own. Mixing guarantees every
        backed token can actually be paid. Returns lb handed over per item.
        """
        if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens <= 0:
            raise LedgerError("tokens must be a positive integer")
        name = self.month_name(month)
        for item in items:
            if item not in DURABLE_ITEMS:
                raise LedgerError(f"{item!r} is not a drum grain")
            if name not in self.rules.redeem_months.get(item, frozenset()):
                raise OutsideWindow(f"{item} is not redeemable in {name}")
        if self.held_by(household, month) < tokens:
            raise InsufficientTokens(f"{household} holds {self.held_by(household, month)} valid tokens")
        due = tokens * self.rules.token_value_usd
        stock = {i: self.sale_reserve.get(i, 0.0) * self.rules.prices_usd[i] for i in items}
        if sum(stock.values()) + 1e-9 < due:
            raise InsufficientReserve("not enough grain in the sale drums")
        handed: dict[str, float] = {}
        for item in sorted(items, key=lambda i: -stock[i]):  # fullest first
            usd = min(due, stock[item])
            if usd <= 0:
                continue
            lb = usd / self.rules.prices_usd[item]
            self.sale_reserve[item] -= lb
            handed[item] = lb
            due -= usd
        self._consume(household, month, tokens)
        self.redeemed_total += tokens
        self._log(Event(month, "redeem", household, tokens=tokens, item="+".join(handed),
                        quantity=sum(handed.values())))
        return handed

    def _consume(self, household: str, month: int, tokens: int) -> None:
        left = tokens
        for lot in sorted(self.lots, key=lambda lot: lot.issued_month):  # oldest first
            if lot.household != household or lot.remaining == 0 or self._is_expired(lot, month):
                continue
            take = min(left, lot.remaining)
            lot.remaining -= take
            left -= take
            if left == 0:
                break
        self.lots = [lot for lot in self.lots if lot.remaining > 0]

    def expire(self, month: int) -> int:
        """Retire every lot older than ``expiry_months``. Returns tokens expired."""
        expired = 0
        keep: list[Lot] = []
        for lot in self.lots:
            if self._is_expired(lot, month):
                expired += lot.remaining
                self._log(Event(month, "expire", lot.household, tokens=lot.remaining))
            else:
                keep.append(lot)
        self.lots = keep
        self.expired_total += expired
        return expired

    def transfer(self, *_: object, **__: object) -> None:
        """Always refused: tokens are named to one household."""
        raise TransferNotAllowed("Milpa Tokens are named to one household and cannot be passed on")

    def cash_out(self, *_: object, **__: object) -> None:
        """Always refused: tokens are never exchanged for money."""
        raise CashOutNotAllowed("Milpa Tokens are redeemed for food only, never for cash")
