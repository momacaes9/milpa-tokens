"""Every Libreta rule, tried and broken."""

from __future__ import annotations

import unittest

from milpa.config import load
from milpa.ledger import (
    CapExceeded, CashOutNotAllowed, DrumFull, FamilyFoodProtected, InsufficientBacking,
    InsufficientReserve, InsufficientTokens, Ledger, LedgerError, NotCornOrBeans,
    OutsideWindow, Overpayment, Rules, TransferNotAllowed,
)

CFG = load()


def ledger(corn: float = 50, beans: float = 200, cap: float | None = 137) -> Ledger:
    led = Ledger(CFG.rules("normal"), annual_cap_tokens=cap)
    if corn:
        led.add_to_drum2("Jan", "corn", corn)
    if beans:
        led.add_to_drum2("Jan", "beans", beans)
    return led


class TestRules(unittest.TestCase):
    def test_from_config(self):
        r = CFG.rules("normal")
        self.assertEqual(r.token_value_usd, 1.0)
        self.assertEqual(r.redeem_months, frozenset({"Jul", "Aug", "Sep"}))
        self.assertEqual(r.drum2_capacity_lb, 250)
        self.assertAlmostEqual(r.lb_per_token("corn"), 10 / 3)
        self.assertEqual(r.lb_per_token("beans"), 1.0)

    def test_invalid_rules(self):
        prices = {"corn": 0.3, "beans": 1.0}
        with self.assertRaises(ValueError):
            Rules({"corn": 0.3, "beans": 1.0, "plantain": 0.25})
        with self.assertRaises(ValueError):
            Rules({"corn": 0.0, "beans": 1.0})
        with self.assertRaises(ValueError):
            Rules(prices, token_value_usd=0)
        with self.assertRaises(ValueError):
            Rules(prices, reward_share=1.5)
        with self.assertRaises(ValueError):
            Rules(prices, on_time_days=0)
        with self.assertRaises(ValueError):
            Rules(prices, redeem_months=frozenset({"Julember"}))
        with self.assertRaises(ValueError):
            Rules(prices, drum2_capacity_lb=0)

    def test_only_corn_and_beans(self):
        with self.assertRaises(NotCornOrBeans):
            CFG.rules().lb_per_token("plantain")


class TestDrums(unittest.TestCase):
    def test_drum1_is_never_touched(self):
        led = ledger()
        led.set_family_food("corn_and_beans", 250)
        with self.assertRaises(FamilyFoodProtected):
            led.take_from_family_drum("corn", 10)
        self.assertEqual(led.drum2_value_usd(), 50 * 0.3 + 200)
        with self.assertRaises(LedgerError):
            led.set_family_food("corn", -1)

    def test_drum2_capacity(self):
        led = ledger()
        with self.assertRaises(DrumFull):
            led.add_to_drum2("Nov", "beans", 1)
        with self.assertRaises(NotCornOrBeans):
            ledger(0, 0).add_to_drum2("Nov", "cacao", 1)
        with self.assertRaises(LedgerError):
            ledger(0, 0).add_to_drum2("Nov", "corn", 0)

    def test_sale_keeps_tokens_backed(self):
        led = ledger(corn=0, beans=10)
        led.issue("Nov", "pickup_neighbor", 8)
        self.assertEqual(led.sell_from_drum2("Jul", "beans", 2), 2.0)
        with self.assertRaises(InsufficientBacking):
            led.sell_from_drum2("Jul", "beans", 1)
        with self.assertRaises(InsufficientReserve):
            led.sell_from_drum2("Jul", "corn", 1)
        with self.assertRaises(LedgerError):
            led.sell_from_drum2("Jul", "beans", 0)


