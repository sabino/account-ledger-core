package store

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"
	"github.com/sabino/account-ledger-core/service/internal/db"
)

var ErrClosePending = errors.New("account day close pending")
var ErrCalendarInput = errors.New("invalid simulation day transition")

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
