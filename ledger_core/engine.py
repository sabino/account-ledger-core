"""Functional orchestration: input event -> staged facts -> one atomic append."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ledger_core.journal import (
    Ledger,
    UnknownAccountError,
    account_for,
    active_hold_total,
    append_batch,
    authorization_view,
    closing_balance,
    closing_balance_from_postings,
    finalized_through,
    has_record_id,
    interest_accruals,
    latest_commit_sequence,
    latest_recorded_day,
    postings,
)
from ledger_core.model import (
    Account,
    AuthorizationApproved,
    AuthorizationDeclined,
    AuthorizationFact,
    AuthorizationRequested,
    AuthorizationSettled,
    Credit,
    Debit,
    EventAccepted,
    EventReceipt,
    EventRejected,
    InputEvent,
    InterestAccrual,
    InterestFinalized,
    JournalFact,
    Money,
    Posting,
    PostingKind,
    RejectionCode,
    SettlementRequested,
    StoredFact,
)
from ledger_core.policy import (
    AcceptSettlement,
    ApproveAuthorization,
    AssessmentPolicy,
    RejectSettlement,
    UnsupportedFeeCurrencyError,
    capitalization_total,
    daily_interest,
    decide_authorization,
    decide_settlement,
    fee_for_close,
    split_installments,
)


class DuplicateEventIdError(ValueError):
    """Raised when the same event ID is reused with different content."""


class AlreadyFinalizedError(ValueError):
    """Raised when a different interest finalization is attempted."""


@dataclass(frozen=True, slots=True)
class ProcessResult:
    ledger: Ledger
    receipt: EventReceipt
    appended: tuple[StoredFact, ...]

    @property
    def commit_sequence(self) -> int:
        if self.appended:
            return self.appended[0].commit_sequence
        existing = _stored_receipt(self.ledger, self.receipt.event.event_id)
        if existing is None:
            raise RuntimeError("event receipt has no journal position")
        return existing.commit_sequence


@dataclass(frozen=True, slots=True)
class ReplayResult:
    ledger: Ledger
    steps: tuple[ProcessResult, ...]


@dataclass(frozen=True, slots=True)
class FinalizationResult:
    ledger: Ledger
    start_day: int
    through_day: int
    pre_capitalization_commit: int
    final_commit: int
    accruals: tuple[InterestAccrual, ...]
    capitalizations: tuple[Posting, ...]


def process_event(
    ledger: Ledger,
    event: InputEvent,
    policy: AssessmentPolicy,
) -> ProcessResult:
    """Process one event without mutating the supplied ledger value."""

    prior = _stored_receipt(ledger, event.event_id)
    if prior is not None:
        receipt = prior.fact
        assert isinstance(receipt, (EventAccepted, EventRejected))
        if receipt.event != event:
            raise DuplicateEventIdError(
                f"event ID {event.event_id} was already used for different content"
            )
        return ProcessResult(ledger=ledger, receipt=receipt, appended=())

    closed_through = finalized_through(ledger)
    if closed_through is not None and event.value_day <= closed_through:
        return _append_rejection(
            ledger,
            event,
            policy,
            RejectionCode.FINALIZED_PERIOD_CORRECTION_UNSUPPORTED,
            (
                f"value day {event.value_day} is inside the finalized "
                f"interest window through day {closed_through}"
            ),
        )

    try:
        account = account_for(ledger, event.account_id)
    except UnknownAccountError:
        return _append_rejection(
            ledger,
            event,
            policy,
            RejectionCode.ACCOUNT_NOT_FOUND,
            f"account does not exist: {event.account_id}",
        )

    event_amount = _event_amount(event)
    if event_amount is not None and event_amount.currency != account.currency:
        return _append_rejection(
            ledger,
            event,
            policy,
            RejectionCode.CURRENCY_MISMATCH,
            (
                f"account {account.account_id} uses {account.currency.code}, "
                f"not {event_amount.currency.code}"
            ),
        )

    facts = _stage_event_facts(ledger, account, event, policy)
    receipt = facts[0]
    if isinstance(receipt, EventRejected):
        return _append_facts(ledger, event, policy, facts, receipt)
    if not isinstance(receipt, EventAccepted):
        raise RuntimeError("the first staged fact must be an event receipt")

    direct_postings = tuple(fact for fact in facts if isinstance(fact, Posting))
    if not direct_postings:
        return _append_facts(ledger, event, policy, facts, receipt)

    # Build and discard a candidate immutable value so every direct fact is
    # validated before policy-derived fees are calculated.
    candidate = append_batch(
        ledger,
        facts,
        recorded_day=event.booked_day,
        policy_version=policy.version,
    )
    try:
        fees = _new_overdraft_fees(
            candidate,
            account,
            event,
            direct_postings,
            policy,
        )
    except UnsupportedFeeCurrencyError as error:
        return _append_rejection(
            ledger,
            event,
            policy,
            RejectionCode.UNSUPPORTED_FEE_CURRENCY,
            str(error),
        )
    return _append_facts(ledger, event, policy, facts + fees, receipt)


def replay_events(
    ledger: Ledger,
    events: Iterable[InputEvent],
    policy: AssessmentPolicy,
) -> ReplayResult:
    """Fold events exactly as supplied; never sort by booked day or value day."""

    current = ledger
    steps: list[ProcessResult] = []
    for event in events:
        result = process_event(current, event, policy)
        current = result.ledger
        steps.append(result)
    return ReplayResult(ledger=current, steps=tuple(steps))


def finalize_interest(
    ledger: Ledger,
    policy: AssessmentPolicy,
    *,
    start_day: int,
    through_day: int,
) -> FinalizationResult:
    """Accrue rounded daily interest and append each account's exact sum."""

    if start_day <= 0 or through_day < start_day:
        raise ValueError("interest window must be a non-empty positive day range")

    prior_finalization = _stored_finalization(ledger)
    if prior_finalization is not None:
        finalized = prior_finalization.fact
        assert isinstance(finalized, InterestFinalized)
        if (
            finalized.start_day != start_day
            or finalized.through_day != through_day
            or prior_finalization.policy_version != policy.version
        ):
            raise AlreadyFinalizedError("interest was already finalized differently")
        commit = prior_finalization.commit_sequence
        return FinalizationResult(
            ledger=ledger,
            start_day=start_day,
            through_day=through_day,
            pre_capitalization_commit=commit - 1,
            final_commit=commit,
            accruals=tuple(
                accrual
                for accrual in interest_accruals(ledger)
                if _commit_for_record(ledger, accrual.record_id) == commit
            ),
            capitalizations=tuple(
                posting
                for posting in postings(ledger, known_through=commit)
                if posting.kind is PostingKind.INTEREST_CAPITALIZATION
                and _commit_for_record(ledger, posting.record_id) == commit
            ),
        )

    finalization_id = _interest_finalization_id(start_day, through_day)
    fee_reconciled_ledger = _reconcile_overdraft_fees_through(
        ledger,
        policy,
        start_day=start_day,
        through_day=through_day,
        recorded_day=through_day,
        caused_by=f"{finalization_id}:fee-reconciliation",
    )
    pre_capitalization_commit = latest_commit_sequence(fee_reconciled_ledger)
    accrual_facts: list[InterestAccrual] = []
    capitalization_facts: list[Posting] = []

    for account in fee_reconciled_ledger.accounts:
        account_accruals: list[Money] = []
        for day in range(start_day, through_day + 1):
            basis = closing_balance(
                fee_reconciled_ledger,
                account.account_id,
                effective_through=day,
                known_through=pre_capitalization_commit,
            )
            accrual = daily_interest(policy, closing=basis)
            account_accruals.append(accrual)
            accrual_facts.append(
                InterestAccrual(
                    record_id=_interest_accrual_id(account.account_id, day),
                    account_id=account.account_id,
                    value_day=day,
                    basis=basis,
                    amount=accrual,
                )
            )

        capitalization = capitalization_total(
            policy,
            currency=account.currency,
            rounded_daily_accruals=tuple(account_accruals),
        )
        if capitalization.minor_units != 0:
            capitalization_facts.append(
                Posting(
                    record_id=_capitalization_id(account.account_id, through_day),
                    account_id=account.account_id,
                    amount=capitalization,
                    value_day=through_day,
                    kind=PostingKind.INTEREST_CAPITALIZATION,
                    direct_event_id=None,
                    caused_by=finalization_id,
                )
            )

    marker = InterestFinalized(
        record_id=finalization_id,
        start_day=start_day,
        through_day=through_day,
    )
    facts: tuple[JournalFact, ...] = (
        *accrual_facts,
        *capitalization_facts,
        marker,
    )
    updated = append_batch(
        fee_reconciled_ledger,
        facts,
        recorded_day=through_day,
        policy_version=policy.version,
    )
    return FinalizationResult(
        ledger=updated,
        start_day=start_day,
        through_day=through_day,
        pre_capitalization_commit=pre_capitalization_commit,
        final_commit=latest_commit_sequence(updated),
        accruals=tuple(accrual_facts),
        capitalizations=tuple(capitalization_facts),
    )


