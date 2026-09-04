from __future__ import annotations

import unittest

from ledger_core.engine import FinalizationResult, finalize_interest, replay_events
from ledger_core.journal import (
    Ledger,
    active_hold_total,
    authorization_view,
    closing_balance,
    event_receipt,
    fee_postings,
    postings,
)
from ledger_core.model import (
    AED,
    BHD,
    AuthorizationStatus,
    EventAccepted,
    EventRejected,
    Money,
    PostingKind,
)
from ledger_core.policy import AssessmentPolicy
from ledger_core.scenario import assessment_events, empty_assessment_ledger


class AcceptanceClaimsTest(unittest.TestCase):
    """Executable verdicts for Claim-1 through Claim-8."""

    ledger: Ledger
    finalization: FinalizationResult

    @classmethod
    def setUpClass(cls) -> None:
        policy = AssessmentPolicy()
        replay = replay_events(
            empty_assessment_ledger(), assessment_events(), policy
        )
        cls.ledger = replay.ledger
        cls.finalization = finalize_interest(
            replay.ledger,
            policy,
            start_day=1,
            through_day=6,
        )

    def test_claim_1_accept_day_2_pre_fee_balance_known_after_e7(self) -> None:
        balance = closing_balance(
            self.ledger,
            "ACC-001",
            effective_through=2,
            known_through=7,
            excluding_kinds=frozenset((PostingKind.OVERDRAFT_FEE,)),
        )
        self.assertEqual(balance, Money.parse(AED, "-370.00"))

    def test_claim_2_refuse_e7_causes_three_fees_not_one(self) -> None:
        fees = fee_postings(self.ledger, account_id="ACC-001")
        self.assertEqual(tuple(fee.value_day for fee in fees), (2, 4, 5))

    def test_claim_3_accept_auth_a_settlement(self) -> None:
        receipt = event_receipt(self.ledger, "E5")
        auth_a = authorization_view(
            self.ledger,
            "Auth-A",
            effective_through=4,
            known_through=5,
        )

        self.assertIsInstance(receipt, EventAccepted)
        self.assertIsNotNone(auth_a)
        assert auth_a is not None
        self.assertIs(auth_a.status, AuthorizationStatus.SETTLED)
        self.assertEqual(auth_a.captured_amount, Money.parse(AED, "185.00"))
        self.assertEqual(auth_a.released_amount, Money.parse(AED, "15.00"))

    def test_claim_4_accept_unknown_authorization_rejects_without_debit(self) -> None:
        receipt = event_receipt(self.ledger, "E6")

        self.assertIsInstance(receipt, EventRejected)
        self.assertFalse(
            any(posting.direct_event_id == "E6" for posting in postings(self.ledger))
        )

    def test_claim_5_accept_active_hold_changes_available_not_ledger(self) -> None:
        ledger_balance = closing_balance(
            self.ledger,
            "ACC-001",
            effective_through=2,
            known_through=3,
        )
        hold = active_hold_total(
            self.ledger,
            "ACC-001",
            effective_through=2,
            known_through=3,
        )

        self.assertEqual(ledger_balance, Money.parse(AED, "250.00"))
        self.assertEqual(hold, Money.parse(AED, "200.00"))
        self.assertEqual(ledger_balance - hold, Money.parse(AED, "50.00"))

    def test_claim_6_refuse_reversal_does_not_remove_independent_fees(self) -> None:
        before_e7 = closing_balance(
            self.ledger,
            "ACC-001",
            effective_through=5,
            known_through=6,
        )
        after_e9 = closing_balance(
            self.ledger,
            "ACC-001",
            effective_through=5,
            known_through=10,
        )

        self.assertEqual(before_e7, Money.parse(AED, "465.00"))
        self.assertEqual(after_e9, Money.parse(AED, "390.00"))
        self.assertEqual(before_e7 - after_e9, Money.parse(AED, "75.00"))
        self.assertEqual(len(fee_postings(self.ledger)), 3)

    def test_claim_7_refuse_three_times_bhd_3_334_exceeds_total(self) -> None:
        installments = tuple(
            posting.amount
            for posting in postings(self.ledger)
            if posting.direct_event_id == "E10"
        )

        self.assertEqual(
            tuple(amount.minor_units for amount in installments),
            (3_334, 3_333, 3_333),
        )
        self.assertEqual(
            sum(amount.minor_units for amount in installments),
            Money.parse(BHD, "10.000").minor_units,
        )
        self.assertNotEqual(3 * 3_334, 10_000)

    def test_claim_8_refuse_capitalization_is_exact_sum_of_daily_rounding(self) -> None:
        for capitalization in self.finalization.capitalizations:
            accrual_total = sum(
                accrual.amount.minor_units
                for accrual in self.finalization.accruals
                if accrual.account_id == capitalization.account_id
            )
            self.assertEqual(capitalization.amount.minor_units, accrual_total)


if __name__ == "__main__":
    unittest.main()
