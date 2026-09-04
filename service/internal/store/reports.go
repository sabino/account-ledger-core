package store

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/sabino/account-ledger-core/service/internal/db"
)

func (s *Store) Accounts(ctx context.Context, runID string) ([]Account, error) {
	rows, err := s.Queries.ListAccounts(ctx, runID)
	if err != nil {
		return nil, err
	}
	accounts := make([]Account, 0, len(rows))
	for _, row := range rows {
		accounts = append(accounts, Account{ID: row.ID, Name: row.Name, Currency: row.Currency, Class: row.Class, Customer: row.Customer, Balance: row.Balance, Held: row.Held, Version: row.Version})
	}
	return accounts, nil
}

func (s *Store) Journal(ctx context.Context, runID, accountID string, cutoff int64) ([]map[string]any, error) {
	rows, err := s.Queries.ListJournal(ctx, db.ListJournalParams{RunID: runID, AccountID: accountID, Cutoff: cutoff})
	if err != nil {
		return nil, err
	}
	items := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		var result Result
		if err = json.Unmarshal(row.Envelope, &result); err != nil {
			return nil, err
		}
		items = append(items, map[string]any{"sequence": fmt.Sprint(row.Sequence), "at": row.CreatedAt.Time, "booked_day": row.BookedDay, "value_day": row.ValueDay, "result": result})
	}
	return items, nil
}

func (s *Store) Reconcile(ctx context.Context, runID string) (map[string]any, error) {
	tx, err := s.Pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly})
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)
	queries := s.Queries.WithTx(tx)
	cutoff, err := queries.CurrentSequence(ctx, runID)
	if err != nil {
		return nil, err
	}
	balances, err := queries.CountBalanceDifferences(ctx, runID)
	if err != nil {
		return nil, err
	}
	batches, err := queries.CountUnbalancedBatches(ctx, runID)
	if err != nil {
		return nil, err
	}
	holds, err := queries.CountHoldDifferences(ctx, runID)
	if err != nil {
		return nil, err
	}
	return map[string]any{"cutoff": fmt.Sprint(cutoff), "balance_discrepancies": balances, "unbalanced_batches": batches, "hold_discrepancies": holds, "ok": balances+batches+holds == 0, "scope": "journal, account projection and holds; external/lake reconciliation not implemented"}, tx.Commit(ctx)
}
