"""Lock-in numbers follow from the case prices and the wage peg."""

from __future__ import annotations

import unittest

from milpa.config import load
from milpa.lockin import latest_usd, lock_in_summary, lock_in_table, reference_data, to_csv_rows, to_markdown

CFG = load()


class TestLockInTable(unittest.TestCase):
    def setUp(self):
        self.rows = {r.item: r for r in lock_in_table(CFG)}

    def test_corn(self):
        corn = self.rows["corn"]
        self.assertAlmostEqual(corn.token_qty, 10.0)
        self.assertAlmostEqual(corn.wage_qty_at_tierra_viva, 2.50 / 0.30)
        self.assertAlmostEqual(corn.advantage_vs_cash_at_tierra_viva, 0.20)
        self.assertIsNone(corn.wage_qty_at_truck_low)  # truck does not sell corn
        self.assertFalse(corn.available_with_cash_pre_harvest)

    def test_plantain_vs_truck(self):
        p = self.rows["plantain"]
        self.assertAlmostEqual(p.token_qty, 12.0)
        self.assertAlmostEqual(p.wage_qty_at_truck_low, 2.50 / (0.25 * 0.90))
        self.assertAlmostEqual(p.wage_qty_at_truck_high, 2.50 / (0.25 * 0.85))
        self.assertAlmostEqual(p.advantage_vs_truck_worst_case, 12 / (2.50 / 0.2125) - 1)
        self.assertGreater(p.advantage_vs_truck_worst_case, 0)

    def test_punta_gorda_reference(self):
        corn = self.rows["corn"]
        self.assertAlmostEqual(corn.wage_qty_at_punta_gorda, 2.50 / 0.225)
        self.assertEqual(corn.punta_gorda_price_date, "2022-08-13")
        self.assertIsNone(self.rows["seed_corn"].wage_qty_at_punta_gorda)

    def test_premium_is_same_for_every_item(self):
        for r in self.rows.values():
            self.assertAlmostEqual(r.advantage_vs_cash_at_tierra_viva, 0.20)

    def test_markdown_and_csv(self):
        md = to_markdown(list(self.rows.values()), 5.0, 2.0)
        self.assertIn("| Corn (dried) | 10.0 lb | 8.3 lb | not sold |", md)
        self.assertIn("BZ$5.00 = US$2.50", md)
        self.assertEqual(len(to_csv_rows(list(self.rows.values()))), 5)


class TestLockInSensitivity(unittest.TestCase):
    def test_nine_pounds_loses_to_truck(self):
        s = lock_in_summary(CFG, in_kind_corn_lb=9)
        self.assertAlmostEqual(s["token_premium_vs_cash_wage"], 0.08)
        self.assertLess(s["worst_truck_advantage"], 0)

    def test_six_dollar_wage_erases_premium(self):
        s = lock_in_summary(CFG, wage_bzd_per_hour=6.0)
        self.assertAlmostEqual(s["token_premium_vs_cash_wage"], 0.0)
        self.assertLess(s["worst_truck_advantage"], 0)

    def test_twelve_pounds_restores_premium_at_six(self):
        s = lock_in_summary(CFG, wage_bzd_per_hour=6.0, in_kind_corn_lb=12)
        self.assertAlmostEqual(s["token_premium_vs_cash_wage"], 0.20)


class TestReferenceData(unittest.TestCase):
    def test_every_row_has_a_source_and_date(self):
        rows = reference_data()
        self.assertGreater(len(rows), 20)
        for r in rows:
            with self.subTest(indicator=r["indicator"], date=r["date"]):
                self.assertTrue(r["source"])
                self.assertTrue(r["date"])
                if r["value"] and not r["source"].startswith("NOT"):
                    self.assertTrue(r["url"].startswith("https://"))

    def test_usd_equivalents_follow_fixed_rate(self):
        for r in reference_data():
            if r["unit"].startswith("BZD") and r["value"] and r["usd_equivalent"]:
                with self.subTest(indicator=r["indicator"], date=r["date"]):
                    self.assertAlmostEqual(float(r["value"]) / 2.0, float(r["usd_equivalent"]))

    def test_wage_six_marked_not_enacted(self):
        rows = [r for r in reference_data() if r["indicator"].startswith("minimum_wage_6")]
        self.assertTrue(rows)
        self.assertTrue(all("not enacted" in r["source"] for r in rows))

    def test_latest(self):
        rows = reference_data()
        self.assertEqual(latest_usd(rows, "bapis_punta_gorda_rk_beans"), (1.0, "2022-08-13"))
        self.assertEqual(latest_usd(rows, "bapis_national_rk_beans"), (1.225, "2026-10-26"))
        self.assertIsNone(latest_usd(rows, "no_such_series"))
        self.assertIsNone(latest_usd(rows, "seasonal_price_swing_corn_beans"))


if __name__ == "__main__":
    unittest.main()
