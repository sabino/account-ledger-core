package store

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"
	"github.com/sabino/account-ledger-core/service/internal/db"
	"github.com/sabino/account-ledger-core/service/internal/domain"
)

var ErrUnsupportedFee = errors.New("no fee policy exists for this currency")

// Each account is already locked. Newly generated fee legs participate in the
// next day's close, but an assessed account/day can never be charged twice.
func missingFees(ctx context.Context, queries *db.Queries, runID string, account *db.Account, from, through int32, pending []Leg, policy domain.Policy) ([]Leg, error) {
	fees := []Leg{}
	assessed, err := queries.AssessedFeeDays(ctx, db.AssessedFeeDaysParams{RunID: runID, AccountID: account.ID})
	if err != nil {
		return nil, err
	}
	exists := make(map[int32]bool, len(assessed))
	for _, day := range assessed {
		exists[day] = true
	}
	for day := from; day <= through; day++ {
		if exists[day] {
			continue
		}
		balance, err := queries.HistoricalBalance(ctx, db.HistoricalBalanceParams{RunID: runID, AccountID: account.ID, ValueDay: day})
		if err != nil {
			return nil, err
		}
		for _, legs := range [][]Leg{pending, fees} {
			for _, leg := range legs {
				if leg.Account == account.ID && leg.ValueDay <= day {
					balance, err = domain.Add(balance, -leg.Units)
					if err != nil {
						return nil, err
					}
				}
			}
		}
		if balance >= 0 {
			continue
		}
		if account.Currency != "AED" {
			return nil, ErrUnsupportedFee
		}
		if err = queries.RecordFee(ctx, db.RecordFeeParams{RunID: runID, AccountID: account.ID, ValueDay: day}); err != nil {
			return nil, err
		}
		fees = append(fees, movement(account.ID, "fees-AED", "AED", policy.FeeAED, day, "overdraft_fee")...)
	}
	return fees, nil
}

func (s *Store) closeBeforeEvent(ctx context.Context, queries *db.Queries, run db.Run, command Command, accounts map[string]*db.Account) error {
	policy, err := domain.ParsePolicy(run.Policy)
	if err != nil {
		return err
	}
	latest, err := queries.LatestBookedDay(ctx, run.ID)
	if err != nil {
		return err
	}
	fees, err := missingFees(ctx, queries, run.ID, accounts[command.Account], 1, max(latest, command.BookedDay)-1, nil, policy)
	if err != nil {
		return err
	}
	if len(fees) == 0 {
		return nil
	}
	maintenance := Result{ID: "day-close-before:" + command.ID, Status: "accepted", Kind: "day_close", Instance: s.Instance, Legs: fees}
	if err = applyBalances(ctx, queries, run.ID, accounts, maintenance); err != nil {
		return err
	}
	maintenanceCommand := command
	maintenanceCommand.Kind = "day_close"
	// Both batches become visible in the same SQL transaction. Completing the
	// original command later replaces only its temporary, uncommitted response.
	return s.appendResult(ctx, queries, run, maintenanceCommand, &maintenance)
}

func reverseDebit(ctx context.Context, queries *db.Queries, runID string, command Command, result *Result) error {
	target, err := queries.FindReversibleDebit(ctx, db.FindReversibleDebitParams{RunID: runID, AccountID: command.Account, CommandID: command.TargetEvent})
	if errors.Is(err, pgx.ErrNoRows) {
		result.reject("reversal target not found")
		return nil
	}
	if err != nil {
		return err
	}
	inserted, err := queries.RecordReversal(ctx, db.RecordReversalParams{RunID: runID, TargetEvent: command.TargetEvent, CommandID: command.ID})
	if err != nil {
		return err
	}
	if inserted == 0 {
		result.reject("reversal already applied")
		return nil
	}
	result.Legs = movement("settlement-"+command.Currency, command.Account, command.Currency, target.Units, command.ValueDay, "reversal")
	return nil
}
