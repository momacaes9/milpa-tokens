"""Monthly replay: run the deck's annual token flows through the Libreta rules.

The annual model (:mod:`milpa.model`) gives the flows; this module lays them on
the calendar of a normal year (Exhibit A month types) and pushes every one
through the real :class:`~milpa.ledger.Ledger`, so a simulated year can never do
something the paper rules forbid:

* credit sales each month (Exhibit A);
* cash repaid within 30 days in the same month (earns the 5% reward);
* the rest of repaid credit at harvest: late cash, and seed credit repaid in
  corn and beans by five farmers (grain into drum 2);
* 12 pickup rides at peak harvest, half the fare in tokens;
* in the pre-harvest gap, every token outstanding is spent on corn or beans from
  drum 2, and drum 2 grain is sold to buyers who are turned away today.

The 15 households that owe Ernestine at any time (Exhibit D) are kept as one
Libreta account here so that reward cents add up the way the deck counts them;
the per-household rules are unit-tested in ``tests/test_ledger.py``.

Year 1 starts in February with drum 2 full from the previous harvest and no
tokens out. Year 2 is the steady state used in the outputs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .config import Config
from .ledger import GRAINS, Ledger
from .model import annual

HOUSEHOLDS = "credit_households"
DRIVER = "pickup_neighbor"


@dataclass
class MonthRow:
    """State at the end of one month."""

    year_number: int
    month: str
    month_type: str
    sales_usd: float
    credit_usd: float
    on_time_cash_usd: float
    late_cash_usd: float
    crop_repaid_usd: float
    crop_tokens_credited: float
    reward_tokens_issued: int
    pickup_tokens_issued: int
    pickup_cash_usd: float
    tokens_redeemed: int
    tokens_outstanding: int
    drum2_sales_usd: float
    drum2_corn_lb: float
    drum2_beans_lb: float
    drum2_value_usd: float
    coverage_ratio: float | None
    family_drum_lb: float


@dataclass
class YearReplay:
    year_number: int
    months: list[MonthRow] = field(default_factory=list)
    totals: dict[str, float] = field(default_factory=dict)


def replay(cfg: Config, years: int = 2, case: str = "base") -> list[YearReplay]:
    """Replay ``years`` consecutive normal years on one Libreta."""
    if years < 1:
        raise ValueError("years must be >= 1")
    t = cfg.token
    a = annual(cfg, case)
    spec = cfg.year("normal")
    types = spec["month_types"]
    months = cfg.months_in_order()
    harvest = cfg.months_of_type("normal", "harvest")
    gap = cfg.months_of_type("normal", "pre_harvest")
    prices = cfg.grain_prices()
    face = float(t["face_value_usd"])
    unpaid = a["unpaid_share_with_libreta"]
    on_time_share = float(t["on_time_share_of_repaid"])
    fill = {i: float(t["drum2_fill_lb"].get(i, 0)) for i in GRAINS}
    crop_lb = {i: float(t["crop_repayment_lb"].get(i, 0)) for i in GRAINS}
    n_farmers = int(t["crop_repaying_farmers"])
    farmers = [f"farmer_{k + 1:02d}" for k in range(n_farmers)]
    per_farmer_lb = {i: lb / n_farmers for i, lb in crop_lb.items()}
    per_farmer_usd = sum(per_farmer_lb[i] * prices[i] for i in GRAINS)
    seed_months = [m for m in months if cfg.month_type("normal", m) == "typical"][-3:]
    farmer_month = {f: harvest[k * len(harvest) // n_farmers] for k, f in enumerate(farmers)}
    late_cash_total = a["repaid_credit_usd"] - a["on_time_cash_usd"] - a["crop_repayment_usd"]
    if late_cash_total < -1e-9:
        raise ValueError("crop repayments exceed the late part of repaid credit")
    rides = int(t["earn"]["pickup"]["rides_per_year"])
    fare = float(t["earn"]["pickup"]["fare_usd"])
    token_share = float(t["earn"]["pickup"]["token_share_of_fare"])
    rides_in = {m: rides // len(harvest) + (1 if k < rides % len(harvest) else 0)
                for k, m in enumerate(harvest)}
    drum2_sales_per_gap_month = a["drum2_sales_usd"] / len(gap)
    capacity = float(cfg.case["drums"]["capacity_lb"])

    ledger = Ledger(cfg.rules("normal"))
    ledger.set_family_food("corn_and_beans", capacity * int(t["drums"]["family"]))
    for item, lb in fill.items():
        if lb:
            ledger.add_to_drum2(months[0], item, lb, note="previous harvest")
    out: list[YearReplay] = []

    for n in range(1, years + 1):
        ledger.start_year(a["cap_tokens"])
        result = YearReplay(n)
        for month in months:
            mtype = cfg.month_type("normal", month)
            issued_before = ledger.issued_total
            redeemed_before = ledger.redeemed_total
            reward = pickup_tokens = 0
            pickup_cash = late_cash = crop_usd = crop_tokens = drum2_sales = 0.0

            # Credit sales (Exhibit A). Before planting, part is seed for the farmers.
            sales = float(types[mtype]["sales_per_month"])
            credit = sales * float(types[mtype]["credit_share"])
            seed = a["crop_repayment_usd"] / len(seed_months) if month in seed_months else 0.0
            for f in farmers:
                if seed:
                    ledger.record_credit(month, f, seed / n_farmers)
            ledger.record_credit(month, HOUSEHOLDS, credit - seed)

            # Cash repaid within 30 days earns the 5% reward in tokens.
            on_time = credit * (1 - unpaid) * on_time_share
            reward = ledger.repay_cash(month, HOUSEHOLDS, on_time, days_late=20)

            if month in harvest:
                # Her own surplus goes in first, leaving room for crop repayments.
                if month == harvest[0]:
                    space = sum(fill.values()) - ledger.drum2_total_lb() - sum(crop_lb.values())
                    for item in GRAINS:
                        room = min(space, fill[item] - ledger.drum2_lb.get(item, 0.0) - crop_lb[item])
                        if room > 1e-9:
                            ledger.add_to_drum2(month, item, room, note="her surplus")
                            space -= room
                for f in farmers:
                    if farmer_month[f] == month:
                        for item in GRAINS:
                            if per_farmer_lb[item]:
                                crop_tokens += ledger.repay_in_crops(month, f, item, per_farmer_lb[item])
                        crop_usd += per_farmer_usd
                late_cash = late_cash_total / len(harvest)
                if late_cash > 1e-9:
                    ledger.repay_cash(month, HOUSEHOLDS, late_cash, days_late=60)
                for _ in range(rides_in[month]):
                    cash, tok = ledger.pay_pickup_fare(month, DRIVER, fare, token_share)
                    pickup_cash += cash
                    pickup_tokens += tok

            if month in gap:
                # Every token out is spent in the gap, spread over its months.
                left = len(gap) - gap.index(month)
                for holder in sorted(ledger.held):
                    want = math.ceil(ledger.held[holder] / left)
                    for _ in range(want):
                        item = max(GRAINS, key=lambda i: ledger.drum2_lb.get(i, 0.0) * prices[i])
                        ledger.redeem(month, holder, 1, item)
                drum2_sales = _sell_to_turned_away(ledger, month, drum2_sales_per_gap_month)

            cov = ledger.coverage_ratio()
            result.months.append(MonthRow(
                year_number=n, month=month, month_type=mtype,
                sales_usd=sales + drum2_sales, credit_usd=credit,
                on_time_cash_usd=on_time, late_cash_usd=late_cash,
                crop_repaid_usd=crop_usd, crop_tokens_credited=crop_tokens,
                reward_tokens_issued=reward, pickup_tokens_issued=pickup_tokens,
                pickup_cash_usd=pickup_cash,
                tokens_redeemed=ledger.redeemed_total - redeemed_before,
                tokens_outstanding=ledger.outstanding,
                drum2_sales_usd=drum2_sales,
                drum2_corn_lb=ledger.drum2_lb.get("corn", 0.0),
                drum2_beans_lb=ledger.drum2_lb.get("beans", 0.0),
                drum2_value_usd=ledger.drum2_value_usd(),
                coverage_ratio=cov,
                family_drum_lb=sum(ledger.family_drum_lb.values()),
            ))
            assert ledger.issued_total - issued_before == reward + pickup_tokens
        result.totals = _totals(result, a)
        out.append(result)
    return out


def _sell_to_turned_away(ledger: Ledger, month: str, budget_usd: float) -> float:
    """Sell drum-2 grain not needed for tokens, up to this month's turned-away demand."""
    budget = min(budget_usd, ledger.free_drum2_value_usd())
    value = ledger.drum2_value_usd()
    if budget <= 1e-9 or value <= 0:
        return 0.0
    sold = 0.0
    stock = {i: ledger.drum2_lb.get(i, 0.0) * ledger.rules.prices_usd[i] for i in GRAINS}
    for item in GRAINS:
        usd = budget * stock[item] / value
        if usd > 1e-9:
            sold += ledger.sell_from_drum2(month, item, usd / ledger.rules.prices_usd[item])
    return sold


