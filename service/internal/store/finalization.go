package store

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"github.com/sabino/account-ledger-core/service/internal/db"
	"github.com/sabino/account-ledger-core/service/internal/domain"
)

// Finalize implements the assessment's terminal window, not recurring live
// periods. The exclusive lifecycle lock waits for all in-flight commands.
func (s *Store) Finalize(ctx context.Context, runID string, from, through int32) (Result, error) {
	if from < 1 || through < from || through > 366 {
		return Result{}, errors.New("invalid bounded finalization window")
	}
	tx, err := s.Pool.Begin(ctx)
	if err != nil {
		return Result{}, err
	}
	defer tx.Rollback(ctx)
	queries := s.Queries.WithTx(tx)
	run, err := queries.LockFinalization(ctx, runID)
	if err != nil {
		return Result{}, err
	}
	if run.Profile != "fixture" {
		return Result{}, errors.New("terminal finalization is fixture-only; live periods use account closes")
	}
	policy, err := domain.ParsePolicy(run.Policy)
	if err != nil {
		return Result{}, err
	}
	command := Command{ID: fmt.Sprintf("interest:%d-%d", from, through), Kind: "interest", BookedDay: through, ValueDay: through}
	// The window and immutable persisted policy are the finalization identity.
	hash := fmt.Sprintf("%d/%d/%s", from, through, run.Policy)
	if err = queries.ClaimCommand(ctx, db.ClaimCommandParams{RunID: runID, ID: command.ID, Hash: hash}); err != nil {
		return Result{}, err
	}
	prior, err := queries.LockCommand(ctx, db.LockCommandParams{RunID: runID, ID: command.ID})
	if err != nil {
		return Result{}, err
	}
	if prior.Hash != hash {
		return Result{}, ErrConflict
	}
	if len(prior.Response) > 0 {
		var result Result
		err = json.Unmarshal(prior.Response, &result)
		return result, err
	}
	if run.Finalized {
		return Result{}, errors.New("a different window was already finalized")
	}
	rows, err := queries.ListAccounts(ctx, runID)
	if err != nil {
		return Result{}, err
	}
	accounts := make(map[string]*db.Account, len(rows))
	for _, row := range rows {
		account, err := queries.LockAccount(ctx, db.LockAccountParams{RunID: runID, ID: row.ID})
		if err != nil {
			return Result{}, err
		}
		accounts[row.ID] = &account
	}
	fees := []Leg{}
	for _, row := range rows {
		if !row.Customer {
			continue
		}
		more, err := missingFees(ctx, queries, runID, accounts[row.ID], from, through, fees, policy)
		if err != nil {
			return Result{}, err
		}
		fees = append(fees, more...)
	}
	if len(fees) > 0 {
		maintenance := Result{ID: command.ID + ":fees", Kind: "day_close", Status: "accepted", Instance: s.Instance, Legs: fees}
		feeCommand := command
		feeCommand.Kind = "day_close"
		if err = applyBalances(ctx, queries, runID, accounts, maintenance); err != nil {
			return Result{}, err
		}
		if err = s.appendResult(ctx, queries, run, feeCommand, &maintenance); err != nil {
			return Result{}, err
		}
	}
	result := Result{ID: command.ID, Kind: "interest", Status: "accepted", Instance: s.Instance, Legs: []Leg{}}
	for _, row := range rows {
		if !row.Customer {
			continue
		}
		var total int64
		for day := from; day <= through; day++ {
			basis, err := queries.HistoricalBalance(ctx, db.HistoricalBalanceParams{RunID: runID, AccountID: row.ID, ValueDay: day})
			if err != nil {
				return Result{}, err
			}
			amount, err := domain.Interest(basis, policy.Numerator, policy.Denominator)
			if err != nil {
				return Result{}, err
			}
			total, err = domain.Add(total, amount)
			if err != nil {
				return Result{}, err
			}
			result.Accruals = append(result.Accruals, Accrual{Account: row.ID, Currency: row.Currency, ValueDay: day, Basis: basis, Amount: amount})
		}
		if total > 0 {
			result.Legs = append(result.Legs, movement("interest-"+row.Currency, row.ID, row.Currency, total, through, "interest")...)
		}
	}
	if err = applyBalances(ctx, queries, runID, accounts, result); err != nil {
		return Result{}, err
	}
	if err = s.appendResult(ctx, queries, run, command, &result); err != nil {
		return Result{}, err
	}
	if err = queries.RecordPeriod(ctx, db.RecordPeriodParams{RunID: runID, StartDay: from, ThroughDay: through, CommandID: command.ID}); err != nil {
		return Result{}, err
	}
	if err = queries.FinalizeRun(ctx, runID); err != nil {
		return Result{}, err
	}
	return result, tx.Commit(ctx)
}
