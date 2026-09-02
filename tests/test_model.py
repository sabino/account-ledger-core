from __future__ import annotations

import unittest

from ledger_core.model import (
    AED,
    BHD,
    CurrencyMismatchError,
    DomainInvariantError,
    Money,
    MoneyPrecisionError,
    allocate_evenly,
    round_ratio_half_even,
)


class MoneyTest(unittest.TestCase):
    def test_parse_and_format_currency_specific_precision(self) -> None:
        self.assertEqual(Money.parse(AED, "1200.00").minor_units, 120_000)
        self.assertEqual(str(Money.parse(AED, "-0.01")), "AED -0.01")
        self.assertEqual(Money.parse(BHD, "10.000").minor_units, 10_000)
        self.assertEqual(str(Money.parse(BHD, "0.004")), "BHD 0.004")

    def test_parse_rejects_excess_precision(self) -> None:
        with self.assertRaises(MoneyPrecisionError):
            Money.parse(AED, "1.001")
        with self.assertRaises(MoneyPrecisionError):
            Money.parse(BHD, "1.0001")

    def test_cross_currency_arithmetic_is_rejected(self) -> None:
        with self.assertRaises(CurrencyMismatchError):
            _ = Money.parse(AED, "1.00") + Money.parse(BHD, "1.000")

    def test_round_ratio_uses_ties_to_even(self) -> None:
        self.assertEqual(round_ratio_half_even(5, 2), 2)
        self.assertEqual(round_ratio_half_even(7, 2), 4)
        self.assertEqual(round_ratio_half_even(-5, 2), -2)
        self.assertEqual(round_ratio_half_even(-7, 2), -4)

    def test_round_ratio_rejects_nonpositive_denominator(self) -> None:
        with self.assertRaises(DomainInvariantError):
            round_ratio_half_even(1, 0)

    def test_even_allocation_preserves_total_and_bounds_difference(self) -> None:
        installments = allocate_evenly(Money.parse(BHD, "10.000"), 3)

        self.assertEqual(
            tuple(item.minor_units for item in installments),
            (3_334, 3_333, 3_333),
        )
        self.assertEqual(sum(item.minor_units for item in installments), 10_000)
        self.assertEqual(
            max(item.minor_units for item in installments)
            - min(item.minor_units for item in installments),
            1,
        )


if __name__ == "__main__":
    unittest.main()
