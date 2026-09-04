//go:build integration

package store

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"sync"
	"testing"
	"time"

	"github.com/sabino/account-ledger-core/service/internal/db"
)

func testLedger(t *testing.T) (*Store, *Store, string) {
	t.Helper()
	url := os.Getenv("TEST_DATABASE_URL")
	if url == "" {
		t.Fatal("TEST_DATABASE_URL must name a disposable integration database")
	}
	ctx := context.Background()
	owner, err := Open(ctx, url, "test-owner")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(owner.Pool.Close)
	if err = owner.Migrate(ctx); err != nil {
		t.Fatal(err)
	}
	run := fmt.Sprintf("test-%d", time.Now().UnixNano())
	if err = owner.Queries.CreateRun(ctx, db.CreateRunParams{ID: run, Profile: "live"}); err != nil {
		t.Fatal(err)
	}
	if err = owner.Queries.CreateClock(ctx, run); err != nil {
		t.Fatal(err)
	}
	if err = owner.Queries.CreateControls(ctx, run); err != nil {
		t.Fatal(err)
	}
	for _, account := range []db.CreateAccountParams{
		{RunID: run, ID: "a", Name: "A", Currency: "AED", Class: "liability", Customer: true},
		{RunID: run, ID: "b", Name: "B", Currency: "AED", Class: "liability", Customer: true},
		{RunID: run, ID: "c", Name: "C", Currency: "BHD", Class: "liability", Customer: true},
		{RunID: run, ID: "settlement-AED", Name: "Settlement", Currency: "AED", Class: "asset"},
	} {
		if err = owner.Queries.CreateAccount(ctx, account); err != nil {
			t.Fatal(err)
		}
	}
	for _, id := range []string{"a", "b"} {
		_, err = owner.Process(ctx, run, Command{ID: "fund-" + id, Kind: "credit", Account: id, Currency: "AED", Amount: "100", BookedDay: 1, ValueDay: 1})
		if err != nil {
			t.Fatal(err)
		}
	}
	appURL := os.Getenv("TEST_APP_DATABASE_URL")
	if appURL == "" {
		t.Fatal("TEST_APP_DATABASE_URL required to verify runtime privileges")
	}
	a, err := Open(ctx, appURL, "replica-a")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(a.Pool.Close)
	b, err := Open(ctx, appURL, "replica-b")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(b.Pool.Close)
	return a, b, run
}

func command(id, kind string) Command {
	return Command{ID: id, Kind: kind, Account: "a", Destination: "b", Currency: "AED", Amount: "80", BookedDay: 1, ValueDay: 1}
}

func TestConcurrentIdempotency(t *testing.T) {
	a, b, run := testLedger(t)
	ctx := context.Background()
	input := command("same-key", "transfer")
	results := make(chan Result, 20)
	failures := make(chan error, 20)
	var wg sync.WaitGroup
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			s := a
			if i%2 == 1 {
				s = b
			}
			result, err := s.Process(ctx, run, input)
			if err != nil {
				failures <- err
			} else {
				results <- result
			}
		}(i)
	}
	wg.Wait()
	close(results)
	close(failures)
	for err := range failures {
		t.Error(err)
	}
	var first []byte
	for result := range results {
		raw, _ := json.Marshal(result)
		if first == nil {
			first = raw
		}
		if string(raw) != string(first) {
			t.Fatalf("different retry response: %s / %s", raw, first)
		}
	}
	input.Amount = "79"
	if _, err := b.Process(ctx, run, input); !errors.Is(err, ErrConflict) {
		t.Fatalf("expected conflict, got %v", err)
	}
	accounts, err := a.Accounts(ctx, run)
	if err != nil {
		t.Fatal(err)
	}
	for _, account := range accounts {
		if account.ID == "a" && account.Balance != 2000 {
			t.Fatal(account)
		}
	}
	assertReconciled(t, a, run)
}

