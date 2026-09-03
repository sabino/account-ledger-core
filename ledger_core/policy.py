"""Pure business-policy decisions for the bounded assessment contract."""

from __future__ import annotations

from dataclasses import dataclass

from ledger_core.model import (
    AED,
    Account,
    AuthorizationStatus,
    AuthorizationView,
    Currency,
    CurrencyMismatchError,
    DomainInvariantError,
    Money,
    RejectionCode,
    allocate_evenly,
    round_ratio_half_even,
)


class UnsupportedFeeCurrencyError(DomainInvariantError):
    """Raised rather than inventing an FX or non-AED overdraft fee rule."""


@dataclass(frozen=True, slots=True)
class Ratio:
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if type(self.numerator) is not int:
            raise DomainInvariantError("ratio numerator must be an integer")
        if type(self.denominator) is not int:
            raise DomainInvariantError("ratio denominator must be an integer")
        if self.numerator < 0:
            raise DomainInvariantError("ratio numerator cannot be negative")
        if self.denominator <= 0:
            raise DomainInvariantError("ratio denominator must be positive")


@dataclass(frozen=True, slots=True)
class AssessmentPolicy:
    """The one explicit policy supplied by the assessment—not a global rules DSL."""

    version: str = "assessment-v1"
    overdraft_fee: Money = Money(AED, 2_500)
    daily_interest_rate: Ratio = Ratio(1, 2_500)

    def __post_init__(self) -> None:
        if not self.version:
            raise DomainInvariantError("policy version cannot be empty")
        if self.overdraft_fee.currency != AED:
            raise DomainInvariantError("the assessment overdraft fee must be AED")
        if self.overdraft_fee.minor_units <= 0:
            raise DomainInvariantError("overdraft fee must be positive")


@dataclass(frozen=True, slots=True)
class ApproveAuthorization:
    hold: Money
    available_before_hold: Money
    available_after_hold: Money


@dataclass(frozen=True, slots=True)
class DeclineAuthorization:
    requested: Money
    available_before_hold: Money
    available_after_hold: Money


type AuthorizationDecision = ApproveAuthorization | DeclineAuthorization


@dataclass(frozen=True, slots=True)
class AcceptSettlement:
    captured: Money
    released: Money


@dataclass(frozen=True, slots=True)
class RejectSettlement:
    code: RejectionCode
    message: str


type SettlementDecision = AcceptSettlement | RejectSettlement


def decide_authorization(
    policy: AssessmentPolicy,
    *,
    ledger_balance: Money,
    active_holds: Money,
    requested: Money,
) -> AuthorizationDecision:
    """Approve exactly when available balance remains nonnegative."""

    _ = policy
    if active_holds.minor_units < 0:
        raise DomainInvariantError("active holds cannot be negative")
    if requested.minor_units <= 0:
        raise DomainInvariantError("authorization request must be positive")
    available_before_hold = ledger_balance - active_holds
    available_after_hold = available_before_hold - requested
    if available_after_hold.minor_units >= 0:
        return ApproveAuthorization(
            hold=requested,
            available_before_hold=available_before_hold,
            available_after_hold=available_after_hold,
        )
    return DeclineAuthorization(
        requested=requested,
        available_before_hold=available_before_hold,
        available_after_hold=available_after_hold,
    )


def decide_settlement(
    policy: AssessmentPolicy,
    *,
    authorization: AuthorizationView | None,
    requested: Money,
) -> SettlementDecision:
    """Resolve one final capture; multi-capture and over-capture are unsupported."""

    _ = policy
    if requested.minor_units <= 0:
        raise DomainInvariantError("settlement request must be positive")
    if authorization is None:
        return RejectSettlement(
            RejectionCode.AUTHORIZATION_NOT_FOUND,
            "settlement references an authorization that does not exist",
        )
    if authorization.status is not AuthorizationStatus.ACTIVE:
        return RejectSettlement(
            RejectionCode.AUTHORIZATION_NOT_ACTIVE,
            f"authorization is {authorization.status.value}, not active",
        )
    if requested.currency != authorization.active_hold.currency:
        return RejectSettlement(
            RejectionCode.CURRENCY_MISMATCH,
            "settlement currency differs from the authorization currency",
        )
    if requested.minor_units > authorization.active_hold.minor_units:
        return RejectSettlement(
            RejectionCode.OVER_CAPTURE,
            "settlement exceeds the active authorization hold",
        )
    return AcceptSettlement(
        captured=requested,
        released=authorization.active_hold - requested,
    )


def fee_for_close(
    policy: AssessmentPolicy,
    *,
    account: Account,
    closing: Money,
) -> Money | None:
    """Return the positive fee charge for a negative daily close."""

    if closing.currency != account.currency:
        raise CurrencyMismatchError("closing balance uses the wrong account currency")
    if closing.minor_units >= 0:
        return None
    if account.currency != policy.overdraft_fee.currency:
        raise UnsupportedFeeCurrencyError(
            f"no overdraft fee rule exists for {account.currency.code}"
        )
    return policy.overdraft_fee


def split_installments(
    policy: AssessmentPolicy, *, total: Money, count: int
) -> tuple[Money, ...]:
    _ = policy
    if total.minor_units <= 0:
        raise DomainInvariantError("installment total must be positive")
    return allocate_evenly(total, count)


def daily_interest(
    policy: AssessmentPolicy, *, closing: Money
) -> Money:
    """Round one day's positive-balance interest directly to minor units."""

    if closing.minor_units <= 0:
        return Money.zero(closing.currency)
    units = round_ratio_half_even(
        closing.minor_units * policy.daily_interest_rate.numerator,
        policy.daily_interest_rate.denominator,
    )
    return Money(closing.currency, units)


def capitalization_total(
    policy: AssessmentPolicy,
    *,
    currency: Currency,
    rounded_daily_accruals: tuple[Money, ...],
) -> Money:
    """Sum stored rounded accruals; never recalculate or discard a remainder."""

    _ = policy
    total = Money.zero(currency)
    for accrual in rounded_daily_accruals:
        if accrual.minor_units < 0:
            raise DomainInvariantError("daily interest accrual cannot be negative")
        total = total + accrual
    return total
