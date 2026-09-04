from __future__ import annotations

import unittest

from ledger_core.model import (
    AED,
    BHD,
    Account,
    AuthorizationStatus,
    AuthorizationView,
    DomainInvariantError,
    Money,
    RejectionCode,
)
from ledger_core.policy import (
    AcceptSettlement,
    ApproveAuthorization,
    AssessmentPolicy,
    DeclineAuthorization,
    Ratio,
    RejectSettlement,
    UnsupportedFeeCurrencyError,
    capitalization_total,
    daily_interest,
    decide_authorization,
    decide_settlement,
    fee_for_close,
    split_installments,
)


class AssessmentPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = AssessmentPolicy()

    def test_authorization_at_exactly_zero_available_is_approved(self) -> None:
        decision = decide_authorization(
            ledger_balance=Money.parse(AED, "250.00"),
            active_holds=Money.parse(AED, "50.00"),
            requested=Money.parse(AED, "200.00"),
        )

        self.assertIsInstance(decision, ApproveAuthorization)
        assert isinstance(decision, ApproveAuthorization)
        self.assertEqual(decision.available_after_hold, Money.zero(AED))

    def test_authorization_below_zero_available_is_declined(self) -> None:
        decision = decide_authorization(
            ledger_balance=Money.parse(AED, "-230.00"),
            active_holds=Money.zero(AED),
            requested=Money.parse(AED, "90.00"),
        )

        self.assertIsInstance(decision, DeclineAuthorization)
        assert isinstance(decision, DeclineAuthorization)
        self.assertEqual(
            decision.available_after_hold, Money.parse(AED, "-320.00")
        )

    def test_authorization_rejects_negative_holds_and_nonpositive_requests(self) -> None:
        with self.assertRaises(DomainInvariantError):
            decide_authorization(
                ledger_balance=Money.parse(AED, "10.00"),
                active_holds=Money.parse(AED, "-1.00"),
                requested=Money.parse(AED, "1.00"),
            )
        with self.assertRaises(DomainInvariantError):
            decide_authorization(
                ledger_balance=Money.parse(AED, "10.00"),
                active_holds=Money.zero(AED),
                requested=Money.zero(AED),
            )

    def test_settlement_rejects_missing_authorization(self) -> None:
        decision = decide_settlement(
            authorization=None,
            requested=Money.parse(AED, "1.00"),
        )

        self.assertIsInstance(decision, RejectSettlement)
        assert isinstance(decision, RejectSettlement)
        self.assertIs(decision.code, RejectionCode.AUTHORIZATION_NOT_FOUND)

    def test_settlement_requires_a_positive_request(self) -> None:
        with self.assertRaises(DomainInvariantError):
            decide_settlement(
                authorization=None,
                requested=Money.parse(AED, "-1.00"),
            )

    def test_final_capture_releases_unused_hold(self) -> None:
        zero = Money.zero(AED)
        authorization = AuthorizationView(
            account_id="A",
            authorization_id="Auth-A",
            requested_amount=Money.parse(AED, "200.00"),
            status=AuthorizationStatus.ACTIVE,
            active_hold=Money.parse(AED, "200.00"),
            captured_amount=zero,
            released_amount=zero,
        )

        decision = decide_settlement(
            authorization=authorization,
            requested=Money.parse(AED, "185.00"),
        )

        self.assertIsInstance(decision, AcceptSettlement)
        assert isinstance(decision, AcceptSettlement)
        self.assertEqual(decision.captured, Money.parse(AED, "185.00"))
        self.assertEqual(decision.released, Money.parse(AED, "15.00"))

    def test_over_capture_is_rejected(self) -> None:
        zero = Money.zero(AED)
        authorization = AuthorizationView(
            account_id="A",
            authorization_id="Auth-A",
            requested_amount=Money.parse(AED, "2.00"),
            status=AuthorizationStatus.ACTIVE,
            active_hold=Money.parse(AED, "2.00"),
            captured_amount=zero,
            released_amount=zero,
        )

        decision = decide_settlement(
            authorization=authorization,
            requested=Money.parse(AED, "2.01"),
        )

        self.assertIsInstance(decision, RejectSettlement)
        assert isinstance(decision, RejectSettlement)
        self.assertIs(decision.code, RejectionCode.OVER_CAPTURE)

    def test_fee_applies_only_to_negative_aed_close(self) -> None:
        aed_account = Account("A", AED, Money.zero(AED))

        self.assertIsNone(
            fee_for_close(
                self.policy,
                account=aed_account,
                closing=Money.zero(AED),
            )
        )
        self.assertEqual(
            fee_for_close(
                self.policy,
                account=aed_account,
                closing=Money.parse(AED, "-0.01"),
            ),
            Money.parse(AED, "25.00"),
        )

    def test_negative_non_aed_close_fails_explicitly(self) -> None:
        bhd_account = Account("B", BHD, Money.zero(BHD))

        with self.assertRaises(UnsupportedFeeCurrencyError):
            fee_for_close(
                self.policy,
                account=bhd_account,
                closing=Money.parse(BHD, "-0.001"),
            )

    def test_interest_rounding_and_capitalization_use_daily_results(self) -> None:
        closes = (
            Money.parse(AED, "250.00"),
            Money.parse(AED, "225.00"),
            Money.parse(AED, "625.00"),
            Money.parse(AED, "415.00"),
            Money.parse(AED, "390.00"),
            Money.parse(AED, "390.00"),
        )
        accruals = tuple(
            daily_interest(self.policy, closing=closing) for closing in closes
        )

        self.assertEqual(
            tuple(accrual.minor_units for accrual in accruals),
            (10, 9, 25, 17, 16, 16),
        )
        self.assertEqual(
            capitalization_total(
                currency=AED,
                rounded_daily_accruals=accruals,
            ),
            Money.parse(AED, "0.93"),
        )

    def test_ratio_requires_integer_components(self) -> None:
        with self.assertRaises(DomainInvariantError):
            Ratio(True, 2_500)
        with self.assertRaises(DomainInvariantError):
            Ratio(1, True)

    def test_installment_split_delegates_to_exact_minor_unit_allocation(self) -> None:
        installments = split_installments(
            total=Money.parse(BHD, "10.000"),
            count=3,
        )
        self.assertEqual(
            tuple(item.minor_units for item in installments),
            (3_334, 3_333, 3_333),
        )


if __name__ == "__main__":
    unittest.main()
