"""Write every table the pitch deck needs to ``outputs/`` (Markdown + CSV)."""

from __future__ import annotations

import csv
import math
from dataclasses import asdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import lockin, sensitivity
from .tokentable import token_table
from .config import Config
from .simulate import SCENARIOS, YearResult, monte_carlo, run_all, simulate_sequence

SCENARIO_LABELS = {"today": "Today (case)", "drums": "Drums only", "tokens": "Drums + Milpa Tokens"}


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
        return "fully backed"
    q = Decimal(1).scaleb(-digits)
    return f"{Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP):,}"


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


SUMMARY_ROWS = (
    ("Sales", "sales_usd", "usd"),
    ("Sold on credit", "credit_usd", "usd"),
    ("Cash collected", "cash_collected_usd", "usd"),
    ("...of which grain sold from sale drums before harvest", "drum_sales_usd", "usd"),
    ("Net cash income (after $460 costs)", "net_cash_income_usd", "usd"),
    ("Drum purchase (one-off, year 1)", "drum_cost_usd", "usd"),
    ("Bad debt recovered as labor (hours)", "bad_debt_recovered_hours", "h"),
    ("Bad debt recovered as labor (US$ at wage)", "bad_debt_recovered_usd", "usd"),
    ("Hours paid in tokens", "token_hours", "h"),
    ("Ernestine's hours saved, whole year", "ernestine_hours_saved_total", "h"),
    ("Ernestine's hours saved, harvest months", "ernestine_hours_saved_harvest", "h"),
    ("Tokens issued", "tokens_issued", "n"),
    ("Tokens redeemed", "tokens_redeemed", "n"),
    ("Tokens expired", "tokens_expired", "n"),
    ("Tokens outstanding at year end (backed)", "tokens_outstanding_end", "n"),
    ("Redeemed in fresh produce that would spoil (US$)", "fresh_redeemed_usd", "usd"),
    ("Redeemed in grain from sale drums (US$)", "grain_redeemed_usd", "usd"),
    ("Lowest coverage ratio (sale drums / tokens out)", "min_coverage_ratio", "ratio"),
    ("Family food in drum, lowest (lb, never touched)", "family_food_lb_min", "h"),
)


def _fmt(value: float, kind: str) -> str:
    if kind == "usd":
        return usd(value)
    if kind == "ratio":
        return "no tokens" if value != value else num(value, 2)
    return num(value, 0 if kind == "n" else 1)


def summary_markdown(results: Mapping[tuple[str, str], YearResult]) -> str:
    out = []
    for year, title in (("normal", "Normal year"), ("bad", "Bad-weather year")):
        out.append(f"### {title}\n")
        out.append("| | " + " | ".join(SCENARIO_LABELS[s] for s in SCENARIOS) + " |")
        out.append("|---|" + "---:|" * len(SCENARIOS))
        for label, key, kind in SUMMARY_ROWS:
            cells = [_fmt(results[(s, year)].totals[key], kind) for s in SCENARIOS]
            out.append(f"| {label} | " + " | ".join(cells) + " |")
        out.append("")
    return "\n".join(out)


def summary_rows(results: Mapping[tuple[str, str], YearResult]) -> list[dict[str, Any]]:
    return [{"year": y, "scenario": s, **r.totals} for (s, y), r in results.items()]


def monthly_rows(results: Mapping[tuple[str, str], YearResult]) -> list[dict[str, Any]]:
    rows = []
    for (s, y), r in results.items():
        for m in r.months:
            rows.append({"year": y, "scenario": s, **asdict(m)})
    return rows


def monte_carlo_markdown(mc: Mapping[str, Mapping[str, Mapping[str, float]]], runs: int, seed: int) -> str:
    labels = (
        ("unpaid_share_of_credit", "Unpaid share of credit (drawn)", "pct"),
        ("today_cash_collected_usd", "Cash collected, today", "usd"),
        ("cash_collected_usd", "Cash collected, drums + tokens", "usd"),
        ("bad_debt_recovered_hours", "Bad debt recovered as labor (h)", "h"),
        ("helper_hours_total", "Total helper hours", "h"),
        ("ernestine_hours_saved_harvest", "Ernestine's hours saved at harvest", "h"),
        ("tokens_expired", "Tokens expired within the year (lapse needs 12 months; see stress test)", "h"),
        ("min_coverage_ratio", "Lowest coverage ratio", "ratio"),
    )
    out = [f"Monte Carlo: {runs:,} runs, fixed seed {seed}. P10 / P50 / P90.\n"]
    for year, title in (("normal", "Normal year"), ("bad", "Bad-weather year")):
        out.append(f"### {title}\n")
        out.append("| Metric | P10 | P50 | P90 |\n|---|---:|---:|---:|")
        for key, label, kind in labels:
            s = mc[year][key]
            if kind == "pct":
                cells = [f"{s[q]:.0%}" for q in ("p10", "p50", "p90")]
            else:
                cells = [_fmt(s[q], kind if kind != "h" else "h") for q in ("p10", "p50", "p90")]
            out.append(f"| {label} | " + " | ".join(cells) + " |")
        out.append("")
    return "\n".join(out)


