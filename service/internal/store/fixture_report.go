package store

import (
	"context"
	"fmt"

	"github.com/sabino/account-ledger-core/service/internal/db"
)

func (s *Store) FixtureReport(ctx context.Context, known int64) (map[string]any, error) {
	latest, err := s.Queries.CurrentSequence(ctx, FixtureRun)
	if err != nil {
		return nil, err
	}
	if known < 0 || known > latest {
		known = latest
	}
	daily := []map[string]any{}
	for day := int32(1); day <= 6; day++ {
		row := map[string]any{"day": day}
		for _, account := range []struct{ id, currency string }{{"ACC-001", "AED"}, {"ACC-002", "BHD"}} {
			var balance int64
			if known > 0 {
				balance, err = s.Queries.HistoricalBalance(ctx, db.HistoricalBalanceParams{RunID: FixtureRun, AccountID: account.id, ValueDay: day, KnownThrough: known})
				if err != nil {
					return nil, err
				}
			}
			row[account.currency] = fmt.Sprint(balance)
		}
		daily = append(daily, row)
	}
	batches := []map[string]any{}
	if known > 0 {
		batches, err = s.Journal(ctx, FixtureRun, "", known)
		if err != nil {
			return nil, err
		}
	}
	return map[string]any{"known_through": fmt.Sprint(known), "latest": fmt.Sprint(latest), "daily": daily, "batches": batches,
		"note": "The final batch includes capitalization. Cutoffs select journal prefixes, not wall-clock snapshots: maintenance and its triggering event commit together."}, nil
}
