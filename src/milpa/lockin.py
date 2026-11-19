"""Lock-in: why a neighbor would rather hold a Milpa Token than take cash.

For each item a token can be redeemed for, compare what **one hour of work**
buys in three ways:

1. paid in a token, redeemed at Tierra Viva;
2. paid in cash at the minimum wage, spent at Tierra Viva;
3. paid in cash at the minimum wage, spent at the produce truck, which sells
   plantains, tomatoes and onions 10-15% cheaper but offers no credit and does
   not accept tokens (case, "Competition").

A Punta Gorda market column (BAPIS retail prices) is shown for reference only:
reaching it costs a $5 round-trip bus fare (Exhibit D), two hours of wage.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import Config

#: Which Tierra Viva items the truck also sells, and the truck's matching product.
TRUCK_ITEMS = {"plantain": "plantains", "fresh_veg": "tomatoes only"}
#: BAPIS series used for the Punta Gorda reference column.
BAPIS_SERIES = {
    "corn": "bapis_punta_gorda_white_corn",
    "beans": "bapis_punta_gorda_rk_beans",
    "plantain": "bapis_punta_gorda_green_plantain",
    "fresh_veg": "bapis_punta_gorda_sweet_pepper",
}
LABELS = {
    "corn": "Corn (dried)",
    "beans": "Beans (dried)",
    "seed_corn": "Seed corn",
    "plantain": "Plantains",
    "fresh_veg": "Peppers / tomatoes / herbs",
}
#: Items Ernestine sells that are scarce before harvest (Exhibit D: buyers turned away).
SCARCE_PRE_HARVEST = {"corn", "beans"}


@dataclass(frozen=True)
class LockInRow:
    """One line of the lock-in table. Quantities are in the item's unit."""

    item: str
    unit: str
    token_qty: float
    wage_qty_at_tierra_viva: float
    wage_qty_at_truck_low: float | None
    wage_qty_at_truck_high: float | None
    wage_qty_at_punta_gorda: float | None
    punta_gorda_price_date: str | None
    advantage_vs_cash_at_tierra_viva: float
    advantage_vs_truck_worst_case: float | None
    available_with_cash_pre_harvest: bool
    note: str


def reference_data(path: Path | None = None) -> list[dict[str, str]]:
    """Rows of ``data/belize_reference_data.csv``."""
    from .config import DEFAULT_CONFIG

    path = path or DEFAULT_CONFIG.parents[1] / "data" / "belize_reference_data.csv"
    with Path(path).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def latest_usd(rows: list[dict[str, str]], indicator: str) -> tuple[float, str] | None:
    """Most recent non-empty USD value for an indicator, with its date."""
    found = [r for r in rows if r["indicator"] == indicator and r["usd_equivalent"]]
    if not found:
        return None
    best = max(found, key=lambda r: r["date"])
    return float(best["usd_equivalent"]), best["date"]


def lock_in_table(cfg: Config, wage_bzd_per_hour: float | None = None,
                  in_kind_corn_lb: float | None = None,
                  rows: list[dict[str, str]] | None = None) -> list[LockInRow]:
    """Build the lock-in table for the given token settings (config defaults otherwise)."""
    overrides = {}
    if in_kind_corn_lb is not None:
        overrides["in_kind_corn_lb"] = in_kind_corn_lb
    rules = cfg.rules("normal", **overrides)
    wage_bzd = cfg.token["wage_bzd_per_hour"] if wage_bzd_per_hour is None else wage_bzd_per_hour
    wage_usd = wage_bzd / cfg.fx
    lo, hi = cfg.case["truck"]["discount_vs_ernestine"]
    rows = reference_data() if rows is None else rows
    out: list[LockInRow] = []
    for item in rules.redeem_months:
        price = rules.prices_usd[item]
        unit = cfg.case["products"][item]["unit"]
        token_qty = rules.units_per_token(item)
        at_tv = wage_usd / price
        truck_low = truck_high = adv_truck = None
        if item in TRUCK_ITEMS:
            truck_low = wage_usd / (price * (1 - lo))   # 10% cheaper
            truck_high = wage_usd / (price * (1 - hi))  # 15% cheaper: most for cash
            adv_truck = token_qty / truck_high - 1
        pg = latest_usd(rows, BAPIS_SERIES[item]) if item in BAPIS_SERIES else None
        notes = []
        if item in SCARCE_PRE_HARVEST:
            notes.append("truck does not sell it; 8-10 buyers a week turned away before harvest")
        if item == "seed_corn":
            notes.append("little competition (Exhibit B); sold before planting")
        if item in TRUCK_ITEMS:
            notes.append(f"truck sells {TRUCK_ITEMS[item]}, no credit, no tokens")
        if item == "fresh_veg":
            notes.append("Punta Gorda column uses BAPIS sweet pepper")
        out.append(LockInRow(
            item=item,
            unit=unit,
            token_qty=token_qty,
            wage_qty_at_tierra_viva=at_tv,
            wage_qty_at_truck_low=truck_low,
            wage_qty_at_truck_high=truck_high,
            wage_qty_at_punta_gorda=(wage_usd / pg[0]) if pg else None,
            punta_gorda_price_date=pg[1] if pg else None,
            advantage_vs_cash_at_tierra_viva=token_qty / at_tv - 1,
            advantage_vs_truck_worst_case=adv_truck,
            available_with_cash_pre_harvest=item not in SCARCE_PRE_HARVEST,
            note="; ".join(notes),
        ))
    return out


