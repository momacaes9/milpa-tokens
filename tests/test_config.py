"""The config must reproduce every case number exactly."""

from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from milpa.cli import main
from milpa.config import ConfigError, load, validate

CFG = load()


class TestCaseNumbers(unittest.TestCase):
    def test_exhibit_a_normal(self):
        y = CFG.year("normal")
        self.assertEqual(y["total_sales_usd"], 1370)
        self.assertEqual(y["credit_usd"], 594)
        self.assertEqual(y["unpaid_usd"], 149)
        self.assertEqual(y["cash_collected_usd"], 1222)
        self.assertEqual(y["net_cash_income_usd"], 762)

    def test_exhibit_a_bad(self):
        y = CFG.year("bad")
        self.assertEqual(y["total_sales_usd"], 900)
        self.assertEqual(y["credit_usd"], 491)
        self.assertEqual(y["unpaid_usd"], 196)
        self.assertEqual(y["cash_collected_usd"], 704)
        self.assertEqual(y["net_cash_income_usd"], 244)

    def test_prices_and_constants(self):
        self.assertEqual(CFG.price("corn"), 0.30)
        self.assertEqual(CFG.price("beans"), 1.00)
        self.assertEqual(CFG.price("seed_corn"), 1.00)
        self.assertEqual(CFG.case["drums"], {"cost_usd_each": 100, "capacity_lb": 250, "neighbors_wanting_storage": 2})
        self.assertEqual(CFG.case["savings_usd"], 350)
        self.assertEqual(CFG.case["fx_bzd_per_usd"], 2.0)
        self.assertEqual(CFG.case["family_size"], 6)


class TestCalendar(unittest.TestCase):
    def test_months_in_order(self):
        months = CFG.months_in_order()
        self.assertEqual(months[0], "Feb")
        self.assertEqual(len(set(months)), 12)

    def test_windows(self):
        self.assertEqual(CFG.months_of_type("normal", "pre_harvest"), ["Jul", "Aug", "Sep"])
        self.assertEqual(CFG.issue_months("normal"), frozenset({"May", "Jun", "Dec", "Nov", "Jan"}))
        rm = CFG.redeem_months("normal")
        self.assertEqual(rm["corn"], frozenset({"Jul", "Aug", "Sep", "Oct"}))
        self.assertEqual(rm["seed_corn"], frozenset({"Apr", "Nov"}))


class TestValidation(unittest.TestCase):
    def broken(self, mutate):
        raw = copy.deepcopy(dict(CFG.raw))
        mutate(raw)
        with self.assertRaises(ConfigError):
            validate(raw)

    def test_rejects_wrong_fx(self):
        self.broken(lambda r: r["case"].__setitem__("fx_bzd_per_usd", 2.5))

    def test_rejects_wrong_sales(self):
        self.broken(lambda r: r["case"]["years"]["normal"]["month_types"]["typical"].__setitem__("sales_per_month", 121))

    def test_rejects_wrong_unpaid(self):
        self.broken(lambda r: r["case"]["years"]["bad"].__setitem__("unpaid_usd", 150))

    def test_rejects_calendar_mismatch(self):
        self.broken(lambda r: r["calendar"]["normal"].__setitem__("Feb", "harvest"))

    def test_rejects_bad_override_path(self):
        with self.assertRaises(ConfigError):
            CFG.with_overrides({"token.nope": 1})
        with self.assertRaises(ConfigError):
            CFG.with_overrides({"nope.x": 1})

    def test_override(self):
        cfg = CFG.with_overrides({"token.in_kind_corn_lb": 9})
        self.assertEqual(cfg.token["in_kind_corn_lb"], 9)
        self.assertEqual(CFG.token["in_kind_corn_lb"], 10)  # original untouched

    def test_unknown_year(self):
        with self.assertRaises(ConfigError):
            CFG.year("great")

    def test_unknown_window(self):
        cfg = CFG.with_overrides({"token.redeem_windows": {"corn": ["someday"]}})
        with self.assertRaises(ConfigError):
            cfg.redeem_months("normal")


class TestCli(unittest.TestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_check(self):
        code, out, _ = self.run_cli("check")
        self.assertEqual(code, 0)
        self.assertIn("config OK", out)

    def test_token_table(self):
        code, out, _ = self.run_cli("token-table")
        self.assertEqual(code, 0)
        self.assertIn("| corn | 10.0 lb | $3.00 |", out)

    def test_bad_config_path(self):
        code, _, err = self.run_cli("--config", "/nonexistent.json", "check")
        self.assertEqual(code, 2)
        self.assertIn("config error", err)

    def test_invalid_config_file(self):
        raw = copy.deepcopy(dict(CFG.raw))
        raw["case"]["fx_bzd_per_usd"] = 3
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text(json.dumps(raw))
            code, _, err = self.run_cli("--config", str(path), "check")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
