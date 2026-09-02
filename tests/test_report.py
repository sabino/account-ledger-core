from __future__ import annotations

import unittest

from ledger_core.engine import finalize_interest, replay_events
from ledger_core.model import AED, BHD, AuthorizationStatus, Money
from ledger_core.policy import AssessmentPolicy
from ledger_core.report import build_report, render_daily_report, render_processing_trace
from ledger_core.scenario import (
    ASSESSMENT_DAYS,
    assessment_events,
    empty_assessment_ledger,
)


class ReportTest(unittest.TestCase):
    def setUp(self) -> None:
        policy = AssessmentPolicy()
        self.replay = replay_events(
            empty_assessment_ledger(), assessment_events(), policy
        )
        self.finalization = finalize_interest(
            self.replay.ledger,
            policy,
            start_day=1,
            through_day=6,
        )
        self.report = build_report(self.finalization, days=ASSESSMENT_DAYS)

    def test_daily_rows_expose_every_required_projection(self) -> None:
        day_4_acc_1 = self.report.days[3].accounts[0]
        day_5_acc_1 = self.report.days[4].accounts[0]
        day_6_acc_2 = self.report.days[5].accounts[1]

        self.assertEqual(day_4_acc_1.closing_before_capitalization, Money.parse(AED, "415.00"))
        self.assertEqual(day_4_acc_1.fees, (Money.parse(AED, "25.00"),))
        self.assertEqual(tuple(error.event_id for error in day_4_acc_1.errors), ("E6",))
        self.assertEqual(
            tuple(auth.status for auth in day_5_acc_1.authorizations),
            (AuthorizationStatus.SETTLED, AuthorizationStatus.DECLINED),
        )
        self.assertEqual(day_6_acc_2.interest_accrual, Money.parse(BHD, "0.004"))
        self.assertEqual(day_6_acc_2.closing_after_finalization, Money.parse(BHD, "10.008"))

    def test_rendered_report_declares_cutoffs_and_key_outcomes(self) -> None:
        rendered = render_daily_report(self.report)

        self.assertIn("knowledge through commit 10", rendered)
        self.assertIn("interest finalization commit 11", rendered)
        self.assertIn("Auth-B=declined(no hold)", rendered)
        self.assertIn("E6:authorization_not_found", rendered)
        self.assertIn("ACC-001: AED 0.93", rendered)
        self.assertIn("ACC-002: BHD 0.008", rendered)

    def test_processing_trace_makes_late_listed_e10_and_e7_fees_visible(self) -> None:
        rendered = render_processing_trace(self.replay)

        self.assertLess(rendered.index("E9 commit=9"), rendered.index("E10 commit=10"))
        self.assertIn("E10 commit=10 booked=D5 value=D5", rendered)
        self.assertEqual(rendered.count("posting[overdraft_fee]"), 3)
        self.assertIn("E6 commit=6 booked=D4 value=D4: rejected", rendered)


if __name__ == "__main__":
    unittest.main()
