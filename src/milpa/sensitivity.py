"""Sensitivity: token value BZ$5 vs BZ$6, in-kind rate 10 vs 9 lb corn, 2 vs 3 drums."""

from __future__ import annotations

import itertools
from typing import Any

from .config import Config
from .lockin import lock_in_summary
from .simulate import simulate_year


def sensitivity_table(cfg: Config) -> list[dict[str, Any]]:
    """One row per combination in ``config.sensitivity``; baseline flagged."""
    grid = cfg.raw["sensitivity"]
    base = (cfg.token["wage_bzd_per_hour"], cfg.token["in_kind_corn_lb"], cfg.raw["simulation"]["drums_total"])
    rows: list[dict[str, Any]] = []
    for wage, lb, drums in itertools.product(grid["wage_bzd_per_hour"], grid["in_kind_corn_lb"], grid["drums_total"]):
        over = {"wage_bzd_per_hour": wage, "in_kind_corn_lb": lb, "drums_total": drums}
        lock = lock_in_summary(cfg, wage, lb)
        normal = simulate_year(cfg, "normal", "tokens", over).totals
        bad = simulate_year(cfg, "bad", "tokens", over).totals
        drums_only = simulate_year(cfg, "normal", "drums", over).totals
        rows.append({
            "wage_bzd_per_hour": wage,
            "in_kind_corn_lb": lb,
            "drums_total": drums,
            "baseline": (wage, lb, drums) == base,
            "token_value_usd": lb * cfg.price("corn"),
            "wage_usd_per_hour": wage / cfg.fx,
            "token_premium_vs_cash_wage": lock["token_premium_vs_cash_wage"],
            "token_vs_truck_worst": lock["worst_truck_advantage"],
            "normal_tokens_issued": normal["tokens_issued"],
            "normal_helper_hours": normal["helper_hours_total"],
            "normal_debt_hours": normal["bad_debt_recovered_hours"],
            "normal_cash_collected_usd": normal["cash_collected_usd"],
            "normal_cash_vs_drums_only_usd": normal["cash_collected_usd"] - drums_only["cash_collected_usd"],
            "normal_min_coverage": normal["min_coverage_ratio"],
            "bad_helper_hours": bad["helper_hours_total"],
            "bad_cash_collected_usd": bad["cash_collected_usd"],
            "drum_cost_usd": normal["drum_cost_usd"],
        })
    return rows


def to_markdown(rows: list[dict[str, Any]]) -> str:
    head = (
        "| Wage peg | In-kind rate | Drums | Token value | Token vs cash wage | Token vs truck (best truck price) "
        "| Helper hours, normal yr | ...of which debt paid in hands | Helper hours, bad yr "
        "| Cash collected, normal yr | Cash vs drums-only | Min coverage |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    lines = [head]
    for r in rows:
        flag = " **(base)**" if r["baseline"] else ""
        lines.append(
            f"| BZ${r['wage_bzd_per_hour']:.0f}/h{flag} | {r['in_kind_corn_lb']:g} lb corn | {r['drums_total']} "
            f"| ${r['token_value_usd']:.2f} | {r['token_premium_vs_cash_wage']:+.0%} | {r['token_vs_truck_worst']:+.0%} "
            f"| {r['normal_helper_hours']:.0f} | {r['normal_debt_hours']:.0f} | {r['bad_helper_hours']:.0f} "
            f"| ${r['normal_cash_collected_usd']:,.0f} | {r['normal_cash_vs_drums_only_usd']:+,.0f} "
            f"| {r['normal_min_coverage']:.2f} |"
        )
    return "\n".join(lines)
