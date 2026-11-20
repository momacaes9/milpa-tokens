"""Lock-in: a token is worth $1 at Tierra Viva and nothing anywhere else.

1 token = BZ$2 = US$1 of Ernestine's corn or beans. It is only worth something
at her market table, so a household that earns one comes back to her:

* at Tierra Viva, in the pre-harvest gap: $1 of corn (3.33 lb at $0.30/lb) or
  beans (1 lb at $1.00/lb), Exhibit B, from drum 2, when she now turns away
  8-10 buyers a week (Exhibit D);
* at the produce truck: $0. The truck sells plantains, tomatoes and onions, not
  corn or beans, and does not accept tokens (case, "Competition");
* as cash: $0. No cash-out;
* passed to a neighbor: $0. No transfers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .config import Config


@dataclass(frozen=True)
class LockInRow:
    where: str
    value_usd: float
    buys: str
    why: str


def lock_in_table(cfg: Config) -> list[LockInRow]:
    face = float(cfg.token["face_value_usd"])
    prices = cfg.grain_prices()
    truck = cfg.case["truck"]
    if truck["accepts_tokens"]:  # pragma: no cover - the case says it does not
        raise ValueError("the case says the produce truck does not accept tokens")
    sold = ", ".join(truck["sells"])
    corn_lb = face / prices["corn"]
    beans_lb = face / prices["beans"]
    return [
        LockInRow("Tierra Viva market table: corn", face, f"{corn_lb:.2f} lb corn from drum 2",
                  f"case price ${prices['corn']:.2f}/lb (Exhibit B); pre-harvest gap, when 8-10 buyers a week are turned away (Exhibit D)"),
        LockInRow("Tierra Viva market table: beans", face, f"{beans_lb:.2f} lb beans from drum 2",
                  f"case price ${prices['beans']:.2f}/lb (Exhibit B); same window"),
        LockInRow("Produce truck", 0.0, "nothing",
                  f"truck sells {sold}, no corn or beans, and does not accept tokens (case, Competition)"),
        LockInRow("As cash", 0.0, "nothing", "no cash-out: a store voucher, not money"),
        LockInRow("Passed to a neighbor", 0.0, "nothing", "no transfers: each token is logged to one holder in the Libreta"),
    ]


def to_markdown(rows: list[LockInRow]) -> str:
    lines = ["| Where the token is used | Value of 1 token | Buys | Why |", "|---|---:|---|---|"]
    for r in rows:
        lines.append(f"| {r.where} | ${r.value_usd:.2f} | {r.buys} | {r.why} |")
    return "\n".join(lines)


def to_csv_rows(rows: list[LockInRow]) -> list[dict[str, object]]:
    return [asdict(r) for r in rows]
