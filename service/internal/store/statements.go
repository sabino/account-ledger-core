package store

import (
	"context"
	"errors"
	"math/big"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/sabino/account-ledger-core/service/internal/db"
)

var ErrStatementInput = errors.New("invalid statement account, cutoff or cursor")
var ErrStatementAccount = errors.New("statement account not found")

type StatementRequest struct {
	Account string
	// -1 captures the current committed position; 0 is a genuinely empty prefix.
	Cutoff        int64
	AfterSequence int64
	AfterLeg      int32
	Limit         int32
}

func (r StatementRequest) Validate() error {
	if r.Account == "" || len(r.Account) > 128 || r.Cutoff < -1 || r.AfterSequence < 0 || r.AfterLeg < -1 ||
		r.Limit < 1 || r.Limit > 100 || (r.AfterSequence == 0 && r.AfterLeg != -1) ||
		(r.AfterSequence > 0 && (r.Cutoff < r.AfterSequence || r.AfterLeg < 0)) {
		return ErrStatementInput
	}
	return nil
}

type StatementCursor struct {
	Sequence int64 `json:"sequence,string"`
	Leg      int32 `json:"leg"`
}
type StatementLine struct {
	StatementCursor
	RecordedAt time.Time `json:"recorded_at"`
	BookedDay  int32     `json:"booked_day"`
	ValueDay   int32     `json:"value_day"`
	Kind       string    `json:"kind"`
	CommandID  string    `json:"command_id"`
	Instance   string    `json:"instance"`
	Debit      string    `json:"debit_minor"`
	Credit     string    `json:"credit_minor"`
	Change     string    `json:"change_minor"`
	Balance    string    `json:"balance_minor"`
}
type Statement struct {
	AccountID    string           `json:"account_id"`
	Name         string           `json:"name"`
	Currency     string           `json:"currency"`
	Class        string           `json:"class"`
	Cutoff       int64            `json:"cutoff,string"`
	PostingCount int64            `json:"posting_count,string"`
	Debit        string           `json:"total_debit_minor"`
	Credit       string           `json:"total_credit_minor"`
	Closing      string           `json:"closing_balance_minor"`
	PageOpening  string           `json:"page_opening_balance_minor"`
	PageClosing  string           `json:"page_closing_balance_minor"`
	Lines        []StatementLine  `json:"lines"`
	Next         *StatementCursor `json:"next"`
	Scope        string           `json:"scope"`
}

func normalBalance(units string, class string) (*big.Int, error) {
	value, ok := new(big.Int).SetString(units, 10)
	if !ok {
		return nil, errors.New("invalid stored statement total")
	}
	if class == "liability" || class == "income" || class == "equity" {
		value.Neg(value)
	}
	return value, nil
}

func (s *Store) Statement(ctx context.Context, runID string, request StatementRequest) (Statement, error) {
	var result Statement
	if err := request.Validate(); err != nil {
		return result, err
	}
	tx, err := s.Pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly})
	if err != nil {
		return result, err
	}
	defer tx.Rollback(ctx)
	q := s.Queries.WithTx(tx)
	account, err := q.StatementAccount(ctx, db.StatementAccountParams{RunID: runID, ID: request.Account})
	if errors.Is(err, pgx.ErrNoRows) {
		return result, ErrStatementAccount
	}
	if err != nil {
		return result, err
	}
	current, err := q.CurrentSequence(ctx, runID)
	if err != nil {
		return result, err
	}
	if request.Cutoff == -1 {
		request.Cutoff = current
	}
	if request.Cutoff > current {
		return result, ErrStatementInput
	}
	totals, err := q.StatementTotals(ctx, db.StatementTotalsParams{RunID: runID, AccountID: request.Account, Cutoff: request.Cutoff, AfterSequence: request.AfterSequence, AfterLeg: request.AfterLeg})
	if err != nil {
		return result, err
	}
	rows, err := q.StatementLines(ctx, db.StatementLinesParams{RunID: runID, AccountID: request.Account, Cutoff: request.Cutoff, AfterSequence: request.AfterSequence, AfterLeg: request.AfterLeg, PageLimit: request.Limit + 1})
	if err != nil {
		return result, err
	}
	opening, err := normalBalance(totals.OpeningUnits, account.Class)
	if err != nil {
		return result, err
	}
	closing, err := normalBalance(totals.ClosingUnits, account.Class)
	if err != nil {
		return result, err
	}
	result = Statement{AccountID: account.ID, Name: account.Name, Currency: account.Currency, Class: account.Class,
		Cutoff: request.Cutoff, PostingCount: totals.PostingCount, Debit: totals.DebitUnits, Credit: totals.CreditUnits,
		Closing: closing.String(), PageOpening: opening.String(), Lines: make([]StatementLine, 0, request.Limit),
		Scope: "Posted monetary entries in journal order at a fixed knowledge cutoff; holds and rejected attempts are in the journal, not this statement. Balances use the account's normal side; no currency conversion."}
	more := len(rows) > int(request.Limit)
	if more {
		rows = rows[:request.Limit]
	}
	for _, row := range rows {
		units := big.NewInt(row.Units)
		debit, credit := "0", "0"
		if units.Sign() > 0 {
			debit = units.String()
		} else {
			credit = new(big.Int).Neg(units).String()
		}
		change, err := normalBalance(units.String(), account.Class)
		if err != nil {
			return Statement{}, err
		}
		opening.Add(opening, change)
		result.Lines = append(result.Lines, StatementLine{StatementCursor: StatementCursor{Sequence: row.Sequence, Leg: row.Leg}, RecordedAt: row.CreatedAt.Time,
			BookedDay: row.BookedDay, ValueDay: row.ValueDay, Kind: row.Kind, CommandID: row.CommandID, Instance: row.Instance,
			Debit: debit, Credit: credit, Change: change.String(), Balance: opening.String()})
	}
	result.PageClosing = opening.String()
	if more {
		cursor := result.Lines[len(result.Lines)-1].StatementCursor
		result.Next = &cursor
	}
	return result, tx.Commit(ctx)
}
