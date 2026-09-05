package store

import (
	"context"
	"errors"
	"strconv"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/sabino/account-ledger-core/service/internal/db"
	"github.com/sabino/account-ledger-core/service/internal/domain"
	"github.com/sabino/account-ledger-core/service/internal/statement"
)

var ErrExternalScenario = statement.ErrScenario

type ExternalComparison struct {
	Cutoff          int64                       `json:"cutoff,string"`
	StatementID     string                      `json:"statement_id"`
	StatementSHA256 string                      `json:"statement_sha256"`
	LedgerLines     int                         `json:"ledger_lines"`
	StatementLines  int                         `json:"statement_lines"`
	Scope           string                      `json:"scope"`
	Comparison      domain.SettlementComparison `json:"comparison"`
}

// CompareOpeningStatement is a read-only fixed-cutoff comparison of the opening
// deposit namespace. It does not assert agreement for subsequent settlements.
func (s *Store) CompareOpeningStatement(ctx context.Context, runID, scenario string) (ExternalComparison, error) {
	doc, err := statement.Opening(scenario)
	if err != nil {
		return ExternalComparison{}, err
	}
	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	tx, err := s.Pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly})
	if err != nil {
		return ExternalComparison{}, err
	}
	defer tx.Rollback(ctx)
	q := s.Queries.WithTx(tx)
	cutoff, err := q.CurrentSequence(ctx, runID)
	if err != nil {
		return ExternalComparison{}, err
	}
	rows, err := q.OpeningSettlementLines(ctx, db.OpeningSettlementLinesParams{RunID: runID, Cutoff: cutoff})
	if err != nil {
		return ExternalComparison{}, err
	}
	if len(rows) > 10000 {
		return ExternalComparison{}, errors.New("opening settlement window exceeds limit")
	}
	lines := make([]domain.SettlementLine, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.ParseInt(row.Amount, 10, 64)
		if err != nil {
			return ExternalComparison{}, err
		}
		lines = append(lines, domain.SettlementLine{Reference: row.Reference, Currency: row.Currency, ValueDay: row.ValueDay, Amount: amount})
	}
	comparison, err := domain.CompareSettlement(lines, doc.Lines)
	if err != nil {
		return ExternalComparison{}, err
	}
	result := ExternalComparison{Cutoff: cutoff, StatementID: doc.ID, StatementSHA256: doc.SHA256, LedgerLines: len(lines), StatementLines: len(doc.Lines), Comparison: comparison,
		Scope: "synthetic opening deposits only: seed-* references on settlement assets; excludes subsequent settlements, fees, tax and interest; read-only, no repair or persisted reconciliation run"}
	return result, tx.Commit(ctx)
}
