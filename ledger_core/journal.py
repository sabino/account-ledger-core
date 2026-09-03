"""Pure append and projection operations over an immutable journal value."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, TypeGuard

from ledger_core.model import (
    Account,
    AccountId,
    AuthorizationApproved,
    AuthorizationDeclined,
    AuthorizationFact,
    AuthorizationId,
    AuthorizationRequested,
    AuthorizationSettled,
    AuthorizationStatus,
    AuthorizationView,
    Credit,
    Currency,
    CurrencyMismatchError,
    CustomerPostingDirection,
    Debit,
    DomainInvariantError,
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
    ReversalRequested,
    SettlementRequested,
    StoredFact,
    allocate_evenly,
    encode_record_component,
)


class JournalInvariantError(DomainInvariantError):
    """Raised when an append would make the journal internally inconsistent."""


class DuplicateRecordError(JournalInvariantError):
    """Raised when an immutable record identity is reused."""


class UnknownAccountError(JournalInvariantError):
    """Raised when a projection or accepted fact names no configured account."""


_EXPECTED_POSTING_DIRECTION = {
    PostingKind.CREDIT: CustomerPostingDirection.CREDIT,
    PostingKind.INSTALLMENT_CREDIT: CustomerPostingDirection.CREDIT,
    PostingKind.DEBIT: CustomerPostingDirection.DEBIT,
    PostingKind.SETTLEMENT: CustomerPostingDirection.DEBIT,
    PostingKind.REVERSAL: CustomerPostingDirection.CREDIT,
    PostingKind.OVERDRAFT_FEE: CustomerPostingDirection.DEBIT,
    PostingKind.INTEREST_CAPITALIZATION: CustomerPostingDirection.CREDIT,
}

_DIRECT_POSTING_KINDS = frozenset(
    (
        PostingKind.CREDIT,
        PostingKind.INSTALLMENT_CREDIT,
        PostingKind.DEBIT,
        PostingKind.SETTLEMENT,
        PostingKind.REVERSAL,
    )
)

_DERIVED_POSTING_KINDS = frozenset(
    (PostingKind.OVERDRAFT_FEE, PostingKind.INTEREST_CAPITALIZATION)
)

_SUPPORTED_JOURNAL_FACT_TYPES = (
    EventAccepted,
    EventRejected,
    Posting,
    AuthorizationApproved,
    AuthorizationDeclined,
    AuthorizationSettled,
    InterestAccrual,
    InterestFinalized,
)


@dataclass(frozen=True, slots=True)
class Ledger:
    """A persistent value: appending returns a new ledger and preserves this one."""

    accounts: tuple[Account, ...]
    records: tuple[StoredFact, ...] = ()
    next_commit_sequence: int = 1

    def __post_init__(self) -> None:
        account_ids = tuple(account.account_id for account in self.accounts)
        if len(account_ids) != len(frozenset(account_ids)):
            raise JournalInvariantError("account IDs must be unique")
        if self.next_commit_sequence <= 0:
            raise JournalInvariantError("next commit sequence must be positive")


def new_ledger(accounts: Iterable[Account]) -> Ledger:
    return Ledger(accounts=tuple(accounts))


def latest_commit_sequence(ledger: Ledger) -> int:
    return ledger.next_commit_sequence - 1


def latest_recorded_day(ledger: Ledger) -> int:
    return max((record.recorded_day for record in ledger.records), default=0)


def account_for(ledger: Ledger, account_id: AccountId) -> Account:
    for account in ledger.accounts:
        if account.account_id == account_id:
            return account
    raise UnknownAccountError(f"unknown account: {account_id}")


def record_id_of(fact: JournalFact) -> str:
    return fact.record_id


def has_record_id(ledger: Ledger, record_id: str) -> bool:
    return any(record_id_of(record.fact) == record_id for record in ledger.records)


def has_overdraft_fee(ledger: Ledger, account_id: AccountId, day: int) -> bool:
    """Return whether the canonical account/day fee exists and is really a fee."""

    expected_id = f"fee:{encode_record_component(account_id)}:day:{day}"
    stored = next(
        (
            record.fact
            for record in ledger.records
            if record_id_of(record.fact) == expected_id
        ),
        None,
    )
    if stored is None:
        return False
    if not (
        isinstance(stored, Posting)
        and stored.kind is PostingKind.OVERDRAFT_FEE
        and stored.account_id == account_id
        and stored.value_day == day
    ):
        raise JournalInvariantError(
            "canonical overdraft fee identity is occupied by an unrelated fact"
        )
    return True


def append_batch(
    ledger: Ledger,
    facts: Iterable[JournalFact],
    *,
    recorded_day: int,
    policy_version: str,
) -> Ledger:
    """Append through the trusted storage boundary and return a new value.

    This is the low-level in-memory storage boundary used by the engine. It
    enforces structural, currency, posting-direction, direct-event, reversal,
    and authorization-history invariants atomically. Policy decisions and
    derived fee or interest calculations belong to the engine. Application
    callers should use ``process_event`` and ``finalize_interest`` rather than
    manufacture facts.
    """

    staged = tuple(facts)
    if not staged:
        raise JournalInvariantError("cannot append an empty batch")
    if any(
        not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            fact, _SUPPORTED_JOURNAL_FACT_TYPES
        )
        for fact in staged
    ):
        raise JournalInvariantError("journal fact type is not supported")
    if type(recorded_day) is not int or recorded_day <= 0:
        raise JournalInvariantError("recorded day must be positive")
    if type(policy_version) is not str or not policy_version:
        raise JournalInvariantError("policy version cannot be empty")

    existing_ids = frozenset(record_id_of(record.fact) for record in ledger.records)
    staged_ids = tuple(record_id_of(fact) for fact in staged)
    if any(type(record_id) is not str or not record_id for record_id in staged_ids):
        raise JournalInvariantError("record IDs cannot be empty")
    if len(staged_ids) != len(frozenset(staged_ids)):
        raise DuplicateRecordError("an atomic batch contains duplicate record IDs")
    duplicate_ids = existing_ids.intersection(staged_ids)
    if duplicate_ids:
        duplicate = min(duplicate_ids)
        raise DuplicateRecordError(f"record already exists: {duplicate}")

    _validate_batch(
        ledger,
        staged,
        recorded_day=recorded_day,
    )

    commit_sequence = ledger.next_commit_sequence
    appended = tuple(
        StoredFact(
            commit_sequence=commit_sequence,
            ordinal=ordinal,
            recorded_day=recorded_day,
            policy_version=policy_version,
            fact=fact,
        )
        for ordinal, fact in enumerate(staged, start=1)
    )
    return Ledger(
        accounts=ledger.accounts,
        records=ledger.records + appended,
        next_commit_sequence=commit_sequence + 1,
    )


def _validate_batch(
    ledger: Ledger,
    staged: tuple[JournalFact, ...],
    *,
    recorded_day: int,
) -> None:
    for fact in staged:
        _validate_fact(ledger, fact)

    _validate_receipt_batch(ledger, staged, recorded_day=recorded_day)
    _validate_authorization_relationships(ledger, staged)
    _validate_posting_relationships(ledger, staged)


def _validate_fact(ledger: Ledger, fact: JournalFact) -> None:
    if isinstance(fact, EventAccepted):
        _validate_accepted_event(ledger, fact.event)
    elif isinstance(fact, EventRejected):
        _require_supported_input_event(fact.event)
        if not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            fact.code, RejectionCode
        ):
            raise JournalInvariantError("rejected event code is not supported")
        if type(fact.message) is not str or not fact.message:
            raise JournalInvariantError("rejected event must explain the error")
    elif isinstance(fact, Posting):
        account = account_for(ledger, fact.account_id)
        _require_currency(account, fact.amount)
        _require_positive_day(fact.value_day)
        if not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            fact.kind, PostingKind
        ):
            raise JournalInvariantError("posting kind is not supported")
        if fact.amount.minor_units == 0:
            raise JournalInvariantError("posting amount cannot be zero")
        expected_direction = _EXPECTED_POSTING_DIRECTION[fact.kind]
        if fact.direction is not expected_direction:
            raise JournalInvariantError(
                f"{fact.kind.value} posting must be a "
                f"{expected_direction.value} customer-account effect"
            )
        if type(fact.caused_by) is not str or not fact.caused_by:
            raise JournalInvariantError("posting must identify its cause")
        if fact.direct_event_id is not None and (
            type(fact.direct_event_id) is not str or not fact.direct_event_id
        ):
            raise JournalInvariantError("direct event ID must be non-empty text")
        if fact.reverses_record_id is not None and (
            type(fact.reverses_record_id) is not str or not fact.reverses_record_id
        ):
            raise JournalInvariantError("reversal target ID must be non-empty text")
        if fact.kind in _DIRECT_POSTING_KINDS and fact.direct_event_id is None:
            raise JournalInvariantError(
                f"{fact.kind.value} posting must identify its direct event"
            )
        if fact.kind in _DERIVED_POSTING_KINDS and fact.direct_event_id is not None:
            raise JournalInvariantError(
                f"{fact.kind.value} posting cannot claim a direct input event"
            )
        if fact.kind is PostingKind.REVERSAL and fact.reverses_record_id is None:
            raise JournalInvariantError("reversal must identify the reversed posting")
        if fact.kind is not PostingKind.REVERSAL and fact.reverses_record_id is not None:
            raise JournalInvariantError("only a reversal may identify a reversed posting")
    elif isinstance(fact, (AuthorizationApproved, AuthorizationDeclined)):
        account = account_for(ledger, fact.account_id)
        _require_currency(account, fact.amount)
        _require_positive_day(fact.value_day)
        if fact.amount.minor_units <= 0:
            raise JournalInvariantError("authorization amount must be positive")
        if isinstance(fact, AuthorizationDeclined):
            _require_currency(account, fact.available_before_hold)
    elif isinstance(fact, AuthorizationSettled):
        account = account_for(ledger, fact.account_id)
        _require_currency(account, fact.captured_amount)
        _require_currency(account, fact.released_amount)
        _require_positive_day(fact.value_day)
        if fact.captured_amount.minor_units <= 0:
            raise JournalInvariantError("captured amount must be positive")
        if fact.released_amount.minor_units < 0:
            raise JournalInvariantError("released amount cannot be negative")
    elif isinstance(fact, InterestAccrual):
        account = account_for(ledger, fact.account_id)
        _require_currency(account, fact.basis)
        _require_currency(account, fact.amount)
        _require_positive_day(fact.value_day)
        if fact.amount.minor_units < 0:
            raise JournalInvariantError("interest accrual cannot be negative")
    else:
        if (
            type(fact.start_day) is not int
            or type(fact.through_day) is not int
            or fact.start_day <= 0
            or fact.through_day < fact.start_day
        ):
            raise JournalInvariantError(
                "interest finalization must cover a non-empty positive day range"
            )

def _validate_receipt_batch(
    ledger: Ledger,
    staged: tuple[JournalFact, ...],
    *,
    recorded_day: int,
) -> None:
    existing_event_ids = frozenset(
        record.fact.event.event_id
        for record in ledger.records
        if isinstance(record.fact, (EventAccepted, EventRejected))
    )
    receipts = tuple(
        fact
        for fact in staged
        if isinstance(fact, (EventAccepted, EventRejected))
    )
    staged_event_ids = tuple(receipt.event.event_id for receipt in receipts)
    if len(staged_event_ids) != len(frozenset(staged_event_ids)):
        raise JournalInvariantError("an atomic batch contains duplicate event receipts")
    duplicate_event_ids = existing_event_ids.intersection(staged_event_ids)
    if duplicate_event_ids:
        duplicate = min(duplicate_event_ids)
        raise JournalInvariantError(f"event receipt already exists: {duplicate}")

    if len(receipts) > 1:
        raise JournalInvariantError("an event batch must contain exactly one receipt")
    if not receipts:
        return

    receipt = receipts[0]
    if staged[0] is not receipt:
        raise JournalInvariantError("the event receipt must be first in its batch")
    if recorded_day != receipt.event.booked_day:
        raise JournalInvariantError(
            "the stored recorded day must equal the event's booked day"
        )
    if isinstance(receipt, EventRejected) and len(staged) != 1:
        raise JournalInvariantError("a rejected event cannot append related facts")


def _validate_authorization_relationships(
    ledger: Ledger,
    staged: tuple[JournalFact, ...],
) -> None:
    accepted_events = {
        fact.event.event_id: fact.event
        for fact in staged
        if isinstance(fact, EventAccepted)
    }
    authorization_facts = tuple(
        fact
        for fact in staged
        if isinstance(
            fact,
            (AuthorizationApproved, AuthorizationDeclined, AuthorizationSettled),
        )
    )
    for fact in authorization_facts:
        event = accepted_events.get(fact.source_event_id)
        if event is None:
            raise JournalInvariantError(
                "an authorization fact must share its batch with its accepted event"
            )
        if fact.account_id != event.account_id or fact.value_day != event.value_day:
            raise JournalInvariantError(
                "authorization fact account and value day must match its event"
            )

        if isinstance(fact, (AuthorizationApproved, AuthorizationDeclined)):
            if not isinstance(event, AuthorizationRequested):
                raise JournalInvariantError(
                    "approval or decline must be caused by an authorization request"
                )
            if (
                fact.authorization_id != event.authorization_id
                or fact.amount != event.amount
            ):
                raise JournalInvariantError(
                    "authorization outcome must match its request identity and amount"
                )
        else:
            if not isinstance(event, SettlementRequested):
                raise JournalInvariantError(
                    "settlement state must be caused by a settlement request"
                )
            if (
                fact.authorization_id != event.authorization_id
                or fact.captured_amount != event.amount
            ):
                raise JournalInvariantError(
                    "settlement state must match its request identity and amount"
                )

    authorization_state = _authorization_map(
        record.fact
        for record in ledger.records
        if _is_authorization_fact(record.fact)
    )

    for event_id, event in accepted_events.items():
        related = tuple(
            fact
            for fact in authorization_facts
            if fact.source_event_id == event_id
        )
        if isinstance(event, AuthorizationRequested):
            if len(related) != 1 or not isinstance(
                related[0], (AuthorizationApproved, AuthorizationDeclined)
            ):
                raise JournalInvariantError(
                    "an accepted authorization request needs one approval or decline"
                )
            outcome = related[0]
            if event.authorization_id in authorization_state:
                raise JournalInvariantError(
                    f"authorization already exists: {event.authorization_id}"
                )
            authorization_state[event.authorization_id] = (
                _active_view(outcome)
                if isinstance(outcome, AuthorizationApproved)
                else _declined_view(outcome)
            )
        elif isinstance(event, SettlementRequested):
            if len(related) != 1 or not isinstance(related[0], AuthorizationSettled):
                raise JournalInvariantError(
                    "an accepted settlement needs one settlement state transition"
                )
            current = authorization_state.get(event.authorization_id)
            if current is None or current.status is not AuthorizationStatus.ACTIVE:
                raise JournalInvariantError(
                    "an accepted settlement requires an authorization that is "
                    "still active at the knowledge cutoff"
                )
            effective = authorization_view(
                ledger,
                event.authorization_id,
                effective_through=event.value_day,
            )
            outcome = related[0]
            if effective is None or effective.status is not AuthorizationStatus.ACTIVE:
                raise JournalInvariantError(
                    "authorization was not active on the settlement value day"
                )
            if current.account_id != outcome.account_id:
                raise JournalInvariantError(
                    "settlement customer account differs from authorization"
                )
            if current.requested_amount != (
                outcome.captured_amount + outcome.released_amount
            ):
                raise JournalInvariantError(
                    "captured and released amounts must equal the approved hold"
                )
            authorization_state[event.authorization_id] = _settled_view(
                current,
                outcome,
            )
        elif related:
            raise JournalInvariantError(
                "only authorization and settlement events may append authorization facts"
            )


def _validate_posting_relationships(
    ledger: Ledger,
    staged: tuple[JournalFact, ...],
) -> None:
    accepted_events = {
        fact.event.event_id: fact.event
        for fact in staged
        if isinstance(fact, EventAccepted)
    }
    direct_postings: dict[str, list[Posting]] = {}

    for fact in staged:
        if not isinstance(fact, Posting):
            continue
        if fact.direct_event_id is None:
            continue
        event = accepted_events.get(fact.direct_event_id)
        if event is None:
            raise JournalInvariantError(
                "a direct posting must share its batch with the accepted event"
            )
        if fact.caused_by != fact.direct_event_id:
            raise JournalInvariantError(
                "a direct posting cause must equal its direct event ID"
            )
        if fact.account_id != event.account_id:
            raise JournalInvariantError("posting account differs from its direct event")
        if fact.value_day != event.value_day:
            raise JournalInvariantError("posting value day differs from its direct event")
        direct_postings.setdefault(fact.direct_event_id, []).append(fact)

    for event_id, event in accepted_events.items():
        event_postings = tuple(direct_postings.get(event_id, ()))
        if isinstance(event, Credit):
            expected_kind = (
                PostingKind.CREDIT
                if event.installments == 1
                else PostingKind.INSTALLMENT_CREDIT
            )
            if len(event_postings) != event.installments or any(
                posting.kind is not expected_kind for posting in event_postings
            ):
                raise JournalInvariantError(
                    "credit postings must match the accepted installment count and kind"
                )
            expected_amounts = allocate_evenly(event.amount, event.installments)
            if tuple(posting.amount for posting in event_postings) != expected_amounts:
                raise JournalInvariantError(
                    "credit postings must use the deterministic installment allocation"
                )
        elif isinstance(event, Debit):
            _require_single_exact_posting(
                event_postings,
                expected_kind=PostingKind.DEBIT,
                expected_amount=-event.amount,
            )
        elif isinstance(event, SettlementRequested):
            _require_single_exact_posting(
                event_postings,
                expected_kind=PostingKind.SETTLEMENT,
                expected_amount=-event.amount,
            )
        elif isinstance(event, ReversalRequested):
            if not event_postings or any(
                posting.kind is not PostingKind.REVERSAL
                for posting in event_postings
            ):
                raise JournalInvariantError(
                    "an accepted reversal must append at least one reversal posting"
                )
            _validate_reversal_postings(ledger, event, event_postings)
        elif event_postings:
            raise JournalInvariantError(
                "an authorization request cannot create a direct monetary posting"
            )


def _require_single_exact_posting(
    postings_for_event: tuple[Posting, ...],
    *,
    expected_kind: PostingKind,
    expected_amount: Money,
) -> None:
    if (
        len(postings_for_event) != 1
        or postings_for_event[0].kind is not expected_kind
        or postings_for_event[0].amount != expected_amount
    ):
        raise JournalInvariantError(
            f"accepted event must append one exact {expected_kind.value} posting"
        )


def _validate_reversal_postings(
    ledger: Ledger,
    event: ReversalRequested,
    reversal_postings: tuple[Posting, ...],
) -> None:
    existing_postings = {
        record.fact.record_id: record.fact
        for record in ledger.records
        if isinstance(record.fact, Posting)
    }
    already_reversed = {
        posting.reverses_record_id
        for posting in existing_postings.values()
        if posting.reverses_record_id is not None
    }
    staged_targets: set[str] = set()

    for reversal in reversal_postings:
        target_id = reversal.reverses_record_id
        assert target_id is not None
        target = existing_postings.get(target_id)
        if target is None:
            raise JournalInvariantError("reversal target posting does not exist")
        if target.kind is not PostingKind.DEBIT:
            raise JournalInvariantError(
                "reversal target must be a posting produced by a Debit event"
            )
        if target.direct_event_id != event.target_event_id:
            raise JournalInvariantError(
                "reversal target is unrelated to the requested source event"
            )
        if target.account_id != reversal.account_id:
            raise JournalInvariantError("reversal account differs from its target")
        if reversal.amount != -target.amount:
            raise JournalInvariantError(
                "reversal amount must be the exact opposite of its target"
            )
        if target_id in already_reversed or target_id in staged_targets:
            raise JournalInvariantError("a posting cannot be reversed more than once")
        staged_targets.add(target_id)


def _validate_accepted_event(ledger: Ledger, event: InputEvent) -> None:
    _require_supported_input_event(event)
    account = account_for(ledger, event.account_id)
    if isinstance(
        event,
        (Credit, Debit, AuthorizationRequested, SettlementRequested),
    ):
        _require_currency(account, event.amount)
    else:
        # Reversals carry no amount; their account and target are validated by
        # the engine before an accepted receipt is staged.
        return


def _require_supported_input_event(event: InputEvent) -> None:
    if not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
        event,
        (
            Credit,
            Debit,
            AuthorizationRequested,
            SettlementRequested,
            ReversalRequested,
        ),
    ):
        raise JournalInvariantError("event type is not supported")


def _require_currency(account: Account, amount: Money) -> None:
    if amount.currency != account.currency:
        raise CurrencyMismatchError(
            f"account {account.account_id} uses {account.currency.code}, "
            f"not {amount.currency.code}"
        )


def _require_positive_day(day: int) -> None:
    if type(day) is not int or day <= 0:
        raise JournalInvariantError("fact value day must be positive")


def stored_facts(
    ledger: Ledger, *, known_through: int | None = None
) -> tuple[StoredFact, ...]:
    cutoff = latest_commit_sequence(ledger) if known_through is None else known_through
    return tuple(
        record for record in ledger.records if record.commit_sequence <= cutoff
    )


def postings(
    ledger: Ledger, *, known_through: int | None = None
) -> tuple[Posting, ...]:
    return tuple(
        record.fact
        for record in stored_facts(ledger, known_through=known_through)
        if isinstance(record.fact, Posting)
    )


def closing_balance(
    ledger: Ledger,
    account_id: AccountId,
    *,
    effective_through: int,
    known_through: int | None = None,
    excluding_kinds: frozenset[PostingKind] = frozenset(),
) -> Money:
    """Return a value-day balance at an explicit knowledge cutoff."""

    if effective_through <= 0:
        raise JournalInvariantError("effective day must be positive")
    account = account_for(ledger, account_id)
    relevant = tuple(
        posting
        for posting in postings(ledger, known_through=known_through)
        if posting.kind not in excluding_kinds
    )
    return closing_balance_from_postings(
        account,
        relevant,
        effective_through=effective_through,
    )


def closing_balance_from_postings(
    account: Account,
    candidate_postings: Iterable[Posting],
    *,
    effective_through: int,
) -> Money:
    """Project a balance from an arbitrary immutable posting snapshot."""

    if effective_through <= 0:
        raise JournalInvariantError("effective day must be positive")
    relevant = (
        posting.amount
        for posting in candidate_postings
        if posting.account_id == account.account_id
        and posting.value_day <= effective_through
    )
    return sum_money(relevant, currency=account.currency, start=account.opening_balance)


def sum_money(
    amounts: Iterable[Money], *, currency: Currency, start: Money | None = None
) -> Money:
    """Sum money without Python's integer zero leaking into typed arithmetic."""

    if start is None:
        total = Money.zero(currency)
    else:
        total = start
        if total.currency != currency:
            raise CurrencyMismatchError("sum start uses a different currency")
    for amount in amounts:
        total = total + amount
    return total


