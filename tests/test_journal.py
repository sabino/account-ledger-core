from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from ledger_core.engine import replay_events
from ledger_core.journal import (
    DuplicateRecordError,
    JournalInvariantError,
    append_batch,
    authorization_view,
    closing_balance,
    latest_commit_sequence,
    new_ledger,
)
from ledger_core.model import (
    AED,
    BHD,
    Account,
    AuthorizationApproved,
    AuthorizationRequested,
    AuthorizationSettled,
    AuthorizationStatus,
    Credit,
    CustomerPostingDirection,
    CurrencyMismatchError,
    Debit,
    EventAccepted,
    EventRejected,
    Money,
    Posting,
    PostingKind,
    RejectionCode,
    ReversalRequested,
    SettlementRequested,
)
from ledger_core.policy import AssessmentPolicy
from ledger_core.scenario import assessment_events, empty_assessment_ledger


def account(account_id: str = "A") -> Account:
    return Account(account_id, AED, Money.zero(AED))


class JournalTest(unittest.TestCase):
    def test_append_returns_new_value_and_preserves_previous_version(self) -> None:
        original = new_ledger((account(),))
        event = Credit("E1", 1, "A", Money.parse(AED, "10.00"), 1)
        updated = append_batch(
            original,
            (
                EventAccepted("event:E1", event),
                Posting(
                    "posting:E1:1",
                    "A",
                    event.amount,
                    1,
                    PostingKind.CREDIT,
                    "E1",
                    "E1",
                ),
            ),
            recorded_day=1,
            policy_version="test-v1",
        )

        self.assertEqual(original.records, ())
        self.assertEqual(latest_commit_sequence(original), 0)
        self.assertEqual(latest_commit_sequence(updated), 1)
        self.assertEqual(len(updated.records), 2)
        self.assertEqual({record.commit_sequence for record in updated.records}, {1})

    def test_duplicate_in_batch_fails_without_changing_original(self) -> None:
        original = new_ledger((account(),))
        posting = Posting(
            "duplicate",
            "A",
            Money.parse(AED, "1.00"),
            1,
            PostingKind.CREDIT,
            "E1",
            "E1",
        )

        with self.assertRaises(DuplicateRecordError):
            append_batch(
                original,
                (posting, posting),
                recorded_day=1,
                policy_version="test-v1",
            )

        self.assertEqual(original.records, ())
        self.assertEqual(original.next_commit_sequence, 1)

    def test_invalid_last_fact_keeps_entire_batch_uncommitted(self) -> None:
        original = new_ledger((account(),))
        valid = Posting(
            "posting:valid",
            "A",
            Money.parse(AED, "1.00"),
            1,
            PostingKind.CREDIT,
            "E1",
            "E1",
        )
        invalid = Posting(
            "posting:wrong-currency",
            "A",
            Money.parse(BHD, "1.000"),
            1,
            PostingKind.CREDIT,
            "E1",
            "E1",
        )

        with self.assertRaises(CurrencyMismatchError):
            append_batch(
                original,
                (valid, invalid),
                recorded_day=1,
                policy_version="test-v1",
            )

        self.assertEqual(original.records, ())

    def test_append_rejects_nonpositive_fact_value_day(self) -> None:
        original = new_ledger((account(),))
        invalid = Posting(
            "posting:invalid-day",
            "A",
            Money.parse(AED, "1.00"),
            0,
            PostingKind.CREDIT,
            "E1",
            "E1",
        )

        with self.assertRaises(JournalInvariantError):
            append_batch(
                original,
                (invalid,),
                recorded_day=1,
                policy_version="test-v1",
            )

        self.assertEqual(original.records, ())

    def test_append_rejects_an_unsupported_fact_type(self) -> None:
        original = new_ledger((account(),))

        with self.assertRaisesRegex(JournalInvariantError, "fact type"):
            append_batch(
                original,
                (object(),),  # pyright: ignore[reportArgumentType]
                recorded_day=1,
                policy_version="test-v1",
            )

        self.assertEqual(original.records, ())

    def test_append_rejects_a_zero_posting(self) -> None:
        original = new_ledger((account(),))
        event = Credit("E1", 1, "A", Money.parse(AED, "1.00"), 1)

        with self.assertRaisesRegex(JournalInvariantError, "cannot be zero"):
            append_batch(
                original,
                (
                    EventAccepted("event:E1", event),
                    Posting(
                        "posting:E1:1",
                        "A",
                        Money.zero(AED),
                        1,
                        PostingKind.CREDIT,
                        "E1",
                        "E1",
                    ),
                ),
                recorded_day=1,
                policy_version="test-v1",
            )

        self.assertEqual(original.records, ())

    def test_balance_distinguishes_value_day_and_knowledge_cutoff(self) -> None:
        ledger = new_ledger((account(),))
        first_event = Credit("E1", 1, "A", Money.parse(AED, "10.00"), 1)
        ledger = append_batch(
            ledger,
            (
                EventAccepted("event:E1", first_event),
                Posting(
                    "posting:E1:1",
                    "A",
                    first_event.amount,
                    1,
                    PostingKind.CREDIT,
                    "E1",
                    "E1",
                ),
            ),
            recorded_day=1,
            policy_version="test-v1",
        )
        before_late_entry = latest_commit_sequence(ledger)
        second_event = Debit("E2", 5, "A", Money.parse(AED, "3.00"), 1)
        ledger = append_batch(
            ledger,
            (
                EventAccepted("event:E2", second_event),
                Posting(
                    "posting:E2:1",
                    "A",
                    Money.parse(AED, "-3.00"),
                    1,
                    PostingKind.DEBIT,
                    "E2",
                    "E2",
                ),
            ),
            recorded_day=5,
            policy_version="test-v1",
        )

        self.assertEqual(
            closing_balance(
                ledger,
                "A",
                effective_through=1,
                known_through=before_late_entry,
            ),
            Money.parse(AED, "10.00"),
        )
        self.assertEqual(
            closing_balance(ledger, "A", effective_through=1),
            Money.parse(AED, "7.00"),
        )

    def test_posting_direction_is_derived_from_one_signed_delta(self) -> None:
        credit = Posting(
            "credit",
            "A",
            Money.parse(AED, "1.00"),
            1,
            PostingKind.CREDIT,
            "E1",
            "E1",
        )
        debit = Posting(
            "debit",
            "A",
            Money.parse(AED, "-1.00"),
            1,
            PostingKind.DEBIT,
            "E2",
            "E2",
        )

        self.assertIs(credit.direction, CustomerPostingDirection.CREDIT)
        self.assertIs(debit.direction, CustomerPostingDirection.DEBIT)
        self.assertEqual(debit.magnitude, Money.parse(AED, "1.00"))

    def test_append_rejects_a_posting_kind_with_the_wrong_sign(self) -> None:
        invalid_cases = (
            (PostingKind.CREDIT, "-1.00"),
            (PostingKind.INSTALLMENT_CREDIT, "-1.00"),
            (PostingKind.DEBIT, "1.00"),
            (PostingKind.SETTLEMENT, "1.00"),
            (PostingKind.REVERSAL, "-1.00"),
            (PostingKind.OVERDRAFT_FEE, "1.00"),
            (PostingKind.INTEREST_CAPITALIZATION, "-1.00"),
        )

        for kind, amount in invalid_cases:
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(
                    JournalInvariantError,
                    "customer-account effect",
                ):
                    append_batch(
                        new_ledger((account(),)),
                        (
                            Posting(
                                f"invalid:{kind.value}",
                                "A",
                                Money.parse(AED, amount),
                                1,
                                kind,
                                "E1" if kind not in (
                                    PostingKind.OVERDRAFT_FEE,
                                    PostingKind.INTEREST_CAPITALIZATION,
                                ) else None,
                                "E1",
                                "target" if kind is PostingKind.REVERSAL else None,
                            ),
                        ),
                        recorded_day=1,
                        policy_version="test-v1",
                    )

    def test_direct_posting_requires_accepted_event_and_matching_cause(self) -> None:
        event = Credit("E1", 1, "A", Money.parse(AED, "1.00"), 1)
        posting = Posting(
            "posting:E1:1",
            "A",
            event.amount,
            1,
            PostingKind.CREDIT,
            "E1",
            "E1",
        )

        with self.assertRaisesRegex(JournalInvariantError, "accepted event"):
            append_batch(
                new_ledger((account(),)),
                (posting,),
                recorded_day=1,
                policy_version="test-v1",
            )

        unrelated = Posting(
            "posting:E1:1",
            "A",
            event.amount,
            1,
            PostingKind.CREDIT,
            "E1",
            "some-other-cause",
        )
        with self.assertRaisesRegex(JournalInvariantError, "cause"):
            append_batch(
                new_ledger((account(),)),
                (EventAccepted("event:E1", event), unrelated),
                recorded_day=1,
                policy_version="test-v1",
            )

    def test_event_receipt_is_first_and_uses_the_booked_day(self) -> None:
        original = new_ledger((account(),))
        event = Credit("E1", 1, "A", Money.parse(AED, "1.00"), 1)
        receipt = EventAccepted("event:E1", event)
        posting = Posting(
            "posting:E1:1",
            "A",
            event.amount,
            1,
            PostingKind.CREDIT,
            "E1",
            "E1",
        )

        with self.assertRaisesRegex(JournalInvariantError, "must be first"):
            append_batch(
                original,
                (posting, receipt),
                recorded_day=1,
                policy_version="test-v1",
            )
        with self.assertRaisesRegex(JournalInvariantError, "recorded day"):
            append_batch(
                original,
                (receipt, posting),
                recorded_day=2,
                policy_version="test-v1",
            )

        self.assertEqual(original.records, ())

    def test_rejected_receipt_requires_typed_code_and_text_message(self) -> None:
        original = new_ledger((account(),))
        event = Debit("E1", 1, "missing", Money.parse(AED, "1.00"), 1)

        invalid_receipts = (
            EventRejected(
                "event:E1",
                event,
                "not-a-code",  # pyright: ignore[reportArgumentType]
                "invalid account",
            ),
            EventRejected(
                "event:E1",
                event,
                RejectionCode.ACCOUNT_NOT_FOUND,
                123,  # pyright: ignore[reportArgumentType]
            ),
            EventRejected(
                "event:invalid",
                object(),  # pyright: ignore[reportArgumentType]
                RejectionCode.ACCOUNT_NOT_FOUND,
                "invalid event",
            ),
        )
        for receipt in invalid_receipts:
            with self.subTest(receipt=receipt):
                with self.assertRaises(JournalInvariantError):
                    append_batch(
                        original,
                        (receipt,),
                        recorded_day=1,
                        policy_version="test-v1",
                    )

        self.assertEqual(original.records, ())

    def test_duplicate_event_receipts_are_rejected(self) -> None:
        original = new_ledger((account(),))
        event = Credit("E1", 1, "A", Money.parse(AED, "1.00"), 1)
        original = append_batch(
            original,
            (
                EventAccepted("event:E1", event),
                Posting(
                    "posting:E1:1",
                    "A",
                    event.amount,
                    1,
                    PostingKind.CREDIT,
                    "E1",
                    "E1",
                ),
            ),
            recorded_day=1,
            policy_version="test-v1",
        )

        with self.assertRaisesRegex(JournalInvariantError, "already exists"):
            append_batch(
                original,
                (EventAccepted("another-receipt-id", event),),
                recorded_day=1,
                policy_version="test-v1",
            )

        self.assertEqual(len(original.records), 2)

    def test_one_batch_cannot_claim_two_input_events(self) -> None:
        original = new_ledger((account(),))
        first = Credit("E1", 1, "A", Money.parse(AED, "1.00"), 1)
        second = Debit("E2", 1, "A", Money.parse(AED, "1.00"), 1)

        with self.assertRaisesRegex(JournalInvariantError, "exactly one receipt"):
            append_batch(
                original,
                (
                    EventAccepted("event:E1", first),
                    EventAccepted("event:E2", second),
                ),
                recorded_day=1,
                policy_version="test-v1",
            )

        self.assertEqual(original.records, ())

    def test_credit_installments_require_the_deterministic_allocation(self) -> None:
        bhd_account = Account("B", BHD, Money.zero(BHD))
        event = Credit("E1", 1, "B", Money.parse(BHD, "10.000"), 1, 3)
        postings = tuple(
            Posting(
                f"posting:E1:{ordinal}",
                "B",
                Money.parse(BHD, amount),
                1,
                PostingKind.INSTALLMENT_CREDIT,
                "E1",
                "E1",
            )
            for ordinal, amount in enumerate(
                ("0.001", "0.001", "9.998"),
                start=1,
            )
        )

        with self.assertRaisesRegex(
            JournalInvariantError,
            "deterministic installment allocation",
        ):
            append_batch(
                new_ledger((bhd_account,)),
                (EventAccepted("event:E1", event), *postings),
                recorded_day=1,
                policy_version="test-v1",
            )

    def test_reversal_requires_an_existing_related_exact_debit(self) -> None:
        debit_event = Debit("E1", 1, "A", Money.parse(AED, "5.00"), 1)
        original = append_batch(
            new_ledger((account(),)),
            (
                EventAccepted("event:E1", debit_event),
                Posting(
                    "posting:E1:1",
                    "A",
                    -debit_event.amount,
                    1,
                    PostingKind.DEBIT,
                    "E1",
                    "E1",
                ),
            ),
            recorded_day=1,
            policy_version="test-v1",
        )

        def reversal_batch(
            *, target_event_id: str, amount: str, target_record_id: str
        ) -> tuple[EventAccepted, Posting]:
            event = ReversalRequested("R1", 2, "A", target_event_id, 1)
            return (
                EventAccepted("event:R1", event),
                Posting(
                    "posting:R1:1",
                    "A",
                    Money.parse(AED, amount),
                    1,
                    PostingKind.REVERSAL,
                    "R1",
                    "R1",
                    target_record_id,
                ),
            )

        invalid_cases = (
            ("E1", "5.00", "missing", "does not exist"),
            ("OTHER", "5.00", "posting:E1:1", "unrelated"),
            ("E1", "4.99", "posting:E1:1", "exact opposite"),
        )
        for target_event_id, amount, target_record_id, message in invalid_cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(JournalInvariantError, message):
                    append_batch(
                        original,
                        reversal_batch(
                            target_event_id=target_event_id,
                            amount=amount,
                            target_record_id=target_record_id,
                        ),
                        recorded_day=2,
                        policy_version="test-v1",
                    )

        updated = append_batch(
            original,
            reversal_batch(
                target_event_id="E1",
                amount="5.00",
                target_record_id="posting:E1:1",
            ),
            recorded_day=2,
            policy_version="test-v1",
        )
        self.assertEqual(
            closing_balance(updated, "A", effective_through=1),
            Money.zero(AED),
        )

        duplicate_target = (
            EventAccepted(
                "event:R2",
                ReversalRequested("R2", 2, "A", "E1", 1),
            ),
            Posting(
                "posting:R2:1",
                "A",
                Money.parse(AED, "5.00"),
                1,
                PostingKind.REVERSAL,
                "R2",
                "R2",
                "posting:E1:1",
            ),
            Posting(
                "posting:R2:2",
                "A",
                Money.parse(AED, "5.00"),
                1,
                PostingKind.REVERSAL,
                "R2",
                "R2",
                "posting:E1:1",
            ),
        )
        with self.assertRaisesRegex(JournalInvariantError, "more than once"):
            append_batch(
                original,
                duplicate_target,
                recorded_day=2,
                policy_version="test-v1",
            )

    def test_authorization_state_is_folded_from_immutable_facts(self) -> None:
        ledger = new_ledger(
            (Account("A", AED, Money.parse(AED, "10.00")),)
        )
        request = AuthorizationRequested(
            "E1",
            1,
            "A",
            "Auth-A",
            Money.parse(AED, "2.00"),
            1,
        )
        approved = AuthorizationApproved(
            "authorization:Auth-A:approved",
            "A",
            "Auth-A",
            Money.parse(AED, "2.00"),
            1,
            "E1",
        )
        ledger = append_batch(
            ledger,
            (EventAccepted("event:E1", request), approved),
            recorded_day=1,
            policy_version="test-v1",
        )
        active = authorization_view(
            ledger, "Auth-A", effective_through=1
        )
        self.assertIsNotNone(active)
        assert active is not None
        self.assertIs(active.status, AuthorizationStatus.ACTIVE)
        self.assertEqual(active.active_hold, Money.parse(AED, "2.00"))

        settlement = SettlementRequested(
            "E2",
            2,
            "A",
            "Auth-A",
            Money.parse(AED, "1.85"),
            2,
        )
        settled = AuthorizationSettled(
            "authorization:Auth-A:settled",
            "A",
            "Auth-A",
            Money.parse(AED, "1.85"),
            Money.parse(AED, "0.15"),
            2,
            "E2",
        )
        ledger = append_batch(
            ledger,
            (
                EventAccepted("event:E2", settlement),
                Posting(
                    "posting:E2:1",
                    "A",
                    Money.parse(AED, "-1.85"),
                    2,
                    PostingKind.SETTLEMENT,
                    "E2",
                    "E2",
                ),
                settled,
            ),
            recorded_day=2,
            policy_version="test-v1",
        )
        final = authorization_view(ledger, "Auth-A", effective_through=2)
        self.assertIsNotNone(final)
        assert final is not None
        self.assertIs(final.status, AuthorizationStatus.SETTLED)
        self.assertEqual(final.active_hold, Money.zero(AED))
        self.assertEqual(final.captured_amount, Money.parse(AED, "1.85"))
        self.assertEqual(final.released_amount, Money.parse(AED, "0.15"))

        with self.assertRaises(FrozenInstanceError):
            setattr(final, "status", AuthorizationStatus.ACTIVE)

    def test_authorization_facts_require_their_exact_accepted_event(self) -> None:
        original = new_ledger((account(),))
        request = AuthorizationRequested(
            "E1",
            1,
            "A",
            "Auth-A",
            Money.parse(AED, "2.00"),
            1,
        )
        approved = AuthorizationApproved(
            "authorization:Auth-A:approved",
            "A",
            "Auth-A",
            Money.parse(AED, "2.00"),
            1,
            "E1",
        )

        with self.assertRaisesRegex(JournalInvariantError, "share its batch"):
            append_batch(
                original,
                (approved,),
                recorded_day=1,
                policy_version="test-v1",
            )
        with self.assertRaisesRegex(JournalInvariantError, "approval or decline"):
            append_batch(
                original,
                (EventAccepted("event:E1", request),),
                recorded_day=1,
                policy_version="test-v1",
            )

        wrong_amount = AuthorizationApproved(
            "authorization:Auth-A:wrong",
            "A",
            "Auth-A",
            Money.parse(AED, "1.00"),
            1,
            "E1",
        )
        with self.assertRaisesRegex(JournalInvariantError, "identity and amount"):
            append_batch(
                original,
                (EventAccepted("event:E1", request), wrong_amount),
                recorded_day=1,
                policy_version="test-v1",
            )

        self.assertEqual(original.records, ())

    def test_accepted_settlement_requires_its_state_transition(self) -> None:
        request = AuthorizationRequested(
            "E1",
            1,
            "A",
            "Auth-A",
            Money.parse(AED, "2.00"),
            1,
        )
        original = append_batch(
            new_ledger((Account("A", AED, Money.parse(AED, "10.00")),)),
            (
                EventAccepted("event:E1", request),
                AuthorizationApproved(
                    "authorization:Auth-A:approved",
                    "A",
                    "Auth-A",
                    Money.parse(AED, "2.00"),
                    1,
                    "E1",
                ),
            ),
            recorded_day=1,
            policy_version="test-v1",
        )
        settlement = SettlementRequested(
            "E2",
            2,
            "A",
            "Auth-A",
            Money.parse(AED, "1.85"),
            2,
        )

        with self.assertRaisesRegex(JournalInvariantError, "state transition"):
            append_batch(
                original,
                (
                    EventAccepted("event:E2", settlement),
                    Posting(
                        "posting:E2:1",
                        "A",
                        Money.parse(AED, "-1.85"),
                        2,
                        PostingKind.SETTLEMENT,
                        "E2",
                        "E2",
                    ),
                ),
                recorded_day=2,
                policy_version="test-v1",
            )

        self.assertEqual(len(original.records), 2)

    def test_raw_append_cannot_backdate_a_second_final_settlement(self) -> None:
        policy = AssessmentPolicy()
        original = replay_events(
            empty_assessment_ledger(),
            assessment_events()[:5],
            policy,
        ).ledger
        settlement = SettlementRequested(
            "settle-again",
            5,
            "ACC-001",
            "Auth-A",
            Money.parse(AED, "100.00"),
            3,
        )
        staged = (
            EventAccepted("event:settle-again", settlement),
            Posting(
                "posting:settle-again:1",
                "ACC-001",
                Money.parse(AED, "-100.00"),
                3,
                PostingKind.SETTLEMENT,
                "settle-again",
                "settle-again",
            ),
            AuthorizationSettled(
                "authorization:Auth-A:settled:settle-again",
                "ACC-001",
                "Auth-A",
                Money.parse(AED, "100.00"),
                Money.parse(AED, "100.00"),
                3,
                "settle-again",
            ),
        )
        records_before = original.records

        with self.assertRaisesRegex(JournalInvariantError, "still active"):
            append_batch(
                original,
                staged,
                recorded_day=5,
                policy_version=policy.version,
            )

        self.assertEqual(original.records, records_before)
        authorization = authorization_view(
            original,
            "Auth-A",
            effective_through=4,
        )
        self.assertIsNotNone(authorization)
        assert authorization is not None
        self.assertIs(authorization.status, AuthorizationStatus.SETTLED)

if __name__ == "__main__":
    unittest.main()
