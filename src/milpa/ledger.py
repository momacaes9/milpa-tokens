"""The Libreta: the rules Ernestine keeps in her paper notebook.

This module is a *proof of the rules*, not software for Ernestine. She keeps a
paper notebook (the Libreta) and numbered, stamped paper tokens. Every method
here mirrors one line she would write by hand.

The final token model (pitch deck):

* **1 token = BZ$2 = US$1** of Ernestine's corn or beans. A store voucher, not
  money: issued and redeemed only by Ernestine.
* **Earned** only three ways: repaying credit in corn or beans at harvest (each
  $1 of crop value is 1 token credited against the debt, and the grain goes into
  drum 2); a 5% reward in tokens for credit repaid in cash within 30 days; and
  half the neighbor's pickup fare at peak harvest.
* **Spent** only at Ernestine's market table, only for corn or beans from drum 2,
  only in the pre-harvest gap, at the case prices.
* **Drum 1** is the family's food: never sold, never backs a token. **Drum 2**
  holds grain from crop repayments plus her surplus. Tokens outstanding (US$)
  may never exceed the value of corn and beans in drum 2.
* Tokens issued in a year are capped at a share of sales (10%).
* No transfers between neighbors, no cash-out, no interest.
"""

from __future__ import annotations

import copy
import math
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator, Mapping

MONTHS: tuple[str, ...] = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

#: The only items a token can be earned or spent in.
GRAINS: tuple[str, ...] = ("corn", "beans")

_EPS = 1e-9


class LedgerError(ValueError):
    """Base class for every rule violation. The ledger is unchanged when raised."""


class OutsideWindow(LedgerError):
    """The operation is not open in this month."""


class NotCornOrBeans(LedgerError):
    """Tokens are earned and spent in corn and beans only."""


class InsufficientBacking(LedgerError):
    """Tokens outstanding would exceed the value of grain in drum 2."""


class CapExceeded(LedgerError):
    """Tokens issued this year would exceed the cap (share of sales)."""


class InsufficientTokens(LedgerError):
    """The holder does not have that many tokens."""


class InsufficientReserve(LedgerError):
    """There is not enough of the grain in drum 2."""


class DrumFull(LedgerError):
    """Drum 2 cannot hold more than its capacity."""


class Overpayment(LedgerError):
    """A repayment larger than the debt."""


class TransferNotAllowed(LedgerError):
    """Tokens are logged to one holder and cannot move to another."""


class CashOutNotAllowed(LedgerError):
    """Tokens are never exchanged for cash."""


class FamilyFoodProtected(LedgerError):
    """Drum 1 (the family's food) is never sold and never backs a token."""


@dataclass(frozen=True)
class Rules:
    """Fixed rules of the system. Every value comes from the config file.

    Attributes:
        prices_usd: Ernestine's price per lb for corn and beans (Exhibit B).
        token_value_usd: Face value of one token (US$1 = BZ$2).
        reward_share: Tokens per $1 of credit repaid in cash on time (0.05).
        on_time_days: Days within which a cash repayment earns the reward.
        redeem_months: Calendar months in which tokens can be spent.
        drum2_capacity_lb: Capacity of drum 2 (Exhibit E: ~250 lb).
    """

    prices_usd: Mapping[str, float]
    token_value_usd: float = 1.0
    reward_share: float = 0.05
    on_time_days: int = 30
    redeem_months: frozenset[str] = frozenset({"Jul", "Aug", "Sep"})
    drum2_capacity_lb: float = 250.0

    def __post_init__(self) -> None:
        if set(self.prices_usd) != set(GRAINS):
            raise ValueError("prices_usd must name exactly corn and beans")
        for item, price in self.prices_usd.items():
            if price <= 0:
                raise ValueError(f"price for {item!r} must be positive")
        if self.token_value_usd <= 0:
            raise ValueError("token value must be positive")
        if not 0 <= self.reward_share < 1:
            raise ValueError("reward_share must be in [0, 1)")
        if self.on_time_days < 1:
            raise ValueError("on_time_days must be >= 1")
        bad = [m for m in self.redeem_months if m not in MONTHS]
        if bad:
            raise ValueError(f"unknown month names: {sorted(bad)}")
        if self.drum2_capacity_lb <= 0:
            raise ValueError("drum 2 capacity must be positive")

    def lb_per_token(self, item: str) -> float:
        """Pounds of ``item`` one token is worth: corn 3.33 lb, beans 1 lb."""
        _grain(item)
        return self.token_value_usd / self.prices_usd[item]


