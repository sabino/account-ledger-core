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
    AuthorizationSettled,
    AuthorizationStatus,
    AuthorizationView,
    Credit,
    Currency,
    CurrencyMismatchError,
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
    SettlementRequested,
    StoredFact,
    AuthorizationRequested,
)


class JournalInvariantError(DomainInvariantError):
    """Raised when an append would make the journal internally inconsistent."""


class DuplicateRecordError(JournalInvariantError):
    """Raised when an immutable record identity is reused."""


class UnknownAccountError(JournalInvariantError):
    """Raised when a projection or accepted fact names no configured account."""


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


def append_batch(
    ledger: Ledger,
    facts: Iterable[JournalFact],
    *,
    recorded_day: int,
    policy_version: str,
) -> Ledger:
    """Validate and append one atomic commit, returning a new ledger value."""

    staged = tuple(facts)
    if not staged:
        raise JournalInvariantError("cannot append an empty batch")
    if recorded_day <= 0:
        raise JournalInvariantError("recorded day must be positive")
    if not policy_version:
        raise JournalInvariantError("policy version cannot be empty")

    existing_ids = frozenset(record_id_of(record.fact) for record in ledger.records)
    staged_ids = tuple(record_id_of(fact) for fact in staged)
    if any(not record_id for record_id in staged_ids):
        raise JournalInvariantError("record IDs cannot be empty")
    if len(staged_ids) != len(frozenset(staged_ids)):
        raise DuplicateRecordError("an atomic batch contains duplicate record IDs")
    duplicate_ids = existing_ids.intersection(staged_ids)
    if duplicate_ids:
        duplicate = min(duplicate_ids)
        raise DuplicateRecordError(f"record already exists: {duplicate}")

    _validate_batch(ledger, staged)

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


def _validate_batch(ledger: Ledger, staged: tuple[JournalFact, ...]) -> None:
    authorization_state = _authorization_map(
        record.fact
        for record in ledger.records
        if _is_authorization_fact(record.fact)
    )

    for fact in staged:
        _validate_fact(ledger, fact)
        if isinstance(fact, AuthorizationApproved):
            if fact.authorization_id in authorization_state:
                raise JournalInvariantError(
                    f"authorization already exists: {fact.authorization_id}"
                )
            authorization_state[fact.authorization_id] = _active_view(fact)
        elif isinstance(fact, AuthorizationDeclined):
            if fact.authorization_id in authorization_state:
                raise JournalInvariantError(
                    f"authorization already exists: {fact.authorization_id}"
                )
            authorization_state[fact.authorization_id] = _declined_view(fact)
        elif isinstance(fact, AuthorizationSettled):
            previous = authorization_state.get(fact.authorization_id)
            if previous is None or previous.status is not AuthorizationStatus.ACTIVE:
                raise JournalInvariantError(
                    f"cannot settle inactive authorization: {fact.authorization_id}"
                )
            if previous.account_id != fact.account_id:
                raise JournalInvariantError("settlement account differs from authorization")
            if previous.requested_amount != fact.captured_amount + fact.released_amount:
                raise JournalInvariantError(
                    "captured and released amounts must equal the approved hold"
                )
            authorization_state[fact.authorization_id] = _settled_view(previous, fact)


def _validate_fact(ledger: Ledger, fact: JournalFact) -> None:
    if isinstance(fact, EventAccepted):
        _validate_accepted_event(ledger, fact.event)
    elif isinstance(fact, EventRejected):
        if not fact.message:
            raise JournalInvariantError("rejected event must explain the error")
    elif isinstance(fact, Posting):
        account = account_for(ledger, fact.account_id)
        _require_currency(account, fact.amount)
        if fact.amount.minor_units == 0:
            raise JournalInvariantError("posting amount cannot be zero")
        if fact.kind is PostingKind.REVERSAL and fact.reverses_record_id is None:
            raise JournalInvariantError("reversal must identify the reversed posting")
        if fact.kind is not PostingKind.REVERSAL and fact.reverses_record_id is not None:
            raise JournalInvariantError("only a reversal may identify a reversed posting")
    elif isinstance(fact, (AuthorizationApproved, AuthorizationDeclined)):
        account = account_for(ledger, fact.account_id)
        _require_currency(account, fact.amount)
        if fact.amount.minor_units <= 0:
            raise JournalInvariantError("authorization amount must be positive")
        if isinstance(fact, AuthorizationDeclined):
            _require_currency(account, fact.available_before_hold)
    elif isinstance(fact, AuthorizationSettled):
        account = account_for(ledger, fact.account_id)
        _require_currency(account, fact.captured_amount)
        _require_currency(account, fact.released_amount)
        if fact.captured_amount.minor_units <= 0:
            raise JournalInvariantError("captured amount must be positive")
        if fact.released_amount.minor_units < 0:
            raise JournalInvariantError("released amount cannot be negative")
    elif isinstance(fact, InterestAccrual):
        account = account_for(ledger, fact.account_id)
        _require_currency(account, fact.basis)
        _require_currency(account, fact.amount)
        if fact.amount.minor_units < 0:
            raise JournalInvariantError("interest accrual cannot be negative")
    else:
        if fact.start_day <= 0 or fact.through_day < fact.start_day:
            raise JournalInvariantError(
                "interest finalization must cover a non-empty positive day range"
            )


def _validate_accepted_event(ledger: Ledger, event: InputEvent) -> None:
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


def _require_currency(account: Account, amount: Money) -> None:
    if amount.currency != account.currency:
        raise CurrencyMismatchError(
            f"account {account.account_id} uses {account.currency.code}, "
            f"not {amount.currency.code}"
        )


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