def _stage_event_facts(
    ledger: Ledger,
    account: Account,
    event: InputEvent,
    policy: AssessmentPolicy,
) -> tuple[JournalFact, ...]:
    accepted = EventAccepted(_event_record_id(event.event_id), event)

    if isinstance(event, Credit):
        installments = split_installments(
            policy,
            total=event.amount,
            count=event.installments,
        )
        kind = (
            PostingKind.CREDIT
            if event.installments == 1
            else PostingKind.INSTALLMENT_CREDIT
        )
        return (
            accepted,
            *(
                Posting(
                    record_id=_posting_record_id(event.event_id, ordinal),
                    account_id=event.account_id,
                    amount=amount,
                    value_day=event.value_day,
                    kind=kind,
                    direct_event_id=event.event_id,
                    caused_by=event.event_id,
                )
                for ordinal, amount in enumerate(installments, start=1)
            ),
        )

    if isinstance(event, Debit):
        return (
            accepted,
            Posting(
                record_id=_posting_record_id(event.event_id, 1),
                account_id=event.account_id,
                amount=-event.amount,
                value_day=event.value_day,
                kind=PostingKind.DEBIT,
                direct_event_id=event.event_id,
                caused_by=event.event_id,
            ),
        )

    if isinstance(event, AuthorizationRequested):
        if _authorization_exists(ledger, event.authorization_id):
            return (
                EventRejected(
                    _event_record_id(event.event_id),
                    event,
                    RejectionCode.AUTHORIZATION_ALREADY_EXISTS,
                    f"authorization already exists: {event.authorization_id}",
                ),
            )
        balance = closing_balance(
            ledger,
            account.account_id,
            effective_through=event.value_day,
        )
        holds = active_hold_total(
            ledger,
            account.account_id,
            effective_through=event.value_day,
        )
        decision = decide_authorization(
            policy,
            ledger_balance=balance,
            active_holds=holds,
            requested=event.amount,
        )
        if isinstance(decision, ApproveAuthorization):
            authorization_fact: AuthorizationFact = AuthorizationApproved(
                record_id=_authorization_record_id(
                    event.authorization_id, "approved", event.event_id
                ),
                account_id=event.account_id,
                authorization_id=event.authorization_id,
                amount=decision.hold,
                value_day=event.value_day,
                source_event_id=event.event_id,
            )
        else:
            authorization_fact = AuthorizationDeclined(
                record_id=_authorization_record_id(
                    event.authorization_id, "declined", event.event_id
                ),
                account_id=event.account_id,
                authorization_id=event.authorization_id,
                amount=decision.requested,
                value_day=event.value_day,
                source_event_id=event.event_id,
                available_before_hold=decision.available_before_hold,
            )
        return accepted, authorization_fact

    if isinstance(event, SettlementRequested):
        current_authorization = authorization_view(
            ledger,
            event.authorization_id,
            effective_through=event.value_day,
        )
        if (
            current_authorization is not None
            and current_authorization.account_id != event.account_id
        ):
            return (
                EventRejected(
                    _event_record_id(event.event_id),
                    event,
                    RejectionCode.AUTHORIZATION_ACCOUNT_MISMATCH,
                    "settlement account differs from the authorization account",
                ),
            )
        decision = decide_settlement(
            policy,
            authorization=current_authorization,
            requested=event.amount,
        )
        if isinstance(decision, RejectSettlement):
            return (
                EventRejected(
                    _event_record_id(event.event_id),
                    event,
                    decision.code,
                    decision.message,
                ),
            )
        return (
            accepted,
            Posting(
                record_id=_posting_record_id(event.event_id, 1),
                account_id=event.account_id,
                amount=-decision.captured,
                value_day=event.value_day,
                kind=PostingKind.SETTLEMENT,
                direct_event_id=event.event_id,
                caused_by=event.event_id,
            ),
            _settlement_fact(event, decision),
        )

    targets = tuple(
        posting
        for posting in postings(ledger)
        if posting.direct_event_id == event.target_event_id
        and posting.account_id == event.account_id
        and posting.kind is PostingKind.DEBIT
    )
    if not targets:
        return (
            EventRejected(
                _event_record_id(event.event_id),
                event,
                RejectionCode.REVERSAL_TARGET_NOT_FOUND,
                f"no reversible debit posting exists for event {event.target_event_id}",
            ),
        )
    already_reversed = frozenset(
        posting.reverses_record_id
        for posting in postings(ledger)
        if posting.reverses_record_id is not None
    )
    if any(target.record_id in already_reversed for target in targets):
        return (
            EventRejected(
                _event_record_id(event.event_id),
                event,
                RejectionCode.REVERSAL_ALREADY_APPLIED,
                f"event {event.target_event_id} was already reversed",
            ),
        )
    return (
        accepted,
        *(
            Posting(
                record_id=_posting_record_id(event.event_id, ordinal),
                account_id=event.account_id,
                amount=-target.amount,
                value_day=event.value_day,
                kind=PostingKind.REVERSAL,
                direct_event_id=event.event_id,
                caused_by=event.event_id,
                reverses_record_id=target.record_id,
            )
            for ordinal, target in enumerate(targets, start=1)
        ),
    )


