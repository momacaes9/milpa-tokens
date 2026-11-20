"""Write every table the pitch deck needs to ``outputs/`` (Markdown + CSV, PNG charts)."""

from __future__ import annotations

import csv
import math
from dataclasses import asdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import lockin
from .config import CASES, Config
from .model import all_cases
from .simulate import YearReplay, replay
from .tokentable import token_rows, token_table

#: The replay year reported in the outputs (year 1 is the warm-up).
REPORT_YEAR = 2


def usd(x: float) -> str:
    """Round half up to whole dollars, the way the case rounds ($148.5 -> $149)."""
    if x != x:  # NaN
        return "n/a"
    d = Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    sign = "-" if d < 0 else ""
    return f"{sign}${abs(int(d)):,}"


def num(x: float, digits: int = 0) -> str:
    if x != x:
        return "n/a"
    if math.isinf(x):
        return "inf"
    q = Decimal(1).scaleb(-digits)
    return f"{Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP):,}"


def pct(x: float, digits: int = 0) -> str:
    return f"{num(x * 100, digits)}%"


def write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        if not rows:
            fh.write("")
            return
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (round(v, 6) if isinstance(v, float) else v) for k, v in row.items()})


# ------------------------------------------------------------- annual model
CASE_ROWS = (
    ("Token cost to Ernestine (share of $1 face)", "token_cost_share", "pct", "deck"),
    ("Unpaid credit today (Exhibit A)", "unpaid_usd_today", "usd", "Exhibit A: $594 x 25%"),
    ("Unpaid credit with the Libreta", "unpaid_usd_with_libreta", "usd", "deck: 10% base, 15% cons., 8% opt."),
    ("Credit no longer lost", "credit_recovered_usd", "usd", "$594 x (25% - unpaid with Libreta)"),
    ("Reward tokens (5% of cash repaid within 30 days)", "reward_tokens", "n", "$594 x repaid x 50% on time x 5%"),
    ("Record gain net of reward tokens", "record_gain_net_usd", "usd", "credit recovered - reward tokens x $1 x cost"),
    ("Pickup rides today (Exhibit C costs)", "pickup_today_usd", "usd", "case cash costs"),
    ("Pickup tokens (12 rides x $10, half in tokens)", "pickup_tokens", "n", "deck"),
    ("Pickup gain net of token cost", "pickup_gain_net_usd", "usd", "$240 - $60 cash - 60 x $1 x cost"),
    ("Pre-harvest demand turned away (Exhibit D)", "turned_away_usd", "usd", "9 buyers/wk x 13 wk x $1.50"),
    ("Drum 2 pre-harvest sales (70% served)", "drum2_sales_usd", "usd", "deck: 70% x $176"),
    ("Total of the three gains", "total_gain_usd", "usd", "record + pickup + drum 2"),
    ("Drums, one-off (2 x $100, Exhibit E)", "drum_cost_usd", "usd", "Exhibit E"),
    ("Year-1 gain after buying the drums", "year1_gain_after_drums_usd", "usd", "total - drums"),
    ("Tokens issued per year", "tokens_issued", "n", "reward + pickup"),
    ("Tokens as a share of sales (cap 10%)", "token_share_of_sales", "pct1", "tokens x $1 / $1,370"),
)


def _fmt(value: Any, kind: str) -> str:
    if kind == "usd":
        return usd(value)
    if kind == "pct":
        return pct(value)
    if kind == "pct1":
        return pct(value, 1)
    if kind == "ratio":
        return "no tokens out" if value != value else num(value, 2)
    return num(value, 0)


def cases_markdown(cases: Mapping[str, Mapping[str, Any]]) -> str:
    head = "| Normal year | " + " | ".join(c.capitalize() for c in CASES) + " | Source |"
    lines = [head, "|---|" + "---:|" * len(CASES) + "---|"]
    for label, key, kind, src in CASE_ROWS:
        lines.append(f"| {label} | " + " | ".join(_fmt(cases[c][key], kind) for c in CASES) + f" | {src} |")
    return "\n".join(lines)


