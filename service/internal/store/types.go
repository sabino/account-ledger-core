// Package store owns database transactions, not HTTP or presentation.
package store

import (
	"context"
	_ "embed"
	"errors"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/sabino/account-ledger-core/service/internal/db"
)

//go:embed schema.sql
var schema string

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
}

type Leg struct {
	Account  string `json:"account"`
	Currency string `json:"currency"`
	Units    int64  `json:"units,string"`
}

type Result struct {
	ID       string `json:"id"`
	Status   string `json:"status"`
	Reason   string `json:"reason,omitempty"`
	Sequence int64  `json:"sequence,string"`
	Instance string `json:"instance"`
	Kind     string `json:"kind"`
	Legs     []Leg  `json:"legs"`
	Captured int64  `json:"captured,string"`
	Released int64  `json:"released,string"`
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
	_, err := s.Pool.Exec(ctx, schema)
	return err
}
