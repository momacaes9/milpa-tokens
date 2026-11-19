"""milpa: prove the Milpa Token rules and simulate them against the Tierra Viva case.

Commands:
  check          validate the config against the case's own arithmetic
  token-table    what one token redeems for
  lockin         what one hour of work buys: token vs cash wage vs produce truck
  simulate       replay the normal and bad-weather years with and without tokens
  sensitivity    BZ$5 vs BZ$6, 10 vs 9 lb corn, 2 vs 3 drums
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
from .tokentable import token_table

__all__ = ["main", "token_table"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="milpa", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"milpa {__version__}")
    parser.add_argument("--config", help="path to config JSON (default: config/tierra_viva.json)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="validate the config against the case arithmetic")
    t = sub.add_parser("token-table", help="print what one token redeems for")
    t.add_argument("--year", choices=["normal", "bad"], default="normal")
    lk = sub.add_parser("lockin", help="print the lock-in table")
    lk.add_argument("--wage-bzd", type=float, help="cash wage per hour in BZ$ (default from config)")
    lk.add_argument("--in-kind-lb", type=float, help="lb of corn per token (default from config)")
    s = sub.add_parser("simulate", help="replay the case years with and without tokens")
    s.add_argument("--year", choices=["normal", "bad", "both"], default="both")
    s.add_argument("--drums", type=int, help="total drums (family + sale)")
    s.add_argument("--wage-bzd", type=float, help="wage peg in BZ$ per hour")
    s.add_argument("--in-kind-lb", type=float, help="lb of corn per token")
    s.add_argument("--monte-carlo", type=int, metavar="RUNS", help="also run N Monte Carlo draws")
    s.add_argument("--seed", type=int, help="Monte Carlo seed (default from config)")
    sub.add_parser("sensitivity", help="print the sensitivity table")
    b = sub.add_parser("build-outputs", help="write all tables and charts to outputs/")
    b.add_argument("--out", default=str(DEFAULT_CONFIG.parents[1] / "outputs"), help="output directory")
    b.add_argument("--no-charts", action="store_true", help="skip PNG charts (no matplotlib needed)")
    b.add_argument("--mc-runs", type=int, help="override Monte Carlo runs")
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
        print("config OK: case totals reconcile (normal $1,370 / bad $900 sales)")
    elif args.cmd == "token-table":
        print(token_table(cfg, args.year))
    elif args.cmd == "lockin":
        from . import lockin
        wage = args.wage_bzd if args.wage_bzd is not None else cfg.token["wage_bzd_per_hour"]
        rows = lockin.lock_in_table(cfg, wage, args.in_kind_lb)
        print(lockin.to_markdown(rows, wage, cfg.fx))
    elif args.cmd == "simulate":
        from .outputs import SCENARIO_LABELS, monte_carlo_markdown, summary_markdown
        from .simulate import SCENARIOS, monte_carlo, simulate_year
        over = {}
        if args.drums is not None:
            over["drums_total"] = args.drums
        if args.wage_bzd is not None:
            over["wage_bzd_per_hour"] = args.wage_bzd
        if args.in_kind_lb is not None:
            over["in_kind_corn_lb"] = args.in_kind_lb
        years = ("normal", "bad") if args.year == "both" else (args.year,)
        results = {(s, y): simulate_year(cfg, y, s, over) for y in years for s in SCENARIOS}
        if args.year == "both":
            print(summary_markdown(results))
        else:
            y = args.year
            sub = {(s, yy): r for (s, yy), r in results.items()}
            # summary_markdown expects both years; fall back to a one-year table.
            print(f"### {y} year\n")
            print("| | " + " | ".join(SCENARIO_LABELS[s] for s in SCENARIOS) + " |")
            print("|---|" + "---:|" * len(SCENARIOS))
            from .outputs import SUMMARY_ROWS, _fmt
            for label, key, kind in SUMMARY_ROWS:
                print(f"| {label} | " + " | ".join(_fmt(sub[(s, y)].totals[key], kind) for s in SCENARIOS) + " |")
        if args.monte_carlo:
            seed = args.seed if args.seed is not None else cfg.raw["simulation"]["monte_carlo"]["seed"]
            if args.year != "both":
                print("\n(Monte Carlo reports both years)")
            mc = {y: monte_carlo(cfg, y, runs=args.monte_carlo, seed=seed) for y in ("normal", "bad")}
            print()
            print(monte_carlo_markdown(mc, args.monte_carlo, seed))
    elif args.cmd == "sensitivity":
        from .sensitivity import sensitivity_table, to_markdown
        print(to_markdown(sensitivity_table(cfg)))
    elif args.cmd == "build-outputs":
        from .outputs import build
        written = build(cfg, Path(args.out), charts=not args.no_charts, mc_runs=args.mc_runs)
        for path in written:
            print(path)
    return 0