# ------------------------------------------------------------------- replay
REPLAY_ROWS = (
    ("Tokens issued: 5% on-time reward", "reward_tokens_issued", "n"),
    ("Tokens issued: half pickup fare", "pickup_tokens_issued", "n"),
    ("Tokens issued, total (cap 137)", "tokens_issued", "n"),
    ("Tokens spent on corn and beans in the gap", "tokens_redeemed", "n"),
    ("Tokens outstanding at year end (backed by drum 2)", "tokens_outstanding_end", "n"),
    ("Crop repayments (US$ = tokens credited against debt)", "crop_repaid_usd", "usd"),
    ("Drum 2 sales to buyers turned away today", "drum2_sales_usd", "usd"),
    ("Pickup fares paid in cash", "pickup_cash_usd", "usd"),
    ("Lowest coverage: drum 2 value / tokens out (rule: >= 1.00)", "min_coverage_ratio", "ratio"),
    ("Drum 2 value, highest (US$)", "drum2_value_max_usd", "usd"),
    ("Drum 2 contents, highest (lb, capacity 250)", "drum2_lb_max", "n"),
    ("Drum 1 family food, lowest (lb, never touched)", "family_drum_lb_min", "n"),
)


def replay_markdown(years: list[YearReplay]) -> str:
    head = "| Monthly replay, normal years | " + " | ".join(f"Year {r.year_number}" for r in years) + " |"
    lines = [head, "|---|" + "---:|" * len(years)]
    for label, key, kind in REPLAY_ROWS:
        lines.append(f"| {label} | " + " | ".join(_fmt(r.totals[key], kind) for r in years) + " |")
    lines += ["", "Year 1 starts in February with drum 2 full from the previous harvest and no tokens out "
              "(warm-up); year 2 is the steady state."]
    return "\n".join(lines)


# -------------------------------------------------------------- key results
def key_results(cfg: Config, cases: Mapping[str, Mapping[str, Any]],
                years: list[YearReplay]) -> dict[str, Any]:
    b = cases["base"]
    r = years[REPORT_YEAR - 1].totals
    rows = {x["item"]: x for x in token_rows(cfg)}
    return {
        "tokens_issued": b["tokens_issued"],
        "reward_tokens": b["reward_tokens"],
        "pickup_tokens": b["pickup_tokens"],
        "token_share_of_sales": b["token_share_of_sales"],
        "sales_usd": b["sales_usd"],
        "cap_share_of_sales": cfg.token["cap_share_of_sales"],
        "cap_tokens": b["cap_tokens"],
        "credit_usd": b["credit_usd"],
        "unpaid_share_today": b["unpaid_share_today"],
        "unpaid_share_with_libreta": b["unpaid_share_with_libreta"],
        "credit_recovered_usd": b["credit_recovered_usd"],
        "record_gain_net_usd": b["record_gain_net_usd"],
        "pickup_today_usd": b["pickup_today_usd"],
        "pickup_cash_usd": b["pickup_cash_usd"],
        "token_cost_share": b["token_cost_share"],
        "pickup_gain_net_usd": b["pickup_gain_net_usd"],
        "drum2_capture": cfg.token["drum2_capture_of_turned_away"],
        "turned_away_usd": b["turned_away_usd"],
        "drum2_sales_usd": b["drum2_sales_usd"],
        "total_gain_base_usd": b["total_gain_usd"],
        "total_gain_conservative_usd": cases["conservative"]["total_gain_usd"],
        "total_gain_optimistic_usd": cases["optimistic"]["total_gain_usd"],
        "drum_cost_usd": b["drum_cost_usd"],
        "corn_lb_per_token": rows["corn"]["lb_per_token"],
        "beans_lb_per_token": rows["beans"]["lb_per_token"],
        "replay_tokens_issued": r["tokens_issued"],
        "replay_min_coverage": r["min_coverage_ratio"],
        "replay_family_drum_lb_min": r["family_drum_lb_min"],
    }


