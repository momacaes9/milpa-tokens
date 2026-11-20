"""Config validation, lock-in table and the monthly replay."""

from __future__ import annotations

import unittest

from milpa.config import ConfigError, load
from milpa.lockin import lock_in_table, to_markdown
from milpa.simulate import replay
from milpa.tokentable import token_table

CFG = load()


class TestConfig(unittest.TestCase):
    def test_case_numbers_kept(self):
        n = CFG.year("normal")
        self.assertEqual((n["total_sales_usd"], n["credit_usd"], n["unpaid_usd"]), (1370, 594, 149))
        self.assertEqual(CFG.case["cash_costs_usd"]["pickup_rides"], 240)
        self.assertEqual(CFG.case["drums"], {"cost_usd_each": 100, "capacity_lb": 250, "neighbors_wanting_storage": 2})
        self.assertEqual(CFG.grain_prices(), {"corn": 0.3, "beans": 1.0})

    def test_rejects_non_grain_tokens(self):
        with self.assertRaises(ConfigError):
            CFG.with_overrides({"token.redeemable_items": ["corn", "beans", "plantain"]})
        with self.assertRaises(ConfigError):
            CFG.with_overrides({"token.earn.crop_repayment.items": ["corn", "cacao"]})

    def test_rejects_labor_earning(self):
        earn = dict(CFG.token["earn"], hours_of_work={"rate": 1})
        with self.assertRaises(ConfigError):
            CFG.with_overrides({"token.earn": earn})

    def test_rejects_bad_values(self):
        for path, value in (
            ("token.face_value_bzd", 3.0),
            ("token.cap_share_of_sales", 0),
            ("token.cost_share_of_face", {"base": 0.75}),
            ("token.unpaid_share_with_libreta", {"base": 2, "conservative": 0.1, "optimistic": 0.1}),
            ("token.drums", {"total": 2, "family": 0, "sale": 2}),
            ("token.drum2_fill_lb", {"corn": 100, "beans": 200}),
            ("token.drum2_fill_lb", {"corn": 50, "plantain": 10}),
            ("token.crop_repayment_lb", {"corn": 60, "beans": 100}),
            ("token.redeem_month_types", ["winter"]),
            ("case.fx_bzd_per_usd", 2.5),
        ):
            with self.subTest(path=path), self.assertRaises(ConfigError):
                CFG.with_overrides({path: value})
        with self.assertRaises(ConfigError):
            CFG.with_overrides({"token.nope": 1})
        with self.assertRaises(ConfigError):
            CFG.year("great")


class TestLockIn(unittest.TestCase):
    def test_one_dollar_at_tierra_viva_zero_elsewhere(self):
        rows = {r.where: r for r in lock_in_table(CFG)}
        self.assertEqual(rows["Tierra Viva market table: corn"].value_usd, 1.0)
        self.assertIn("3.33 lb corn", rows["Tierra Viva market table: corn"].buys)
        self.assertEqual(rows["Tierra Viva market table: beans"].value_usd, 1.0)
        self.assertEqual(rows["Produce truck"].value_usd, 0.0)
        self.assertEqual(rows["As cash"].value_usd, 0.0)
        md = to_markdown(lock_in_table(CFG))
        self.assertIn("| Produce truck | $0.00 |", md)
        self.assertIn("| As cash | $0.00 |", md)

    def test_token_table(self):
        md = token_table(CFG)
        self.assertIn("| Corn (dried) | $0.30/lb | 3.33 lb | 3 tokens |", md)
        self.assertIn("| Beans (dried) | $1.00/lb | 1.00 lb | 10 tokens |", md)


class TestReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.years = replay(CFG, years=3)

    def test_steady_state_matches_deck(self):
        t = self.years[1].totals
        self.assertEqual(t["reward_tokens_issued"], 13)
        self.assertEqual(t["pickup_tokens_issued"], 60)
        self.assertEqual(t["tokens_issued"], 73)
        self.assertAlmostEqual(t["drum2_sales_usd"], 122.85)
        self.assertEqual(t["pickup_cash_usd"], 60)
        self.assertAlmostEqual(t["crop_tokens_credited"], 115)

    def test_backing_and_cap_hold_every_month(self):
        for r in self.years:
            self.assertLessEqual(r.totals["tokens_issued"], r.totals["cap_tokens"])
            self.assertLessEqual(r.totals["drum2_lb_max"], 250 + 1e-9)
            self.assertEqual(r.totals["family_drum_lb_min"], 250)
            for m in r.months:
                self.assertLessEqual(m.tokens_outstanding, m.drum2_value_usd + 1e-9)
                if m.tokens_redeemed:
                    self.assertEqual(m.month_type, "pre_harvest")

    def test_gap_empties_outstanding(self):
        sep = [m for m in self.years[1].months if m.month == "Sep"][0]
        self.assertEqual(sep.tokens_outstanding, 0)

    def test_years_must_be_positive(self):
        with self.assertRaises(ValueError):
            replay(CFG, years=0)


if __name__ == "__main__":
    unittest.main()