func TestCompetingTransfersAndHolds(t *testing.T) {
	for _, kind := range []string{"transfer", "hold"} {
		t.Run(kind, func(t *testing.T) {
			a, b, run := testLedger(t)
			results := make(chan Result, 2)
			failures := make(chan error, 2)
			var wg sync.WaitGroup
			for i, s := range []*Store{a, b} {
				wg.Add(1)
				go func(i int, s *Store) {
					defer wg.Done()
					input := command(fmt.Sprint(i), kind)
					input.Authorization = fmt.Sprintf("hold-%d", i)
					result, err := s.Process(context.Background(), run, input)
					if err != nil {
						failures <- err
					} else {
						results <- result
					}
				}(i, s)
			}
			wg.Wait()
			close(results)
			close(failures)
			for err := range failures {
				t.Error(err)
			}
			accepted, declined := 0, 0
			for result := range results {
				if result.Status == "accepted" {
					accepted++
				}
				if result.Status == "declined" {
					declined++
				}
			}
			if accepted != 1 || declined != 1 {
				t.Fatalf("accepted=%d declined=%d", accepted, declined)
			}
			assertReconciled(t, a, run)
		})
	}
}

func TestPartialCaptureAndInvalidCommands(t *testing.T) {
	a, b, run := testLedger(t)
	ctx := context.Background()
	input := command("hold", "hold")
	input.Authorization = "auth"
	input.Amount = "80"
	if result, err := a.Process(ctx, run, input); err != nil || result.Status != "accepted" {
		t.Fatalf("%+v %v", result, err)
	}
	input.ID = "capture"
	input.Kind = "capture"
	input.Amount = "75"
	result, err := b.Process(ctx, run, input)
	if err != nil {
		t.Fatal(err)
	}
	if result.Captured != 7500 || result.Released != 500 {
		t.Fatal(result)
	}
	input.ID = "capture-again"
	result, err = a.Process(ctx, run, input)
	if err != nil || result.Status != "rejected" {
		t.Fatalf("%+v %v", result, err)
	}
	for i, input := range []Command{
		{Kind: "transfer", Account: "a", Destination: "a", Currency: "AED", Amount: "1", BookedDay: 1, ValueDay: 1},
		{Kind: "transfer", Account: "a", Destination: "c", Currency: "AED", Amount: "1", BookedDay: 1, ValueDay: 1},
		{Kind: "transfer", Account: "a", Destination: "b", Currency: "AED", Amount: "1.001", BookedDay: 1, ValueDay: 1},
		{Kind: "hold", Account: "a", Currency: "AED", Amount: "1", BookedDay: 1, ValueDay: 2},
	} {
		input.ID = fmt.Sprint("invalid-", i)
		result, err = a.Process(ctx, run, input)
		if err != nil || result.Status != "rejected" {
			t.Fatalf("%+v %v", result, err)
		}
	}
	assertReconciled(t, a, run)
}

func TestDatabaseRejectsUnbalancedBatch(t *testing.T) {
	a, _, run := testLedger(t)
	ctx := context.Background()
	tx, err := a.Pool.Begin(ctx)
	if err != nil {
		t.Fatal(err)
	}
	defer tx.Rollback(ctx)
	q := a.Queries.WithTx(tx)
	if err = q.ClaimCommand(ctx, db.ClaimCommandParams{RunID: run, ID: "malformed", Hash: "test"}); err != nil {
		t.Fatal(err)
	}
	seq, err := q.NextSequence(ctx, run)
	if err != nil {
		t.Fatal(err)
	}
	result := Result{ID: "malformed", Kind: "transfer", Status: "accepted", Legs: movement("a", "b", "AED", 100, 1, "transfer")}
	result.Legs[1].Units = -99
	raw, _ := json.Marshal(result)
	if err = q.AppendBatch(ctx, db.AppendBatchParams{RunID: run, Sequence: seq, CommandID: "malformed", Kind: "transfer", BookedDay: 1, ValueDay: 1, Instance: "test", Envelope: raw}); err != nil {
		t.Fatal(err)
	}
	for i, leg := range result.Legs {
		if err = q.AppendPosting(ctx, db.AppendPostingParams{RunID: run, Sequence: seq, Leg: int32(i), AccountID: leg.Account, Currency: leg.Currency, Units: leg.Units, ValueDay: 1, Kind: "transfer"}); err != nil {
			t.Fatal(err)
		}
	}
	if err = tx.Commit(ctx); err == nil {
		t.Fatal("unbalanced batch committed")
	}
	assertReconciled(t, a, run)
}

func TestOppositeDirectionTransfers(t *testing.T) {
	a, b, run := testLedger(t)
	ctx := context.Background()
	failures := make(chan error, 100)
	var wg sync.WaitGroup
	for worker, s := range []*Store{a, b} {
		wg.Add(1)
		go func(worker int, s *Store) {
			defer wg.Done()
			for i := 0; i < 50; i++ {
				input := command(fmt.Sprintf("race-%d-%d", worker, i), "transfer")
				input.Amount = "1"
				if worker == 1 {
					input.Account, input.Destination = "b", "a"
				}
				if _, err := s.Process(ctx, run, input); err != nil {
					failures <- err
				}
			}
		}(worker, s)
	}
	wg.Wait()
	close(failures)
	for err := range failures {
		t.Error(err)
	}
	assertReconciled(t, a, run)
}

