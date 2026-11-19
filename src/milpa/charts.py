"""PNG charts for the pitch deck. Needs the optional ``matplotlib`` dependency.

Palette: categorical slots 1-3 of a colorblind-validated reference palette
(blue, orange, aqua) on a light surface; text stays in neutral ink.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .config import Config
from .lockin import LockInRow
from .simulate import YearResult

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"


def _setup():
    try:
        import matplotlib
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "charts need matplotlib: pip install 'milpa-tokens[charts]' (or run build-outputs --no-charts)"
        ) from exc
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "text.color": INK,
        "xtick.color": INK_2, "ytick.color": INK_2, "axes.grid": True, "grid.color": GRID,
        "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
        "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "legend.frameon": False, "lines.linewidth": 2, "svg.hashsalt": "milpa", "axes.axisbelow": True,
    })
    return plt


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight", metadata={"Software": None})
    import matplotlib.pyplot as plt

    plt.close(fig)
    return path


def coverage_chart(seq: Mapping[str, list[YearResult]], path: Path) -> Path:
    """Coverage over a normal year followed by a storm year (24 months, one notebook)."""
    plt = _setup()
    fig, ax = plt.subplots(figsize=(10, 4))
    rows = [m for r in seq["tokens"] for m in r.months]
    xs = list(range(len(rows)))
    ys = [float("nan") if r.coverage_ratio is None else r.coverage_ratio for r in rows]
    ax.plot(xs, ys, color=BLUE, marker="o", markersize=5, label="Drums + Milpa Tokens")
    ax.axhline(1.0, color=INK_2, linestyle="--", linewidth=1)
    ax.text(0, 1.12, "rule floor: fully backed (1.0)", ha="left", color=INK_2, fontsize=9)
    ax.text(0, 0.45, "no line = no tokens out yet", ha="left", color=INK_2, fontsize=8)
    ax.axvspan(11.5, len(rows) - 0.5, color=ORANGE, alpha=0.08, linewidth=0)
    ax.text(12, max(y for y in ys if y == y) * 0.95, "storm year", color=INK_2, fontsize=9)
    ax.set_xticks(xs, [r.month for r in rows], fontsize=8)
    ax.set_ylim(bottom=0)
    ax.set_ylabel("Sale-drum value / value of tokens out")
    ax.set_title("Every token out stays backed by grain, through a normal year and a storm year")
    return _save(fig, path)


def drums_chart(results: Mapping[tuple[str, str], YearResult], path: Path) -> Path:
    plt = _setup()
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, year, title in zip(axes, ("normal", "bad"), ("Normal year", "Bad-weather year")):
        fam = results[("tokens", year)].months
        xs = list(range(len(fam)))
        ax.plot(xs, [r.family_food_lb for r in fam], color=AQUA, label="Family drum (never used for tokens)")
        ax.plot(xs, [r.sale_drum_lb for r in results[("drums", year)].months], color=BLUE, label="Sale drum: drums only")
        ax.plot(xs, [r.sale_drum_lb for r in fam], color=ORANGE, label="Sale drum: drums + tokens")
        ax.set_xticks(range(12), [r.month for r in fam], fontsize=8)
        ax.set_title(title)
    axes[0].set_ylabel("lb of dried corn and beans")
    axes[0].legend(loc="lower left", fontsize=8)
    fig.suptitle("Food in drums by month", x=0.01, y=1.03, ha="left", fontweight="bold")
    return _save(fig, path)


def tokens_chart(results: Mapping[tuple[str, str], YearResult], path: Path) -> Path:
    plt = _setup()
    fig, ax = plt.subplots(figsize=(8, 4))
    rows = results[("tokens", "normal")].months
    xs = list(range(len(rows)))
    w = 0.38
    ax.bar([x - w / 2 for x in xs], [r.tokens_issued for r in rows], width=w - 0.04, color=BLUE, label="Issued (hours worked)")
    ax.bar([x + w / 2 for x in xs], [r.tokens_redeemed for r in rows], width=w - 0.04, color=ORANGE, label="Redeemed (food handed out)")
    ax.plot(xs, [r.tokens_outstanding for r in rows], color=AQUA, marker="o", markersize=5, label="Outstanding at month end")
    ax.set_xticks(range(12), [r.month for r in rows])
    ax.set_ylabel("Tokens (1 token = 1 hour)")
    ax.set_ylim(0, max(r.tokens_outstanding for r in rows) * 1.45)
    ax.set_title("Normal year: tokens go out at planting and harvest, come back pre-harvest")
    ax.legend(loc="upper left", fontsize=9)
    return _save(fig, path)


def lock_in_chart(rows: list[LockInRow], wage_bzd: float, path: Path) -> Path:
    plt = _setup()
    by = {r.item: r for r in rows}
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6), gridspec_kw={"wspace": 0.12})
    panels = (("corn", "Corn (lb)"), ("plantain", "Plantains (count)"))
    for k, (ax, (item, title)) in enumerate(zip(axes, panels)):
        r = by[item]
        labels = ["Token at Tierra Viva", f"BZ${wage_bzd:.0f} cash at Tierra Viva", "Cash at produce truck"]
        values = [r.token_qty, r.wage_qty_at_tierra_viva, r.wage_qty_at_truck_high or 0.0]
        colors = [BLUE, ORANGE, AQUA]
        ys = range(len(labels))[::-1]
        ax.barh(list(ys), values, color=colors, height=0.6)
        for y, v, lab in zip(ys, values, labels):
            txt = "truck does not sell it" if (lab.startswith("Cash at produce") and v == 0) else f"{v:.1f}"
            ax.text(max(v, 0) + 0.2, y, txt, va="center", color=INK, fontsize=9)
        ax.set_yticks(list(ys), labels if k == 0 else [""] * len(labels))
        ax.set_title(f"What 1 hour of work buys: {title}")
        ax.grid(axis="y", visible=False)
        ax.set_xlim(0, max(values) * 1.35)
    return _save(fig, path)


def cash_hours_chart(results: Mapping[tuple[str, str], YearResult], path: Path) -> Path:
    plt = _setup()
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    scen = (("today", "Today", BLUE), ("drums", "Drums only", ORANGE), ("tokens", "Drums + tokens", AQUA))
    w = 0.26
    for j, (key, label, color) in enumerate(scen):
        cash = [results[(key, y)].totals["cash_collected_usd"] for y in ("normal", "bad")]
        hours = [results[(key, y)].totals["helper_hours_total"] for y in ("normal", "bad")]
        xs = [i + (j - 1) * w for i in range(2)]
        axes[0].bar(xs, cash, width=w - 0.03, color=color, label=label)
        axes[1].bar(xs, hours, width=w - 0.03, color=color, label=label)
        for x, v in zip(xs, cash):
            axes[0].text(x, v + 15, f"${v:,.0f}", ha="center", fontsize=8, color=INK)
        for x, v in zip(xs, hours):
            axes[1].text(x, v + 1.5, f"{v:.0f} h", ha="center", fontsize=8, color=INK)
    for ax in axes:
        ax.set_xticks([0, 1], ["Normal year", "Bad-weather year"])
        ax.grid(axis="x", visible=False)
    axes[0].set_title("Cash collected (US$)")
    axes[1].set_title("Helper hours at planting + harvest")
    axes[0].legend(loc="upper right", fontsize=8)
    return _save(fig, path)


def render_all(cfg: Config, results: Mapping[tuple[str, str], YearResult], lock_rows: list[LockInRow],
               sens: list[dict[str, Any]], out_dir: Path,
               seq: Mapping[str, list[YearResult]]) -> list[Path]:
    """Render every chart into ``out_dir``."""
    out_dir = Path(out_dir)
    return [
        coverage_chart(seq, out_dir / "coverage_over_time.png"),
        drums_chart(results, out_dir / "food_in_drums.png"),
        tokens_chart(results, out_dir / "tokens_flow.png"),
        lock_in_chart(lock_rows, cfg.token["wage_bzd_per_hour"], out_dir / "lock_in.png"),
        cash_hours_chart(results, out_dir / "cash_and_hours.png"),
    ]
