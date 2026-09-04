package store

import (
	"context"
	"fmt"

	"github.com/sabino/account-ledger-core/service/internal/db"
)

func (s *Store) Seed(ctx context.Context) error {
	tx, err := s.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	queries := s.Queries.WithTx(tx)
	for _, step := range []func(context.Context) error{
		queries.LockBootstrap, queries.CreateDemoRun, queries.CreateDemoClock, queries.CreateDemoControls,
	} {
		if err = step(ctx); err != nil {
			return err
		}
	}
	for _, currency := range []string{"AED", "BHD"} {
		for _, account := range []struct{ id, class, name string }{
			{"settlement", "asset", "Simulated settlement asset"},
			{"fees", "income", "Fee income"},
			{"interest", "expense", "Interest expense"},
		} {
			err = queries.CreateAccount(ctx, db.CreateAccountParams{
				RunID: "demo", ID: account.id + "-" + currency, Name: account.name,
				Currency: currency, Class: account.class, Customer: false,
			})
			if err != nil {
				return err
			}
		}
	}
	names := []string{"Alex", "Robin", "Sam", "Casey", "Ari", "Drew", "Jules", "Morgan", "Taylor", "Riley"}
	for i := 1; i <= 40; i++ {
		err = queries.CreateAccount(ctx, db.CreateAccountParams{
			RunID: "demo", ID: fmt.Sprintf("ACC-%03d", i),
			Name:     fmt.Sprintf("%s · %02d", names[(i-1)%len(names)], i),
			Currency: seedCurrency(i), Class: "liability", Customer: true,
		})
		if err != nil {
			return err
		}
	}
	if err = tx.Commit(ctx); err != nil {
		return err
	}
	for i := 1; i <= 40; i++ {
		_, err = s.Process(ctx, "demo", Command{
			ID: fmt.Sprintf("seed-%03d", i), Kind: "credit", Account: fmt.Sprintf("ACC-%03d", i),
			Currency: seedCurrency(i), Amount: "1000", BookedDay: 1, ValueDay: 1,
		})
		if err != nil {
			return err
		}
	}
	return nil
}

func seedCurrency(i int) string {
	if i > 20 {
		return "BHD"
	}
	return "AED"
}