def event_receipt(ledger: Ledger, event_id: str) -> EventReceipt | None:
    for record in ledger.records:
        fact = record.fact
        if isinstance(fact, (EventAccepted, EventRejected)) and fact.event.event_id == event_id:
            return fact
    return None


def commit_for_event(ledger: Ledger, event_id: str) -> int | None:
    for record in ledger.records:
        fact = record.fact
        if isinstance(fact, (EventAccepted, EventRejected)) and fact.event.event_id == event_id:
            return record.commit_sequence
    return None


def authorization_views(
    ledger: Ledger,
    *,
    effective_through: int,
    known_through: int | None = None,
) -> tuple[AuthorizationView, ...]:
    facts = (
        record.fact
        for record in stored_facts(ledger, known_through=known_through)
        if _is_authorization_fact(record.fact)
        and record.fact.value_day <= effective_through
    )
    views = _authorization_map(facts)
    return tuple(views[authorization_id] for authorization_id in sorted(views))


def authorization_view(
    ledger: Ledger,
    authorization_id: AuthorizationId,
    *,
    effective_through: int,
    known_through: int | None = None,
) -> AuthorizationView | None:
    return next(
        (
            view
            for view in authorization_views(
                ledger,
                effective_through=effective_through,
                known_through=known_through,
            )
            if view.authorization_id == authorization_id
        ),
        None,
    )