def lock_in_summary(cfg: Config, wage_bzd_per_hour: float | None = None,
                    in_kind_corn_lb: float | None = None) -> dict[str, float]:
    """Headline lock-in numbers for one token setting."""
    table = lock_in_table(cfg, wage_bzd_per_hour, in_kind_corn_lb)
    by_item = {r.item: r for r in table}
    truck = [r.advantage_vs_truck_worst_case for r in table if r.advantage_vs_truck_worst_case is not None]
    return {
        "token_premium_vs_cash_wage": by_item["corn"].advantage_vs_cash_at_tierra_viva,
        "worst_truck_advantage": min(truck),
        "corn_lb_per_token": by_item["corn"].token_qty,
        "corn_lb_per_wage_hour": by_item["corn"].wage_qty_at_tierra_viva,
    }


def _fmt_qty(q: float | None, unit: str) -> str:
    if q is None:
        return "not sold"
    unit = "" if unit == "each" else f" {unit}"
    return f"{q:.1f}{unit}"


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:+.0%}"


def to_markdown(table: list[LockInRow], wage_bzd: float, fx: float) -> str:
    """Render the lock-in table as Markdown."""
    head = (
        f"| Item | 1 token buys at Tierra Viva | 1 hour's cash wage (BZ${wage_bzd:.2f} = US${wage_bzd / fx:.2f}) buys at Tierra Viva "
        "| ...at the produce truck (10-15% cheaper) | ...at Punta Gorda market* | Token vs cash at Tierra Viva "
        "| Token vs truck (truck's best price) | Can cash buy it from her pre-harvest? |\n"
        "|---|---|---|---|---|---|---|---|"
    )
    lines = [head]
    for r in table:
        truck = (
            "not sold" if r.wage_qty_at_truck_low is None
            else f"{r.wage_qty_at_truck_low:.1f}-{r.wage_qty_at_truck_high:.1f}"
        )
        pg = (
            "n/a" if r.wage_qty_at_punta_gorda is None
            else f"{_fmt_qty(r.wage_qty_at_punta_gorda, r.unit)} ({r.punta_gorda_price_date})"
        )
        avail = "yes" if r.available_with_cash_pre_harvest else "not today: 8-10 buyers a week turned away"
        lines.append(
            f"| {LABELS[r.item]} | {_fmt_qty(r.token_qty, r.unit)} | {_fmt_qty(r.wage_qty_at_tierra_viva, r.unit)} "
            f"| {truck} | {pg} | {_pct(r.advantage_vs_cash_at_tierra_viva)} "
            f"| {_pct(r.advantage_vs_truck_worst_case)} | {avail} |"
        )
    lines.append("")
    lines.append(
        "\\* BAPIS retail prices, latest Punta Gorda report reachable (2022). Reaching the market costs a "
        "$5 round-trip bus fare (Exhibit D), two hours of wage, so it is not a practical option for one hour's pay."
    )
    return "\n".join(lines)


def to_csv_rows(table: list[LockInRow]) -> list[dict[str, object]]:
    return [asdict(r) for r in table]
