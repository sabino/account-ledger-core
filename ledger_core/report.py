"""Read-only projections and rendering for the assessment replay."""

from __future__ import annotations

from dataclasses import dataclass

from ledger_core.engine import FinalizationResult, ReplayResult
from ledger_core.journal import (
    Ledger,
    authorization_views,
    closing_balance,
    fee_postings,
)
from ledger_core.model import (
    AccountId,
    AuthorizationApproved,
    AuthorizationDeclined,
    AuthorizationSettled,
    AuthorizationStatus,
    AuthorizationView,
    EventAccepted,
    EventRejected,
    InterestAccrual,
    Money,
    Posting,
)


@dataclass(frozen=True, slots=True)
class ErrorView:
    event_id: str
    account_id: AccountId
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class AccountDayReport:
    account_id: AccountId
    closing_before_capitalization: Money
    closing_after_finalization: Money
    fees: tuple[Money, ...]
    authorizations: tuple[AuthorizationView, ...]
    errors: tuple[ErrorView, ...]
    interest_accrual: Money


@dataclass(frozen=True, slots=True)
class DayReport:
    day: int
    accounts: tuple[AccountDayReport, ...]


@dataclass(frozen=True, slots=True)
class AssessmentReport:
    known_through_commit: int
    final_commit: int
    days: tuple[DayReport, ...]
    capitalizations: tuple[Posting, ...]


def build_report(
    finalization: FinalizationResult,
    *,
    days: tuple[int, ...],
) -> AssessmentReport:
    """Build a final-known view while keeping interest's pre-cap basis explicit."""

    ledger = finalization.ledger
    rows = tuple(
        DayReport(
            day=day,
            accounts=tuple(
                _account_day_report(
                    ledger,
                    account.account_id,
                    day,
                    finalization,
                )
                for account in ledger.accounts
            ),
        )
        for day in days
    )
    return AssessmentReport(
        known_through_commit=finalization.pre_capitalization_commit,
        final_commit=finalization.final_commit,
        days=rows,
        capitalizations=finalization.capitalizations,
    )


def _account_day_report(
    ledger: Ledger,
    account_id: AccountId,
    day: int,
    finalization: FinalizationResult,
) -> AccountDayReport:
    before = closing_balance(
        ledger,
        account_id,
        effective_through=day,
        known_through=finalization.pre_capitalization_commit,
    )
    after = closing_balance(
        ledger,
        account_id,
        effective_through=day,
        known_through=finalization.final_commit,
    )
    fees = tuple(
        -posting.amount
        for posting in fee_postings(ledger, account_id=account_id)
        if posting.value_day == day
    )
    authorizations = tuple(
        authorization
        for authorization in authorization_views(
            ledger,
            effective_through=day,
            known_through=finalization.pre_capitalization_commit,
        )
        if authorization.account_id == account_id
    )
    errors = tuple(
        ErrorView(
            event_id=record.fact.event.event_id,
            account_id=record.fact.event.account_id,
            code=record.fact.code.value,
            message=record.fact.message,
        )
        for record in ledger.records
        if record.commit_sequence <= finalization.pre_capitalization_commit
        and record.recorded_day == day
        and isinstance(record.fact, EventRejected)
        and record.fact.event.account_id == account_id
    )
    accrual = next(
        (
            record.fact.amount
            for record in ledger.records
            if isinstance(record.fact, InterestAccrual)
            and record.fact.account_id == account_id
            and record.fact.value_day == day
            and record.commit_sequence == finalization.final_commit
        ),
        Money.zero(before.currency),
    )
    return AccountDayReport(
        account_id=account_id,
        closing_before_capitalization=before,
        closing_after_finalization=after,
        fees=fees,
        authorizations=authorizations,
        errors=errors,
        interest_accrual=accrual,
    )


def render_processing_trace(replay: ReplayResult) -> str:
    lines = ["Processing trace (supplied order; never date-sorted)"]
    for step in replay.steps:
        event = step.receipt.event
        if isinstance(step.receipt, EventAccepted):
            outcome = "accepted"
        else:
            outcome = f"rejected[{step.receipt.code.value}]"
        lines.append(
            f"  {event.event_id} commit={step.commit_sequence} "
            f"booked=D{event.booked_day} value=D{event.value_day}: {outcome}"
        )
        if isinstance(step.receipt, EventRejected):
            lines.append(f"    error: {step.receipt.message}")
        for record in step.appended:
            fact = record.fact
            if isinstance(fact, (EventAccepted, EventRejected)):
                continue
            if isinstance(
                fact,
                (
                    Posting,
                    AuthorizationApproved,
                    AuthorizationDeclined,
                    AuthorizationSettled,
                ),
            ):
                lines.append(f"    {_render_effect(fact)}")
    return "\n".join(lines)


def _render_effect(
    fact: Posting | AuthorizationApproved | AuthorizationDeclined | AuthorizationSettled,
) -> str:
    if isinstance(fact, Posting):
        reversal = (
            f" reverses={fact.reverses_record_id}"
            if fact.reverses_record_id is not None
            else ""
        )
        return (
            f"posting[{fact.kind.value}] {fact.account_id} "
            f"{fact.amount} value=D{fact.value_day}{reversal}"
        )
    if isinstance(fact, AuthorizationApproved):
        return (
            f"authorization[{fact.authorization_id}] active "
            f"hold={fact.amount}"
        )
    if isinstance(fact, AuthorizationDeclined):
        after = fact.available_before_hold - fact.amount
        return (
            f"authorization[{fact.authorization_id}] declined "
            f"available_after={after}"
        )
    return (
        f"authorization[{fact.authorization_id}] settled "
        f"captured={fact.captured_amount} released={fact.released_amount}"
    )


def render_daily_report(report: AssessmentReport) -> str:
    lines = [
        (
            "Daily financial view "
            f"(final event knowledge through commit {report.known_through_commit}; "
            f"interest finalization commit {report.final_commit})"
        )
    ]
    for day in report.days:
        lines.append(f"Day {day.day}")
        for account in day.accounts:
            close = str(account.closing_after_finalization)
            if account.closing_after_finalization != account.closing_before_capitalization:
                close += (
                    " (pre-capitalization basis "
                    f"{account.closing_before_capitalization})"
                )
            fees = ", ".join(str(fee) for fee in account.fees) or "none"
            auths = ", ".join(
                _render_authorization_view(authorization)
                for authorization in account.authorizations
            ) or "none"
            errors = ", ".join(
                f"{error.event_id}:{error.code}" for error in account.errors
            ) or "none"
            lines.append(
                f"  {account.account_id}: close={close}; fees={fees}; "
                f"interest={account.interest_accrual}; auth={auths}; errors={errors}"
            )

    lines.append("Day 6 capitalization")
    lines.extend(
        f"  {posting.account_id}: {posting.amount}"
        for posting in report.capitalizations
    )
    return "\n".join(lines)


def _render_authorization_view(authorization: AuthorizationView) -> str:
    if authorization.status is AuthorizationStatus.ACTIVE:
        return (
            f"{authorization.authorization_id}=active"
            f"(hold {authorization.active_hold})"
        )
    if authorization.status is AuthorizationStatus.DECLINED:
        return f"{authorization.authorization_id}=declined(no hold)"
    return (
        f"{authorization.authorization_id}=settled"
        f"(captured {authorization.captured_amount}, "
        f"released {authorization.released_amount})"
    )
