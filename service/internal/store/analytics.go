package store

import (
	"context"
	"encoding/json"
	"github.com/sabino/account-ledger-core/service/internal/db"
)

// Analytics reports recorded decisions, not HTTP requests or retry attempts.
func (s *Store) Analytics(ctx context.Context, runID, currency string, seconds int32) (json.RawMessage, error) {
	value, err := s.Queries.EventAnalytics(ctx, db.EventAnalyticsParams{RunID: runID, Currency: currency, Seconds: seconds})
	return json.RawMessage(value), err
}