func assertReconciled(t *testing.T, s *Store, run string) {
	t.Helper()
	result, err := s.Reconcile(context.Background(), run)
	if err != nil {
		t.Fatal(err)
	}
	if result["ok"] != true {
		t.Fatal(result)
	}
}

func TestSixDayFixture(t *testing.T) {
	ctx := context.Background()
	owner, err := Open(ctx, os.Getenv("TEST_DATABASE_URL"), "fixture")
	if err != nil {
		t.Fatal(err)
	}
	defer owner.Pool.Close()
	if err = owner.Migrate(ctx); err != nil {
		t.Fatal(err)
	}
	if err = owner.SeedFixture(ctx); err != nil {
		t.Fatal(err)
	}
	final, err := owner.Finalize(ctx, FixtureRun, 1, 6)
	if err != nil {
		t.Fatal(err)
	}
	if final.Sequence != 12 {
		t.Fatalf("expected final batch 12, got %d", final.Sequence)
	}
	expected := []int64{25000, 22500, 62500, 41500, 39000, 39000}
	for i, want := range expected {
		balance, err := owner.Queries.HistoricalBalance(ctx, db.HistoricalBalanceParams{
			RunID: FixtureRun, AccountID: "ACC-001", ValueDay: int32(i + 1), KnownThrough: 11,
		})
		if err != nil || balance != want {
			t.Fatalf("day %d: got %d want %d (%v)", i+1, balance, want, err)
		}
	}
	for _, check := range []struct{ sequence, want int64 }{{6, 46500}, {7, -20500}, {8, -20500}, {9, -23000}, {10, 39000}} {
		balance, err := owner.Queries.HistoricalBalance(ctx, db.HistoricalBalanceParams{RunID: FixtureRun, AccountID: "ACC-001", ValueDay: 5, KnownThrough: check.sequence})
		if err != nil || balance != check.want {
			t.Fatalf("knowledge %d: %d / %v", check.sequence, balance, err)
		}
	}
	var aed, bhd int64
	for _, accrual := range final.Accruals {
		if accrual.Currency == "AED" {
			aed += accrual.Amount
		} else {
			bhd += accrual.Amount
		}
	}
	if aed != 93 || bhd != 8 {
		t.Fatalf("interest: %d / %d", aed, bhd)
	}
	commands := FixtureCommands()
	e7, err := owner.Process(ctx, FixtureRun, commands[6])
	if err != nil {
		t.Fatal(err)
	}
	var feeDays []int32
	for _, leg := range e7.Legs {
		if leg.Account == "ACC-001" && leg.Kind == "overdraft_fee" {
			feeDays = append(feeDays, leg.ValueDay)
		}
	}
	if fmt.Sprint(feeDays) != "[2 4]" {
		t.Fatal(feeDays)
	}
	e9, err := owner.Process(ctx, FixtureRun, commands[8])
	if err != nil || e9.Sequence != 10 {
		t.Fatalf("E9: %+v %v", e9, err)
	}
	e10, err := owner.Process(ctx, FixtureRun, commands[9])
	if err != nil {
		t.Fatal(err)
	}
	var parts []int64
	for _, leg := range e10.Legs {
		if leg.Account == "ACC-002" {
			parts = append(parts, -leg.Units)
		}
	}
	if fmt.Sprint(parts) != "[3334 3333 3333]" {
		t.Fatal(parts)
	}
	e5, err := owner.Process(ctx, FixtureRun, commands[4])
	if err != nil || e5.Captured != 18500 || e5.Released != 1500 {
		t.Fatalf("E5 %+v %v", e5, err)
	}
	e8, err := owner.Process(ctx, FixtureRun, commands[7])
	if err != nil || e8.Status != "declined" {
		t.Fatalf("E8 %+v %v", e8, err)
	}
	e6, err := owner.Process(ctx, FixtureRun, commands[5])
	if err != nil || e6.Status != "rejected" {
		t.Fatalf("E6 %+v %v", e6, err)
	}
	assertReconciled(t, owner, FixtureRun)
}