def stress_markdown(seq: Mapping[str, list[YearResult]]) -> str:
    """Two consecutive years (normal harvest, then a storm year) on one notebook."""
    rows = (
        ("Cash collected", "cash_collected_usd", "usd"),
        ("Helper hours (tokens + debt paid in hands)", "helper_hours_total", "h"),
        ("Tokens issued", "tokens_issued", "n"),
        ("Tokens redeemed", "tokens_redeemed", "n"),
        ("Tokens expired", "tokens_expired", "n"),
        ("Tokens outstanding at year end (backed)", "tokens_outstanding_end", "n"),
        ("Lowest coverage ratio", "min_coverage_ratio", "ratio"),
        ("Lowest sale-drum stock (lb)", "sale_drum_lb_min", "h"),
        ("Family food in drum, lowest (lb)", "family_food_lb_min", "h"),
    )
    years = [r.year for r in seq["tokens"]]
    head = " | ".join(f"Year {i + 1} ({y})" for i, y in enumerate(years))
    out = [f"| Drums + Milpa Tokens | {head} |", "|---|" + "---:|" * len(years)]
    for label, key, kind in rows:
        out.append(f"| {label} | " + " | ".join(_fmt(r.totals[key], kind) for r in seq["tokens"]) + " |")
    return "\n".join(out)


def key_results(cfg: Config, results: Mapping[tuple[str, str], YearResult],
                lock_rows: list[lockin.LockInRow],
                seq: Mapping[str, list[YearResult]] | None = None) -> dict[str, Any]:
    """The handful of numbers the README and the pitch slide quote."""
    n_tok = results[("tokens", "normal")].totals
    b_tok = results[("tokens", "bad")].totals
    n_today = results[("today", "normal")].totals
    corn = next(r for r in lock_rows if r.item == "corn")
    plantain = next(r for r in lock_rows if r.item == "plantain")
    nine = lockin.lock_in_summary(cfg, in_kind_corn_lb=9)
    six = lockin.lock_in_summary(cfg, wage_bzd_per_hour=6.0)
    return {
        "token_premium_vs_cash_wage": corn.advantage_vs_cash_at_tierra_viva,
        "corn_lb_per_token": corn.token_qty,
        "corn_lb_per_wage_hour": corn.wage_qty_at_tierra_viva,
        "plantain_token_vs_truck_best_price": plantain.advantage_vs_truck_worst_case,
        "premium_at_9lb": nine["token_premium_vs_cash_wage"],
        "truck_at_9lb": nine["worst_truck_advantage"],
        "premium_at_bzd6": six["token_premium_vs_cash_wage"],
        "truck_at_bzd6": six["worst_truck_advantage"],
        "normal_helper_hours": n_tok["helper_hours_total"],
        "normal_harvest_hours": n_tok["ernestine_hours_saved_harvest"],
        "normal_debt_hours": n_tok["bad_debt_recovered_hours"],
        "normal_debt_usd": n_tok["bad_debt_recovered_usd"],
        "bad_helper_hours": b_tok["helper_hours_total"],
        "bad_debt_hours": b_tok["bad_debt_recovered_hours"],
        "normal_unpaid_usd": n_today["unpaid_credit_usd"],
        "normal_tokens_issued": n_tok["tokens_issued"],
        "normal_tokens_redeemed": n_tok["tokens_redeemed"],
        "normal_fresh_redeemed_usd": n_tok["fresh_redeemed_usd"],
        "min_coverage_normal": n_tok["min_coverage_ratio"],
        "min_coverage_bad": b_tok["min_coverage_ratio"],
        "in_kind_lb_to_keep_premium_at_bzd6": corn.token_qty * 6.0 / cfg.token["wage_bzd_per_hour"],
        "stress_tokens_expired": sum(r.totals["tokens_expired"] for r in seq["tokens"]) if seq else float("nan"),
        "stress_min_coverage": min(r.totals["min_coverage_ratio"] for r in seq["tokens"]) if seq else float("nan"),
    }


