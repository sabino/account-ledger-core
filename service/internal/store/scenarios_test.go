//go:build integration

package store

import (
	"context"
	"os"
	"reflect"
	"testing"

	"github.com/sabino/account-ledger-core/service/internal/db"
)

func TestScenarioRecipeAndDecisionEvidence(t *testing.T) {
	a, b, run := testLedger(t)
	ctx := context.Background()
	owner, err := Open(ctx, os.Getenv("TEST_DATABASE_URL"), "scenario-setup")
	if err != nil {
		t.Fatal(err)
	}
	defer owner.Pool.Close()
	if err = owner.Queries.CreateAccount(ctx, db.CreateAccountParams{RunID: run, ID: "tax-AED", Name: "Synthetic tax", Currency: "AED", Class: "liability"}); err != nil {
		t.Fatal(err)
	}
	want := []string{"accepted", "declined", "rejected", "accepted", "accepted", "rejected", "rejected", "rejected", "accepted", "accepted", "accepted", "accepted"}
	var first Result
	for step, status := range want {
		input := GeneratedCommand(int64(step))
		input.Account, input.Destination = "a", "b"
		if step == 7 {
			input.Destination = "c"
		}
		writer := a
		if step%2 == 1 {
			writer = b
		}
		result, err := writer.Process(ctx, run, input)
		if err != nil || result.Status != status {
			t.Fatalf("step %d: %+v %v", step, result, err)
		}
		if status != "accepted" && len(result.Legs) != 0 {
			t.Fatalf("step %d moved money", step)
		}
		switch step {
		case 0:
			first = result
		case 1:
			if result.Decision == nil || result.Decision.Available >= result.Decision.Requested {
				t.Fatal("decline evidence missing", result)
			}
		case 4:
			if result.Captured != 2 || result.Released != 1 {
				t.Fatal(result)
			}
		case 8:
			if len(result.Legs) != 6 || result.Legs[0].Units != 334 || result.Legs[2].Units != 333 || result.Legs[4].Units != 333 {
				t.Fatal(result)
			}
		case 9:
			if result.Calculation == nil || result.Calculation.Tax != 0 || result.Calculation.Gross != 10 {
				t.Fatal(result)
			}
		case 10:
			if result.Calculation == nil || result.Calculation.Tax != 2 || result.Calculation.Gross != 32 {
				t.Fatal(result)
			}
		case 11:
			if !reflect.DeepEqual(first, result) {
				t.Fatal("retry changed original outcome")
			}
		}
	}
	assertReconciled(t, a, run)
}

func TestBHDTransferSplit(t *testing.T) {
	a, _, run := testLedger(t)
	ctx := context.Background()
	owner, err := Open(ctx, os.Getenv("TEST_DATABASE_URL"), "split-setup")
	if err != nil {
		t.Fatal(err)
	}
	defer owner.Pool.Close()
	for _, account := range []db.CreateAccountParams{
		{RunID: run, ID: "d", Name: "D", Currency: "BHD", Class: "liability", Customer: true},
		{RunID: run, ID: "settlement-BHD", Name: "Settlement", Currency: "BHD", Class: "asset"},
	} {
		if err = owner.Queries.CreateAccount(ctx, account); err != nil {
			t.Fatal(err)
		}
	}
	input := Command{ID: "fund-c", Kind: "credit", Account: "c", Currency: "BHD", Amount: "10.000", BookedDay: 1, ValueDay: 1}
	if result, err := a.Process(ctx, run, input); err != nil || result.Status != "accepted" {
		t.Fatal(result, err)
	}
	input.ID, input.Kind, input.Destination, input.Installments = "split", "split_transfer", "d", 3
	result, err := a.Process(ctx, run, input)
	if err != nil || result.Status != "accepted" || len(result.Legs) != 6 {
		t.Fatal(result, err)
	}
	for i, want := range []int64{3334, 3333, 3333} {
		if result.Legs[i*2].Units != want || result.Legs[i*2+1].Units != -want {
			t.Fatal(result)
		}
	}
	assertReconciled(t, a, run)
}
