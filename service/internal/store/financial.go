package store

import (
	"context"
	"encoding/json"
)

// Financial reports complete run/UTC-period flows and current customer stocks.
// It never aggregates the paginated journal preview or combines currencies.
func (s *Store) Financial(ctx context.Context, runID string) (json.RawMessage, error) {
	value, err := s.Queries.FinancialSummary(ctx, runID)
	return json.RawMessage(value), err
}
