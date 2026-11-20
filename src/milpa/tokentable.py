"""Tokens per lb: how corn and beans convert to tokens, both ways."""

from __future__ import annotations

from typing import Any

from .config import Config
from .ledger import GRAINS

LABELS = {"corn": "Corn (dried)", "beans": "Beans (dried)"}


def token_rows(cfg: Config) -> list[dict[str, Any]]:
    face = float(cfg.token["face_value_usd"])
    rows = []
    for item in GRAINS:
        price = cfg.price(item)
        rows.append({
            "item": item,
            "price_usd_per_lb": price,
            "lb_per_token": face / price,
            "tokens_per_lb": price / face,
            "example_lb": 10,
            "example_tokens": 10 * price / face,
        })
    return rows


def token_table(cfg: Config) -> str:
    """Markdown table: corn 3.33 lb = 1 token, beans 1 lb = 1 token."""
    order = cfg.months_in_order()
    months = ", ".join(sorted(cfg.redeem_months("normal"), key=order.index))
    lines = [
        "| Item | Case price (Exhibit B) | 1 token = | Repaying 10 lb credits | Spent in |",
        "|---|---:|---:|---:|---|",
    ]
    for r in token_rows(cfg):
        lines.append(
            f"| {LABELS[r['item']]} | ${r['price_usd_per_lb']:.2f}/lb | {r['lb_per_token']:.2f} lb "
            f"| {r['example_tokens']:g} tokens | pre-harvest gap ({months}) |"
        )
    return "\n".join(lines)