def _totals(r: YearReplay, a: dict[str, Any]) -> dict[str, float]:
    m = r.months
    covs = [x.coverage_ratio for x in m if x.coverage_ratio is not None]
    issued = sum(x.reward_tokens_issued + x.pickup_tokens_issued for x in m)
    return {
        "reward_tokens_issued": sum(x.reward_tokens_issued for x in m),
        "pickup_tokens_issued": sum(x.pickup_tokens_issued for x in m),
        "tokens_issued": issued,
        "cap_tokens": a["cap_tokens"],
        "tokens_redeemed": sum(x.tokens_redeemed for x in m),
        "tokens_outstanding_end": m[-1].tokens_outstanding,
        "pickup_cash_usd": sum(x.pickup_cash_usd for x in m),
        "on_time_cash_usd": sum(x.on_time_cash_usd for x in m),
        "late_cash_usd": sum(x.late_cash_usd for x in m),
        "crop_repaid_usd": sum(x.crop_repaid_usd for x in m),
        "crop_tokens_credited": sum(x.crop_tokens_credited for x in m),
        "drum2_sales_usd": sum(x.drum2_sales_usd for x in m),
        "min_coverage_ratio": min(covs) if covs else float("nan"),
        "drum2_value_max_usd": max(x.drum2_value_usd for x in m),
        "drum2_value_min_usd": min(x.drum2_value_usd for x in m),
        "drum2_lb_max": max(x.drum2_corn_lb + x.drum2_beans_lb for x in m),
        "family_drum_lb_min": min(x.family_drum_lb for x in m),
    }
