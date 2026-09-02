"""Immutable domain values and algebraic event/fact types.

All authoritative monetary values are integer minor units.  The dataclasses are
frozen so transitions can only produce new values; no accepted fact can be
edited in place.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Self


type AccountId = str
type AuthorizationId = str
type EventId = str
type RecordId = str
type Day = int


class DomainInvariantError(ValueError):
    """Raised when a value would violate a ledger-domain invariant."""


class CurrencyMismatchError(DomainInvariantError):
    """Raised when arithmetic mixes different currencies."""


class MoneyPrecisionError(DomainInvariantError):
    """Raised when a decimal amount is not representable in minor units."""


@dataclass(frozen=True, slots=True, order=True)
class Currency:
    """Currency identity and its mandated number of fractional digits."""

    code: str
    decimal_places: int

    def __post_init__(self) -> None:
        if not self.code or self.code != self.code.upper():
            raise DomainInvariantError("currency code must be non-empty uppercase text")
        if self.decimal_places < 0:
            raise DomainInvariantError("currency decimal places cannot be negative")

    @property
    def minor_unit_factor(self) -> int:
        return 10**self.decimal_places


AED = Currency("AED", 2)
BHD = Currency("BHD", 3)


@dataclass(frozen=True, slots=True)
class Money:
    """An exact amount expressed in one currency's smallest supported unit."""

    currency: Currency
    minor_units: int

    def __post_init__(self) -> None:
        if type(self.minor_units) is not int:
            raise DomainInvariantError("minor_units must be an integer")

    @classmethod
    def parse(cls, currency: Currency, text: str) -> Self:
        """Parse exact decimal text, rejecting unrepresentable precision."""

        try:
            decimal = Decimal(text)
        except InvalidOperation as error:
            raise MoneyPrecisionError(f"invalid {currency.code} amount: {text!r}") from error

        if not decimal.is_finite():
            raise MoneyPrecisionError(f"amount must be finite: {text!r}")

        scaled = decimal * currency.minor_unit_factor
        integral = scaled.to_integral_value()
        if scaled != integral:
            raise MoneyPrecisionError(
                f"{text!r} exceeds {currency.code} precision "
                f"of {currency.decimal_places} decimal places"
            )
        return cls(currency=currency, minor_units=int(integral))

    @classmethod
    def zero(cls, currency: Currency) -> Self:
        return cls(currency=currency, minor_units=0)

    def __add__(self, other: Money) -> Money:
        self._require_same_currency(other)
        return Money(self.currency, self.minor_units + other.minor_units)

    def __sub__(self, other: Money) -> Money:
        self._require_same_currency(other)
        return Money(self.currency, self.minor_units - other.minor_units)

    def __neg__(self) -> Money:
        return Money(self.currency, -self.minor_units)

    def __abs__(self) -> Money:
        return Money(self.currency, abs(self.minor_units))

    def _require_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"cannot combine {self.currency.code} and {other.currency.code}"
            )

    def format_amount(self) -> str:
        sign = "-" if self.minor_units < 0 else ""
        absolute = abs(self.minor_units)
        whole, fractional = divmod(absolute, self.currency.minor_unit_factor)
        if self.currency.decimal_places == 0:
            return f"{sign}{whole}"
        return (
            f"{sign}{whole}."
            f"{fractional:0{self.currency.decimal_places}d}"
        )

    def __str__(self) -> str:
        return f"{self.currency.code} {self.format_amount()}"


def round_ratio_half_even(numerator: int, denominator: int) -> int:
    """Round an exact rational number to an integer using ties-to-even."""

    if denominator <= 0:
        raise DomainInvariantError("rounding denominator must be positive")

    sign = -1 if numerator < 0 else 1
    quotient, remainder = divmod(abs(numerator), denominator)
    comparison = 2 * remainder - denominator
    if comparison > 0 or (comparison == 0 and quotient % 2 == 1):
        quotient += 1
    return sign * quotient


def allocate_evenly(amount: Money, parts: int) -> tuple[Money, ...]:
    """Split a non-negative amount exactly, assigning spare units left-to-right."""

    if parts <= 0:
        raise DomainInvariantError("installment count must be positive")
    if amount.minor_units < 0:
        raise DomainInvariantError("cannot allocate a negative amount")

    quotient, remainder = divmod(amount.minor_units, parts)
    return tuple(
        Money(amount.currency, quotient + (1 if index < remainder else 0))
        for index in range(parts)
    )


def _validate_event_identity(event_id: EventId, booked_day: Day, value_day: Day) -> None:
    if not event_id:
        raise DomainInvariantError("event_id cannot be empty")
    if booked_day <= 0 or value_day <= 0:
        raise DomainInvariantError("booked_day and value_day must be positive")


def _validate_positive_amount(amount: Money) -> None:
    if amount.minor_units <= 0:
        raise DomainInvariantError("event amount must be positive")


@dataclass(frozen=True, slots=True)
class Credit:
    event_id: EventId
    booked_day: Day
    account_id: AccountId
    amount: Money
    value_day: Day
    installments: int = 1

    def __post_init__(self) -> None:
        _validate_event_identity(self.event_id, self.booked_day, self.value_day)
        _validate_positive_amount(self.amount)
        if self.installments <= 0:
            raise DomainInvariantError("installments must be positive")


@dataclass(frozen=True, slots=True)
class Debit:
    event_id: EventId
    booked_day: Day
    account_id: AccountId
    amount: Money
    value_day: Day

    def __post_init__(self) -> None:
        _validate_event_identity(self.event_id, self.booked_day, self.value_day)
        _validate_positive_amount(self.amount)