def current_authorization_view(
    ledger: Ledger,
    authorization_id: AuthorizationId,
    *,
    known_through: int | None = None,
) -> AuthorizationView | None:
    """Return lifecycle state at a knowledge cutoff, independent of value day."""

    facts = (
        record.fact
        for record in stored_facts(ledger, known_through=known_through)
        if _is_authorization_fact(record.fact)
    )
    return _authorization_map(facts).get(authorization_id)


def active_hold_total(
    ledger: Ledger,
    account_id: AccountId,
    *,
    effective_through: int,
    known_through: int | None = None,
) -> Money:
    account = account_for(ledger, account_id)
    holds = (
        view.active_hold
        for view in authorization_views(
            ledger,
            effective_through=effective_through,
            known_through=known_through,
        )
        if view.account_id == account_id and view.status is AuthorizationStatus.ACTIVE
    )
    return sum_money(holds, currency=account.currency)


def _authorization_map(
    facts: Iterable[AuthorizationFact],
) -> dict[AuthorizationId, AuthorizationView]:
    views: dict[AuthorizationId, AuthorizationView] = {}
    for fact in facts:
        if isinstance(fact, AuthorizationApproved):
            if fact.authorization_id in views:
                raise JournalInvariantError(
                    f"duplicate authorization origin: {fact.authorization_id}"
                )
            views[fact.authorization_id] = _active_view(fact)
        elif isinstance(fact, AuthorizationDeclined):
            if fact.authorization_id in views:
                raise JournalInvariantError(
                    f"duplicate authorization origin: {fact.authorization_id}"
                )
            views[fact.authorization_id] = _declined_view(fact)
        else:
            previous = views.get(fact.authorization_id)
            if previous is None or previous.status is not AuthorizationStatus.ACTIVE:
                raise JournalInvariantError(
                    f"settlement without active authorization: {fact.authorization_id}"
                )
            views[fact.authorization_id] = _settled_view(previous, fact)
    return views


