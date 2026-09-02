"""Run the exact supplied assessment replay and print its audit projections."""

from __future__ import annotations

from ledger_core.engine import finalize_interest, replay_events
from ledger_core.policy import AssessmentPolicy
from ledger_core.report import build_report, render_daily_report, render_processing_trace
from ledger_core.scenario import (
    ASSESSMENT_DAYS,
    assessment_events,
    empty_assessment_ledger,
)


def main() -> None:
    policy = AssessmentPolicy()
    replay = replay_events(
        empty_assessment_ledger(),
        assessment_events(),
        policy,
    )
    finalization = finalize_interest(
        replay.ledger,
        policy,
        start_day=ASSESSMENT_DAYS[0],
        through_day=ASSESSMENT_DAYS[-1],
    )
    report = build_report(finalization, days=ASSESSMENT_DAYS)

    print(render_processing_trace(replay))
    print()
    print(render_daily_report(report))


if __name__ == "__main__":
    main()

