//go:build integration

package store

import (
	"context"
	"errors"
	"reflect"
	"testing"

	"github.com/jackc/pgx/v5"
	"github.com/sabino/account-ledger-core/service/internal/db"
)

func TestGeneratedClaimFencesStaleWorkerAndCommitsCursor(t *testing.T) {
	a, b, run := testLedger(t)
	ctx := context.Background()
	_, err := a.Pool.Exec(ctx, "UPDATE controls SET eps=1, next_at=now(), guard_until=now()+interval '1 hour' WHERE run_id=$1", run)
	if err != nil {
		t.Fatal(err)
	}
	first, err := a.Queries.ClaimGeneratedCommand(ctx, run)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = b.Queries.ClaimGeneratedCommand(ctx, run); !errors.Is(err, pgx.ErrNoRows) {
		t.Fatalf("another worker claimed an unexpired ordinal: %v", err)
	}
	// Simulate death before processing without a wall-clock sleep.
	if _, err = a.Pool.Exec(ctx, "UPDATE controls SET generator_until=now()-interval '1 second' WHERE run_id=$1", run); err != nil {
		t.Fatal(err)
	}
	replacement, err := b.Queries.ClaimGeneratedCommand(ctx, run)
	if err != nil {
		t.Fatal(err)
	}
	if replacement.Ordinal != first.Ordinal || replacement.GeneratorToken <= first.GeneratorToken {
		t.Fatalf("bad takeover: %+v -> %+v", first, replacement)
	}
	input := command("generated-takeover", "transfer")
	if _, err = a.process(ctx, run, input, &first); !errors.Is(err, pgx.ErrNoRows) {
		t.Fatalf("stale claim processed: %v", err)
	}
	if _, err = a.Queries.LockCommand(ctx, db.LockCommandParams{RunID: run, ID: input.ID}); !errors.Is(err, pgx.ErrNoRows) {
		t.Fatalf("stale worker recorded a command: %v", err)
	}
	result, err := b.process(ctx, run, input, &replacement)
	if err != nil {
		t.Fatal(err)
	}
	if result.Status != "accepted" {
		t.Fatalf("unexpected outcome: %+v", result)
	}
	var ordinal int64
	if err = a.Pool.QueryRow(ctx, "SELECT ordinal FROM controls WHERE run_id=$1", run).Scan(&ordinal); err != nil {
		t.Fatal(err)
	}
	if ordinal != first.Ordinal+1 {
		t.Fatalf("cursor not committed with result: %d", ordinal)
	}
	if _, err = a.process(ctx, run, input, &replacement); !errors.Is(err, pgx.ErrNoRows) {
		t.Fatalf("acknowledged claim reused: %v", err)
	}
	// The recipe deliberately retries a previous payload. It advances the cursor
	// without adding another journal batch, even through the other replica.
	if _, err = a.Pool.Exec(ctx, "UPDATE controls SET next_at=now() WHERE run_id=$1", run); err != nil {
		t.Fatal(err)
	}
	retry, err := a.Queries.ClaimGeneratedCommand(ctx, run)
	if err != nil {
		t.Fatal(err)
	}
	conflict := input
	conflict.Amount = "1"
	if _, err = a.process(ctx, run, conflict, &retry); !errors.Is(err, ErrConflict) {
		t.Fatalf("changed recipe payload accepted: %v", err)
	}
	if err = a.Pool.QueryRow(ctx, "SELECT ordinal FROM controls WHERE run_id=$1", run).Scan(&ordinal); err != nil {
		t.Fatal(err)
	}
	if ordinal != first.Ordinal+1 {
		t.Fatal("failed transaction advanced the cursor")
	}
	replay, err := a.process(ctx, run, input, &retry)
	if err != nil {
		t.Fatal(err)
	}
	if replay.Sequence != result.Sequence {
		t.Fatal("recipe retry created a second batch")
	}
	if err = a.Pool.QueryRow(ctx, "SELECT ordinal FROM controls WHERE run_id=$1", run).Scan(&ordinal); err != nil {
		t.Fatal(err)
	}
	if ordinal != first.Ordinal+2 {
		t.Fatalf("replayed result lost cursor progress: %d", ordinal)
	}
}

func TestGeneratedDatesAdvanceButOriginalRetriesDoNot(t *testing.T) {
	a, b, run := testLedger(t)
	ctx := context.Background()
	claim := func() db.ClaimGeneratedCommandRow {
		t.Helper()
		if _, err := a.Pool.Exec(ctx, "UPDATE controls SET eps=1,next_at=now(),guard_until=now()+interval '1 hour' WHERE run_id=$1", run); err != nil {
			t.Fatal(err)
		}
		c, err := a.Queries.ClaimGeneratedCommand(ctx, run)
		if err != nil {
			t.Fatal(err)
		}
		return c
	}
	input := command("cross-day-retry", "transfer")
	input.Amount = "0.01"
	firstClaim := claim()
	first, err := a.process(ctx, run, input, &firstClaim)
	if err != nil || first.Status != "accepted" {
		t.Fatalf("first: %+v %v", first, err)
	}
	if err = a.AdvanceDay(ctx, run, 1); err != nil {
		t.Fatal(err)
	}
	// An already-committed retry needs no new money and can be replayed while
	// closes are pending. Its cursor acknowledgement remains atomic.
	retryClaim := claim()
	retry, err := b.process(ctx, run, input, &retryClaim)
	if err != nil || !reflect.DeepEqual(first, retry) {
		t.Fatalf("retry: %+v %v", retry, err)
	}
	nextClaim := claim()
	input.ID = "new-day-command"
	if _, err = b.process(ctx, run, input, &nextClaim); !errors.Is(err, ErrClosePending) {
		t.Fatalf("unfinished close bypassed: %v", err)
	}
	for _, id := range []string{"a", "b", "c"} {
		if _, err = a.CloseAccountDay(ctx, run, id, 1); err != nil {
			t.Fatal(err)
		}
	}
	result, err := b.process(ctx, run, input, &nextClaim)
	if err != nil || result.Status != "accepted" || result.Command.BookedDay != 2 || result.Command.ValueDay != 2 {
		t.Fatalf("new day: %+v %v", result, err)
	}
	// Public commands retain their explicit date validation; this is not a
	// blanket rewrite of caller input into whatever date happens to work.
	input.ID = "public-old-date"
	public, err := a.Process(ctx, run, input)
	if err != nil || public.Status != "rejected" {
		t.Fatalf("public date: %+v %v", public, err)
	}
}

func TestExpiredGeneratedClaimCannotStartFinancialWork(t *testing.T) {
	a, _, run := testLedger(t)
	ctx := context.Background()
	_, err := a.Pool.Exec(ctx, "UPDATE controls SET eps=1, next_at=now(), guard_until=now()+interval '1 hour' WHERE run_id=$1", run)
	if err != nil {
		t.Fatal(err)
	}
	claim, err := a.Queries.ClaimGeneratedCommand(ctx, run)
	if err != nil {
		t.Fatal(err)
	}
	_, err = a.Pool.Exec(ctx, "UPDATE controls SET generator_until=now()-interval '1 second' WHERE run_id=$1", run)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = a.process(ctx, run, command("expired", "transfer"), &claim); !errors.Is(err, pgx.ErrNoRows) {
		t.Fatalf("expired worker processed: %v", err)
	}
}
