"""Every ledger rule has a test that tries to break it."""

from __future__ import annotations

import unittest

from milpa.config import load
from milpa.ledger import (
    CapExceeded,
    CashOutNotAllowed,
    FamilyFoodProtected,
    InsufficientBacking,
    InsufficientReserve,
    InsufficientTokens,
    Ledger,
    LedgerError,
    OutsideWindow,
    Rules,
    TransferNotAllowed,
)

CFG = load()


def make_ledger(corn_lb: float = 250.0, **overrides) -> Ledger:
    """A normal-year ledger starting in February with one corn drum."""
    ledger = Ledger(CFG.rules("normal", **overrides), start_month="Feb")
    if corn_lb:
        ledger.add_to_reserve(0, "corn", corn_lb)
    return ledger


# Normal-year calendar, start Feb: 0 Feb, 3 May, 4 Jun, 5 Jul, 6 Aug, 9 Nov, 10 Dec, 11 Jan
MAY, JUN, JUL, AUG, NOV, DEC = 3, 4, 5, 6, 9, 10


class TestRules(unittest.TestCase):
    def test_token_value_is_in_kind_corn(self):
        rules = CFG.rules("normal")
        self.assertAlmostEqual(rules.token_value_usd, 10 * 0.30)
        self.assertAlmostEqual(rules.units_per_token("corn"), 10)
        self.assertAlmostEqual(rules.units_per_token("beans"), 3.0)
        self.assertAlmostEqual(rules.units_per_token("plantain"), 12.0)

    def test_nine_pound_rate(self):
        rules = CFG.rules("normal", in_kind_corn_lb=9)
        self.assertAlmostEqual(rules.token_value_usd, 2.70)
        self.assertAlmostEqual(rules.units_per_token("beans"), 2.7)

    def test_invalid_rules_rejected(self):
        base = dict(
            in_kind_corn_lb=10, prices_usd={"corn": 0.3}, max_tokens_per_household=10,
            expiry_months=12, min_coverage=1.0, issue_months=frozenset({"May"}),
            redeem_months={"corn": frozenset({"Jul"})},
        )
        for bad in (
            {"in_kind_corn_lb": 0}, {"min_coverage": 0.9}, {"expiry_months": 0},
            {"max_tokens_per_household": 0}, {"issue_months": frozenset({"Maio"})},
            {"prices_usd": {"beans": 1.0}}, {"prices_usd": {"corn": -1}},
            {"redeem_months": {"rice": frozenset({"Jul"})}},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Rules(**{**base, **bad})

    def test_unknown_item(self):
        with self.assertRaises(LedgerError):
            CFG.rules("normal").units_per_token("rice")


class TestIssue(unittest.TestCase):
    def test_issue_in_work_month(self):
        ledger = make_ledger()
        lot = ledger.issue(MAY, "Pop household", 4)
        self.assertEqual((lot.first_serial, lot.count), (1, 4))
        self.assertEqual(ledger.outstanding, 4)
        self.assertEqual(ledger.next_serial, 5)

    def test_issue_outside_window(self):
        ledger = make_ledger()
        with self.assertRaises(OutsideWindow):
            ledger.issue(JUL, "Pop household", 1)  # July is pre-harvest

    def test_whole_hours_only(self):
        ledger = make_ledger()
        for hours in (0, -1, 1.5, True):
            with self.subTest(hours=hours), self.assertRaises(LedgerError):
                ledger.issue(MAY, "Pop household", hours)

    def test_household_cap(self):
        ledger = make_ledger()
        ledger.issue(MAY, "Pop household", 10)
        with self.assertRaises(CapExceeded):
            ledger.issue(JUN, "Pop household", 1)
        ledger.issue(JUN, "Cal household", 1)  # another household is fine

    def test_backing_limits_issue(self):
        ledger = make_ledger(corn_lb=50)  # 50 lb = $15 = 5 tokens at 10 lb each
        self.assertEqual(ledger.backable_tokens(), 5)
        ledger.issue(MAY, "A", 5)
        with self.assertRaises(InsufficientBacking):
            ledger.issue(MAY, "B", 1)
        self.assertAlmostEqual(ledger.coverage_ratio(), 1.0)

    def test_no_reserve_no_tokens(self):
        ledger = make_ledger(corn_lb=0)
        self.assertEqual(ledger.coverage_ratio(), float("inf"))
        with self.assertRaises(InsufficientBacking):
            ledger.issue(MAY, "A", 1)

    def test_min_coverage_buffer(self):
        ledger = make_ledger(corn_lb=50, min_coverage=1.25)
        self.assertEqual(ledger.backable_tokens(), 4)


class TestFamilyFood(unittest.TestCase):
    def test_family_food_does_not_back_tokens(self):
        ledger = make_ledger(corn_lb=0)
        ledger.set_family_food("corn", 250)
        self.assertEqual(ledger.reserve_value_usd(), 0)
        with self.assertRaises(InsufficientBacking):
            ledger.issue(MAY, "A", 1)

    def test_family_food_cannot_be_taken(self):
        ledger = make_ledger()
        with self.assertRaises(FamilyFoodProtected):
            ledger.take_from_family_food("corn", 10)

    def test_negative_family_food(self):
        with self.assertRaises(LedgerError):
            make_ledger().set_family_food("corn", -1)


class TestRedeem(unittest.TestCase):
    def test_redeem_corn_pre_harvest(self):
        ledger = make_ledger()
        ledger.issue(MAY, "A", 3)
        qty = ledger.redeem(JUL, "A", 2, "corn")
        self.assertAlmostEqual(qty, 20)
        self.assertAlmostEqual(ledger.sale_reserve["corn"], 230)
        self.assertEqual(ledger.outstanding, 1)
        self.assertEqual(ledger.redeemed_total, 2)

    def test_redeem_outside_window(self):
        ledger = make_ledger()
        ledger.issue(MAY, "A", 3)
        with self.assertRaises(OutsideWindow):
            ledger.redeem(JUN, "A", 1, "corn")

    def test_redeem_more_than_held(self):
        ledger = make_ledger()
        ledger.issue(MAY, "A", 2)
        with self.assertRaises(InsufficientTokens):
            ledger.redeem(JUL, "A", 3, "corn")
        with self.assertRaises(InsufficientTokens):
            ledger.redeem(JUL, "B", 1, "corn")  # tokens are named

    def test_redeem_item_not_listed(self):
        ledger = make_ledger()
        ledger.issue(MAY, "A", 2)
        with self.assertRaises(LedgerError):
            ledger.redeem(JUL, "A", 1, "cacao")

    def test_redeem_bad_count(self):
        ledger = make_ledger()
        ledger.issue(MAY, "A", 2)
        with self.assertRaises(LedgerError):
            ledger.redeem(JUL, "A", 0, "corn")

    def test_redeem_needs_item_in_drum(self):
        ledger = make_ledger()
        ledger.issue(MAY, "A", 2)
        with self.assertRaises(InsufficientReserve):
            ledger.redeem(JUL, "A", 1, "beans")  # only corn in the drum

    def test_fresh_redeem_only_from_surplus_that_month(self):
        ledger = make_ledger()
        ledger.issue(NOV, "A", 3)
        ledger.set_fresh_on_hand(NOV, "plantain", 24)
        self.assertAlmostEqual(ledger.redeem(NOV, "A", 2, "plantain"), 24)
        with self.assertRaises(InsufficientReserve):
            ledger.redeem(NOV, "A", 1, "plantain")
        with self.assertRaises(InsufficientReserve):
            ledger.redeem(DEC, "A", 1, "plantain")  # last month's surplus is gone

    def test_fresh_surplus_validation(self):
        ledger = make_ledger()
        with self.assertRaises(LedgerError):
            ledger.set_fresh_on_hand(NOV, "corn", 5)
        with self.assertRaises(LedgerError):
            ledger.set_fresh_on_hand(NOV, "plantain", -1)

    def test_oldest_tokens_used_first(self):
        ledger = make_ledger()
        ledger.issue(MAY, "A", 2)
        ledger.issue(JUN, "A", 2)
        ledger.redeem(JUL, "A", 3, "corn")
        self.assertEqual([(lot.issued_month, lot.remaining) for lot in ledger.lots], [(JUN, 1)])


class TestExpiry(unittest.TestCase):
    def test_tokens_expire_after_twelve_months(self):
        ledger = make_ledger()
        ledger.issue(MAY, "A", 4)
        self.assertEqual(ledger.expire(MAY + 11), 0)
        self.assertEqual(ledger.expire(MAY + 12), 4)
        self.assertEqual(ledger.outstanding, 0)
        self.assertEqual(ledger.expired_total, 4)

    def test_expired_tokens_cannot_be_redeemed(self):
        ledger = make_ledger()
        ledger.issue(MAY, "A", 4)
        with self.assertRaises(InsufficientTokens):
            ledger.redeem(MAY + 14, "A", 1, "corn")  # July next year, expired

    def test_expired_lots_do_not_count_toward_cap(self):
        ledger = make_ledger()
        ledger.issue(MAY, "A", 10)
        ledger.add_to_reserve(MAY + 12, "corn", 100)
        ledger.issue(MAY + 12, "A", 1)  # May next year: old lot has expired


class TestClosedLoop(unittest.TestCase):
    def test_no_transfers(self):
        ledger = make_ledger()
        ledger.issue(MAY, "A", 2)
        with self.assertRaises(TransferNotAllowed):
            ledger.transfer("A", "B", 1)

    def test_no_cash_out(self):
        ledger = make_ledger()
        ledger.issue(MAY, "A", 2)
        with self.assertRaises(CashOutNotAllowed):
            ledger.cash_out("A", 1)

    def test_no_interest(self):
        ledger = make_ledger()
        ledger.issue(MAY, "A", 1)
        self.assertAlmostEqual(ledger.redeem(AUG, "A", 1, "corn"), 10)


class TestReserveAndCredit(unittest.TestCase):
    def test_sell_keeps_tokens_covered(self):
        ledger = make_ledger(corn_lb=100)  # $30
        ledger.issue(MAY, "A", 5)          # $15 owed
        self.assertAlmostEqual(ledger.free_reserve_value_usd(), 15)
        with self.assertRaises(InsufficientBacking):
            ledger.sell_from_reserve(JUL, "corn", 60)
        self.assertAlmostEqual(ledger.sell_from_reserve(JUL, "corn", 50), 15)

    def test_sell_validation(self):
        ledger = make_ledger(corn_lb=10)
        with self.assertRaises(LedgerError):
            ledger.sell_from_reserve(JUL, "corn", 0)
        with self.assertRaises(InsufficientReserve):
            ledger.sell_from_reserve(JUL, "corn", 11)

    def test_reserve_validation(self):
        ledger = make_ledger()
        with self.assertRaises(LedgerError):
            ledger.add_to_reserve(0, "plantain", 10)
        with self.assertRaises(LedgerError):
            ledger.add_to_reserve(0, "corn", 0)

    def test_debt_paid_in_hands(self):
        ledger = make_ledger()
        ledger.record_credit(0, "A", 10.0)
        usd = ledger.settle_debt_with_labor(MAY, "A", 2, wage_usd_per_hour=2.5)
        self.assertAlmostEqual(usd, 5.0)
        self.assertAlmostEqual(ledger.debts_usd["A"], 5.0)
        self.assertEqual(ledger.outstanding, 0)  # labor for debt issues no tokens

    def test_debt_labor_rules(self):
        ledger = make_ledger()
        ledger.record_credit(0, "A", 4.0)
        with self.assertRaises(LedgerError):
            ledger.settle_debt_with_labor(MAY, "A", 2, wage_usd_per_hour=2.5)  # overpays
        with self.assertRaises(OutsideWindow):
            ledger.settle_debt_with_labor(JUL, "A", 1, wage_usd_per_hour=2.5)
        with self.assertRaises(LedgerError):
            ledger.settle_debt_with_labor(MAY, "A", 0, wage_usd_per_hour=2.5)
        with self.assertRaises(LedgerError):
            ledger.record_credit(0, "A", 0)


class TestAtomicity(unittest.TestCase):
    def test_failed_issue_changes_nothing(self):
        ledger = make_ledger(corn_lb=50)
        before = (ledger.outstanding, ledger.next_serial, len(ledger.events))
        with self.assertRaises(InsufficientBacking):
            ledger.issue(MAY, "A", 6)
        self.assertEqual(before, (ledger.outstanding, ledger.next_serial, len(ledger.events)))

    def test_failed_redeem_changes_nothing(self):
        ledger = make_ledger()
        ledger.issue(MAY, "A", 2)
        reserve = dict(ledger.sale_reserve)
        with self.assertRaises(InsufficientTokens):
            ledger.redeem(JUL, "A", 3, "corn")
        self.assertEqual(reserve, ledger.sale_reserve)
        self.assertEqual(ledger.outstanding, 2)

    def test_batch_rolls_back_everything(self):
        ledger = make_ledger()
        with self.assertRaises(CapExceeded):
            with ledger.batch():
                ledger.issue(MAY, "A", 6)
                ledger.issue(MAY, "A", 6)  # over the cap: undo both
        self.assertEqual(ledger.outstanding, 0)
        self.assertEqual(ledger.next_serial, 1)
        self.assertEqual([e.kind for e in ledger.events], ["reserve_in"])

    def test_batch_commits_when_all_succeed(self):
        ledger = make_ledger()
        with ledger.batch():
            ledger.issue(MAY, "A", 3)
            ledger.issue(MAY, "B", 3)
        self.assertEqual(ledger.outstanding, 6)


class TestCalendar(unittest.TestCase):
    def test_month_names(self):
        ledger = make_ledger()
        self.assertEqual(ledger.month_name(0), "Feb")
        self.assertEqual(ledger.month_name(11), "Jan")
        self.assertEqual(ledger.month_name(12), "Feb")
        with self.assertRaises(ValueError):
            ledger.month_name(-1)

    def test_bad_start_month(self):
        with self.assertRaises(ValueError):
            Ledger(CFG.rules("normal"), start_month="Feb.")


if __name__ == "__main__":
    unittest.main()
