"""Season simulator: replay the case's normal and bad-weather years.

Three scenarios are run on the same months (Exhibit A month types laid on the
calendar in the config):

* ``today``  - the case as written: no drums, no tokens.
* ``drums``  - sealed drums only (family drum + sale drums); grain from the sale
  drums is sold to buyers the case says are turned away before harvest.
* ``tokens`` - drums plus Milpa Tokens: neighbors' hours at planting and harvest
  are paid in tokens backed by the sale drums, and part of never-repaid credit is
  paid back in hours ("pay in hands").

Every rule is enforced by running the real :class:`~milpa.ledger.Ledger`, so a
simulated year can never do something the paper rules forbid.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .config import Config
from .ledger import InsufficientReserve, Ledger

SCENARIOS = ("today", "drums", "tokens")


@dataclass
class MonthRow:
    """State at the end of one month."""

    index: int
    month: str
    month_type: str
    sales_usd: float
    credit_usd: float
    cash_collected_usd: float
    drum_sales_usd: float
    family_food_lb: float
    sale_drum_lb: float
    sale_drum_value_usd: float
    tokens_issued: int
    tokens_redeemed: int
    tokens_expired: int
    tokens_outstanding: int
    coverage_ratio: float | None
    token_hours: int
    debt_labor_hours: float
    fresh_redeemed_usd: float
    grain_redeemed_usd: float


@dataclass
class YearResult:
    """Totals and monthly path for one scenario and one year type."""

    scenario: str
    year: str
    months: list[MonthRow] = field(default_factory=list)
    totals: dict[str, float] = field(default_factory=dict)


def _monthly_credit_shares(cfg: Config, year: str) -> dict[str, float]:
    """Credit share by month type. Bad year: normal shares scaled to the case's $491."""
    normal = cfg.year("normal")["month_types"]
    shares = {k: v["credit_share"] for k, v in normal.items()}
    if year == "normal":
        return shares
    spec = cfg.year("bad")
    types = spec["month_types"]
    raw = sum(t["months"] * t["sales_per_month"] * shares[k] for k, t in types.items())
    scale = spec["credit_usd"] / raw
    return {k: s * scale for k, s in shares.items()}


