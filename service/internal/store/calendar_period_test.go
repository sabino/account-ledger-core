//go:build integration

package store

import (
	"context"
	"fmt"
	"os"
	"reflect"
	"sync"
	"testing"

	"github.com/sabino/account-ledger-core/service/internal/db"
)

func TestRecurringPeriodsCapitalizeRoundedDaysExactlyOnce(t *testing.T) {
	a, b, run := testLedger(t)
	ctx := context.Background()
	owner, err := Open(ctx, os.Getenv("TEST_DATABASE_URL"), "period-test-owner")
	if err != nil {
		t.Fatal(err)
	}
	defer owner.Pool.Close()
	for _, currency := range []string{"AED", "BHD"} {
		if err = owner.Queries.CreateAccount(ctx, db.CreateAccountParams{RunID: run, ID: "interest-" + currency, Name: "Interest expense", Currency: currency, Class: "expense"}); err != nil {
			t.Fatal(err)
		}
	}
	if err = owner.Queries.CreateAccount(ctx, db.CreateAccountParams{RunID: run, ID: "settlement-BHD", Name: "Settlement", Currency: "BHD", Class: "asset"}); err != nil {
		t.Fatal(err)
	}
	// Half-even ties: 1,250 / 2,500 rounds to zero; 3,750 / 2,500
	// rounds to two. Six rounded days are NOT rounding the six-day sum.
	for _, cmd := range []Command{
		{ID: "reduce-a", Kind: "debit", Account: "a", Currency: "AED", Amount: "87.50", BookedDay: 1, ValueDay: 1},
		{ID: "reduce-b", Kind: "debit", Account: "b", Currency: "AED", Amount: "62.50", BookedDay: 1, ValueDay: 1},
		{ID: "fund-c", Kind: "credit", Account: "c", Currency: "BHD", Amount: "3.750", BookedDay: 1, ValueDay: 1},
	} {
		if r, e := a.Process(ctx, run, cmd); e != nil || r.Status != "accepted" {
			t.Fatalf("setup: %+v %v", r, e)
		}
	}
	var firstPeriod Result
	for day := int32(1); day <= 12; day++ {
		if day == 7 {
			if r, e := a.Process(ctx, run, Command{ID: "increase-a", Kind: "credit", Account: "a", Currency: "AED", Amount: "25", BookedDay: 7, ValueDay: 7}); e != nil || r.Status != "accepted" {
				t.Fatalf("new-period credit: %+v %v", r, e)
			}
		}
		if _, e := a.CloseAccountDay(ctx, run, "a", day); e == nil {
			t.Fatal("closed an unfinished current day")
		}
		if err = a.AdvanceDay(ctx, run, day); err != nil {
			t.Fatal(err)
		}
		if day == 6 {
			// Fail after balance/journal/outbox staging, at period insertion.
			// Only the new local period table is locked; no live calendar runs.
			blocker, e := owner.Pool.Begin(ctx)
			if e != nil {
				t.Fatal(e)
			}
			defer blocker.Rollback(ctx)
			if _, e = blocker.Exec(ctx, "LOCK TABLE account_periods IN SHARE MODE"); e != nil {
				t.Fatal(e)
			}
			var before, after int64
			if e = a.Pool.QueryRow(ctx, "SELECT position FROM journal_clock WHERE run_id=$1", run).Scan(&before); e != nil {
				t.Fatal(e)
			}
			if _, e = a.CloseAccountDay(ctx, run, "b", day); e == nil {
				t.Fatal("period insertion bypassed blocked table")
			}
			if e = blocker.Rollback(ctx); e != nil {
				t.Fatal(e)
			}
			var balance int64
			var state string
			var claims int
			e = a.Pool.QueryRow(ctx, `SELECT a.balance,j.state,c.position,
 (SELECT count(*) FROM command_results WHERE run_id=$1 AND id='system:close:6:b')
 FROM accounts a JOIN account_close_jobs j ON j.run_id=a.run_id AND j.account_id=a.id
 JOIN journal_clock c ON c.run_id=a.run_id WHERE a.run_id=$1 AND a.id='b' AND j.day=6`, run).Scan(&balance, &state, &after, &claims)
			if e != nil || balance != 3750 || state != "pending" || after != before || claims != 0 {
				t.Fatalf("partial close escaped rollback: balance=%d state=%s clock=%d/%d claims=%d %v", balance, state, after, before, claims, e)
			}
		}
		type outcome struct {
			account string
			result  Result
			err     error
		}
		results := make(chan outcome, 12)
		var wg sync.WaitGroup
		for _, account := range []string{"a", "b", "c"} {
			for retry := 0; retry < 4; retry++ {
				wg.Add(1)
				go func(id string, n int) {
					defer wg.Done()
					s := a
					if n%2 == 1 {
						s = b
					}
					r, e := s.CloseAccountDay(ctx, run, id, day)
					results <- outcome{id, r, e}
				}(account, retry)
			}
		}
		wg.Wait()
		close(results)
		seen := map[string]Result{}
		for got := range results {
			if got.err != nil {
				t.Fatalf("day %d %s: %v", day, got.account, got.err)
			}
			r := got.result
			if previous, ok := seen[got.account]; ok && !reflect.DeepEqual(previous, r) {
				t.Fatal("concurrent retries changed response")
			}
			seen[got.account] = r
			if day%6 != 0 {
				if r.Period != nil || len(r.Legs) != 0 || len(r.Accruals) != 1 {
					t.Fatalf("premature capitalization: %+v", r)
				}
			} else {
				want := int64(12)
				if day == 6 && got.account == "a" {
					want = 0
				}
				if r.Period == nil || r.Period.Amount != want || r.Period.StartDay != day-5 || r.Period.ThroughDay != day || len(r.Period.PriorSequences) != 5 || len(r.Accruals) != 6 {
					t.Fatalf("period: %+v", r)
				}
				if r.Command.BookedDay != day+1 || r.Command.ValueDay != day {
					t.Fatal("capitalization dates confused")
				}
				if want == 0 {
					if len(r.Legs) != 0 {
						t.Fatal("zero interest emitted postings")
					}
				} else {
					if len(r.Legs) != 2 || r.Legs[0].Units != want || r.Legs[1].Units != -want || r.Legs[1].Account != got.account || r.Legs[0].ValueDay != day {
						t.Fatalf("unbalanced/wrong posting: %+v", r.Legs)
					}
				}
				if day == 6 && got.account == "b" {
					firstPeriod = r
				}
			}
			if day == 7 && got.account == "b" && r.Accruals[0].Basis != 3762 {
				t.Fatal("next period omitted previous capitalization")
			}
		}
	}
	retried, err := b.CloseAccountDay(ctx, run, "b", 6)
	if err != nil || !reflect.DeepEqual(firstPeriod, retried) {
		t.Fatalf("late retry: %+v %v", retried, err)
	}
	for id, want := range map[string]int64{"a": 3762, "b": 3774, "c": 3774, "interest-AED": 36, "interest-BHD": 24} {
		var balance int64
		if err = a.Pool.QueryRow(ctx, "SELECT balance FROM accounts WHERE run_id=$1 AND id=$2", run, id).Scan(&balance); err != nil || balance != want {
			t.Fatalf("%s balance=%d expected=%d err=%v", id, balance, want, err)
		}
	}
	var periods, closes int
	if err = a.Pool.QueryRow(ctx, "SELECT (SELECT count(*) FROM account_periods WHERE run_id=$1),(SELECT count(*) FROM account_close_jobs WHERE run_id=$1 AND state='done')", run).Scan(&periods, &closes); err != nil || periods != 6 || closes != 36 {
		t.Fatalf("periods=%d closes=%d %v", periods, closes, err)
	}
	for _, sql := range []string{"DELETE FROM account_periods WHERE run_id=$1", "UPDATE account_periods SET amount=amount+1 WHERE run_id=$1"} {
		if _, err = a.Pool.Exec(ctx, sql, run); err == nil {
			t.Fatal("runtime mutated period evidence")
		}
		if _, err = owner.Pool.Exec(ctx, sql, run); err == nil {
			t.Fatal("period immutable trigger bypassed")
		}
	}
	// Period linkage is a committed journal identity, not a separate credit.
	var mismatches int
	err = a.Pool.QueryRow(ctx, `SELECT count(*) FROM account_periods p JOIN journal_batches j USING(run_id,sequence)
 WHERE p.run_id=$1 AND (j.envelope->'period'->>'amount')::bigint<>p.amount`, run).Scan(&mismatches)
	if err != nil || mismatches != 0 {
		t.Fatal(fmt.Sprintf("period/journal mismatch: %d %v", mismatches, err))
	}
}
