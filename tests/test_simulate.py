"""The simulator must reproduce the case exactly and never break a rule."""

from __future__ import annotations

import math
import unittest

from milpa.config import load
from milpa.sensitivity import sensitivity_table, to_markdown
from milpa.simulate import SCENARIOS, monte_carlo, run_all, simulate_sequence, simulate_year

CFG = load()
RESULTS = run_all(CFG)


def t(scenario, year):
    return RESULTS[(scenario, year)].totals


class TestBaselineMatchesCase(unittest.TestCase):
    def test_normal_year(self):
        today = t("today", "normal")
        self.assertAlmostEqual(today["sales_usd"], 1370)
        self.assertAlmostEqual(today["credit_usd"], 594)
        self.assertAlmostEqual(today["unpaid_credit_usd"], 148.5)  # case rounds to $149
        self.assertAlmostEqual(today["cash_collected_usd"], 1221.5)  # case: $1,222
        self.assertAlmostEqual(today["net_cash_income_usd"], 761.5)  # case: $762

    def test_bad_year(self):
        today = t("today", "bad")
        self.assertAlmostEqual(today["sales_usd"], 900)
        self.assertAlmostEqual(today["credit_usd"], 491)
        self.assertAlmostEqual(today["unpaid_credit_usd"], 196.4)  # case: $196
        self.assertAlmostEqual(today["cash_collected_usd"], 703.6)  # case: $704
        self.assertAlmostEqual(today["net_cash_income_usd"], 243.6)  # case: $244

    def test_today_has_no_tokens_or_drums(self):
        for year in ("normal", "bad"):
            today = t("today", year)
            self.assertEqual(today["tokens_issued"], 0)
            self.assertEqual(today["drum_cost_usd"], 0)
            self.assertEqual(today["helper_hours_total"], 0)


class TestInvariants(unittest.TestCase):
    def test_coverage_never_below_one(self):
        for year in ("normal", "bad"):
            for m in RESULTS[("tokens", year)].months:
                if m.coverage_ratio is not None:
                    self.assertGreaterEqual(m.coverage_ratio, 1.0 - 1e-9)

    def test_family_food_never_touched(self):
        cap = CFG.case["drums"]["capacity_lb"]
        for scenario in ("drums", "tokens"):
            for year in ("normal", "bad"):
                for m in RESULTS[(scenario, year)].months:
                    self.assertEqual(m.family_food_lb, cap)

    def test_token_flows_balance(self):
        for year in ("normal", "bad"):
            r = RESULTS[("tokens", year)]
            tot = r.totals
            self.assertEqual(tot["tokens_issued"],
                             tot["tokens_redeemed"] + tot["tokens_expired"] + tot["tokens_outstanding_end"])
            self.assertEqual(tot["tokens_issued"], tot["token_hours"])

    def test_help_never_exceeds_wanted(self):
        wanted = CFG.raw["simulation"]["help_hours_wanted_per_work_month"]
        for year in ("normal", "bad"):
            for m in RESULTS[("tokens", year)].months:
                self.assertLessEqual(m.token_hours + m.debt_labor_hours, wanted + 1e-9)

    def test_tokens_only_in_work_months(self):
        for year in ("normal", "bad"):
            work = CFG.issue_months(year)
            for m in RESULTS[("tokens", year)].months:
                if m.tokens_issued:
                    self.assertIn(m.month, work)

    def test_drum_sales_only_pre_harvest(self):
        for m in RESULTS[("drums", "normal")].months:
            if m.drum_sales_usd:
                self.assertEqual(m.month_type, "pre_harvest")

    def test_drum_sales_capped_by_turned_away_demand(self):
        demand = 9 * 13 * 1.50
        self.assertLessEqual(t("drums", "normal")["drum_sales_usd"], demand + 1e-9)


class TestScenarioEffects(unittest.TestCase):
    def test_debt_paid_in_hands(self):
        tok = t("tokens", "normal")
        expected_hours = 594 * 0.25 * 0.30 / 2.50
        self.assertAlmostEqual(tok["bad_debt_recovered_hours"], expected_hours, places=3)
        self.assertAlmostEqual(tok["bad_debt_recovered_usd"], expected_hours * 2.50, places=3)

    def test_tokens_trade_some_drum_cash_for_hours(self):
        self.assertLess(t("tokens", "normal")["drum_sales_usd"], t("drums", "normal")["drum_sales_usd"])
        self.assertGreater(t("tokens", "normal")["helper_hours_total"], 0)

    def test_tokens_never_cost_case_cash(self):
        for year in ("normal", "bad"):
            self.assertGreaterEqual(t("tokens", year)["cash_collected_usd"] + 1e-9,
                                    t("today", year)["cash_collected_usd"])

    def test_fresh_redemptions_absorb_spoilage_only(self):
        harvest_sales = 3 * 170 * 0.35
        spoiled = harvest_sales * 0.2 / 0.8
        self.assertLessEqual(t("tokens", "normal")["fresh_redeemed_usd"], spoiled + 1e-9)

    def test_third_drum_removes_cash_trade_off(self):
        three = simulate_year(CFG, "normal", "tokens", {"drums_total": 3}).totals
        drums3 = simulate_year(CFG, "normal", "drums", {"drums_total": 3}).totals
        self.assertAlmostEqual(three["cash_collected_usd"], drums3["cash_collected_usd"])

    def test_bad_year_fill(self):
        first = RESULTS[("drums", "bad")].months[0]
        self.assertAlmostEqual(first.sale_drum_lb, 125.0)


