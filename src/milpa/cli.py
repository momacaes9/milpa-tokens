"""milpa: prove the token rules and reproduce the pitch deck's numbers from the case.

Commands:
  check          validate the config against the case's own arithmetic
  token-table    tokens per lb of corn and beans
  lockin         what one token is worth at Tierra Viva, the truck, and as cash
  model          annual gains, base / conservative / optimistic
  simulate       monthly replay of the token flows through the Libreta rules
  build-outputs  write every table (Markdown + CSV) and chart (PNG) to outputs/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import DEFAULT_CONFIG, ConfigError, load
from .ledger import LedgerError

__all__ = ["main"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="milpa", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"milpa {__version__}")
    parser.add_argument("--config", help="path to config JSON (default: config/tierra_viva.json)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="validate the config against the case arithmetic")
    sub.add_parser("token-table", help="tokens per lb of corn and beans")
    sub.add_parser("lockin", help="print the lock-in table")
    sub.add_parser("model", help="annual gains in three cases")
    s = sub.add_parser("simulate", help="monthly replay through the Libreta rules")
    s.add_argument("--years", type=int, default=2, help="consecutive normal years (default 2)")
    b = sub.add_parser("build-outputs", help="write all tables and charts to outputs/")
    b.add_argument("--out", default=str(DEFAULT_CONFIG.parents[1] / "outputs"), help="output directory")
    b.add_argument("--no-charts", action="store_true", help="skip PNG charts (no matplotlib needed)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cfg = load(args.config)
    except (ConfigError, OSError, ValueError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    try:
        return _run(cfg, args)
    except (LedgerError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _run(cfg, args) -> int:
    if args.cmd == "check":
        print("config OK: case totals reconcile (normal $1,370 / bad $900 sales); token block follows the final model")
    elif args.cmd == "token-table":
        from .tokentable import token_table
        print(token_table(cfg))
    elif args.cmd == "lockin":
        from . import lockin
        print(lockin.to_markdown(lockin.lock_in_table(cfg)))
    elif args.cmd == "model":
        from .model import all_cases
        from .outputs import cases_markdown
        print(cases_markdown(all_cases(cfg)))
    elif args.cmd == "simulate":
        from .outputs import replay_markdown
        from .simulate import replay
        print(replay_markdown(replay(cfg, years=args.years)))
    elif args.cmd == "build-outputs":
        from .outputs import build
        for path in build(cfg, Path(args.out), charts=not args.no_charts):
            print(path)
    return 0
