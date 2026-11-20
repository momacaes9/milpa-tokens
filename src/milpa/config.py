"""Load and validate ``config/tierra_viva.json`` and turn it into ledger rules."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .ledger import GRAINS, MONTHS, Rules

#: Default config shipped with the repo.
DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "tierra_viva.json"

MONTH_TYPES = ("pre_harvest", "typical", "harvest", "storm")
YEAR_TYPES = ("normal", "bad")
CASES = ("base", "conservative", "optimistic")


class ConfigError(ValueError):
    """The config file is missing a value or contradicts the case."""


@dataclass(frozen=True)
class Config:
    """A validated, read-only view over the JSON config."""

    raw: Mapping[str, Any]

    @property
    def case(self) -> Mapping[str, Any]:
        return self.raw["case"]

    @property
    def token(self) -> Mapping[str, Any]:
        return self.raw["token"]

    @property
    def calendar(self) -> Mapping[str, Any]:
        return self.raw["calendar"]

    def price(self, item: str) -> float:
        """Ernestine's selling price for ``item`` (USD per lb or each), Exhibit B."""
        return float(self.case["products"][item]["price_usd"])

    def grain_prices(self) -> dict[str, float]:
        return {item: self.price(item) for item in GRAINS}

    @property
    def fx(self) -> float:
        """Belize dollars per US dollar (fixed at 2 by the case)."""
        return float(self.case["fx_bzd_per_usd"])

    def year(self, year: str) -> Mapping[str, Any]:
        if year not in YEAR_TYPES:
            raise ConfigError(f"year must be one of {YEAR_TYPES}, not {year!r}")
        return self.case["years"][year]

    def months_in_order(self) -> list[str]:
        """The twelve calendar months starting at ``calendar.start_month``."""
        start = MONTHS.index(self.calendar["start_month"])
        return [MONTHS[(start + i) % 12] for i in range(12)]

    def month_type(self, year: str, month: str) -> str:
        return self.calendar[year][month]

    def months_of_type(self, year: str, kind: str) -> list[str]:
        return [m for m in self.months_in_order() if self.month_type(year, m) == kind]

    def redeem_months(self, year: str = "normal") -> frozenset[str]:
        months: set[str] = set()
        for kind in self.token["redeem_month_types"]:
            months.update(self.months_of_type(year, kind))
        return frozenset(months)

    def rules(self, year: str = "normal") -> Rules:
        """Ledger rules for a year type."""
        t = self.token
        return Rules(
            prices_usd=self.grain_prices(),
            token_value_usd=float(t["face_value_usd"]),
            reward_share=float(t["earn"]["on_time_cash_reward_share"]),
            on_time_days=int(t["earn"]["on_time_days"]),
            redeem_months=self.redeem_months(year),
            drum2_capacity_lb=float(self.case["drums"]["capacity_lb"]) * int(t["drums"]["sale"]),
        )

    def with_overrides(self, updates: Mapping[str, Any]) -> Config:
        """Return a copy with dotted-path values replaced, e.g. ``{"token.cap_share_of_sales": 0.05}``."""
        raw = copy.deepcopy(dict(self.raw))
        for path, value in updates.items():
            node = raw
            keys = path.split(".")
            for key in keys[:-1]:
                if key not in node:
                    raise ConfigError(f"unknown config path {path!r}")
                node = node[key]
            if keys[-1] not in node:
                raise ConfigError(f"unknown config path {path!r}")
            node[keys[-1]] = value
        return validate(raw)


def _close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