def _settlement_fact(
    event: SettlementRequested, decision: AcceptSettlement
) -> AuthorizationSettled:
    return AuthorizationSettled(
        record_id=_authorization_record_id(
            event.authorization_id, "settled", event.event_id
        ),
        account_id=event.account_id,
        authorization_id=event.authorization_id,
        captured_amount=decision.captured,
        released_amount=decision.released,
        value_day=event.value_day,
        source_event_id=event.event_id,
    )


def _new_overdraft_fees(
    candidate: Ledger,
    account: Account,
    event: InputEvent,
    direct_postings: tuple[Posting, ...],
    policy: AssessmentPolicy,
) -> tuple[Posting, ...]:
    affected_from = min(posting.value_day for posting in direct_postings)
    horizon = latest_recorded_day(candidate)
    return _missing_overdraft_fees(
        candidate,
        account,
        policy,
        start_day=affected_from,
        through_day=horizon,
        caused_by=event.event_id,
    )


def _reconcile_overdraft_fees_through(
    ledger: Ledger,
    policy: AssessmentPolicy,
    *,
    start_day: int,
    through_day: int,
    recorded_day: int,
    caused_by: str,
) -> Ledger:
    generated: list[Posting] = []
    for account in ledger.accounts:
        generated.extend(
            _missing_overdraft_fees(
                ledger,
                account,
                policy,
                start_day=start_day,
                through_day=through_day,
                caused_by=caused_by,
                prior_generated=tuple(generated),
            )
        )
    if not generated:
        return ledger
    return append_batch(
        ledger,
        generated,
        recorded_day=recorded_day,
        policy_version=policy.version,
    )


