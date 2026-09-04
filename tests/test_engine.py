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
    AuthorizationRequested,
    Credit,
    Debit,
    EventAccepted,
    EventRejected,
    Money,
    PostingKind,
    RejectionCode,
    ReversalRequested,
    SettlementRequested,
)
from ledger_core.policy import AssessmentPolicy, UnsupportedFeeCurrencyError
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
        self.assertEqual(result.steps[8].commit_sequence, 10)
        self.assertEqual(result.steps[9].commit_sequence, 11)

    def test_regressed_booked_day_rescans_closed_days_not_the_open_day(self) -> None:
        later_day = process_event(
            empty_assessment_ledger(),
            Credit(
                "day-six-credit",
                6,
                "ACC-001",
                Money.parse(AED, "1.00"),
                6,
            ),
            self.policy,
        )

        earlier_day = process_event(
            later_day.ledger,
            Debit(
                "late-day-five-debit",
                5,
                "ACC-001",
                Money.parse(AED, "2.00"),
                5,
            ),
            self.policy,
        )

        self.assertIsInstance(earlier_day.receipt, EventAccepted)
        self.assertEqual(
            tuple(fee.value_day for fee in fee_postings(earlier_day.ledger)),
            (5,),
        )
        self.assertEqual(
            closing_balance(
                earlier_day.ledger,
                "ACC-001",
                effective_through=6,
            ),
            Money.parse(AED, "-26.00"),
        )

    def test_same_booked_day_rescue_does_not_leave_a_premature_fee(self) -> None:
        funded = process_event(
            empty_assessment_ledger(),
            Credit(
                "initial-funds",
                1,
                "ACC-001",
                Money.parse(AED, "100.00"),
                1,
            ),
            self.policy,
        )
        backdated_debit = process_event(
            funded.ledger,
            Debit(
                "backdated-debit",
                5,
                "ACC-001",
                Money.parse(AED, "150.00"),
                1,
            ),
            self.policy,
        )
        rescued = process_event(
            backdated_debit.ledger,
            Credit(
                "same-booked-day-rescue",
                5,
                "ACC-001",
                Money.parse(AED, "200.00"),
                1,
            ),
            self.policy,
        )

        self.assertEqual(
            tuple(fee.value_day for fee in fee_postings(rescued.ledger)),
            (1, 2, 3, 4),
        )
        self.assertEqual(
            closing_balance(rescued.ledger, "ACC-001", effective_through=5),
            Money.parse(AED, "50.00"),
        )

    def test_regressed_non_posting_event_closes_its_accounts_known_horizon(
        self,
    ) -> None:
        negative_day_five = process_event(
            empty_assessment_ledger(),
            Debit(
                "aed-negative-day-five",
                5,
                "ACC-001",
                Money.parse(AED, "1.00"),
                5,
            ),
            self.policy,
        )
        other_account_day_six = process_event(
            negative_day_five.ledger,
            Credit(
                "bhd-day-six",
                6,
                "ACC-002",
                Money.parse(BHD, "1.000"),
                6,
            ),
            self.policy,
        )

        authorization = process_event(
            other_account_day_six.ledger,
            AuthorizationRequested(
                "late-day-five-authorization",
                5,
                "ACC-001",
                "Auth-late-day-five",
                Money.parse(AED, "1.00"),
                5,
            ),
            self.policy,
        )

        self.assertEqual(
            tuple(fee.value_day for fee in fee_postings(authorization.ledger)),
            (5,),
        )
        self.assertEqual(
            {record.commit_sequence for record in authorization.appended},
            {3, 4},
        )
        view = authorization_view(
            authorization.ledger,
            "Auth-late-day-five",
            effective_through=5,
        )
        self.assertIsNotNone(view)
        assert view is not None
        self.assertIs(view.status, AuthorizationStatus.DECLINED)

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

    def test_backdated_second_settlement_cannot_reopen_a_settled_hold(self) -> None:
        funded = process_event(
            empty_assessment_ledger(),
            Credit("fund", 1, "ACC-001", Money.parse(AED, "500.00"), 1),
            self.policy,
        )
        authorized = process_event(
            funded.ledger,
            AuthorizationRequested(
                "authorize",
                1,
                "ACC-001",
                "Auth-single-use",
                Money.parse(AED, "80.00"),
                1,
            ),
            self.policy,
        )
        settled = process_event(
            authorized.ledger,
            SettlementRequested(
                "settle-first",
                3,
                "ACC-001",
                "Auth-single-use",
                Money.parse(AED, "80.00"),
                3,
            ),
            self.policy,
        )

        repeated = process_event(
            settled.ledger,
            SettlementRequested(
                "settle-backdated",
                4,
                "ACC-001",
                "Auth-single-use",
                Money.parse(AED, "80.00"),
                2,
            ),
            self.policy,
        )

        self.assertIsInstance(repeated.receipt, EventRejected)
        assert isinstance(repeated.receipt, EventRejected)
        self.assertIs(repeated.receipt.code, RejectionCode.AUTHORIZATION_NOT_ACTIVE)
        self.assertFalse(
            any(
                posting.direct_event_id == "settle-backdated"
                for posting in postings(repeated.ledger)
            )
        )
        authorization = authorization_view(
            repeated.ledger,
            "Auth-single-use",
            effective_through=3,
        )
        self.assertIsNotNone(authorization)
        assert authorization is not None
        self.assertIs(authorization.status, AuthorizationStatus.SETTLED)
        self.assertEqual(
            closing_balance(
                repeated.ledger,
                "ACC-001",
                effective_through=3,
            ),
            Money.parse(AED, "420.00"),
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
            Money.parse(AED, "-205.00"),
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

    def test_delimiter_bearing_ids_generate_distinct_record_identities(self) -> None:
        funded = process_event(
            empty_assessment_ledger(),
            Credit(
                "seed",
                1,
                "ACC-001",
                Money.parse(AED, "10.00"),
                1,
            ),
            self.policy,
        )
        first_event = AuthorizationRequested(
            "y:approved:z",
            1,
            "ACC-001",
            "x",
            Money.parse(AED, "1.00"),
            1,
        )
        second_event = AuthorizationRequested(
            "z",
            1,
            "ACC-001",
            "x:approved:y",
            Money.parse(AED, "1.00"),
            1,
        )

        first = process_event(funded.ledger, first_event, self.policy)
        second = process_event(first.ledger, second_event, self.policy)

        self.assertIsInstance(first.receipt, EventAccepted)
        self.assertIsInstance(second.receipt, EventAccepted)
        self.assertIsNotNone(
            authorization_view(second.ledger, "x", effective_through=1)
        )
        self.assertIsNotNone(
            authorization_view(
                second.ledger,
                "x:approved:y",
                effective_through=1,
            )
        )
        record_ids = tuple(record.fact.record_id for record in second.ledger.records)
        self.assertEqual(len(record_ids), len(set(record_ids)))

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

    def test_e7_generates_fees_only_for_days_closed_before_day_five(self) -> None:
        result = replay_events(
            empty_assessment_ledger(), assessment_events()[:7], self.policy
        )
        e7 = result.steps[-1]
        fees = fee_postings(result.ledger, account_id="ACC-001")

        self.assertEqual(tuple(fee.value_day for fee in fees), (2, 4))
        self.assertEqual(
            tuple(fee.amount for fee in fees),
            (Money.parse(AED, "-25.00"),) * 2,
        )
        self.assertEqual({fact.commit_sequence for fact in e7.appended}, {7})
        self.assertEqual(
            tuple(fee.record_id for fee in fees),
            (
                "fee:ACC-001:day:2",
                "fee:ACC-001:day:4",
            ),
        )

    def test_processing_result_exposes_prior_day_fee_and_event_commits(self) -> None:
        before_e9 = replay_events(
            empty_assessment_ledger(), assessment_events()[:8], self.policy
        ).ledger

        e9 = process_event(before_e9, assessment_events()[8], self.policy)

        self.assertEqual(e9.commit_sequence, 10)
        self.assertEqual(
            tuple(record.commit_sequence for record in e9.appended),
            (9, 10, 10),
        )
        fee = e9.appended[0]
        self.assertEqual(fee.fact.record_id, "fee:ACC-001:day:5")
        self.assertIsInstance(e9.receipt, EventAccepted)

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
            9: Money.parse(AED, "-395.00"),
            10: Money.parse(AED, "225.00"),
            11: Money.parse(AED, "225.00"),
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

    def test_post_finalization_forward_event_is_an_explicit_bounded_core_rejection(
        self,
    ) -> None:
        replay = replay_events(
            empty_assessment_ledger(), assessment_events(), self.policy
        )
        finalization = finalize_interest(
            replay.ledger,
            self.policy,
            start_day=1,
            through_day=6,
        )
        next_window_credit = Credit(
            "NEXT-WINDOW-1",
            7,
            "ACC-001",
            Money.parse(AED, "100.00"),
            7,
        )

        result = process_event(
            finalization.ledger,
            next_window_credit,
            self.policy,
        )

        self.assertIsInstance(result.receipt, EventRejected)
        assert isinstance(result.receipt, EventRejected)
        self.assertIs(
            result.receipt.code,
            RejectionCode.POST_FINALIZATION_EVENT_UNSUPPORTED,
        )
        self.assertFalse(
            any(
                posting.direct_event_id == next_window_credit.event_id
                for posting in postings(result.ledger)
            )
        )

    def test_finalization_reconciles_fees_across_quiet_negative_days(self) -> None:
        debit = Debit(
            "quiet-negative",
            1,
            "ACC-001",
            Money.parse(AED, "1.00"),
            1,
        )
        processed = process_event(
            empty_assessment_ledger(), debit, self.policy
        )

        finalization = finalize_interest(
            processed.ledger,
            self.policy,
            start_day=1,
            through_day=6,
        )

        self.assertEqual(
            tuple(fee.value_day for fee in fee_postings(finalization.ledger)),
            (1, 2, 3, 4, 5, 6),
        )
        self.assertEqual(
            closing_balance(
                finalization.ledger,
                "ACC-001",
                effective_through=6,
            ),
            Money.parse(AED, "-151.00"),
        )

    def test_finalization_refuses_an_undefined_fee_currency_atomically(self) -> None:
        debit = Debit(
            "bhd-negative-before-finalization",
            1,
            "ACC-002",
            Money.parse(BHD, "1.000"),
            1,
        )
        processed = process_event(
            empty_assessment_ledger(), debit, self.policy
        )
        records_before = processed.ledger.records

        with self.assertRaisesRegex(
            UnsupportedFeeCurrencyError,
            "no overdraft fee rule exists for BHD",
        ):
            finalize_interest(
                processed.ledger,
                self.policy,
                start_day=1,
                through_day=1,
            )

        self.assertEqual(processed.ledger.records, records_before)

    def test_temporary_same_day_negative_does_not_assess_a_fee(self) -> None:
        debit = Debit(
            "temporary-debit",
            1,
            "ACC-001",
            Money.parse(AED, "1.00"),
            1,
        )
        credit = Credit(
            "same-day-credit",
            1,
            "ACC-001",
            Money.parse(AED, "100.00"),
            1,
        )
        replay = replay_events(
            empty_assessment_ledger(),
            (debit, credit),
            self.policy,
        )

        finalization = finalize_interest(
            replay.ledger,
            self.policy,
            start_day=1,
            through_day=1,
        )

        self.assertEqual(fee_postings(finalization.ledger), ())

    def test_later_booked_event_closes_and_fees_the_prior_day(self) -> None:
        debit = Debit(
            "negative-day-1",
            1,
            "ACC-001",
            Money.parse(AED, "1.00"),
            1,
        )
        first = process_event(empty_assessment_ledger(), debit, self.policy)
        authorization = AuthorizationRequested(
            "advance-to-day-2",
            2,
            "ACC-001",
            "Auth-next-day",
            Money.parse(AED, "1.00"),
            2,
        )

        second = process_event(first.ledger, authorization, self.policy)
        auth = authorization_view(
            second.ledger,
            "Auth-next-day",
            effective_through=2,
        )

        self.assertEqual(
            tuple(fee.value_day for fee in fee_postings(second.ledger)),
            (1,),
        )
        self.assertIsNotNone(auth)
        assert auth is not None
        self.assertIs(auth.status, AuthorizationStatus.DECLINED)

    def test_missing_fee_rule_is_isolated_to_the_account_that_needs_it(self) -> None:
        unsupported_negative = Debit(
            "bhd-negative-day-1",
            1,
            "ACC-002",
            Money.parse(BHD, "1.000"),
            1,
        )
        first = process_event(
            empty_assessment_ledger(), unsupported_negative, self.policy
        )
        next_day_unrelated = Credit(
            "aed-day-2",
            2,
            "ACC-001",
            Money.parse(AED, "1.00"),
            2,
        )

        second = process_event(first.ledger, next_day_unrelated, self.policy)

        self.assertIsInstance(first.receipt, EventAccepted)
        self.assertIsInstance(second.receipt, EventAccepted)
        self.assertTrue(
            any(
                posting.direct_event_id == next_day_unrelated.event_id
                for posting in postings(second.ledger)
            )
        )
        self.assertEqual(
            event_receipt(second.ledger, next_day_unrelated.event_id),
            second.receipt,
        )

        same_account_event = Credit(
            "bhd-day-2",
            2,
            "ACC-002",
            Money.parse(BHD, "1.000"),
            2,
        )
        records_before = second.ledger.records
        with self.assertRaisesRegex(
            UnsupportedFeeCurrencyError,
            "no overdraft fee rule exists for BHD",
        ):
            process_event(second.ledger, same_account_event, self.policy)

        self.assertEqual(second.ledger.records, records_before)
        self.assertIsNone(event_receipt(second.ledger, same_account_event.event_id))

    def test_reversal_is_narrowly_a_direct_debit_compensation(self) -> None:
        replay = replay_events(
            empty_assessment_ledger(), assessment_events()[:5], self.policy
        )
        reversal = ReversalRequested(
            "settlement-reversal",
            5,
            "ACC-001",
            "E5",
            4,
        )

        result = process_event(replay.ledger, reversal, self.policy)

        self.assertIsInstance(result.receipt, EventRejected)
        assert isinstance(result.receipt, EventRejected)
        self.assertIs(
            result.receipt.code,
            RejectionCode.REVERSAL_TARGET_NOT_FOUND,
        )


if __name__ == "__main__":
    unittest.main()
