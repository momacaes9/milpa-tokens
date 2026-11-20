"""PNG charts for the pitch deck. Needs the optional ``matplotlib`` dependency.

Palette: categorical slots 1-3 of a colorblind-validated reference palette
(blue, orange, aqua) on a light surface; text stays in neutral ink.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .config import CASES
from .simulate import YearReplay

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
        "legend.frameon": False, "lines.linewidth": 2, "axes.axisbelow": True,
    })
    return plt


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight", metadata={"Software": None})
    import matplotlib.pyplot as plt

    plt.close(fig)
    return path


def backing_chart(years: list[YearReplay], path: Path) -> Path:
    """Drum-2 value vs tokens outstanding (US$), month by month."""
    plt = _setup()
    rows = [m for r in years for m in r.months]
    xs = list(range(len(rows)))
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(xs, [m.drum2_value_usd for m in rows], color=BLUE, marker="o", markersize=4,
            label=r"Corn + beans in drum 2 (US\$)")
    ax.plot(xs, [float(m.tokens_outstanding) for m in rows], color=ORANGE, marker="o", markersize=4,
            label=r"Tokens outstanding (US\$, 1 token = \$1)")
    for i, m in enumerate(rows):
        if m.month_type == "pre_harvest":
            ax.axvspan(i - 0.5, i + 0.5, color=AQUA, alpha=0.10, linewidth=0)
    ax.text(rows.index(next(m for m in rows if m.month_type == "pre_harvest")) - 0.4,
            ax.get_ylim()[1] * 0.92, "pre-harvest gap", color=INK_2, fontsize=9)
    ax.set_xticks(xs, [m.month for m in rows], fontsize=8)
    ax.set_ylim(bottom=0)
    ax.set_ylabel("US$")
    ax.set_title("Tokens out never exceed the grain in drum 2 (two normal years)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2, fontsize=9)
    return _save(fig, path)


def gains_chart(cases: Mapping[str, Mapping[str, Any]], path: Path) -> Path:
    """Annual gain by source, three cases."""
    plt = _setup()
    parts = (("record_gain_net_usd", "Libreta: credit recovered, net of reward tokens", BLUE),
             ("pickup_gain_net_usd", "Pickup rides, net of token cost", ORANGE),
             ("drum2_sales_usd", "Drum 2 pre-harvest sales", AQUA))
    fig, ax = plt.subplots(figsize=(8, 4))
    xs = list(range(len(CASES)))
    bottom = [0.0] * len(CASES)
    for key, label, color in parts:
        vals = [cases[c][key] for c in CASES]
        ax.bar(xs, vals, bottom=bottom, color=color, width=0.55, label=label)
        for x, v, b in zip(xs, vals, bottom):
            ax.text(x, b + v / 2, f"${v:,.0f}", ha="center", va="center", fontsize=9, color="white")
        bottom = [b + v for b, v in zip(bottom, vals)]
    for x, total in zip(xs, bottom):
        ax.text(x, total + 6, f"${total:,.0f}", ha="center", fontsize=10, color=INK, fontweight="bold")
    ax.set_xticks(xs, [c.capitalize() for c in CASES])
    ax.set_ylim(0, max(bottom) * 1.35)
    ax.set_ylabel("US$ per normal year")
    ax.grid(axis="x", visible=False)
    ax.set_title("Annual gain from the token model")
    ax.legend(loc="upper left", fontsize=8)
    return _save(fig, path)


def token_flow_chart(year: YearReplay, path: Path) -> Path:
    """Tokens issued (by source) and spent, by month, in the steady-state year."""
    plt = _setup()
    rows = year.months
    xs = list(range(len(rows)))
    w = 0.38
    fig, ax = plt.subplots(figsize=(9, 4))
    reward = [m.reward_tokens_issued for m in rows]
    pickup = [m.pickup_tokens_issued for m in rows]
    ax.bar([x - w / 2 for x in xs], reward, width=w - 0.04, color=BLUE, label="Issued: 5% on-time reward")
    ax.bar([x - w / 2 for x in xs], pickup, bottom=reward, width=w - 0.04, color=ORANGE,
           label="Issued: half pickup fare")
    ax.bar([x + w / 2 for x in xs], [m.tokens_redeemed for m in rows], width=w - 0.04, color=AQUA,
           label="Spent on corn and beans")
    ax.set_xticks(xs, [m.month for m in rows])
    ax.set_ylabel(r"Tokens (1 token = \$1)")
    ax.set_title("Tokens go out at harvest and through the year, come back in the pre-harvest gap")
    ax.legend(loc="upper left", fontsize=9)
    return _save(fig, path)


def render_all(cases: Mapping[str, Mapping[str, Any]], years: list[YearReplay], out_dir: Path) -> list[Path]:
    """Render every chart into ``out_dir``."""
    out_dir = Path(out_dir)
    return [
        backing_chart(years, out_dir / "drum2_backing.png"),
        gains_chart(cases, out_dir / "annual_gains.png"),
        token_flow_chart(years[-1], out_dir / "token_flow.png"),
    ]
