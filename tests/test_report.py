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

    def test_complete_six_day_projection_matches_the_oracle(self) -> None:
        acc_1 = tuple(day.accounts[0] for day in self.report.days)
        acc_2 = tuple(day.accounts[1] for day in self.report.days)

        self.assertEqual(
            tuple(row.closing_before_capitalization.minor_units for row in acc_1),
            (25_000, 22_500, 62_500, 41_500, 39_000, 39_000),
        )
        self.assertEqual(
            tuple(row.closing_after_finalization.minor_units for row in acc_1),
            (25_000, 22_500, 62_500, 41_500, 39_000, 39_093),
        )
        self.assertEqual(
            tuple(tuple(fee.minor_units for fee in row.fees) for row in acc_1),
            ((), (2_500,), (), (2_500,), (2_500,), ()),
        )
        self.assertEqual(
            tuple(row.interest_accrual.minor_units for row in acc_1),
            (10, 9, 25, 17, 16, 16),
        )
        self.assertEqual(
            tuple(
                tuple((auth.authorization_id, auth.status, auth.active_hold.minor_units) for auth in row.authorizations)
                for row in acc_1
            ),
            (
                (),
                (("Auth-A", AuthorizationStatus.ACTIVE, 20_000),),
                (("Auth-A", AuthorizationStatus.ACTIVE, 20_000),),
                (("Auth-A", AuthorizationStatus.SETTLED, 0),),
                (
                    ("Auth-A", AuthorizationStatus.SETTLED, 0),
                    ("Auth-B", AuthorizationStatus.DECLINED, 0),
                ),
                (
                    ("Auth-A", AuthorizationStatus.SETTLED, 0),
                    ("Auth-B", AuthorizationStatus.DECLINED, 0),
                ),
            ),
        )
        self.assertEqual(
            tuple(tuple(error.event_id for error in row.errors) for row in acc_1),
            ((), (), (), ("E6",), (), ()),
        )

        self.assertEqual(
            tuple(row.closing_before_capitalization.minor_units for row in acc_2),
            (0, 0, 0, 0, 10_000, 10_000),
        )
        self.assertEqual(
            tuple(row.closing_after_finalization.minor_units for row in acc_2),
            (0, 0, 0, 0, 10_000, 10_008),
        )
        self.assertTrue(all(not row.fees for row in acc_2))
        self.assertTrue(all(not row.authorizations for row in acc_2))
        self.assertTrue(all(not row.errors for row in acc_2))
        self.assertEqual(
            tuple(row.interest_accrual.minor_units for row in acc_2),
            (0, 0, 0, 0, 4, 4),
        )

    def test_rendered_report_declares_cutoffs_and_key_outcomes(self) -> None:
        rendered = render_daily_report(self.report)

        self.assertIn("knowledge through commit 11", rendered)
        self.assertIn("interest finalization commit 12", rendered)
        self.assertIn("retain their original assessment day", rendered)
        self.assertIn("Auth-B=declined(no hold)", rendered)
        self.assertIn("E6:authorization_not_found", rendered)
        self.assertIn("ACC-001: AED 0.93", rendered)
        self.assertIn("ACC-002: BHD 0.008", rendered)

    def test_processing_trace_makes_late_listed_e10_and_e7_fees_visible(self) -> None:
        rendered = render_processing_trace(self.replay)

        self.assertLess(
            rendered.index("E9 event_commit=10"),
            rendered.index("E10 event_commit=11"),
        )
        self.assertIn("E10 event_commit=11 booked=D5 value=D5", rendered)
        self.assertIn(
            "commit=9 posting[overdraft_fee] ACC-001 AED -25.00 value=D5",
            rendered,
        )
        self.assertIn(
            "commit=10 posting[reversal] ACC-001 AED 620.00 value=D2",
            rendered,
        )
        self.assertEqual(rendered.count("posting[overdraft_fee]"), 3)
        self.assertIn(
            "E6 event_commit=6 booked=D4 value=D4: rejected",
            rendered,
        )


if __name__ == "__main__":
    unittest.main()
