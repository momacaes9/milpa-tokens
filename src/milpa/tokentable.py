"""The 'what one token buys' table."""

from __future__ import annotations

from .config import Config
from .ledger import FRESH_ITEMS


def token_table(cfg: Config, year: str = "normal") -> str:
    """Markdown table: what one token redeems for, and when."""
    rules = cfg.rules(year)
    lines = [
        "| Item | One token redeems for | Retail value at Tierra Viva | Redeemable in |",
        "|---|---|---|---|",
    ]
    for item, months in rules.redeem_months.items():
        unit = cfg.case["products"][item]["unit"]
        qty = rules.units_per_token(item)
        when = ", ".join(m for m in cfg.months_in_order() if m in months)
        kind = " (fresh, on hand that month)" if item in FRESH_ITEMS else ""
        lines.append(f"| {item}{kind} | {qty:.1f} {unit} | ${rules.token_value_usd:.2f} | {when} |")
    return "\n".join(lines)
