//go:build integration

package store

import (
	"context"
	"testing"
)

func TestOpeningStatementAdapterDoesNotInventMissingFunding(t *testing.T) {
	s, _, run := testLedger(t)
	ctx := context.Background()
	before, err := s.Queries.CurrentSequence(ctx, run)
	if err != nil {
		t.Fatal(err)
	}
	report, err := s.CompareOpeningStatement(ctx, run, "clean")
	if err != nil || report.LedgerLines != 0 || len(report.Comparison.Differences) != 40 {
		t.Fatalf("missing funding hidden: %+v %v", report, err)
	}
	result, err := s.Process(ctx, run, Command{ID: "seed-001", Kind: "credit", Account: "a", Currency: "AED", Amount: "1000", BookedDay: 1, ValueDay: 1})
	if err != nil || result.Status != "accepted" {
		t.Fatalf("setup: %+v %v", result, err)
	}
	report, err = s.CompareOpeningStatement(ctx, run, "clean")
	if err != nil || report.Cutoff != result.Sequence || report.LedgerLines != 1 || report.Comparison.Matched != 1 || len(report.Comparison.Differences) != 39 {
		t.Fatalf("partial coverage: %+v %v", report, err)
	}
	after, err := s.Queries.CurrentSequence(ctx, run)
	if err != nil || after != before+1 {
		t.Fatal("read-only comparison appended records")
	}
}