def _grain(item: str) -> str:
    if item not in GRAINS:
        raise NotCornOrBeans(f"tokens are for corn and beans only, not {item!r}")
    return item


def _whole(n: object, what: str = "tokens") -> int:
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
        raise LedgerError(f"{what} must be a positive whole number")
    return n


@dataclass(frozen=True)
class Event:
    """One line in the Libreta."""

    month: str
    kind: str
    holder: str | None = None
    tokens: float = 0
    item: str | None = None
    lb: float = 0.0
    usd: float = 0.0
    serials: tuple[int, int] | None = None
    note: str = ""


@dataclass
class Ledger:
    """State of the Libreta and the two drums, plus the rules that guard every change.

    ``annual_cap_tokens`` is the most tokens that may be issued between two calls
    to :meth:`start_year` (10% of sales; ``None`` means no cap).
    """

    rules: Rules
    annual_cap_tokens: float | None = None
    family_drum_lb: dict[str, float] = field(default_factory=dict)
    drum2_lb: dict[str, float] = field(default_factory=dict)
    held: dict[str, int] = field(default_factory=dict)
    debts_usd: dict[str, float] = field(default_factory=dict)
    reward_carry_usd: dict[str, float] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    next_serial: int = 1
    issued_this_year: int = 0
    issued_total: int = 0
    redeemed_total: int = 0
    crop_tokens_credited: float = 0.0

    # ------------------------------------------------------------------ views
    @property
    def outstanding(self) -> int:
        """Tokens issued and not yet spent."""
        return sum(self.held.values())

    @property
    def outstanding_usd(self) -> float:
        return self.outstanding * self.rules.token_value_usd

    def drum2_value_usd(self) -> float:
        """Value of corn and beans in drum 2 at Ernestine's prices."""
        return sum(lb * self.rules.prices_usd[i] for i, lb in self.drum2_lb.items())

    def drum2_total_lb(self) -> float:
        return sum(self.drum2_lb.values())

    def coverage_ratio(self) -> float | None:
        """Drum-2 value / tokens outstanding (US$). ``None`` with nothing outstanding."""
        if self.outstanding == 0:
            return None
        return self.drum2_value_usd() / self.outstanding_usd

    def free_drum2_value_usd(self) -> float:
        """Drum-2 value not needed to back tokens outstanding (sellable for cash)."""
        return max(0.0, self.drum2_value_usd() - self.outstanding_usd)

    def backable_tokens(self) -> int:
        """How many more tokens drum 2 could back right now."""
        return max(0, math.floor(self.free_drum2_value_usd() / self.rules.token_value_usd + _EPS))

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

    def start_year(self, annual_cap_tokens: float | None) -> None:
        """Open a new year in the Libreta and reset the issue cap."""
        self.annual_cap_tokens = annual_cap_tokens
        self.issued_this_year = 0

    # ------------------------------------------------------------------ drums
    def set_family_food(self, item: str, lb: float) -> None:
        """Record drum 1, the family's food. No token rule ever reads it."""
        if lb < 0:
            raise LedgerError("family food cannot be negative")
        self.family_drum_lb[item] = lb

    def take_from_family_drum(self, *_: object, **__: object) -> None:
        """Always refused: drum 1 is never sold and never backs a token."""
        raise FamilyFoodProtected("drum 1 is the family's food: never sold, never backs tokens")

    def add_to_drum2(self, month: str, item: str, lb: float, note: str = "") -> None:
        """Put dried corn or beans (her own surplus) into drum 2."""
        _grain(item)
        if lb <= 0:
            raise LedgerError("quantity must be positive")
        if self.drum2_total_lb() + lb > self.rules.drum2_capacity_lb + _EPS:
            raise DrumFull(f"drum 2 holds {self.rules.drum2_capacity_lb:.0f} lb")
        self.drum2_lb[item] = self.drum2_lb.get(item, 0.0) + lb
        self._log(Event(month, "drum2_in", item=item, lb=lb, note=note))

    def sell_from_drum2(self, month: str, item: str, lb: float) -> float:
        """Sell grain from drum 2 for cash, keeping every token outstanding backed.

        Returns the sale value in USD.
        """
        _grain(item)
        if lb <= 0:
            raise LedgerError("quantity must be positive")
        on_hand = self.drum2_lb.get(item, 0.0)
        if lb > on_hand + _EPS:
            raise InsufficientReserve(f"only {on_hand:.1f} lb of {item} in drum 2")
        usd = lb * self.rules.prices_usd[item]
        if self.drum2_value_usd() - usd + _EPS < self.outstanding_usd:
            raise InsufficientBacking("selling this would leave tokens outstanding unbacked")
        self.drum2_lb[item] = on_hand - lb
        self._log(Event(month, "drum2_sale", item=item, lb=lb, usd=usd))
        return usd

    # ------------------------------------------------------------- credit book
    def record_credit(self, month: str, household: str, usd: float) -> None:
        """A sale on credit, written in the Libreta and read back to the buyer."""
        if usd <= 0:
            raise LedgerError("credit amount must be positive")
        self.debts_usd[household] = self.debts_usd.get(household, 0.0) + usd
        self._log(Event(month, "credit", household, usd=usd))

    def _reduce_debt(self, household: str, usd: float) -> None:
        owed = self.debts_usd.get(household, 0.0)
        if usd > owed + _EPS:
            raise Overpayment(f"{household} owes ${owed:.2f}, not ${usd:.2f}")
        self.debts_usd[household] = max(0.0, owed - usd)

    def repay_in_crops(self, month: str, household: str, item: str, lb: float) -> float:
        """Repay credit in corn or beans at the case price.

        Each $1 of crop value is 1 token credited against the debt, and the grain
        goes into drum 2. Credited tokens settle debt; they are not vouchers in
        circulation. Returns the tokens credited.
        """
        _grain(item)
        if lb <= 0:
            raise LedgerError("quantity must be positive")
        usd = lb * self.rules.prices_usd[item]
        if self.drum2_total_lb() + lb > self.rules.drum2_capacity_lb + _EPS:
            raise DrumFull(f"drum 2 holds {self.rules.drum2_capacity_lb:.0f} lb")
        self._reduce_debt(household, usd)
        self.drum2_lb[item] = self.drum2_lb.get(item, 0.0) + lb
        tokens = usd / self.rules.token_value_usd
        self.crop_tokens_credited += tokens
        self._log(Event(month, "repay_crops", household, tokens=tokens, item=item, lb=lb, usd=usd))
        return tokens

    def repay_cash(self, month: str, household: str, usd: float, days_late: int) -> int:
        """Repay credit in cash. Within ``on_time_days`` it earns the reward.

        The reward (5% of the payment) is kept in cents in the Libreta; a paper
        token is stamped for each full $1 of reward. If drum 2 cannot back the
        token yet (or the year's cap is reached) the reward stays pending in
        the Libreta and no token is stamped. Returns tokens issued now.
        """
        if usd <= 0:
            raise LedgerError("payment must be positive")
        if days_late < 0:
            raise LedgerError("days_late cannot be negative")
        on_time = days_late <= self.rules.on_time_days
        self._reduce_debt(household, usd)
        self._log(Event(month, "repay_cash", household, usd=usd,
                        note="on time" if on_time else "late, no reward"))
        if not on_time:
            return 0
        carry = self.reward_carry_usd.get(household, 0.0) + usd * self.rules.reward_share
        due = math.floor(carry / self.rules.token_value_usd + _EPS)
        issued = 0
        if due:
            try:
                self.issue(month, household, due, note="5% on-time reward")
                issued = due
            except (InsufficientBacking, CapExceeded):
                self._log(Event(month, "reward_pending", household, tokens=due))
        self.reward_carry_usd[household] = carry - issued * self.rules.token_value_usd
        return issued

    def pay_pickup_fare(self, month: str, driver: str, fare_usd: float,
                        token_share: float) -> tuple[float, int]:
        """Pay a neighbor's pickup ride: part cash, part tokens.

        Returns ``(cash_usd, tokens)``. A transport fare, not labor.
        """
        if fare_usd <= 0 or not 0 <= token_share <= 1:
            raise LedgerError("fare must be positive and token share in [0, 1]")
        tokens_usd = fare_usd * token_share
        tokens = tokens_usd / self.rules.token_value_usd
        if abs(tokens - round(tokens)) > _EPS:
            raise LedgerError("the token part of a fare must be whole tokens")
        tokens = int(round(tokens))
        cash = fare_usd - tokens * self.rules.token_value_usd
        with self.batch():
            if tokens:
                self.issue(month, driver, tokens, note="half pickup fare")
            self._log(Event(month, "pickup_fare", driver, tokens=tokens, usd=cash))
        return cash, tokens

    # ---------------------------------------------------------------- tokens
    def issue(self, month: str, holder: str, tokens: int, note: str = "") -> tuple[int, int]:
        """Stamp and number ``tokens`` paper tokens for ``holder``.

        Refused if drum 2 would not cover every token outstanding, or if the
        year's cap would be exceeded. Returns the serial range.
        """
        _whole(tokens)
        if (self.annual_cap_tokens is not None
                and self.issued_this_year + tokens > self.annual_cap_tokens + _EPS):
            raise CapExceeded(f"cap is {self.annual_cap_tokens:.0f} tokens this year")
        if (self.outstanding + tokens) * self.rules.token_value_usd > self.drum2_value_usd() + _EPS:
            raise InsufficientBacking(
                f"drum 2 backs {self.backable_tokens()} more tokens, not {tokens}")
        serials = (self.next_serial, self.next_serial + tokens - 1)
        self.next_serial += tokens
        self.held[holder] = self.held.get(holder, 0) + tokens
        self.issued_this_year += tokens
        self.issued_total += tokens
        self._log(Event(month, "issue", holder, tokens=tokens, serials=serials, note=note))
        return serials

    def redeem(self, month: str, holder: str, tokens: int, item: str) -> float:
        """Spend tokens at the market table for corn or beans from drum 2.

        Returns the lb handed over.
        """
        _whole(tokens)
        _grain(item)
        if month not in self.rules.redeem_months:
            raise OutsideWindow(f"tokens are spent in the pre-harvest gap, not {month}")
        if self.held.get(holder, 0) < tokens:
            raise InsufficientTokens(f"{holder} holds {self.held.get(holder, 0)} tokens")
        lb = tokens * self.rules.lb_per_token(item)
        on_hand = self.drum2_lb.get(item, 0.0)
        if lb > on_hand + _EPS:
            raise InsufficientReserve(f"only {on_hand:.1f} lb of {item} in drum 2")
        self.drum2_lb[item] = on_hand - lb
        self.held[holder] -= tokens
        if self.held[holder] == 0:
            del self.held[holder]
        self.redeemed_total += tokens
        self._log(Event(month, "redeem", holder, tokens=tokens, item=item, lb=lb,
                        usd=tokens * self.rules.token_value_usd))
        return lb

    def transfer(self, *_: object, **__: object) -> None:
        """Always refused: no transfers between neighbors."""
        raise TransferNotAllowed("tokens are logged to one holder and cannot be passed on")

    def cash_out(self, *_: object, **__: object) -> None:
        """Always refused: tokens are never exchanged for cash."""
        raise CashOutNotAllowed("tokens buy corn and beans at Tierra Viva only, never cash")
