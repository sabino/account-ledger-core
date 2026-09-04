// Package store owns database transactions, not HTTP or presentation.
package store

import (
	"context"
	"embed"
	"encoding/json"
	"errors"
	"io/fs"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/jackc/pgx/v5/stdlib"
	"github.com/pressly/goose/v3"
	"github.com/pressly/goose/v3/lock"
	"github.com/sabino/account-ledger-core/service/internal/db"
)

//go:embed migrations/*.sql
var migrations embed.FS

type Store struct {
	Pool     *pgxpool.Pool
	Queries  *db.Queries
	Instance string
}

type Command struct {
	ID            string `json:"id"`
	Kind          string `json:"kind"`
	Account       string `json:"account"`
	Destination   string `json:"destination,omitempty"`
	Currency      string `json:"currency"`
	Amount        string `json:"amount"`
	Authorization string `json:"authorization,omitempty"`
	BookedDay     int32  `json:"booked_day"`
	ValueDay      int32  `json:"value_day"`
	Installments  int32  `json:"installments,omitempty"`
	TargetEvent   string `json:"target_event,omitempty"`
}

type Leg struct {
	Account  string `json:"account"`
	Currency string `json:"currency"`
	Units    int64  `json:"units,string"`
	ValueDay int32  `json:"value_day"`
	Kind     string `json:"kind"`
}

type Result struct {
	ID       string          `json:"id"`
	Status   string          `json:"status"`
	Reason   string          `json:"reason,omitempty"`
	Sequence int64           `json:"sequence,string"`
	Instance string          `json:"instance"`
	Kind     string          `json:"kind"`
	Legs     []Leg           `json:"legs"`
	Captured int64           `json:"captured,string"`
	Released int64           `json:"released,string"`
	Accruals []Accrual       `json:"accruals,omitempty"`
	Policy   json.RawMessage `json:"policy"`
	Command  *Command        `json:"command,omitempty"`
}

type Accrual struct {
	Account  string `json:"account"`
	Currency string `json:"currency"`
	ValueDay int32  `json:"value_day"`
	Basis    int64  `json:"basis,string"`
	Amount   int64  `json:"amount,string"`
}

func movement(debit, credit, currency string, amount int64, day int32, kind string) []Leg {
	return []Leg{
		{Account: debit, Currency: currency, Units: amount, ValueDay: day, Kind: kind},
		{Account: credit, Currency: currency, Units: -amount, ValueDay: day, Kind: kind},
	}
}

func (r *Result) reject(reason string) {
	r.Status = "rejected"
	r.Reason = reason
}

type Account struct {
	ID       string `json:"id"`
	Name     string `json:"name"`
	Currency string `json:"currency"`
	Class    string `json:"class"`
	Customer bool   `json:"customer"`
	Balance  int64  `json:"balance_minor,string"`
	Held     int64  `json:"held_minor,string"`
	Version  int64  `json:"version,string"`
}

var ErrConflict = errors.New("idempotency key already used with another payload")
var ErrCapacity = errors.New("simulation capacity or safety limit reached")

func Open(ctx context.Context, url, instance string) (*Store, error) {
	config, err := pgxpool.ParseConfig(url)
	if err != nil {
		return nil, err
	}
	config.MaxConns = 6
	config.ConnConfig.RuntimeParams["statement_timeout"] = "5000"
	config.ConnConfig.RuntimeParams["lock_timeout"] = "2000"
	config.ConnConfig.RuntimeParams["idle_in_transaction_session_timeout"] = "5000"
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		return nil, err
	}
	if err = pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, err
	}
	return &Store{Pool: pool, Queries: db.New(pool), Instance: instance}, nil
}

func (s *Store) Migrate(ctx context.Context) error {
	database := stdlib.OpenDB(*s.Pool.Config().ConnConfig)
	defer database.Close()
	database.SetMaxOpenConns(2)
	files, err := fs.Sub(migrations, "migrations")
	if err != nil {
		return err
	}
	locker, err := lock.NewPostgresSessionLocker()
	if err != nil {
		return err
	}
	provider, err := goose.NewProvider(goose.DialectPostgres, database, files,
		goose.WithSessionLocker(locker), goose.WithDisableGlobalRegistry(true))
	if err != nil {
		return err
	}
	_, err = provider.Up(ctx)
	return err
}