def validate(raw: Mapping[str, Any]) -> Config:
    """Check the config against the case's own arithmetic and the token rules.

    Raises:
        ConfigError: if a key is missing, a case total does not reconcile, or the
            token block breaks a rule of the final model.
    """
    try:
        case = raw["case"]
        years = case["years"]
        calendar = raw["calendar"]
        token = raw["token"]
    except KeyError as exc:  # pragma: no cover - message path
        raise ConfigError(f"missing config section: {exc}") from exc

    if case["fx_bzd_per_usd"] != 2.0:
        raise ConfigError("the case fixes BZ$2 = US$1")
    for year in YEAR_TYPES:
        spec = years[year]
        types = spec["month_types"]
        months = sum(t["months"] for t in types.values())
        if months != 12:
            raise ConfigError(f"{year} year has {months} months, expected 12")
        sales = sum(t["months"] * t["sales_per_month"] for t in types.values())
        if sales != spec["total_sales_usd"]:
            raise ConfigError(f"{year} sales {sales} != case total {spec['total_sales_usd']}")
        unpaid = spec["credit_usd"] * spec["unpaid_share_of_credit"]
        if not _close(unpaid, spec["unpaid_usd"], 0.6):
            raise ConfigError(f"{year} unpaid credit does not reconcile")
        cash = spec["total_sales_usd"] - unpaid
        if not _close(cash, spec["cash_collected_usd"], 0.6):
            raise ConfigError(f"{year} cash collected does not reconcile")
        costs = sum(case["cash_costs_usd"].values())
        if not _close(cash - costs, spec["net_cash_income_usd"], 0.6):
            raise ConfigError(f"{year} net cash income does not reconcile")
        cal = calendar[year]
        if sorted(cal) != sorted(MONTHS):
            raise ConfigError(f"calendar.{year} must name all twelve months")
        for kind, t in types.items():
            n = sum(1 for v in cal.values() if v == kind)
            if n != t["months"]:
                raise ConfigError(f"calendar.{year} has {n} {kind} months, case says {t['months']}")
    normal = years["normal"]["month_types"]
    credit = sum(t["months"] * t["sales_per_month"] * t["credit_share"] for t in normal.values())
    if not _close(credit, years["normal"]["credit_usd"], 0.6):
        raise ConfigError("normal-year credit does not reconcile with Exhibit A month types")
    if calendar["start_month"] not in MONTHS:
        raise ConfigError("calendar.start_month must be a month name")

    # ---- token block: the final model's invariants
    if token["face_value_usd"] * case["fx_bzd_per_usd"] != token["face_value_bzd"]:
        raise ConfigError("1 token must be BZ$2 = US$1")
    if sorted(token["redeemable_items"]) != sorted(GRAINS):
        raise ConfigError("tokens are spent on corn and beans only")
    if sorted(token["earn"]["crop_repayment"]["items"]) != sorted(GRAINS):
        raise ConfigError("crop repayments are in corn and beans only")
    if set(token["earn"]) != {"crop_repayment", "on_time_cash_reward_share", "on_time_days", "pickup"}:
        raise ConfigError("tokens are earned only by crop repayment, on-time cash reward and pickup fare")
    for kind in token["redeem_month_types"]:
        if kind not in MONTH_TYPES:
            raise ConfigError(f"unknown month type {kind!r}")
    for key in ("cost_share_of_face", "unpaid_share_with_libreta"):
        if set(token[key]) != set(CASES):
            raise ConfigError(f"token.{key} needs base, conservative and optimistic")
        for v in token[key].values():
            if not 0 <= v <= 1:
                raise ConfigError(f"token.{key} values must be shares in [0, 1]")
    if not 0 < token["cap_share_of_sales"] <= 1:
        raise ConfigError("token.cap_share_of_sales must be in (0, 1]")
    drums = token["drums"]
    if drums["family"] + drums["sale"] != drums["total"] or drums["family"] < 1 or drums["sale"] < 1:
        raise ConfigError("need one family drum and at least one sale drum")
    capacity = case["drums"]["capacity_lb"] * drums["sale"]
    for key in ("drum2_fill_lb", "crop_repayment_lb"):
        if set(token[key]) - set(GRAINS):
            raise ConfigError(f"token.{key} may hold corn and beans only")
    if sum(token["drum2_fill_lb"].values()) > capacity:
        raise ConfigError("drum 2 fill exceeds drum capacity (Exhibit E)")
    for item, lb in token["crop_repayment_lb"].items():
        if lb > token["drum2_fill_lb"].get(item, 0):
            raise ConfigError("crop repayments go into drum 2, so they cannot exceed its fill")
    return Config(raw)


def load(path: str | Path | None = None) -> Config:
    """Read and validate a config file (the repo default when ``path`` is None)."""
    path = Path(path) if path else DEFAULT_CONFIG
    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    return validate(raw)
