"""The annual model reproduces every number in the pitch deck (whole dollars/tokens)."""

from __future__ import annotations

import unittest

from milpa.config import load
from milpa.model import all_cases, annual
from milpa.outputs import usd

CFG = load()
BASE = annual(CFG, "base")


class TestDeckNumbers(unittest.TestCase):
    def test_tokens_issued_per_year(self):
        self.assertEqual(round(BASE["reward_tokens"]), 13)
        self.assertEqual(round(BASE["pickup_tokens"]), 60)
        self.assertEqual(round(BASE["tokens_issued"]), 73)

    def test_share_of_sales_under_cap(self):
        self.assertEqual(BASE["sales_usd"], 1370)
        self.assertEqual(f"{BASE['token_share_of_sales']:.1%}", "5.4%")
        self.assertLess(BASE["token_share_of_sales"], 0.10)
        self.assertEqual(round(BASE["cap_tokens"]), 137)
        self.assertTrue(BASE["within_cap"])

    def test_credit_no_longer_lost(self):
        self.assertAlmostEqual(BASE["credit_recovered_usd"], 594 * (0.25 - 0.10))
        self.assertEqual(usd(BASE["credit_recovered_usd"]), "$89")

    def test_record_gain_net_of_reward(self):
        self.assertEqual(usd(BASE["record_gain_net_usd"]), "$79")

    def test_pickup_gain(self):
        self.assertAlmostEqual(BASE["pickup_gain_net_usd"], 240 - 60 - 60 * 1 * 0.75)
        self.assertEqual(usd(BASE["pickup_gain_net_usd"]), "$135")
        self.assertEqual(BASE["pickup_cash_usd"], 60)

    def test_drum2_pre_harvest_sales(self):
        self.assertEqual(usd(BASE["turned_away_usd"]), "$176")
        self.assertAlmostEqual(BASE["drum2_sales_usd"], 0.70 * 175.5)
        self.assertEqual(usd(BASE["drum2_sales_usd"]), "$123")

    def test_tokens_per_lb(self):
        self.assertEqual(f"{BASE['corn_lb_per_token']:.2f}", "3.33")
        self.assertEqual(BASE["beans_lb_per_token"], 1.0)

    def test_drum2_can_cover_the_gap(self):
        self.assertGreaterEqual(BASE["drum2_fill_value_usd"], BASE["drum2_needed_in_gap_usd"])

    def test_cases_are_ordered(self):
        c = all_cases(CFG)
        self.assertLess(c["conservative"]["total_gain_usd"], c["base"]["total_gain_usd"])
        self.assertLess(c["base"]["total_gain_usd"], c["optimistic"]["total_gain_usd"])
        self.assertEqual(c["conservative"]["token_cost_share"], 0.90)
        self.assertEqual(c["optimistic"]["unpaid_share_with_libreta"], 0.08)
        for case in c.values():
            self.assertTrue(case["within_cap"])

    def test_unknown_case(self):
        with self.assertRaises(ValueError):
            annual(CFG, "wild")


class TestNoLabor(unittest.TestCase):
    def test_config_has_no_labor_rules(self):
        text = str(CFG.raw["token"]).lower()
        for word in ("wage", "hour", "labor", "labour", "work"):
            self.assertNotIn(word, text)
        self.assertNotIn("time_hours_per_week", CFG.case)


if __name__ == "__main__":
    unittest.main()
