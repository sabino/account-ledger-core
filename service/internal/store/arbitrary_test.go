//go:build integration

package store

import (
	"context"
	"fmt"
	"math/rand/v2"
	"testing"
)

// A fixed seed makes unexpected outcomes reproducible. This independent model
// deliberately knows only conservation and insufficient-funds behavior.
func TestSeededArbitraryTransfers(t *testing.T) {
	a, b, run := testLedger(t)
	ctx := context.Background()
	random := rand.New(rand.NewPCG(20260904, 42))
	balances := map[string]int64{"a": 10000, "b": 10000}
	for i := 0; i < 500; i++ {
		from, to := "a", "b"
		if random.IntN(2) == 1 {
			from, to = to, from
		}
		units := int64(random.IntN(25000) + 1)
		input := Command{ID: fmt.Sprintf("arbitrary-%d", i), Kind: "transfer", Account: from, Destination: to,
			Currency: "AED", Amount: fmt.Sprintf("%d.%02d", units/100, units%100), BookedDay: 1, ValueDay: 1}
		writer, retryWriter := a, b
		if i%2 == 1 {
			writer, retryWriter = b, a
		}
		result, err := writer.Process(ctx, run, input)
		if err != nil {
			t.Fatalf("step %d: %v", i, err)
		}
		want := "declined"
		if balances[from] >= units {
			want = "accepted"
			balances[from] -= units
			balances[to] += units
		}
		if result.Status != want {
			t.Fatalf("step %d: status %s, want %s", i, result.Status, want)
		}
		if i%7 == 0 {
			retry, err := retryWriter.Process(ctx, run, input)
			if err != nil || retry.Sequence != result.Sequence || retry.Status != result.Status {
				t.Fatalf("step %d: retry %+v, error %v", i, retry, err)
			}
		}
		accounts, err := writer.Accounts(ctx, run)
		if err != nil {
			t.Fatal(err)
		}
		for _, account := range accounts {
			if wantBalance, ok := balances[account.ID]; ok && account.Balance != wantBalance {
				t.Fatalf("step %d, %s: got %d, want %d", i, account.ID, account.Balance, wantBalance)
			}
		}
	}
	assertReconciled(t, a, run)
}