class TestSequence(unittest.TestCase):
    def test_normal_then_storm(self):
        seq = simulate_sequence(CFG, ("normal", "bad"), "tokens")
        self.assertEqual([r.year for r in seq], ["normal", "bad"])
        self.assertEqual(seq[1].months[0].index, 12)
        issued = sum(r.totals["tokens_issued"] for r in seq)
        gone = sum(r.totals["tokens_redeemed"] + r.totals["tokens_expired"] for r in seq)
        self.assertEqual(issued, gone + seq[-1].totals["tokens_outstanding_end"])
        self.assertGreater(seq[1].totals["tokens_expired"], 0)  # unredeemed tokens lapse
        self.assertEqual(seq[1].totals["drum_cost_usd"], 0)  # drums are bought once
        for r in seq:
            for m in r.months:
                if m.coverage_ratio is not None:
                    self.assertGreaterEqual(m.coverage_ratio, 1.0 - 1e-9)

    def test_first_year_of_sequence_matches_single_year(self):
        seq = simulate_sequence(CFG, ("normal", "bad"), "tokens")
        self.assertEqual(seq[0].totals, t("tokens", "normal"))

    def test_full_redemption_means_no_expiry(self):
        # Every backed token can be paid (grain may be mixed), so none lapse.
        seq = simulate_sequence(CFG, ("normal", "bad"), "tokens", {"redemption_rate": 1.0})
        self.assertEqual(sum(r.totals["tokens_expired"] for r in seq), 0)

    def test_errors(self):
        with self.assertRaises(ValueError):
            simulate_sequence(CFG, (), "tokens")
        with self.assertRaises(ValueError):
            simulate_year(CFG, "normal", "magic")
        with self.assertRaises(ValueError):
            simulate_year(CFG, "normal", "tokens", {"drums_total": 1})
        with self.assertRaises(ValueError):
            simulate_year(CFG, "normal", "tokens", {"wage_bzd_per_hour": 0})


class TestOverrides(unittest.TestCase):
    def test_higher_wage_fewer_debt_hours(self):
        six = simulate_year(CFG, "normal", "tokens", {"wage_bzd_per_hour": 6.0}).totals
        self.assertAlmostEqual(six["bad_debt_recovered_hours"], 594 * 0.25 * 0.30 / 3.0, places=3)

    def test_scalar_fill_share(self):
        r = simulate_year(CFG, "normal", "drums", {"sale_drum_fill_share": 0.5})
        self.assertAlmostEqual(r.months[0].sale_drum_lb, 125.0)

    def test_unpaid_override(self):
        r = simulate_year(CFG, "normal", "today", {"unpaid_share_of_credit": 0.0}).totals
        self.assertAlmostEqual(r["cash_collected_usd"], 1370)


class TestMonteCarlo(unittest.TestCase):
    def test_reproducible(self):
        a = monte_carlo(CFG, "normal", runs=40, seed=7)
        b = monte_carlo(CFG, "normal", runs=40, seed=7)
        self.assertEqual(a, b)

    def test_quantiles_ordered_and_centered(self):
        mc = monte_carlo(CFG, "normal", runs=300, seed=1)
        for key, s in mc.items():
            with self.subTest(key=key):
                self.assertLessEqual(s["p10"], s["p50"] + 1e-9)
                self.assertLessEqual(s["p50"], s["p90"] + 1e-9)
        self.assertAlmostEqual(mc["unpaid_share_of_credit"]["mean"], 0.25, delta=0.02)
        self.assertGreaterEqual(mc["min_coverage_ratio"]["p10"], 1.0 - 1e-9)

    def test_bad_year_and_single_run(self):
        mc = monte_carlo(CFG, "bad", runs=1, seed=3)
        s = mc["cash_collected_usd"]
        self.assertEqual(s["p10"], s["p90"])
        with self.assertRaises(ValueError):
            monte_carlo(CFG, "bad", runs=0)


class TestSensitivity(unittest.TestCase):
    def test_grid(self):
        rows = sensitivity_table(CFG)
        self.assertEqual(len(rows), 8)
        self.assertEqual(sum(r["baseline"] for r in rows), 1)
        base = next(r for r in rows if r["baseline"])
        self.assertAlmostEqual(base["token_premium_vs_cash_wage"], 0.20)
        for r in rows:
            self.assertGreaterEqual(r["normal_min_coverage"], 1.0 - 1e-9)
            if r["wage_bzd_per_hour"] == 6.0 and r["in_kind_corn_lb"] == 9:
                self.assertLess(r["token_premium_vs_cash_wage"], 0)
        md = to_markdown(rows)
        self.assertIn("**(base)**", md)
        self.assertEqual(md.count("\n"), 9)


class TestScenarioList(unittest.TestCase):
    def test_all_present(self):
        self.assertEqual(len(RESULTS), 2 * len(SCENARIOS))
        for r in RESULTS.values():
            self.assertEqual(len(r.months), 12)
            self.assertFalse(math.isnan(r.totals["cash_collected_usd"]))


if __name__ == "__main__":
    unittest.main()