def _sim_params(cfg: Config, overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    params = dict(cfg.raw["simulation"])
    params.update(overrides or {})
    return params


def simulate_year(cfg: Config, year: str = "normal", scenario: str = "tokens",
                  overrides: Mapping[str, Any] | None = None) -> YearResult:
    """Run twelve months of one scenario from a fresh start.

    Args:
        cfg: validated config.
        year: ``"normal"`` or ``"bad"``.
        scenario: one of :data:`SCENARIOS`.
        overrides: replace ``simulation`` settings (e.g. ``{"drums_total": 3}``)
            or token settings via keys ``wage_bzd_per_hour``, ``in_kind_corn_lb``,
            ``unpaid_share_of_credit``.

    Returns:
        A :class:`YearResult` with monthly rows and totals.
    """
    return simulate_sequence(cfg, (year,), scenario, overrides)[0]


def simulate_sequence(cfg: Config, years: Sequence[str], scenario: str = "tokens",
                      overrides: Mapping[str, Any] | None = None) -> list[YearResult]:
    """Run consecutive years on one ledger, e.g. ``("normal", "bad")``.

    Tokens, debts and drum contents carry over, so a token earned in a good
    harvest must still be honored, or expire under the rules, in a storm year.
    """
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {SCENARIOS}")
    if not years:
        raise ValueError("years must not be empty")
    p = _sim_params(cfg, overrides)
    token_over = {k: p[k] for k in ("in_kind_corn_lb",) if k in p}
    wage_usd = float(p.get("wage_bzd_per_hour", cfg.token["wage_bzd_per_hour"])) / cfg.fx
    if wage_usd <= 0:
        raise ValueError("wage must be positive")
    months = cfg.months_in_order()
    cust = cfg.case["customers"]
    capacity = cfg.case["drums"]["capacity_lb"]
    use_drums = scenario in ("drums", "tokens")
    use_tokens = scenario == "tokens"
    drums_total = int(p["drums_total"]) if use_drums else 0
    family_drums = int(p["family_drums"]) if use_drums else 0
    if use_drums and drums_total <= family_drums:
        raise ValueError("need at least one sale drum beyond the family drums")
    sale_drums = drums_total - family_drums
    mix = p["sale_drum_mix_by_weight"]
    households = [f"household_{n + 1:02d}" for n in range(int(p["participating_households"]))]
    spoil = cust["harvest_fresh_spoilage_share"]
    products = cfg.case["products"]
    plantain_share = products["plantain"]["share_of_sales"] / (
        products["plantain"]["share_of_sales"] + products["fresh_veg"]["share_of_sales"])
    redeem_target = float(p["redemption_rate"])
    turned_away_usd = p["turned_away_per_week_used"] * cust["turned_away_weeks"] * cust["turned_away_avg_purchase_usd"]
    normal_pre = cfg.year("normal")["month_types"]["pre_harvest"]["sales_per_month"]

    ledger = Ledger(cfg.rules(years[0], **token_over), start_month=cfg.calendar["start_month"])
    if use_drums:
        # Family drum(s) hold the family's own food and never enter the reserve.
        ledger.set_family_food("corn_and_beans", family_drums * capacity)
    types_seq = [cfg.month_type(y, m) for y in years for m in months]
    results: list[YearResult] = []
    hh_cursor = 0
    # Tokens that will never be brought back (lost, forgotten, kept as a keepsake).
    # For every 1 / (1 - redemption_rate) tokens issued, one is held back by its
    # household; it can only leave the notebook by expiring.
    never: dict[str, int] = {}
    dormant_credit = 0.0

    for n, year in enumerate(years):
        offset = 12 * n
        rules = cfg.rules(year, **token_over)
        ledger.rules = rules
        spec = cfg.year(year)
        types = spec["month_types"]
        unpaid_share = float(p.get("unpaid_share_of_credit", spec["unpaid_share_of_credit"]))
        credit_shares = _monthly_credit_shares(cfg, year)
        fs = p["sale_drum_fill_share"]
        fill = float(fs[year]) if isinstance(fs, Mapping) else float(fs)
        target_lb = {item: sale_drums * capacity * fill * share for item, share in mix.items()}

        def top_up(month: int) -> None:
            for item, target in target_lb.items():
                gap = target - ledger.sale_reserve.get(item, 0.0)
                if gap > 1e-9:
                    ledger.add_to_reserve(month, item, gap, note="harvest fill")

        harvest_local = [i for i, m in enumerate(months) if cfg.month_type(year, m) == "harvest"]
        pre_months = [i for i, m in enumerate(months) if cfg.month_type(year, m) == "pre_harvest"]
        demand_per_pre_month = turned_away_usd * types["pre_harvest"]["sales_per_month"] / normal_pre / len(pre_months)
        total_credit = sum(t["months"] * t["sales_per_month"] * credit_shares[k] for k, t in types.items())
        unpaid_total = total_credit * unpaid_share
        issue_idx = [i for i, m in enumerate(months) if m in rules.issue_months]
        debt_hours_pool = (unpaid_total * float(p["labor_settlement_share"]) / wage_usd) if use_tokens else 0.0
        debt_hours_per_work_month = debt_hours_pool / len(issue_idx) if issue_idx else 0.0
        grain_windows = [i for i, m in enumerate(months) if m in rules.redeem_months["corn"]]

        result = YearResult(scenario, year)
        for i, name in enumerate(months):
            g = offset + i  # global month index on the ledger
            mtype = types_seq[g]
            expired = ledger.expire(g)
            for hh in list(never):
                never[hh] = min(never[hh], ledger.held_by(hh, g))
            if use_drums and (g == 0 or (mtype == "harvest" and types_seq[g - 1] != "harvest")):
                top_up(g)

            sales = types[mtype]["sales_per_month"]
            credit = sales * credit_shares[mtype]
            cash = sales - credit * unpaid_share
            issued_before, redeemed_before = ledger.issued_total, ledger.redeemed_total
            token_hours = 0
            debt_hours = 0.0
            fresh_usd = grain_usd = 0.0

            # Fresh surplus that would spoil at harvest (Exhibit D: 20% of what is offered).
            if mtype == "harvest":
                fresh_sold = sales * float(p["fresh_share_of_harvest_sales"])
                spoiled_usd = fresh_sold * spoil / (1 - spoil)
                ledger.set_fresh_on_hand(g, "plantain", spoiled_usd * plantain_share / rules.prices_usd["plantain"])
                ledger.set_fresh_on_hand(g, "fresh_veg", spoiled_usd * (1 - plantain_share) / rules.prices_usd["fresh_veg"])

            # Work months: debt paid in hands first, then hours paid in tokens.
            if use_tokens and i in issue_idx:
                wanted = float(p["help_hours_wanted_per_work_month"])
                debt_hours = min(debt_hours_per_work_month, wanted)
                room = int(wanted - debt_hours)
                for _ in range(room):
                    if ledger.backable_tokens() < 1:
                        break
                    placed = False
                    for _ in range(len(households)):
                        hh = households[hh_cursor % len(households)]
                        hh_cursor += 1
                        if ledger.held_by(hh, g) < rules.max_tokens_per_household:
                            ledger.issue(g, hh, 1)
                            token_hours += 1
                            dormant_credit += 1 - redeem_target
                            if dormant_credit >= 1 - 1e-9:
                                dormant_credit -= 1
                                never[hh] = never.get(hh, 0) + 1
                            placed = True
                            break
                    if not placed:
                        break
                # Harvest-month tokens taken straight away in produce that would spoil.
                if mtype == "harvest" and token_hours:
                    want = round(token_hours * float(p["fresh_redemption_share_at_harvest"]))
                    fresh_usd += _redeem_fresh(ledger, g, want, never)

            # Grain windows: redeem a share of eligible tokens from the sale drums.
            if use_tokens and i in grain_windows and ledger.outstanding:
                left_windows = len([w for w in grain_windows if w >= i])
                eligible = sum(_redeemable(ledger, hh, g, never, before=True) for hh in households)
                want = math.ceil(eligible / left_windows)
                grain_usd += _redeem_grain(ledger, g, want, never, households)

            # Pre-harvest: sell free grain to buyers who would otherwise be turned away.
            drum_sales = 0.0
            if use_drums and mtype == "pre_harvest":
                drum_sales = _sell_free_grain(ledger, g, demand_per_pre_month)
                drum_credit = drum_sales * credit_shares["pre_harvest"]
                sales += drum_sales
                credit += drum_credit
                cash += drum_sales - drum_credit * unpaid_share

            cov = ledger.coverage_ratio()
            result.months.append(MonthRow(
                index=g, month=name, month_type=mtype,
                sales_usd=sales, credit_usd=credit, cash_collected_usd=cash,
                drum_sales_usd=drum_sales,
                family_food_lb=sum(ledger.family_reserve_lb.values()),
                sale_drum_lb=max(0.0, sum(ledger.sale_reserve.values())),
                sale_drum_value_usd=ledger.reserve_value_usd(),
                tokens_issued=ledger.issued_total - issued_before,
                tokens_redeemed=ledger.redeemed_total - redeemed_before,
                tokens_expired=expired,
                tokens_outstanding=ledger.outstanding,
                coverage_ratio=None if cov == float("inf") else cov,
                token_hours=token_hours,
                debt_labor_hours=round(debt_hours, 4),
                fresh_redeemed_usd=fresh_usd,
                grain_redeemed_usd=grain_usd,
            ))
        result.totals = _totals(cfg, result, p, wage_usd, unpaid_total,
                                drums_total if n == 0 else 0, [offset + i for i in harvest_local])
        results.append(result)
    return results


def _redeemable(ledger: Ledger, household: str, month: int, never: Mapping[str, int],
                before: bool = False) -> int:
    """Valid tokens a household will bring back this month (``before``: issued earlier)."""
    held = sum(lot.remaining for lot in ledger.lots
               if lot.household == household and month - lot.issued_month < ledger.rules.expiry_months
               and (not before or lot.issued_month < month))
    return max(0, held - never.get(household, 0))


def _redeem_fresh(ledger: Ledger, month: int, want: int, never: Mapping[str, int] | None = None) -> float:
    """Redeem up to ``want`` tokens issued this month in fresh produce on hand."""
    usd = 0.0
    never = never or {}
    takers = sorted({lot.household for lot in ledger.lots if lot.issued_month == month})
    for item in ("plantain", "fresh_veg"):
        per = ledger.rules.units_per_token(item)
        for hh in takers:
            while (want > 0 and _redeemable(ledger, hh, month, never) > 0
                   and ledger.fresh_on_hand.get(item, 0.0) + 1e-9 >= per):
                ledger.redeem(month, hh, 1, item)
                usd += ledger.rules.token_value_usd
                want -= 1
    return usd


def _redeem_grain(ledger: Ledger, month: int, want: int, never: Mapping[str, int],
                  households: Sequence[str]) -> float:
    """Redeem up to ``want`` tokens in corn or beans; households with the oldest tokens first."""
    usd = 0.0

    def oldest(hh: str) -> int:
        return min((lot.issued_month for lot in ledger.lots if lot.household == hh), default=10**9)

    for hh in sorted(households, key=oldest):
        while want > 0 and _redeemable(ledger, hh, month, never, before=True) > 0:
            # Paid from the fullest grain first, topped up with the other if needed.
            try:
                ledger.redeem_grain_mix(month, hh, 1)
            except InsufficientReserve:
                return usd  # drums empty
            usd += ledger.rules.token_value_usd
            want -= 1
    return usd


def _sell_free_grain(ledger: Ledger, month: int, demand_usd: float) -> float:
    """Sell grain not needed to back tokens, up to the month's turned-away demand."""
    budget = min(demand_usd, ledger.free_reserve_value_usd())
    sold = 0.0
    value = ledger.reserve_value_usd()
    if value <= 0 or budget <= 0:
        return 0.0
    for item in ("corn", "beans"):
        item_value = ledger.sale_reserve.get(item, 0.0) * ledger.rules.prices_usd[item]
        share_usd = budget * item_value / value
        lb = share_usd / ledger.rules.prices_usd[item]
        if lb > 1e-9:
            sold += ledger.sell_from_reserve(month, item, lb)
    return sold


def _totals(cfg: Config, r: YearResult, p: Mapping[str, Any], wage_usd: float,
            unpaid_total: float, drums_total: int, harvest_idx: list[int]) -> dict[str, float]:
    m = r.months
    costs = sum(cfg.case["cash_costs_usd"].values())
    drum_cost = drums_total * cfg.case["drums"]["cost_usd_each"]
    cash = sum(x.cash_collected_usd for x in m)
    token_hours = sum(x.token_hours for x in m)
    debt_hours = sum(x.debt_labor_hours for x in m)
    productivity = float(p["helper_productivity"])
    harvest_help = sum(x.token_hours + x.debt_labor_hours for x in m if x.index in harvest_idx)
    covs = [x.coverage_ratio for x in m if x.coverage_ratio is not None]
    return {
        "sales_usd": sum(x.sales_usd for x in m),
        "credit_usd": sum(x.credit_usd for x in m),
        "unpaid_credit_usd": unpaid_total,
        "cash_collected_usd": cash,
        "drum_sales_usd": sum(x.drum_sales_usd for x in m),
        "net_cash_income_usd": cash - costs,
        "drum_cost_usd": drum_cost,
        "net_cash_after_drums_year1_usd": cash - costs - drum_cost,
        "bad_debt_recovered_hours": debt_hours,
        "bad_debt_recovered_usd": debt_hours * wage_usd,
        "token_hours": token_hours,
        "helper_hours_total": token_hours + debt_hours,
        "ernestine_hours_saved_total": (token_hours + debt_hours) * productivity,
        "ernestine_hours_saved_harvest": harvest_help * productivity,
        "tokens_issued": sum(x.tokens_issued for x in m),
        "tokens_redeemed": sum(x.tokens_redeemed for x in m),
        "tokens_expired": sum(x.tokens_expired for x in m),
        "tokens_outstanding_end": m[-1].tokens_outstanding,
        "fresh_redeemed_usd": sum(x.fresh_redeemed_usd for x in m),
        "grain_redeemed_usd": sum(x.grain_redeemed_usd for x in m),
        "min_coverage_ratio": min(covs) if covs else float("nan"),
        "family_food_lb_min": min(x.family_food_lb for x in m),
        "sale_drum_lb_min": max(0.0, min(x.sale_drum_lb for x in m)),
    }


def run_all(cfg: Config, overrides: Mapping[str, Any] | None = None) -> dict[tuple[str, str], YearResult]:
    """Every scenario for both year types."""
    return {(s, y): simulate_year(cfg, y, s, overrides) for y in ("normal", "bad") for s in SCENARIOS}


# ----------------------------------------------------------------- Monte Carlo
def monte_carlo(cfg: Config, year: str = "normal", runs: int | None = None,
                seed: int | None = None) -> dict[str, dict[str, float]]:
    """Repayment uncertainty: draw unpaid share, labor settlement, redemption and fill.

    * unpaid share of credit ~ Beta with mean = the case value and concentration
      ``unpaid_share_concentration``;
    * labor settlement share, redemption rate and bad-year drum fill ~ uniform on
      their configured ranges.

    Returns P10 / P50 / P90 (and mean) of key totals for the ``tokens`` scenario,
    plus the ``today`` cash for the same draw of the unpaid share.
    """
    mc = cfg.raw["simulation"]["monte_carlo"]
    runs = int(mc["runs"] if runs is None else runs)
    if runs < 1:
        raise ValueError("runs must be >= 1")
    rng = random.Random(mc["seed"] if seed is None else seed)
    mean = cfg.year(year)["unpaid_share_of_credit"]
    k = float(mc["unpaid_share_concentration"])
    keys = ("cash_collected_usd", "bad_debt_recovered_hours", "bad_debt_recovered_usd",
            "helper_hours_total", "ernestine_hours_saved_harvest", "tokens_issued",
            "tokens_expired", "min_coverage_ratio", "drum_sales_usd")
    samples: dict[str, list[float]] = {key: [] for key in keys}
    samples["today_cash_collected_usd"] = []
    samples["unpaid_share_of_credit"] = []
    fill = dict(cfg.raw["simulation"]["sale_drum_fill_share"])
    for _ in range(runs):
        unpaid = rng.betavariate(mean * k, (1 - mean) * k)
        if year == "bad":
            fill = {**fill, "bad": rng.uniform(*mc["bad_year_fill_share_range"])}
        over = {
            "unpaid_share_of_credit": unpaid,
            "labor_settlement_share": rng.uniform(*mc["labor_settlement_share_range"]),
            "redemption_rate": rng.uniform(*mc["redemption_rate_range"]),
            "sale_drum_fill_share": fill,
        }
        tok = simulate_year(cfg, year, "tokens", over).totals
        today = simulate_year(cfg, year, "today", {"unpaid_share_of_credit": unpaid}).totals
        for key in keys:
            samples[key].append(tok[key])
        samples["today_cash_collected_usd"].append(today["cash_collected_usd"])
        samples["unpaid_share_of_credit"].append(unpaid)
    return {key: _summary(vals) for key, vals in samples.items()}


def _summary(values: list[float]) -> dict[str, float]:
    vals = sorted(v for v in values if v == v)  # drop NaN
    if not vals:
        return {"p10": float("nan"), "p50": float("nan"), "p90": float("nan"), "mean": float("nan")}
    if len(vals) == 1:
        v = vals[0]
        return {"p10": v, "p50": v, "p90": v, "mean": v}
    q = statistics.quantiles(vals, n=10, method="inclusive")
    return {"p10": q[0], "p50": statistics.median(vals), "p90": q[-1], "mean": statistics.fmean(vals)}
