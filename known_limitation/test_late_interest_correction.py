"""Required red test: a production capability deliberately outside this core."""

from __future__ import annotations

import unittest

from ledger_core.engine import finalize_interest, process_event, replay_events
from ledger_core.journal import closing_balance
from ledger_core.model import AED, Credit, EventAccepted, Money
from ledger_core.policy import AssessmentPolicy
from ledger_core.scenario import assessment_events, empty_assessment_ledger


class LateInterestCorrectionLimitationTest(unittest.TestCase):
    def test_post_finalization_backdate_can_append_an_interest_correction(self) -> None:
        policy = AssessmentPolicy()
        replay = replay_events(
            empty_assessment_ledger(), assessment_events(), policy
        )
        finalized = finalize_interest(
            replay.ledger,
            policy,
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
        result = process_event(finalized.ledger, late_credit, policy)

        # Intentionally red: a production correction workflow could admit this
        # late fact under controlled approval, preserve the original AED 0.93
        # capitalization, and append the AED 0.16 interest delta caused by four
        # additional rounded AED 0.04 accruals (Days 3-6).  This bounded engine
        # instead records a rejection after finalization.  The assertion exposes
        # that missing append-only correction capability; it is not claiming that
        # automatic admission is a universal regulatory requirement.
        self.assertIsInstance(
            result.receipt,
            EventAccepted,
            "known limitation: post-finalization backdates require a controlled "
            "interest-correction workflow",
        )
        self.assertEqual(
            closing_balance(
                result.ledger,
                "ACC-001",
                effective_through=6,
            ),
            Money.parse(AED, "491.09"),
            "accepting the principal is insufficient: the append-only result "
            "must also include the AED 0.16 interest correction",
        )


if __name__ == "__main__":
    unittest.main()
