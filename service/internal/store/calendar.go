package store

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/sabino/account-ledger-core/service/internal/db"
	"github.com/sabino/account-ledger-core/service/internal/domain"
)

var ErrClosePending = errors.New("account day close pending")
var ErrCalendarInput = errors.New("invalid simulation day transition")
var ErrClosePolicy = errors.New("live overdraft close policy is not configured")

// CloseAccountDay records accrual evidence, not capitalization. Identity,
// account lock, job completion, journal and outbox commit together. It does not
// perform network IO or hold another customer's lock.
func (s *Store) CloseAccountDay(ctx context.Context, runID, accountID string, day int32) (Result, error) {
	if day < 1 || day >= 366 || len(accountID) == 0 || len(accountID) > 80 {
		return Result{}, ErrCalendarInput
	}
	tx, err := s.Pool.Begin(ctx)
	if err != nil {
		return Result{}, err
	}
	defer tx.Rollback(ctx)
	q := s.Queries.WithTx(tx)
	run, err := q.LockRun(ctx, runID)
	if err != nil {
		return Result{}, err
	}
	if run.Profile != "live" || run.Finalized || day >= run.Day {
		return Result{}, ErrCalendarInput
	}
	command := Command{ID: fmt.Sprintf("system:close:%d:%s", day, accountID), Kind: "account_close", Account: accountID, BookedDay: run.Day, ValueDay: day}
	hash := fmt.Sprintf("close/%d/%s/%s", day, accountID, run.Policy)
	if err = q.ClaimCommand(ctx, db.ClaimCommandParams{RunID: runID, ID: command.ID, Hash: hash}); err != nil {
		return Result{}, err
	}
	prior, err := q.LockCommand(ctx, db.LockCommandParams{RunID: runID, ID: command.ID})
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
	account, err := q.LockAccount(ctx, db.LockAccountParams{RunID: runID, ID: accountID})
	if err != nil {
		return Result{}, err
	}
	if !account.Customer {
		return Result{}, ErrCalendarInput
	}
	job, err := q.LockAccountCloseJob(ctx, db.LockAccountCloseJobParams{RunID: runID, AccountID: accountID, Day: day})
	if err != nil {
		return Result{}, err
	}
	if job.State == "done" {
		return Result{}, errors.New("completed close has no journal response")
	}
	policy, err := domain.ParsePolicy(run.Policy)
	if err != nil {
		return Result{}, err
	}
	basis, err := q.HistoricalBalance(ctx, db.HistoricalBalanceParams{RunID: runID, AccountID: accountID, ValueDay: day})
	if err != nil {
		return Result{}, err
	}
	if basis < 0 {
		if err = q.SetAccountCloseJob(ctx, db.SetAccountCloseJobParams{RunID: runID, AccountID: accountID, Day: day, State: "blocked", Reason: ErrClosePolicy.Error()}); err != nil {
			return Result{}, err
		}
		if err = tx.Commit(ctx); err != nil {
			return Result{}, err
		}
		return Result{}, ErrClosePolicy
	}
	amount, err := domain.Interest(basis, policy.Numerator, policy.Denominator)
	if err != nil {
		return Result{}, err
	}
	command.Currency = account.Currency
	result := Result{ID: command.ID, Kind: command.Kind, Status: "accepted", Instance: s.Instance, Legs: []Leg{}, Accruals: []Accrual{{Account: accountID, Currency: account.Currency, ValueDay: day, Basis: basis, Amount: amount}}}
	if err = s.appendResult(ctx, q, run, command, &result); err != nil {
		return Result{}, err
	}
	if err = q.SetAccountCloseJob(ctx, db.SetAccountCloseJobParams{RunID: runID, AccountID: accountID, Day: day, State: "done"}); err != nil {
		return Result{}, err
	}
	return result, tx.Commit(ctx)
}

// AdvanceDay is an internal scheduler operation, not a public date override.
// The exclusive lifecycle lock waits for old-day commands and creates every
// close job in the same transaction as the new day. Repeating the same transition
// is a no-op even after the run has advanced further.
func (s *Store) AdvanceDay(ctx context.Context, runID string, from int32) error {
	if from < 1 || from >= 366 {
		return ErrCalendarInput
	}
	tx, err := s.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	q := s.Queries.WithTx(tx)
	run, err := q.LockFinalization(ctx, runID)
	if err != nil {
		return err
	}
	if run.Profile != "live" || run.Finalized {
		return ErrCalendarInput
	}
	_, err = q.FindDayTransition(ctx, db.FindDayTransitionParams{RunID: runID, FromDay: from})
	if err == nil {
		return nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return err
	}
	if run.Day != from {
		return ErrCalendarInput
	}
	pending, err := q.PendingRunCloses(ctx, runID)
	if err != nil {
		return err
	}
	if pending > 0 {
		return ErrClosePending
	}
	if err = q.RecordDayTransition(ctx, db.RecordDayTransitionParams{RunID: runID, FromDay: from, ToDay: from + 1, Instance: s.Instance}); err != nil {
		return err
	}
	if err = q.ScheduleAccountCloses(ctx, db.ScheduleAccountClosesParams{RunID: runID, Day: from}); err != nil {
		return err
	}
	if err = q.AdvanceRunDay(ctx, db.AdvanceRunDayParams{ID: runID, Day: from + 1}); err != nil {
		return err
	}
	return tx.Commit(ctx)
}
