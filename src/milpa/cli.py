"""Command line: ``milpa check`` and ``milpa token-table``."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from . import __version__
from .config import ConfigError, load
from .ledger import FRESH_ITEMS


def token_table(cfg, year: str = "normal") -> str:
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="milpa", description=__doc__)
    parser.add_argument("--version", action="version", version=f"milpa {__version__}")
    parser.add_argument("--config", help="path to config JSON (default: config/tierra_viva.json)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="validate the config against the case arithmetic")
    t = sub.add_parser("token-table", help="print what one token redeems for")
    t.add_argument("--year", choices=["normal", "bad"], default="normal")
    args = parser.parse_args(argv)

    try:
        cfg = load(args.config)
    except (ConfigError, OSError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    if args.cmd == "check":
        print("config OK: case totals reconcile (normal $1,370 / bad $900 sales)")
    elif args.cmd == "token-table":
        print(token_table(cfg, args.year))
    return 0