def _missing_overdraft_fees(
    ledger: Ledger,
    account: Account,
    policy: AssessmentPolicy,
    *,
    start_day: int,
    through_day: int,
    caused_by: str,
    prior_generated: tuple[Posting, ...] = (),
) -> tuple[Posting, ...]:
    existing = postings(ledger)
    generated: list[Posting] = []

    for day in range(start_day, through_day + 1):
        record_id = _fee_record_id(account.account_id, day)
        if has_record_id(ledger, record_id) or any(
            posting.record_id == record_id
            for posting in (*prior_generated, *generated)
        ):
            continue
        close = closing_balance_from_postings(
            account,
            (*existing, *prior_generated, *generated),
            effective_through=day,
        )
        charge = fee_for_close(policy, account=account, closing=close)
        if charge is None:
            continue
        generated.append(
            Posting(
                record_id=record_id,
                account_id=account.account_id,
                amount=-charge,
                value_day=day,
                kind=PostingKind.OVERDRAFT_FEE,
                direct_event_id=None,
                caused_by=caused_by,
            )
        )
    return tuple(generated)


def _append_rejection(
    ledger: Ledger,
    event: InputEvent,
    policy: AssessmentPolicy,
    code: RejectionCode,
    message: str,
) -> ProcessResult:
    receipt = EventRejected(_event_record_id(event.event_id), event, code, message)
    return _append_facts(ledger, event, policy, (receipt,), receipt)