class TestEarning(unittest.TestCase):
    def test_crop_repayment_credits_tokens_and_fills_drum2(self):
        led = ledger(0, 0)
        led.record_credit("May", "farmer_01", 23.0)
        self.assertAlmostEqual(led.repay_in_crops("Nov", "farmer_01", "corn", 10), 3.0)
        self.assertAlmostEqual(led.repay_in_crops("Nov", "farmer_01", "beans", 20), 20.0)
        self.assertAlmostEqual(led.debts_usd["farmer_01"], 0.0)
        self.assertEqual(led.drum2_lb, {"corn": 10, "beans": 20})
        self.assertEqual(led.outstanding, 0)  # credits settle debt; no vouchers out
        self.assertAlmostEqual(led.crop_tokens_credited, 23.0)

    def test_crop_repayment_rules(self):
        led = ledger(0, 0)
        led.record_credit("May", "farmer_01", 5.0)
        with self.assertRaises(Overpayment):
            led.repay_in_crops("Nov", "farmer_01", "beans", 6)
        with self.assertRaises(NotCornOrBeans):
            led.repay_in_crops("Nov", "farmer_01", "cassava", 1)
        with self.assertRaises(LedgerError):
            led.repay_in_crops("Nov", "farmer_01", "corn", 0)
        full = ledger()
        full.record_credit("May", "farmer_01", 5.0)
        with self.assertRaises(DrumFull):
            full.repay_in_crops("Nov", "farmer_01", "beans", 1)

    def test_on_time_cash_reward(self):
        led = ledger()
        led.record_credit("Feb", "hh_01", 100)
        self.assertEqual(led.repay_cash("Feb", "hh_01", 30, days_late=10), 1)  # $1.50 -> 1 token
        self.assertAlmostEqual(led.reward_carry_usd["hh_01"], 0.5)
        self.assertEqual(led.repay_cash("Mar", "hh_01", 10, days_late=30), 1)  # 0.5 + 0.5
        self.assertEqual(led.repay_cash("Apr", "hh_01", 40, days_late=31), 0)  # late: no reward
        self.assertEqual(led.held, {"hh_01": 2})
        self.assertAlmostEqual(led.debts_usd["hh_01"], 20)

    def test_cash_repayment_rules(self):
        led = ledger()
        led.record_credit("Feb", "hh_01", 10)
        with self.assertRaises(Overpayment):
            led.repay_cash("Feb", "hh_01", 11, 0)
        with self.assertRaises(LedgerError):
            led.repay_cash("Feb", "hh_01", 0, 0)
        with self.assertRaises(LedgerError):
            led.repay_cash("Feb", "hh_01", 1, -1)
        with self.assertRaises(LedgerError):
            led.record_credit("Feb", "hh_01", 0)

    def test_reward_waits_when_drum2_is_empty(self):
        led = ledger(0, 0)
        led.record_credit("Feb", "hh_01", 100)
        self.assertEqual(led.repay_cash("Feb", "hh_01", 40, 5), 0)
        self.assertAlmostEqual(led.reward_carry_usd["hh_01"], 2.0)
        self.assertEqual(led.events[-1].kind, "reward_pending")
        led.add_to_drum2("Nov", "beans", 5)
        self.assertEqual(led.repay_cash("Nov", "hh_01", 20, 5), 3)

    def test_pickup_fare(self):
        led = ledger()
        self.assertEqual(led.pay_pickup_fare("Nov", "pickup_neighbor", 10, 0.5), (5.0, 5))
        self.assertEqual(led.held["pickup_neighbor"], 5)
        with self.assertRaises(LedgerError):
            led.pay_pickup_fare("Nov", "pickup_neighbor", 9, 0.5)  # $4.50: not whole tokens
        with self.assertRaises(LedgerError):
            led.pay_pickup_fare("Nov", "pickup_neighbor", 0, 0.5)
        self.assertEqual(led.pay_pickup_fare("Nov", "pickup_neighbor", 10, 0), (10.0, 0))


class TestIssueAndSpend(unittest.TestCase):
    def test_backing_never_exceeded(self):
        led = ledger(corn=0, beans=10)
        led.issue("Nov", "a", 10)
        self.assertEqual(led.coverage_ratio(), 1.0)
        self.assertEqual(led.backable_tokens(), 0)
        with self.assertRaises(InsufficientBacking):
            led.issue("Nov", "b", 1)

    def test_cap(self):
        led = ledger(cap=5)
        led.issue("Nov", "a", 5)
        with self.assertRaises(CapExceeded):
            led.issue("Nov", "a", 1)
        led.start_year(5)
        led.issue("Feb", "a", 1)

    def test_whole_tokens_numbered(self):
        led = ledger()
        self.assertEqual(led.issue("Nov", "a", 3), (1, 3))
        self.assertEqual(led.issue("Nov", "b", 2), (4, 5))
        for bad in (0, -1, 1.5, True):
            with self.assertRaises(LedgerError):
                led.issue("Nov", "a", bad)

    def test_redeem_corn_and_beans_in_gap(self):
        led = ledger()
        led.issue("Nov", "a", 6)
        self.assertAlmostEqual(led.redeem("Jul", "a", 3, "corn"), 10.0)
        self.assertAlmostEqual(led.redeem("Aug", "a", 3, "beans"), 3.0)
        self.assertEqual(led.outstanding, 0)
        self.assertAlmostEqual(led.drum2_lb["corn"], 40)
        self.assertIsNone(led.coverage_ratio())

    def test_redeem_rules(self):
        led = ledger(corn=3, beans=200)
        led.issue("Nov", "a", 5)
        with self.assertRaises(OutsideWindow):
            led.redeem("Nov", "a", 1, "beans")
        with self.assertRaises(NotCornOrBeans):
            led.redeem("Jul", "a", 1, "plantain")
        with self.assertRaises(InsufficientTokens):
            led.redeem("Jul", "b", 1, "beans")
        with self.assertRaises(InsufficientReserve):
            led.redeem("Jul", "a", 1, "corn")

    def test_not_money(self):
        led = ledger()
        with self.assertRaises(TransferNotAllowed):
            led.transfer("a", "b", 1)
        with self.assertRaises(CashOutNotAllowed):
            led.cash_out("a", 1)

    def test_batch_rolls_back(self):
        led = ledger(corn=0, beans=5)
        with self.assertRaises(InsufficientBacking):
            with led.batch():
                led.issue("Nov", "a", 3)
                led.issue("Nov", "b", 3)
        self.assertEqual(led.outstanding, 0)
        self.assertEqual(led.next_serial, 1)


if __name__ == "__main__":
    unittest.main()
