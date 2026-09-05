//go:build integration

package store

import (
	"context"
	"errors"
	"testing"

	"github.com/jackc/pgx/v5/pgconn"
	"github.com/sabino/account-ledger-core/service/internal/db"
)

func TestRuntimeCannotRenewHostLease(t *testing.T) {
	a, _, _ := testLedger(t)
	ctx := context.Background()
	tx, err := a.Pool.Begin(ctx)
	if err != nil {
		t.Fatal(err)
	}
	defer tx.Rollback(ctx)
	err = a.Queries.WithTx(tx).PublishHostGuard(ctx, db.PublishHostGuardParams{Reason: "", Evidence: []byte(`{}`)})
	var denied *pgconn.PgError
	if !errors.As(err, &denied) || denied.Code != "42501" {
		t.Fatalf("expected permission denial, got %v", err)
	}
}

func TestRuntimeCanReadCDCSourceState(t *testing.T) {
	a, _, _ := testLedger(t)
	row, err := a.Queries.CDCSourceStatus(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if !row.Present && (row.Active || row.Invalidated || row.RetainedWalBytes != "") {
		t.Fatalf("absent slot had invented evidence: %+v", row)
	}
}
