from __future__ import annotations

from collections.abc import Callable
import unittest

from ledger_core.model import (
    AED,
    BHD,
    Account,
    AuthorizationRequested,
    Credit,
    Currency,
    CurrencyMismatchError,
    DomainInvariantError,
    Debit,
    Money,
    MoneyPrecisionError,
    ReversalRequested,
    SettlementRequested,
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

    def test_parse_is_exact_beyond_decimal_context_precision(self) -> None:
        amount = Money.parse(AED, "1234567890123456789012345678.90")

        self.assertEqual(
            amount.minor_units,
            123456789012345678901234567890,
        )
        self.assertEqual(
            amount.format_amount(),
            "1234567890123456789012345678.90",
        )

    def test_cross_currency_arithmetic_is_rejected(self) -> None:
        with self.assertRaises(CurrencyMismatchError):
            _ = Money.parse(AED, "1.00") + Money.parse(BHD, "1.000")

    def test_direct_construction_rejects_non_integer_minor_units(self) -> None:
        for invalid in (True, 1.5, "100", None):
            with self.subTest(invalid=invalid):
                with self.assertRaises(DomainInvariantError):
                    Money(AED, invalid)  # pyright: ignore[reportArgumentType]

    def test_money_requires_a_currency_value(self) -> None:
        with self.assertRaises(DomainInvariantError):
            Money("AED", 100)  # pyright: ignore[reportArgumentType]

    def test_currency_precision_requires_an_integer(self) -> None:
        for invalid in (True, 2.0, "2", None):
            with self.subTest(invalid=invalid):
                with self.assertRaises(DomainInvariantError):
                    Currency("TST", invalid)  # pyright: ignore[reportArgumentType]

    def test_input_events_reject_zero_and_negative_amounts(self) -> None:
        constructors: tuple[Callable[[Money], object], ...] = (
            lambda amount: Credit("E1", 1, "A", amount, 1),
            lambda amount: Debit("E2", 1, "A", amount, 1),
            lambda amount: AuthorizationRequested(
                "E3", 1, "A", "Auth-A", amount, 1
            ),
            lambda amount: SettlementRequested(
                "E4", 1, "A", "Auth-A", amount, 1
            ),
        )

        for constructor in constructors:
            for amount in (Money.zero(AED), Money.parse(AED, "-0.01")):
                with self.subTest(constructor=constructor, amount=amount):
                    with self.assertRaises(DomainInvariantError):
                        constructor(amount)

    def test_credit_rejects_more_installments_than_minor_units(self) -> None:
        with self.assertRaisesRegex(DomainInvariantError, "minor units"):
            Credit("E1", 1, "A", Money.parse(AED, "0.01"), 1, installments=2)

    def test_account_and_reference_identifiers_require_text(self) -> None:
        amount = Money.parse(AED, "1.00")
        invalid_calls: tuple[Callable[[], object], ...] = (
            lambda: Account(1, AED, Money.zero(AED)),  # pyright: ignore[reportArgumentType]
            lambda: Credit("E1", 1, 1, amount, 1),  # pyright: ignore[reportArgumentType]
            lambda: AuthorizationRequested(
                "E2",
                1,
                "A",
                1,  # pyright: ignore[reportArgumentType]
                amount,
                1,
            ),
            lambda: SettlementRequested(
                "E3",
                1,
                "A",
                1,  # pyright: ignore[reportArgumentType]
                amount,
                1,
            ),
            lambda: ReversalRequested(
                "E4",
                1,
                "A",
                1,  # pyright: ignore[reportArgumentType]
                1,
            ),
        )

        for invalid_call in invalid_calls:
            with self.subTest(invalid_call=invalid_call):
                with self.assertRaises(DomainInvariantError):
                    invalid_call()

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
