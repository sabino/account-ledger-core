from __future__ import annotations

import unittest

from ledger_core.engine import (
    AlreadyFinalizedError,
    DuplicateEventIdError,
    finalize_interest,
    process_event,
    replay_events,
)
from ledger_core.journal import (
    authorization_view,
    closing_balance,
    event_receipt,
    fee_postings,
    interest_accruals,
    latest_commit_sequence,
    postings,
)
from ledger_core.model import (
    AED,
    BHD,
    AuthorizationStatus,
    Credit,
    EventAccepted,
    EventRejected,
    Money,
    PostingKind,
    RejectionCode,
)
from ledger_core.policy import AssessmentPolicy
from ledger_core.scenario import assessment_events, empty_assessment_ledger


class ReplayEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = AssessmentPolicy()

    def test_replay_preserves_supplied_sequence_instead_of_sorting_days(self) -> None:
        result = replay_events(
            empty_assessment_ledger(), assessment_events(), self.policy
        )

        self.assertEqual(
            tuple(step.receipt.event.event_id for step in result.steps),
            tuple(f"E{index}" for index in range(1, 11)),
        )
        self.assertEqual(result.steps[8].receipt.event.booked_day, 6)
        self.assertEqual(result.steps[9].receipt.event.booked_day, 5)
        self.assertEqual(result.steps[8].commit_sequence, 9)
        self.assertEqual(result.steps[9].commit_sequence, 10)

    def test_missing_authorization_is_a_rejected_event_without_money_moving(self) -> None:
        result = replay_events(
            empty_assessment_ledger(), assessment_events()[:6], self.policy
        )
        receipt = event_receipt(result.ledger, "E6")

        self.assertIsInstance(receipt, EventRejected)
        assert isinstance(receipt, EventRejected)
        self.assertIs(receipt.code, RejectionCode.AUTHORIZATION_NOT_FOUND)
        self.assertFalse(
            any(posting.direct_event_id == "E6" for posting in postings(result.ledger))
        )
        self.assertIsNone(
            authorization_view(
                result.ledger,
                "Auth-Z",
                effective_through=6,
            )
        )

    def test_auth_b_is_a_stored_decline_not_a_processing_error(self) -> None:
        result = replay_events(
            empty_assessment_ledger(), assessment_events()[:8], self.policy
        )
        receipt = event_receipt(result.ledger, "E8")
        auth_b = authorization_view(
            result.ledger,
            "Auth-B",
            effective_through=5,
        )

        self.assertIsInstance(receipt, EventAccepted)
        self.assertIsNotNone(auth_b)
        assert auth_b is not None
        self.assertIs(auth_b.status, AuthorizationStatus.DECLINED)
        self.assertEqual(auth_b.active_hold, Money.zero(AED))
        self.assertEqual(
            closing_balance(result.ledger, "ACC-001", effective_through=5),
            Money.parse(AED, "-230.00"),
        )

    def test_replaying_identical_event_is_an_idempotent_noop(self) -> None:
        event = assessment_events()[0]
        first = process_event(empty_assessment_ledger(), event, self.policy)
        repeated = process_event(first.ledger, event, self.policy)

        self.assertIs(repeated.ledger, first.ledger)
        self.assertEqual(repeated.appended, ())
        self.assertEqual(repeated.commit_sequence, first.commit_sequence)

    def test_reusing_event_id_for_different_content_is_rejected(self) -> None:
        event = assessment_events()[0]
        first = process_event(empty_assessment_ledger(), event, self.policy)
        conflicting = Credit(
            "E1",
            1,
            "ACC-001",
            Money.parse(AED, "1.00"),
            1,
        )

        with self.assertRaises(DuplicateEventIdError):
            process_event(first.ledger, conflicting, self.policy)

        self.assertEqual(latest_commit_sequence(first.ledger), 1)

    def test_currency_mismatch_is_recorded_without_a_posting(self) -> None:
        event = Credit(
            "wrong-currency",
            1,
            "ACC-001",
            Money.parse(BHD, "1.000"),
            1,
        )
        result = process_event(empty_assessment_ledger(), event, self.policy)

        self.assertIsInstance(result.receipt, EventRejected)
        assert isinstance(result.receipt, EventRejected)
        self.assertIs(result.receipt.code, RejectionCode.CURRENCY_MISMATCH)
        self.assertEqual(postings(result.ledger), ())

    def test_e7_generates_three_stable_fees_in_the_same_atomic_commit(self) -> None:
        result = replay_events(
            empty_assessment_ledger(), assessment_events()[:7], self.policy
        )
        e7 = result.steps[-1]
        fees = fee_postings(result.ledger, account_id="ACC-001")

        self.assertEqual(tuple(fee.value_day for fee in fees), (2, 4, 5))
        self.assertEqual(
            tuple(fee.amount for fee in fees),
            (Money.parse(AED, "-25.00"),) * 3,
        )
        self.assertEqual({fact.commit_sequence for fact in e7.appended}, {7})
        self.assertEqual(
            tuple(fee.record_id for fee in fees),
            (
                "fee:ACC-001:day:2",
                "fee:ACC-001:day:4",
                "fee:ACC-001:day:5",
            ),
        )

    def test_e9_compensates_e7_principal_and_preserves_fees(self) -> None:
        result = replay_events(
            empty_assessment_ledger(), assessment_events()[:9], self.policy
        )
        e7_posting = next(
            posting
            for posting in postings(result.ledger)
            if posting.direct_event_id == "E7"
        )
        e9_posting = next(
            posting
            for posting in postings(result.ledger)
            if posting.direct_event_id == "E9"
        )

        self.assertEqual(e9_posting.amount, -e7_posting.amount)
        self.assertEqual(e9_posting.reverses_record_id, e7_posting.record_id)
        self.assertEqual(len(fee_postings(result.ledger)), 3)
        self.assertEqual(
            closing_balance(result.ledger, "ACC-001", effective_through=5),
            Money.parse(AED, "390.00"),
        )

    def test_e10_installments_are_exact_and_keep_the_supplied_order(self) -> None:
        result = replay_events(
            empty_assessment_ledger(), assessment_events(), self.policy
        )
        installments = tuple(
            posting
            for posting in postings(result.ledger)
            if posting.direct_event_id == "E10"
        )

        self.assertEqual(
            tuple(posting.amount.minor_units for posting in installments),
            (3_334, 3_333, 3_333),
        )
        self.assertTrue(
            all(
                posting.kind is PostingKind.INSTALLMENT_CREDIT
                for posting in installments
            )
        )
        self.assertEqual(
            closing_balance(result.ledger, "ACC-002", effective_through=6),
            Money.parse(BHD, "10.000"),
        )

    def test_two_axis_historical_balances_match_the_event_oracle(self) -> None:
        result = replay_events(
            empty_assessment_ledger(), assessment_events(), self.policy
        )
        expected_day_2 = {
            2: Money.parse(AED, "250.00"),
            7: Money.parse(AED, "-395.00"),
            9: Money.parse(AED, "225.00"),
            10: Money.parse(AED, "225.00"),
        }

        for known_through, expected in expected_day_2.items():
            with self.subTest(known_through=known_through):
                self.assertEqual(
                    closing_balance(
                        result.ledger,
                        "ACC-001",
                        effective_through=2,
                        known_through=known_through,
                    ),
                    expected,
                )

    def test_interest_finalization_stores_daily_rounding_and_exact_sums(self) -> None:
        replay = replay_events(
            empty_assessment_ledger(), assessment_events(), self.policy
        )
        finalization = finalize_interest(
            replay.ledger,
            self.policy,
            start_day=1,
            through_day=6,
        )

        aed = interest_accruals(finalization.ledger, account_id="ACC-001")
        bhd = interest_accruals(finalization.ledger, account_id="ACC-002")
        self.assertEqual(
            tuple(accrual.amount.minor_units for accrual in aed),
            (10, 9, 25, 17, 16, 16),
        )
        self.assertEqual(
            tuple(accrual.amount.minor_units for accrual in bhd),
            (0, 0, 0, 0, 4, 4),
        )
        self.assertEqual(
            tuple(posting.amount.minor_units for posting in finalization.capitalizations),
            (93, 8),
        )
        self.assertEqual(
            closing_balance(
                finalization.ledger,
                "ACC-001",
                effective_through=6,
            ),
            Money.parse(AED, "390.93"),
        )
        self.assertEqual(
            closing_balance(
                finalization.ledger,
                "ACC-002",
                effective_through=6,
            ),
            Money.parse(BHD, "10.008"),
        )

    def test_interest_finalization_is_idempotent(self) -> None:
        replay = replay_events(
            empty_assessment_ledger(), assessment_events(), self.policy
        )
        first = finalize_interest(
            replay.ledger,
            self.policy,
            start_day=1,
            through_day=6,
        )
        second = finalize_interest(
            first.ledger,
            self.policy,
            start_day=1,
            through_day=6,
        )

        self.assertIs(second.ledger, first.ledger)
        self.assertEqual(second.final_commit, first.final_commit)
        self.assertEqual(second.capitalizations, first.capitalizations)

    def test_finalization_idempotency_includes_the_complete_window(self) -> None:
        replay = replay_events(
            empty_assessment_ledger(), assessment_events(), self.policy
        )
        first = finalize_interest(
            replay.ledger,
            self.policy,
            start_day=1,
            through_day=6,
        )

        with self.assertRaises(AlreadyFinalizedError):
            finalize_interest(
                first.ledger,
                self.policy,
                start_day=2,
                through_day=6,
            )

    def test_post_finalization_backdate_is_an_explicit_bounded_core_rejection(self) -> None:
        replay = replay_events(
            empty_assessment_ledger(), assessment_events(), self.policy
        )
        finalization = finalize_interest(
            replay.ledger,
            self.policy,
            start_day=1,
            through_day=6,
        )
        late_credit = Credit(
            "LATE-1",
            7,
            "ACC-001",
            Money.parse(AED, "100.00"),
            3,
        )

        result = process_event(finalization.ledger, late_credit, self.policy)

        self.assertIsInstance(result.receipt, EventRejected)
        assert isinstance(result.receipt, EventRejected)
        self.assertIs(
            result.receipt.code,
            RejectionCode.FINALIZED_PERIOD_CORRECTION_UNSUPPORTED,
        )
        self.assertFalse(
            any(
                posting.direct_event_id == "LATE-1"
                for posting in postings(result.ledger)
            )
        )


if __name__ == "__main__":
    unittest.main()