@dataclass(frozen=True, slots=True)
class AuthorizationRequested:
    event_id: EventId
    booked_day: Day
    account_id: AccountId
    authorization_id: AuthorizationId
    amount: Money
    value_day: Day

    def __post_init__(self) -> None:
        _validate_event_identity(self.event_id, self.booked_day, self.value_day)
        _validate_positive_amount(self.amount)
        if not self.authorization_id:
            raise DomainInvariantError("authorization_id cannot be empty")


@dataclass(frozen=True, slots=True)
class SettlementRequested:
    event_id: EventId
    booked_day: Day
    account_id: AccountId
    authorization_id: AuthorizationId
    amount: Money
    value_day: Day

    def __post_init__(self) -> None:
        _validate_event_identity(self.event_id, self.booked_day, self.value_day)
        _validate_positive_amount(self.amount)
        if not self.authorization_id:
            raise DomainInvariantError("authorization_id cannot be empty")


@dataclass(frozen=True, slots=True)
class ReversalRequested:
    event_id: EventId
    booked_day: Day
    account_id: AccountId
    target_event_id: EventId
    value_day: Day

    def __post_init__(self) -> None:
        _validate_event_identity(self.event_id, self.booked_day, self.value_day)
        if not self.target_event_id:
            raise DomainInvariantError("target_event_id cannot be empty")


type InputEvent = (
    Credit
    | Debit
    | AuthorizationRequested
    | SettlementRequested
    | ReversalRequested
)


@dataclass(frozen=True, slots=True)
class Account:
    account_id: AccountId
    currency: Currency
    opening_balance: Money

    def __post_init__(self) -> None:
        if not self.account_id:
            raise DomainInvariantError("account_id cannot be empty")
        if self.opening_balance.currency != self.currency:
            raise CurrencyMismatchError("opening balance must use the account currency")


class PostingKind(StrEnum):
    CREDIT = "credit"
    INSTALLMENT_CREDIT = "installment_credit"
    DEBIT = "debit"
    SETTLEMENT = "settlement"
    REVERSAL = "reversal"
    OVERDRAFT_FEE = "overdraft_fee"
    INTEREST_CAPITALIZATION = "interest_capitalization"


class AuthorizationStatus(StrEnum):
    ACTIVE = "active"
    DECLINED = "declined"
    SETTLED = "settled"


class RejectionCode(StrEnum):
    ACCOUNT_NOT_FOUND = "account_not_found"
    AUTHORIZATION_ACCOUNT_MISMATCH = "authorization_account_mismatch"
    AUTHORIZATION_ALREADY_EXISTS = "authorization_already_exists"
    AUTHORIZATION_NOT_FOUND = "authorization_not_found"
    AUTHORIZATION_NOT_ACTIVE = "authorization_not_active"
    CURRENCY_MISMATCH = "currency_mismatch"
    OVER_CAPTURE = "over_capture"
    REVERSAL_ALREADY_APPLIED = "reversal_already_applied"
    REVERSAL_TARGET_NOT_FOUND = "reversal_target_not_found"
    UNSUPPORTED_FEE_CURRENCY = "unsupported_fee_currency"
    FINALIZED_PERIOD_CORRECTION_UNSUPPORTED = (
        "finalized_period_correction_unsupported"
    )


@dataclass(frozen=True, slots=True)
class EventAccepted:
    record_id: RecordId
    event: InputEvent


@dataclass(frozen=True, slots=True)
class EventRejected:
    record_id: RecordId
    event: InputEvent
    code: RejectionCode
    message: str


type EventReceipt = EventAccepted | EventRejected


@dataclass(frozen=True, slots=True)
class Posting:
    record_id: RecordId
    account_id: AccountId
    amount: Money
    value_day: Day
    kind: PostingKind
    direct_event_id: EventId | None
    caused_by: RecordId | EventId
    reverses_record_id: RecordId | None = None


@dataclass(frozen=True, slots=True)
class AuthorizationApproved:
    record_id: RecordId
    account_id: AccountId
    authorization_id: AuthorizationId
    amount: Money
    value_day: Day
    source_event_id: EventId


@dataclass(frozen=True, slots=True)
class AuthorizationDeclined:
    record_id: RecordId
    account_id: AccountId
    authorization_id: AuthorizationId
    amount: Money
    value_day: Day
    source_event_id: EventId
    available_before_hold: Money


@dataclass(frozen=True, slots=True)
class AuthorizationSettled:
    record_id: RecordId
    account_id: AccountId
    authorization_id: AuthorizationId
    captured_amount: Money
    released_amount: Money
    value_day: Day
    source_event_id: EventId


type AuthorizationFact = (
    AuthorizationApproved | AuthorizationDeclined | AuthorizationSettled
)


@dataclass(frozen=True, slots=True)
class AuthorizationView:
    account_id: AccountId
    authorization_id: AuthorizationId
    requested_amount: Money
    status: AuthorizationStatus
    active_hold: Money
    captured_amount: Money
    released_amount: Money


@dataclass(frozen=True, slots=True)
class InterestAccrual:
    record_id: RecordId
    account_id: AccountId
    value_day: Day
    basis: Money
    amount: Money


@dataclass(frozen=True, slots=True)
class InterestFinalized:
    record_id: RecordId
    start_day: Day
    through_day: Day


type JournalFact = (
    EventAccepted
    | EventRejected
    | Posting
    | AuthorizationApproved
    | AuthorizationDeclined
    | AuthorizationSettled
    | InterestAccrual
    | InterestFinalized
)


@dataclass(frozen=True, slots=True)
class StoredFact:
    """A fact plus its atomic commit position and decision-policy evidence."""

    commit_sequence: int
    ordinal: int
    recorded_day: Day
    policy_version: str
    fact: JournalFact
