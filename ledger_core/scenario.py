"""The supplied assessment fixture, kept separate from reusable ledger logic."""

from __future__ import annotations

from ledger_core.journal import Ledger, new_ledger
from ledger_core.model import (
    AED,
    BHD,
    Account,
    AuthorizationRequested,
    Credit,
    Debit,
    InputEvent,
    Money,
    ReversalRequested,
    SettlementRequested,
)


ASSESSMENT_DAYS: tuple[int, ...] = (1, 2, 3, 4, 5, 6)


def assessment_accounts() -> tuple[Account, ...]:
    return (
        Account("ACC-001", AED, Money.zero(AED)),
        Account("ACC-002", BHD, Money.zero(BHD)),
    )


def empty_assessment_ledger() -> Ledger:
    return new_ledger(assessment_accounts())


def assessment_events() -> tuple[InputEvent, ...]:
    """Return E1-E10 in supplied sequence, including late-listed E10."""

    return (
        Credit("E1", 1, "ACC-001", Money.parse(AED, "1200.00"), 1),
        Debit("E2", 1, "ACC-001", Money.parse(AED, "950.00"), 1),
        AuthorizationRequested(
            "E3",
            2,
            "ACC-001",
            "Auth-A",
            Money.parse(AED, "200.00"),
            2,
        ),
        Credit("E4", 3, "ACC-001", Money.parse(AED, "400.00"), 3),
        SettlementRequested(
            "E5",
            4,
            "ACC-001",
            "Auth-A",
            Money.parse(AED, "185.00"),
            4,
        ),
        SettlementRequested(
            "E6",
            4,
            "ACC-001",
            "Auth-Z",
            Money.parse(AED, "180.00"),
            4,
        ),
        Debit("E7", 5, "ACC-001", Money.parse(AED, "620.00"), 2),
        AuthorizationRequested(
            "E8",
            5,
            "ACC-001",
            "Auth-B",
            Money.parse(AED, "90.00"),
            5,
        ),
        ReversalRequested("E9", 6, "ACC-001", "E7", 2),
        Credit(
            "E10",
            5,
            "ACC-002",
            Money.parse(BHD, "10.000"),
            5,
            installments=3,
        ),
    )

