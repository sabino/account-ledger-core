//go:build integration

package store

import (
	"context"
	"errors"
	"reflect"
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
	for _, id := range []string{"a", "b"} {
		if _, err = a.CloseAccountDay(ctx, run, id, 1); err != nil {
			t.Fatal(err)
		}
	}
	result, err := b.Process(ctx, run, input)
	if err != nil || result.Status != "accepted" {
		t.Fatalf("unrelated pending BHD close poisoned AED transfer: %+v %v", result, err)
	}
	if err = a.AdvanceDay(ctx, run, 2); !errors.Is(err, ErrClosePending) {
		t.Fatalf("next transition: %v", err)
	}
	if _, err = a.CloseAccountDay(ctx, run, "c", 1); err != nil {
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

func TestCloseAccountDayRetriesPreserveEvidence(t *testing.T) {
	a, b, run := testLedger(t)
	ctx := context.Background()
	held := command("reserved", "hold")
	held.Authorization = "hold-a"
	if result, err := a.Process(ctx, run, held); err != nil || result.Status != "accepted" {
		t.Fatalf("hold: %+v %v", result, err)
	}
	if err := a.AdvanceDay(ctx, run, 1); err != nil {
		t.Fatal(err)
	}
	results := make(chan Result, 8)
	failures := make(chan error, 8)
	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			s := a
			if i%2 == 1 {
				s = b
			}
			r, err := s.CloseAccountDay(ctx, run, "a", 1)
			results <- r
			failures <- err
		}(i)
	}
	wg.Wait()
	close(results)
	close(failures)
	for err := range failures {
		if err != nil {
			t.Fatal(err)
		}
	}
	var sequence int64
	var first *Result
	for r := range results {
		if first == nil {
			copy := r
			first = &copy
		} else if !reflect.DeepEqual(*first, r) {
			t.Fatal("close retries changed the recorded response")
		}
		if sequence == 0 {
			sequence = r.Sequence
		}
		if r.Sequence != sequence || len(r.Legs) != 0 || len(r.Accruals) != 1 || r.Accruals[0].Basis != 10000 || r.Accruals[0].Amount != 4 {
			t.Fatalf("close: %+v", r)
		}
	}
	var batches, outbox int
	if err := a.Pool.QueryRow(ctx, "SELECT (SELECT count(*) FROM journal_batches WHERE run_id=$1 AND kind='account_close'),(SELECT count(*) FROM outbox WHERE run_id=$1 AND sequence=$2)", run, sequence).Scan(&batches, &outbox); err != nil {
		t.Fatal(err)
	}
	if batches != 1 || outbox != 1 {
		t.Fatalf("batches=%d outbox=%d", batches, outbox)
	}
	var balance, heldUnits int64
	if err := a.Pool.QueryRow(ctx, "SELECT balance,held FROM accounts WHERE run_id=$1 AND id='a'", run).Scan(&balance, &heldUnits); err != nil {
		t.Fatal(err)
	}
	if balance != 10000 || heldUnits != 8000 {
		t.Fatal("accrual moved posted or reserved money")
	}
	invalid := command("system:close:1:b", "transfer")
	if _, err := a.Process(ctx, run, invalid); err == nil {
		t.Fatal("public command occupied the internal namespace")
	}
}

func TestNegativeCloseIsBlockedWithoutPoisoningOtherAccount(t *testing.T) {
	a, b, run := testLedger(t)
	ctx := context.Background()
	debit := command("overdraft", "debit")
	debit.Amount = "101"
	if r, err := a.Process(ctx, run, debit); err != nil || r.Status != "accepted" {
		t.Fatalf("setup: %+v %v", r, err)
	}
	if err := a.AdvanceDay(ctx, run, 1); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 2; i++ {
		if _, err := a.CloseAccountDay(ctx, run, "a", 1); !errors.Is(err, ErrClosePolicy) {
			t.Fatalf("negative close: %v", err)
		}
	}
	var state, reason string
	if err := a.Pool.QueryRow(ctx, "SELECT state,reason FROM account_close_jobs WHERE run_id=$1 AND account_id='a' AND day=1", run).Scan(&state, &reason); err != nil {
		t.Fatal(err)
	}
	if state != "blocked" || reason != ErrClosePolicy.Error() {
		t.Fatalf("job: %s %s", state, reason)
	}
	if _, err := b.CloseAccountDay(ctx, run, "b", 1); err != nil {
		t.Fatal(err)
	}
	credit := command("unrelated", "credit")
	credit.Account = "b"
	credit.BookedDay = 2
	credit.ValueDay = 2
	if r, err := b.Process(ctx, run, credit); err != nil || r.Status != "accepted" {
		t.Fatalf("unrelated credit: %+v %v", r, err)
	}
	var count int
	if err := a.Pool.QueryRow(ctx, "SELECT count(*) FROM journal_batches WHERE run_id=$1 AND command_id='system:close:1:a'", run).Scan(&count); err != nil {
		t.Fatal(err)
	}
	if count != 0 {
		t.Fatal("blocked close wrote accounting evidence")
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
