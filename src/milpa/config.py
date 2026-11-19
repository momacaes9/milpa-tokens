"""Load and validate ``config/tierra_viva.json`` and turn it into ledger rules."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .ledger import MONTHS, Rules

#: Default config shipped with the repo.
DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "tierra_viva.json"

MONTH_TYPES = ("pre_harvest", "typical", "harvest", "storm")
YEAR_TYPES = ("normal", "bad")
REDEEMABLE = ("corn", "beans", "seed_corn", "plantain", "fresh_veg")


class ConfigError(ValueError):
    """The config file is missing a value or contradicts the case."""


@dataclass(frozen=True)
class Config:
    """A validated, read-only view over the JSON config."""

    raw: Mapping[str, Any]

    # ----------------------------------------------------------- case values
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
        """Ernestine's selling price for ``item`` (USD per lb or each)."""
        return float(self.case["products"][item]["price_usd"])

    def prices(self) -> dict[str, float]:
        return {item: self.price(item) for item in REDEEMABLE}

    @property
    def fx(self) -> float:
        """Belize dollars per US dollar (fixed at 2 by the case)."""
        return float(self.case["fx_bzd_per_usd"])

    def wage_usd_per_hour(self) -> float:
        """Cash value of one token's hour: the Belize minimum wage, in USD."""
        return float(self.token["wage_bzd_per_hour"]) / self.fx

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

    def issue_months(self, year: str) -> frozenset[str]:
        """Work months: planting months plus the harvest months of this year type."""
        return frozenset(self.calendar["planting_months"]) | frozenset(self.months_of_type(year, "harvest"))

    def redeem_months(self, year: str) -> dict[str, frozenset[str]]:
        """Resolve each item's window names (month types or calendar keys) to months."""
        out: dict[str, frozenset[str]] = {}
        for item, windows in self.token["redeem_windows"].items():
            months: set[str] = set()
            for window in windows:
                if window in MONTH_TYPES:
                    months.update(self.months_of_type(year, window))
                elif window in self.calendar:
                    months.update(self.calendar[window])
                else:
                    raise ConfigError(f"unknown redeem window {window!r} for {item}")
            out[item] = frozenset(months)
        return out

    def rules(self, year: str, **overrides: Any) -> Rules:
        """Ledger rules for a year type. ``overrides`` replace token settings."""
        token = {**self.token, **overrides}
        return Rules(
            in_kind_corn_lb=float(token["in_kind_corn_lb"]),
            prices_usd=self.prices(),
            max_tokens_per_household=int(token["max_tokens_per_household"]),
            expiry_months=int(token["expiry_months"]),
            min_coverage=float(token["min_coverage"]),
            issue_months=self.issue_months(year),
            redeem_months=self.redeem_months(year),
        )

    def with_overrides(self, updates: Mapping[str, Any]) -> Config:
        """Return a copy with dotted-path values replaced, e.g. ``{"token.in_kind_corn_lb": 9}``."""
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
    """Check the config against the case's own arithmetic and return a :class:`Config`.

    Raises:
        ConfigError: if a key is missing or a case total does not reconcile.
    """
    try:
        case = raw["case"]
        years = case["years"]
        calendar = raw["calendar"]
        raw["token"]
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
    for item in REDEEMABLE:
        if item not in case["products"]:
            raise ConfigError(f"no price for redeemable item {item!r}")
    if calendar["start_month"] not in MONTHS:
        raise ConfigError("calendar.start_month must be a month name")
    return Config(raw)


def load(path: str | Path | None = None) -> Config:
    """Read and validate a config file (the repo default when ``path`` is None)."""
    path = Path(path) if path else DEFAULT_CONFIG
    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    return validate(raw)
