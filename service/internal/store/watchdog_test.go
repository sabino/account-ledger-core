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