def _is_authorization_fact(fact: JournalFact) -> TypeGuard[AuthorizationFact]:
    return isinstance(
        fact,
        (AuthorizationApproved, AuthorizationDeclined, AuthorizationSettled),
    )


def _active_view(fact: AuthorizationApproved) -> AuthorizationView:
    zero = Money.zero(fact.amount.currency)
    return AuthorizationView(
        account_id=fact.account_id,
        authorization_id=fact.authorization_id,
        requested_amount=fact.amount,
        status=AuthorizationStatus.ACTIVE,
        active_hold=fact.amount,
        captured_amount=zero,
        released_amount=zero,
    )


def _declined_view(fact: AuthorizationDeclined) -> AuthorizationView:
    zero = Money.zero(fact.amount.currency)
    return AuthorizationView(
        account_id=fact.account_id,
        authorization_id=fact.authorization_id,
        requested_amount=fact.amount,
        status=AuthorizationStatus.DECLINED,
        active_hold=zero,
        captured_amount=zero,
        released_amount=zero,
    )


def _settled_view(
    previous: AuthorizationView, fact: AuthorizationSettled
) -> AuthorizationView:
    return AuthorizationView(
        account_id=fact.account_id,
        authorization_id=fact.authorization_id,
        requested_amount=previous.requested_amount,
        status=AuthorizationStatus.SETTLED,
        active_hold=Money.zero(previous.requested_amount.currency),
        captured_amount=fact.captured_amount,
        released_amount=fact.released_amount,
    )


def fee_postings(
    ledger: Ledger, *, account_id: AccountId | None = None
) -> tuple[Posting, ...]:
    return tuple(
        posting
        for posting in postings(ledger)
        if posting.kind is PostingKind.OVERDRAFT_FEE
        and (account_id is None or posting.account_id == account_id)
    )


def interest_accruals(
    ledger: Ledger, *, account_id: AccountId | None = None
) -> tuple[InterestAccrual, ...]:
    return tuple(
        record.fact
        for record in ledger.records
        if isinstance(record.fact, InterestAccrual)
        and (account_id is None or record.fact.account_id == account_id)
    )


def finalized_through(ledger: Ledger) -> int | None:
    finalized_days = tuple(
        record.fact.through_day
        for record in ledger.records
        if isinstance(record.fact, InterestFinalized)
    )
    return max(finalized_days, default=None)