def _append_facts(
    ledger: Ledger,
    event: InputEvent,
    policy: AssessmentPolicy,
    facts: tuple[JournalFact, ...],
    receipt: EventReceipt,
) -> ProcessResult:
    updated = append_batch(
        ledger,
        facts,
        recorded_day=event.booked_day,
        policy_version=policy.version,
    )
    appended = updated.records[len(ledger.records) :]
    return ProcessResult(ledger=updated, receipt=receipt, appended=appended)


def _event_amount(event: InputEvent) -> Money | None:
    if isinstance(
        event,
        (Credit, Debit, AuthorizationRequested, SettlementRequested),
    ):
        return event.amount
    return None


def _authorization_exists(ledger: Ledger, authorization_id: str) -> bool:
    return any(
        isinstance(
            record.fact,
            (AuthorizationApproved, AuthorizationDeclined, AuthorizationSettled),
        )
        and record.fact.authorization_id == authorization_id
        for record in ledger.records
    )


def _stored_receipt(ledger: Ledger, event_id: str) -> StoredFact | None:
    return next(
        (
            record
            for record in ledger.records
            if isinstance(record.fact, (EventAccepted, EventRejected))
            and record.fact.event.event_id == event_id
        ),
        None,
    )


def _stored_finalization(ledger: Ledger) -> StoredFact | None:
    return next(
        (
            record
            for record in ledger.records
            if isinstance(record.fact, InterestFinalized)
        ),
        None,
    )


def _commit_for_record(ledger: Ledger, record_id: str) -> int | None:
    return next(
        (
            record.commit_sequence
            for record in ledger.records
            if record.fact.record_id == record_id
        ),
        None,
    )


def _event_record_id(event_id: str) -> str:
    return f"event:{event_id}"


def _posting_record_id(event_id: str, ordinal: int) -> str:
    return f"posting:{event_id}:{ordinal}"


def _authorization_record_id(
    authorization_id: str, outcome: str, event_id: str
) -> str:
    return f"authorization:{authorization_id}:{outcome}:{event_id}"


def _fee_record_id(account_id: str, day: int) -> str:
    return f"fee:{account_id}:day:{day}"


def _interest_accrual_id(account_id: str, day: int) -> str:
    return f"interest-accrual:{account_id}:day:{day}"


def _capitalization_id(account_id: str, day: int) -> str:
    return f"interest-capitalization:{account_id}:day:{day}"


def _interest_finalization_id(start_day: int, through_day: int) -> str:
    return f"interest-finalization:days:{start_day}-{through_day}"
