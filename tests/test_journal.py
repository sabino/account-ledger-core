from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from ledger_core.journal import (
    DuplicateRecordError,
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
    AuthorizationSettled,
    AuthorizationStatus,
    Credit,
    CurrencyMismatchError,
    EventAccepted,
    Money,
    Posting,
    PostingKind,
)


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

    def test_balance_distinguishes_value_day_and_knowledge_cutoff(self) -> None:
        ledger = new_ledger((account(),))
        ledger = append_batch(
            ledger,
            (
                Posting(
                    "posting:E1:1",
                    "A",
                    Money.parse(AED, "10.00"),
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
        ledger = append_batch(
            ledger,
            (
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

    def test_authorization_state_is_folded_from_immutable_facts(self) -> None:
        ledger = new_ledger((account(),))
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
            (approved,),
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
            (settled,),
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


if __name__ == "__main__":
    unittest.main()
