package store

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strconv"

	"github.com/jackc/pgx/v5"
	"github.com/sabino/account-ledger-core/service/internal/db"
	"github.com/sabino/account-ledger-core/service/internal/domain"
)

var ErrClosePending = errors.New("account day close pending")
var ErrCalendarInput = errors.New("invalid simulation day transition")
var ErrClosePolicy = errors.New("live overdraft close policy is not configured")

// Fixed simulation cadence, recorded explicitly in each period envelope.
// This is not a configurable bank month or a change to fixture finalization.
const simulationPeriodDays int32 = 6

// CloseAccountDay records daily accrual and, on a period boundary, capitalizes
// the sum of rounded daily amounts. The final accrual, balanced posting, period,
// completed job and outbox commit together before next-day spending is allowed.
func (s *Store) CloseAccountDay(ctx context.Context, runID, accountID string, day int32) (Result, error) {
	return s.closeAccountDay(ctx, runID, accountID, day, false)
}

func (s *Store) closeAccountDay(ctx context.Context, runID, accountID string, day int32, scheduled bool) (Result, error) {
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
	if scheduled {
		if err = admitCalendar(ctx, q, runID); err != nil {
			return Result{}, err
		}
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
	metadata, err := q.StatementAccount(ctx, db.StatementAccountParams{RunID: runID, ID: accountID})
	if err != nil {
		return Result{}, err
	}
	if !metadata.Customer || metadata.Class != "liability" {
		return Result{}, ErrCalendarInput
	}
	ids := []string{accountID}
	boundary := day%simulationPeriodDays == 0
	if boundary {
		ids = append(ids, "interest-"+metadata.Currency)
	}
	sort.Strings(ids)
	accounts := make(map[string]*db.Account, len(ids))
	for _, id := range ids {
		locked, err := q.LockAccount(ctx, db.LockAccountParams{RunID: runID, ID: id})
		if err != nil {
			return Result{}, err
		}
		accounts[id] = &locked
	}
	account := accounts[accountID]
	if account.Currency != metadata.Currency || !account.Customer || account.Class != "liability" {
		return Result{}, ErrCalendarInput
	}
	if boundary {
		counterpart := accounts["interest-"+account.Currency]
		if counterpart.Customer || counterpart.Class != "expense" || counterpart.Currency != account.Currency {
			return Result{}, errors.New("invalid interest expense account")
		}
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
	if boundary {
		start := day - simulationPeriodDays + 1
		prior, err := q.PriorPeriodCloses(ctx, db.PriorPeriodClosesParams{RunID: runID, AccountID: accountID, StartDay: start, ThroughDay: day})
		if err != nil {
			return Result{}, err
		}
		if len(prior) != int(simulationPeriodDays-1) {
			return Result{}, ErrClosePending
		}
		period := &PeriodEvidence{StartDay: start, ThroughDay: day, Amount: amount}
		accruals := make([]Accrual, 0, simulationPeriodDays)
		for i, row := range prior {
			var closed Result
			if err = json.Unmarshal(row.Response, &closed); err != nil {
				return Result{}, err
			}
			if row.Day != start+int32(i) || closed.Status != "accepted" || closed.Kind != "account_close" || len(closed.Accruals) != 1 || closed.Sequence <= 0 {
				return Result{}, errors.New("incomplete period accrual evidence")
			}
			accrual := closed.Accruals[0]
			if accrual.Account != accountID || accrual.Currency != account.Currency || accrual.ValueDay != row.Day || accrual.Amount < 0 {
				return Result{}, errors.New("inconsistent period accrual evidence")
			}
			period.Amount, err = domain.Add(period.Amount, accrual.Amount)
			if err != nil {
				return Result{}, err
			}
			period.PriorSequences = append(period.PriorSequences, strconv.FormatInt(closed.Sequence, 10))
			accruals = append(accruals, accrual)
		}
		result.Accruals = append(accruals, result.Accruals...)
		result.Period = period
		if period.Amount > 0 {
			result.Legs = movement("interest-"+account.Currency, accountID, account.Currency, period.Amount, day, "interest")
			if err = applyBalances(ctx, q, runID, accounts, result); err != nil {
				return Result{}, err
			}
		}
	}
	if err = s.appendResult(ctx, q, run, command, &result); err != nil {
		return Result{}, err
	}
	if result.Period != nil {
		if err = q.RecordAccountPeriod(ctx, db.RecordAccountPeriodParams{RunID: runID, AccountID: accountID, StartDay: result.Period.StartDay, ThroughDay: day, Sequence: result.Sequence, Amount: result.Period.Amount}); err != nil {
			return Result{}, err
		}
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
	return s.advanceDay(ctx, runID, from, false)
}

func (s *Store) advanceDay(ctx context.Context, runID string, from int32, scheduled bool) error {
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
	if scheduled {
		// The exclusive lifecycle lock makes the due-time decision and day
		// transition indivisible across replicas. No wall-clock catch-up loop.
		due, err := q.CalendarDue(ctx, runID)
		if err != nil {
			return err
		}
		if !due {
			return nil
		}
		if err = admitCalendar(ctx, q, runID); err != nil {
			return err
		}
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

// CalendarStep executes at most one close or one due transition. Replicas may
// choose the same job; its existing transaction identity makes this harmless.
// Pending work drains even when generation is paused, but never without host
// and database admission. Blocked jobs require a policy/operator resolution.
func (s *Store) CalendarStep(ctx context.Context, runID string) error {
	job, err := s.Queries.NextPendingClose(ctx, runID)
	if err == nil {
		_, err = s.closeAccountDay(ctx, runID, job.AccountID, job.Day, true)
		return err
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return err
	}
	day, err := s.Queries.CalendarRunDay(ctx, runID)
	if err != nil {
		return err
	}
	if day >= 366 {
		return nil
	}
	return s.advanceDay(ctx, runID, day, true)
}

// Same shared 20-operation/second budget as public/generator traffic. Held
// after the lifecycle lock and before operation/account/journal locks.
func admitCalendar(ctx context.Context, q *db.Queries, runID string) error {
	n, err := q.Admit(ctx, runID)
	if err != nil {
		return err
	}
	if n != 1 {
		return ErrCapacity
	}
	return nil
}
