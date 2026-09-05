package store

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"
	"github.com/sabino/account-ledger-core/service/internal/db"
)

const FixtureRun = "assessment-v1"

func FixtureCommands() []Command {
	return []Command{
		{ID: "E1", Kind: "credit", Account: "ACC-001", Currency: "AED", Amount: "1200.00", BookedDay: 1, ValueDay: 1},
		{ID: "E2", Kind: "debit", Account: "ACC-001", Currency: "AED", Amount: "950.00", BookedDay: 1, ValueDay: 1},
		{ID: "E3", Kind: "hold", Account: "ACC-001", Currency: "AED", Amount: "200.00", Authorization: "Auth-A", BookedDay: 2, ValueDay: 2},
		{ID: "E4", Kind: "credit", Account: "ACC-001", Currency: "AED", Amount: "400.00", BookedDay: 3, ValueDay: 3},
		{ID: "E5", Kind: "capture", Account: "ACC-001", Currency: "AED", Amount: "185.00", Authorization: "Auth-A", BookedDay: 4, ValueDay: 4},
		{ID: "E6", Kind: "capture", Account: "ACC-001", Currency: "AED", Amount: "180.00", Authorization: "Auth-Z", BookedDay: 4, ValueDay: 4},
		{ID: "E7", Kind: "debit", Account: "ACC-001", Currency: "AED", Amount: "620.00", BookedDay: 5, ValueDay: 2},
		{ID: "E8", Kind: "hold", Account: "ACC-001", Currency: "AED", Amount: "90.00", Authorization: "Auth-B", BookedDay: 5, ValueDay: 5},
		{ID: "E9", Kind: "reversal", Account: "ACC-001", Currency: "AED", TargetEvent: "E7", BookedDay: 6, ValueDay: 2},
		{ID: "E10", Kind: "credit", Account: "ACC-002", Currency: "BHD", Amount: "10.000", Installments: 3, BookedDay: 5, ValueDay: 5},
	}
}

func (s *Store) SeedFixture(ctx context.Context) error {
	tx, err := s.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	queries := s.Queries.WithTx(tx)
	if err = queries.LockBootstrap(ctx); err != nil {
		return err
	}
	_, err = queries.LockRun(ctx, FixtureRun)
	if errors.Is(err, pgx.ErrNoRows) {
		if err = queries.CreateRun(ctx, db.CreateRunParams{ID: FixtureRun, Profile: "fixture"}); err != nil {
			return err
		}
		if err = queries.CreateClock(ctx, FixtureRun); err != nil {
			return err
		}
		if err = queries.CreateControls(ctx, FixtureRun); err != nil {
			return err
		}
		for _, currency := range []string{"AED", "BHD"} {
			accountID := "ACC-001"
			if currency == "BHD" {
				accountID = "ACC-002"
			}
			for _, account := range []db.CreateAccountParams{
				{RunID: FixtureRun, ID: accountID, Name: "Assessment account", Currency: currency, Class: "liability", Customer: true},
				{RunID: FixtureRun, ID: "settlement-" + currency, Name: "Settlement asset", Currency: currency, Class: "asset"},
				{RunID: FixtureRun, ID: "fees-" + currency, Name: "Fee income", Currency: currency, Class: "income"},
				{RunID: FixtureRun, ID: "interest-" + currency, Name: "Interest expense", Currency: currency, Class: "expense"},
			} {
				if err = queries.CreateAccount(ctx, account); err != nil {
					return err
				}
			}
		}
	} else if err != nil {
		return err
	}
	if err = tx.Commit(ctx); err != nil {
		return err
	}
	for _, command := range FixtureCommands() {
		if _, err = s.Process(ctx, FixtureRun, command); err != nil {
			return err
		}
	}
	_, err = s.Finalize(ctx, FixtureRun, 1, 6)
	return err
}