def key_results_markdown(k: Mapping[str, Any]) -> str:
    return "\n".join([
        "| Result (normal year, base case) | Value | Source |",
        "|---|---|---|",
        f"| Tokens issued per year | {num(k['tokens_issued'])} ({num(k['reward_tokens'])} on-time reward + {num(k['pickup_tokens'])} pickup) | deck |",
        f"| Tokens as a share of sales | {pct(k['token_share_of_sales'], 1)} of {usd(k['sales_usd'])} (cap {pct(k['cap_share_of_sales'])} = {num(k['cap_tokens'])} tokens) | Exhibit A, deck |",
        f"| Credit no longer lost | {usd(k['credit_usd'])} x ({pct(k['unpaid_share_today'])} - {pct(k['unpaid_share_with_libreta'])}) = {usd(k['credit_recovered_usd'])} | Exhibit A, deck |",
        f"| Record gain net of reward tokens | {usd(k['record_gain_net_usd'])} | deck |",
        f"| Pickup rides gain net of token cost | {usd(k['pickup_gain_net_usd'])} ({usd(k['pickup_today_usd'])} - {usd(k['pickup_cash_usd'])} cash - {num(k['pickup_tokens'])} x $1 x {pct(k['token_cost_share'])}) | case cash costs, deck |",
        f"| Drum 2 pre-harvest sales | {pct(k['drum2_capture'])} x {usd(k['turned_away_usd'])} turned away = {usd(k['drum2_sales_usd'])} | Exhibit D, deck |",
        f"| Total of the three gains | {usd(k['total_gain_base_usd'])} (conservative {usd(k['total_gain_conservative_usd'])}, optimistic {usd(k['total_gain_optimistic_usd'])}); drums cost {usd(k['drum_cost_usd'])} once | Exhibit E, deck |",
        f"| Corn repaid in kind | {num(k['corn_lb_per_token'], 2)} lb = 1 token | Exhibit B ($0.30/lb) |",
        f"| Beans repaid in kind | {num(k['beans_lb_per_token'], 2)} lb = 1 token | Exhibit B ($1.00/lb) |",
        f"| Monthly replay (steady state) | {num(k['replay_tokens_issued'])} tokens issued; lowest drum-2 coverage {num(k['replay_min_coverage'], 2)} (rule: never below 1.00); drum 1 stays at {num(k['replay_family_drum_lb_min'])} lb | ledger replay |",
    ])


def build(cfg: Config, out_dir: Path, charts: bool = True) -> list[Path]:
    """Generate every output file. Returns the paths written."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def text(name: str, body: str) -> None:
        path = out_dir / name
        path.write_text(body.rstrip() + "\n", encoding="utf-8")
        written.append(path)

    def table(name: str, rows: Iterable[Mapping[str, Any]]) -> None:
        path = out_dir / name
        write_csv(path, rows)
        written.append(path)

    cases = all_cases(cfg)
    text("annual_model.md", "# Annual model: normal year, three cases\n\n" + cases_markdown(cases))
    table("annual_model.csv", [dict(v) for v in cases.values()])

    lock = lockin.lock_in_table(cfg)
    text("lock_in_table.md", "# Lock-in: what one token is worth, and where\n\n" + lockin.to_markdown(lock))
    table("lock_in_table.csv", lockin.to_csv_rows(lock))

    text("token_table.md", "# Tokens per lb of corn and beans\n\n" + token_table(cfg)
         + "\n\nRepaying credit in crops credits tokens against the debt; the grain goes into drum 2. "
         "Spending tokens takes the same weight back out of drum 2.")
    table("token_table.csv", token_rows(cfg))

    years = replay(cfg, years=REPORT_YEAR)
    text("monthly_replay.md", "# Monthly replay through the Libreta rules\n\n" + replay_markdown(years))
    table("monthly_replay.csv", [asdict(m) for r in years for m in r.months])

    keys = key_results(cfg, cases, years)
    text("key_results.md", "# Key results\n\n" + key_results_markdown(keys))
    table("key_results.csv", [{"metric": k, "value": v} for k, v in keys.items()])

    if charts:
        from . import charts as charts_mod
        written += charts_mod.render_all(cases, years, out_dir / "charts")
    return written
