//go:build integration

package store

import (
	"context"
	"errors"
	"fmt"
	"net/url"
	"os"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
)

// Guard experiments must never overwrite the watcher evidence used by the
// running demo. This test owns and removes one newly created tiny database.
func TestCalendarSchedulerHonorsAdmissionAndDrainsPausedWork(t *testing.T) {
	ctx := context.Background()
	admin, err := Open(ctx, os.Getenv("TEST_DATABASE_URL"), "calendar-db-owner")
	if err != nil {
		t.Fatal(err)
	}
	name := fmt.Sprintf("ledger_calendar_test_%d", time.Now().UnixNano())
	if _, err = admin.Pool.Exec(ctx, "CREATE DATABASE "+pgx.Identifier{name}.Sanitize()); err != nil {
		admin.Pool.Close()
		t.Fatal(err)
	}
	t.Cleanup(func() {
		defer admin.Pool.Close()
		if _, err := admin.Pool.Exec(context.Background(), "DROP DATABASE "+pgx.Identifier{name}.Sanitize()); err != nil {
			t.Errorf("remove test-only database %s: %v", name, err)
		}
	})
	for _, key := range []string{"TEST_DATABASE_URL", "TEST_APP_DATABASE_URL"} {
		parsed, e := url.Parse(os.Getenv(key))
		if e != nil {
			t.Fatal(e)
		}
		parsed.Path = "/" + name
		t.Setenv(key, parsed.String())
	}
	a, b, run := testLedger(t)
	owner, err := Open(ctx, os.Getenv("TEST_DATABASE_URL"), "calendar-test-owner")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(owner.Pool.Close)
	exec := func(sql string, args ...any) {
		t.Helper()
		if _, e := owner.Pool.Exec(ctx, sql, args...); e != nil {
			t.Fatal(e)
		}
	}
	exec("UPDATE runs SET created_at=now()-interval '6 minutes' WHERE id=$1", run)
	exec("UPDATE controls SET eps=1,guard_until=now()+interval '1 hour',guard_reason='' WHERE run_id=$1", run)
	if err = a.CalendarStep(ctx, run); !errors.Is(err, ErrCapacity) {
		t.Fatalf("absent host guard: %v", err)
	}
	exec("INSERT INTO host_guard(id,safe_until,reason,evidence) VALUES(true,now()-interval '1 second','test expired','{}')")
	if err = a.CalendarStep(ctx, run); !errors.Is(err, ErrCapacity) {
		t.Fatalf("expired host guard: %v", err)
	}
	exec("UPDATE host_guard SET safe_until=now()+interval '1 hour',reason='' WHERE id")
	exec("UPDATE controls SET guard_until=now()-interval '1 second' WHERE run_id=$1", run)
	if err = a.CalendarStep(ctx, run); !errors.Is(err, ErrCapacity) {
		t.Fatalf("expired database guard: %v", err)
	}
	exec("UPDATE controls SET guard_until=now()+interval '1 hour',pause_reason='test safety pause' WHERE run_id=$1", run)
	if err = a.CalendarStep(ctx, run); !errors.Is(err, ErrCapacity) {
		t.Fatalf("safety pause: %v", err)
	}
	exec("UPDATE controls SET pause_reason='',eps=0 WHERE run_id=$1", run)
	if err = a.CalendarStep(ctx, run); err != nil {
		t.Fatal(err)
	}
	assertDay := func(want int32) {
		t.Helper()
		got, e := a.Queries.CalendarRunDay(ctx, run)
		if e != nil || got != want {
			t.Fatalf("day=%d expected=%d: %v", got, want, e)
		}
	}
	assertDay(1)
	exec("UPDATE controls SET eps=1 WHERE run_id=$1", run)
	var wg sync.WaitGroup
	failures := make(chan error, 2)
	for _, s := range []*Store{a, b} {
		wg.Add(1)
		go func(s *Store) { defer wg.Done(); failures <- s.CalendarStep(ctx, run) }(s)
	}
	wg.Wait()
	close(failures)
	for e := range failures {
		if e != nil {
			t.Fatal(e)
		}
	}
	assertDay(2)
	// A second worker can already have drained the first close. Pause must
	// prevent another transition, while remaining admitted closes still drain.
	exec("UPDATE controls SET eps=0 WHERE run_id=$1", run)
	exec("UPDATE host_guard SET safe_until=now()-interval '1 second' WHERE id")
	if err = a.CalendarStep(ctx, run); !errors.Is(err, ErrCapacity) {
		t.Fatalf("close bypassed expired host guard: %v", err)
	}
	exec("UPDATE host_guard SET safe_until=now()+interval '1 hour' WHERE id")
	var position int64
	if err = a.Pool.QueryRow(ctx, "SELECT position FROM journal_clock WHERE run_id=$1", run).Scan(&position); err != nil {
		t.Fatal(err)
	}
	exec("UPDATE journal_clock SET position=100000 WHERE run_id=$1", run)
	if err = a.CalendarStep(ctx, run); !errors.Is(err, ErrCapacity) {
		t.Fatalf("close bypassed run ceiling: %v", err)
	}
	exec("UPDATE journal_clock SET position=$2 WHERE run_id=$1", run, position)
	for i := 0; i < 3; i++ {
		if err = b.CalendarStep(ctx, run); err != nil {
			t.Fatal(err)
		}
	}
	pending, err := a.Queries.PendingRunCloses(ctx, run)
	if err != nil || pending != 0 {
		t.Fatalf("paused drain: %d %v", pending, err)
	}
	assertDay(2)
	exec("UPDATE controls SET eps=1 WHERE run_id=$1", run)
	if err = a.CalendarStep(ctx, run); err != nil {
		t.Fatal(err)
	}
	assertDay(2) // Not due again: restarting/catching up cannot race through days.
	var transitions int
	if err = a.Pool.QueryRow(ctx, "SELECT count(*) FROM day_transitions WHERE run_id=$1", run).Scan(&transitions); err != nil || transitions != 1 {
		t.Fatalf("transitions=%d: %v", transitions, err)
	}
}
