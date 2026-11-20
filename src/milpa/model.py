"""The pitch deck's annual arithmetic for the final token model (normal year).

Every number comes from the case packet (Exhibits A-E) or the pitch deck, through
``config/tierra_viva.json``. Nothing is rounded until it is printed.

Base case, normal year:

* Credit no longer lost: $594 x (25% - 10%) = $89.
* Reward tokens: $594 x 90% repaid x 50% within 30 days x 5% = 13 tokens.
* Record gain net of reward tokens: $89 - 13 x $1 x 75% = $79.
* Pickup: $240 today - $60 cash - 60 tokens x $1 x 75% = $135.
* Drum 2 pre-harvest sales: 70% x $176 turned away = $123.
* Tokens issued: 13 + 60 = 73 a year, 5.4% of $1,370 sales (cap 10%).
"""

from __future__ import annotations

from typing import Any

from .config import CASES, Config
from .ledger import GRAINS


def annual(cfg: Config, case: str = "base") -> dict[str, Any]:
    """Annual gains of the token model for a normal year, under one case."""
    if case not in CASES:
        raise ValueError(f"case must be one of {CASES}, not {case!r}")
    t = cfg.token
    y = cfg.year("normal")
    face = float(t["face_value_usd"])
    cost = float(t["cost_share_of_face"][case])
    sales = float(y["total_sales_usd"])
    credit = float(y["credit_usd"])

    # 1. The Libreta and the on-time reward.
    unpaid_today = float(y["unpaid_share_of_credit"])
    unpaid_libreta = float(t["unpaid_share_with_libreta"][case])
    recovered = credit * (unpaid_today - unpaid_libreta)
    repaid = credit * (1 - unpaid_libreta)
    on_time_cash = repaid * float(t["on_time_share_of_repaid"])
    reward_tokens = on_time_cash * float(t["earn"]["on_time_cash_reward_share"]) / face
    reward_cost = reward_tokens * face * cost
    record_gain = recovered - reward_cost

    # 2. The neighbor's pickup at peak harvest: half the fare in tokens.
    p = t["earn"]["pickup"]
    pickup_today = float(cfg.case["cash_costs_usd"]["pickup_rides"])
    fares = int(p["rides_per_year"]) * float(p["fare_usd"])
    pickup_tokens = fares * float(p["token_share_of_fare"]) / face
    pickup_cash = fares - pickup_tokens * face
    pickup_token_cost = pickup_tokens * face * cost
    pickup_gain = pickup_today - pickup_cash - pickup_token_cost

    # 3. Drum 2 serves buyers turned away before harvest.
    c = cfg.case["customers"]
    turned_away = float(t["turned_away_per_week_used"]) * c["turned_away_weeks"] * c["turned_away_avg_purchase_usd"]
    drum2_sales = turned_away * float(t["drum2_capture_of_turned_away"])

    tokens_issued = reward_tokens + pickup_tokens
    cap_tokens = sales * float(t["cap_share_of_sales"]) / face
    drum_cost = int(t["drums"]["total"]) * float(cfg.case["drums"]["cost_usd_each"])
    total_gain = record_gain + pickup_gain + drum2_sales
    prices = cfg.grain_prices()
    fill = t["drum2_fill_lb"]
    crop = t["crop_repayment_lb"]
    drum2_value = sum(fill.get(i, 0) * prices[i] for i in GRAINS)
    return {
        "case": case,
        "token_cost_share": cost,
        "sales_usd": sales,
        "credit_usd": credit,
        "unpaid_share_today": unpaid_today,
        "unpaid_share_with_libreta": unpaid_libreta,
        "unpaid_usd_today": credit * unpaid_today,
        "unpaid_usd_with_libreta": credit * unpaid_libreta,
        "credit_recovered_usd": recovered,
        "repaid_credit_usd": repaid,
        "on_time_cash_usd": on_time_cash,
        "reward_tokens": reward_tokens,
        "reward_token_cost_usd": reward_cost,
        "record_gain_net_usd": record_gain,
        "pickup_today_usd": pickup_today,
        "pickup_fares_usd": fares,
        "pickup_cash_usd": pickup_cash,
        "pickup_tokens": pickup_tokens,
        "pickup_token_cost_usd": pickup_token_cost,
        "pickup_gain_net_usd": pickup_gain,
        "turned_away_usd": turned_away,
        "drum2_sales_usd": drum2_sales,
        "tokens_issued": tokens_issued,
        "tokens_issued_usd": tokens_issued * face,
        "token_share_of_sales": tokens_issued * face / sales,
        "cap_tokens": cap_tokens,
        "within_cap": tokens_issued <= cap_tokens,
        "total_token_cost_usd": reward_cost + pickup_token_cost,
        "total_gain_usd": total_gain,
        "drum_cost_usd": drum_cost,
        "year1_gain_after_drums_usd": total_gain - drum_cost,
        "drum2_fill_value_usd": drum2_value,
        "drum2_needed_in_gap_usd": tokens_issued * face + drum2_sales,
        "crop_repayment_usd": sum(crop.get(i, 0) * prices[i] for i in GRAINS),
        "corn_lb_per_token": face / prices["corn"],
        "beans_lb_per_token": face / prices["beans"],
    }


def all_cases(cfg: Config) -> dict[str, dict[str, Any]]:
    return {case: annual(cfg, case) for case in CASES}