def key_results_markdown(k: Mapping[str, Any]) -> str:
    return "\n".join([
        "| Result | Value |",
        "|---|---|",
        f"| Food one token buys vs one hour's cash wage at Tierra Viva | {k['corn_lb_per_token']:.0f} lb vs {k['corn_lb_per_wage_hour']:.1f} lb corn ({k['token_premium_vs_cash_wage']:+.0%}) |",
        f"| Token vs produce truck's best plantain price | {k['plantain_token_vs_truck_best_price']:+.0%} |",
        f"| Lock-in if the in-kind rate drops to 9 lb | {k['premium_at_9lb']:+.0%} vs cash; {k['truck_at_9lb']:+.0%} vs truck |",
        f"| Lock-in if the wage peg rises to BZ$6 | {k['premium_at_bzd6']:+.0%} vs cash; {k['truck_at_bzd6']:+.0%} vs truck |",
        f"| Helper hours a normal year (tokens + debt paid in hands) | {num(k['normal_helper_hours'], 0)} h, {num(k['normal_harvest_hours'], 0)} h of them at harvest |",
        f"| Never-repaid credit recovered as labor, normal year | {num(k['normal_debt_hours'], 1)} h = {usd(k['normal_debt_usd'])} of the {usd(k['normal_unpaid_usd'])} lost today |",
        f"| Helper hours, bad-weather year | {num(k['bad_helper_hours'], 0)} h ({num(k['bad_debt_hours'], 1)} h from old debt) |",
        f"| Tokens issued / redeemed, normal year | {k['normal_tokens_issued']} / {k['normal_tokens_redeemed']} (rest outstanding, backed) |",
        f"| Value redeemed in produce that would have spoiled | {usd(k['normal_fresh_redeemed_usd'])} |",
        f"| Lowest coverage of tokens by sale drums | {num(k['min_coverage_normal'], 2)} normal / {num(k['min_coverage_bad'], 2)} bad / {num(k['stress_min_coverage'], 2)} normal-then-storm (rule: never below 1.00) |",
        f"| Tokens expired over a normal year followed by a storm year | {num(k['stress_tokens_expired'], 0)} |",
        f"| In-kind rate needed to keep the same premium if the wage rises to BZ$6 | {k['in_kind_lb_to_keep_premium_at_bzd6']:.0f} lb corn per token |",
    ])


def build(cfg: Config, out_dir: Path, charts: bool = True, mc_runs: int | None = None) -> list[Path]:
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

    wage = cfg.token["wage_bzd_per_hour"]
    lock_rows = lockin.lock_in_table(cfg)
    text("lock_in_table.md", "# Lock-in: what one hour of work buys\n\n" + lockin.to_markdown(lock_rows, wage, cfg.fx))
    table("lock_in_table.csv", lockin.to_csv_rows(lock_rows))

    text("token_table.md", "# What one Milpa Token redeems for\n\n" + token_table(cfg, "normal"))

    results = run_all(cfg)
    text("simulation_summary.md", "# Season simulation\n\n" + summary_markdown(results))
    table("simulation_summary.csv", summary_rows(results))
    table("simulation_monthly.csv", monthly_rows(results))

    seq = {s: simulate_sequence(cfg, ("normal", "bad"), s) for s in SCENARIOS}
    text("stress_normal_then_storm.md",
         "# Stress test: a normal year, then a storm year, on one notebook\n\n"
         "Tokens earned at the normal harvest must be honored, or expire under the rules, "
         "during the storm year that follows.\n\n" + stress_markdown(seq))
    table("stress_normal_then_storm_monthly.csv", [
        {"year_number": n + 1, "year": r.year, "scenario": s, **asdict(m)}
        for s, rs in seq.items() for n, r in enumerate(rs) for m in r.months
    ])

    mc_cfg = cfg.raw["simulation"]["monte_carlo"]
    runs = int(mc_cfg["runs"] if mc_runs is None else mc_runs)
    mc = {y: monte_carlo(cfg, y, runs=runs) for y in ("normal", "bad")}
    text("monte_carlo.md", "# Repayment uncertainty\n\n" + monte_carlo_markdown(mc, runs, mc_cfg["seed"]))
    table("monte_carlo.csv", [
        {"year": y, "metric": k, **v} for y, d in mc.items() for k, v in d.items()
    ])

    sens = sensitivity.sensitivity_table(cfg)
    text("sensitivity.md", "# Sensitivity\n\n" + sensitivity.to_markdown(sens))
    table("sensitivity.csv", sens)

    keys = key_results(cfg, results, lock_rows, seq)
    text("key_results.md", "# Key results\n\n" + key_results_markdown(keys))
    table("key_results.csv", [{"metric": k, "value": v} for k, v in keys.items()])

    if charts:
        from . import charts as charts_mod
        written += charts_mod.render_all(cfg, results, lock_rows, sens, out_dir / "charts", seq)
    return written
