//go:build integration

package store

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"
)

func TestCalendarTransitionIsAtomicAndIdempotent(t *testing.T) {
	a, b, run := testLedger(t)
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	var wg sync.WaitGroup
	failures := make(chan error, 8)
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			s := a
			if i%2 == 1 {
				s = b
			}
			failures <- s.AdvanceDay(ctx, run, 1)
		}(i)
	}
	wg.Wait()
	close(failures)
	for err := range failures {
		if err != nil {
			t.Fatal(err)
		}
	}
	var day, jobs, transitions int
	err := a.Pool.QueryRow(ctx, `SELECT day,(SELECT count(*) FROM account_close_jobs WHERE run_id=$1),(SELECT count(*) FROM day_transitions WHERE run_id=$1) FROM runs WHERE id=$1`, run).Scan(&day, &jobs, &transitions)
	if err != nil {
		t.Fatal(err)
	}
	if day != 2 || jobs != 3 || transitions != 1 {
		t.Fatalf("day=%d jobs=%d transitions=%d", day, jobs, transitions)
	}
	input := command("after-transition", "transfer")
	input.BookedDay = 2
	input.ValueDay = 2
	if _, err = a.Process(ctx, run, input); !errors.Is(err, ErrClosePending) {
		t.Fatalf("pending: %v", err)
	}
	var recorded int
	if err = a.Pool.QueryRow(ctx, "SELECT count(*) FROM command_results WHERE run_id=$1 AND id=$2", run, input.ID).Scan(&recorded); err != nil {
		t.Fatal(err)
	}
	if recorded != 0 {
		t.Fatal("administrative close refusal became a command outcome")
	}
	// Stand in for the not-yet-connected close executor. These operational rows
	// are mutable; the transition itself must remain immutable.
	if _, err = a.Pool.Exec(ctx, "UPDATE account_close_jobs SET state='done' WHERE run_id=$1 AND account_id IN ('a','b')", run); err != nil {
		t.Fatal(err)
	}
	result, err := b.Process(ctx, run, input)
	if err != nil || result.Status != "accepted" {
		t.Fatalf("unrelated pending BHD close poisoned AED transfer: %+v %v", result, err)
	}
	if err = a.AdvanceDay(ctx, run, 2); !errors.Is(err, ErrClosePending) {
		t.Fatalf("next transition: %v", err)
	}
	if _, err = a.Pool.Exec(ctx, "UPDATE account_close_jobs SET state='done' WHERE run_id=$1", run); err != nil {
		t.Fatal(err)
	}
	if err = a.AdvanceDay(ctx, run, 2); err != nil {
		t.Fatal(err)
	}
	if err = b.AdvanceDay(ctx, run, 1); err != nil {
		t.Fatalf("old exact retry: %v", err)
	}
	if err = a.AdvanceDay(ctx, run, 4); !errors.Is(err, ErrCalendarInput) {
		t.Fatalf("skipped day: %v", err)
	}
	if _, err = a.Pool.Exec(ctx, "DELETE FROM day_transitions WHERE run_id=$1", run); err == nil {
		t.Fatal("runtime deleted immutable transition")
	}
}

func TestCalendarWaitsForOldDayLifecycleLock(t *testing.T) {
	a, b, run := testLedger(t)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	tx, err := a.Pool.Begin(ctx)
	if err != nil {
		t.Fatal(err)
	}
	defer tx.Rollback(ctx)
	if _, err = a.Queries.WithTx(tx).LockRun(ctx, run); err != nil {
		t.Fatal(err)
	}
	finished := make(chan error, 1)
	go func() { finished <- b.AdvanceDay(ctx, run, 1) }()
	select {
	case err := <-finished:
		t.Fatalf("advanced through an old-day lock: %v", err)
	case <-time.After(100 * time.Millisecond):
	}
	if err = tx.Commit(ctx); err != nil {
		t.Fatal(err)
	}
	if err = <-finished; err != nil {
		t.Fatal(err)
	}
	for _, from := range []int32{0, -1, 366} {
		if err = a.AdvanceDay(ctx, run, from); !errors.Is(err, ErrCalendarInput) {
			t.Fatalf("invalid day %d: %v", from, err)
		}
	}
}
