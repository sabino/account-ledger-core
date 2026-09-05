package store

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"slices"
	"sort"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/sabino/account-ledger-core/service/internal/db"
	"github.com/sabino/account-ledger-core/service/internal/domain"
)

// Process locks lifecycle, identity, sorted accounts, authorization, and finally
// the journal clock. The transaction includes the complete outcome and outbox.
func (s *Store) Process(ctx context.Context, runID string, command Command) (Result, error) {
	return s.process(ctx, runID, command, nil)
}

func (s *Store) process(ctx context.Context, runID string, command Command, generated *db.ClaimGeneratedCommandRow) (Result, error) {
	if len(command.ID) < 1 || len(command.ID) > 100 || strings.HasPrefix(command.ID, "system:") || len(command.Account) > 80 ||
		len(command.Authorization) > 100 || len(command.Destination) > 80 {
		return Result{}, errors.New("invalid command identity")
	}
	tx, err := s.Pool.Begin(ctx)
	if err != nil {
		return Result{}, err
	}
	defer tx.Rollback(ctx)
	queries := s.Queries.WithTx(tx)
	run, err := queries.LockRun(ctx, runID)
	if err != nil {
		return Result{}, err
	}
	if generated != nil {
		_, err = queries.LockGeneratedCommand(ctx, db.LockGeneratedCommandParams{
			RunID: runID, Ordinal: generated.Ordinal, GeneratorToken: generated.GeneratorToken,
		})
		if err != nil {
			return Result{}, err
		}
		// Assign dates only after the lifecycle and generator fences. A retry
		// reuses the original dates, but every other field must still hash to
		// the original payload; changed recipe inputs are not silently accepted.
		command.BookedDay, command.ValueDay = run.Day, run.Day
		original, lookupErr := queries.LockCommand(ctx, db.LockCommandParams{RunID: runID, ID: command.ID})
		if lookupErr != nil && !errors.Is(lookupErr, pgx.ErrNoRows) {
			return Result{}, lookupErr
		}
		if lookupErr == nil && len(original.Response) > 0 {
			var recorded Result
			if err = json.Unmarshal(original.Response, &recorded); err != nil {
				return Result{}, err
			}
			if recorded.Command == nil {
				return Result{}, errors.New("generated retry has no original command evidence")
			}
			command.BookedDay, command.ValueDay = recorded.Command.BookedDay, recorded.Command.ValueDay
		}
	}
	payload, err := json.Marshal(command)
	if err != nil {
		return Result{}, err
	}
	digest := sha256.Sum256(payload)
	hash := hex.EncodeToString(digest[:])
	commit := func() error {
		if generated != nil {
			changed, err := queries.AcknowledgeGeneratedCommand(ctx, db.AcknowledgeGeneratedCommandParams{
				RunID: runID, Ordinal: generated.Ordinal, GeneratorToken: generated.GeneratorToken,
			})
			if err != nil {
				return err
			}
			if changed != 1 {
				return errors.New("generator claim no longer current")
			}
		}
		return tx.Commit(ctx)
	}
	if err = queries.ClaimCommand(ctx, db.ClaimCommandParams{RunID: runID, ID: command.ID, Hash: hash}); err != nil {
		return Result{}, err
	}
	prior, err := queries.LockCommand(ctx, db.LockCommandParams{RunID: runID, ID: command.ID})
	if err != nil {
		return Result{}, err
	}
	if prior.Hash != hash {
		return Result{}, ErrConflict
	}
	if len(prior.Response) > 0 {
		var result Result
		err = json.Unmarshal(prior.Response, &result)
		if err == nil && generated != nil {
			err = commit()
		}
		return result, err
	}
	result := Result{ID: command.ID, Status: "accepted", Instance: s.Instance, Kind: command.Kind, Legs: []Leg{}}
	var amount int64
	if command.Kind != "reversal" {
		amount, err = domain.Parse(command.Amount, command.Currency)
		if err != nil {
			result.reject(err.Error())
		}
	}
	if command.BookedDay < 1 || command.ValueDay < 1 {
		result.reject("dates must be positive")
	}
	if run.Finalized {
		result.reject("run finalized")
	}
	if run.Profile == "live" && (command.BookedDay != run.Day || command.ValueDay != run.Day) {
		result.reject("live commands use the current simulation day")
	}
	accounts, err := lockAccounts(ctx, queries, runID, command, run.Profile, &result)
	if err != nil {
		return Result{}, err
	}
	if result.Status == "accepted" {
		if run.Profile == "live" {
			for _, account := range accounts {
				if !account.Customer {
					continue
				}
				pending, err := queries.PendingAccountCloses(ctx, db.PendingAccountClosesParams{RunID: runID, AccountID: account.ID})
				if err != nil {
					return Result{}, err
				}
				if pending > 0 {
					return Result{}, ErrClosePending
				}
			}
		}
		if run.Profile == "fixture" {
			if err = s.closeBeforeEvent(ctx, queries, run, command, accounts); err != nil {
				return Result{}, err
			}
		}
		source := accounts[command.Account]
		available, availableErr := domain.Add(source.Balance, -source.Held)
		if availableErr != nil {
			return Result{}, availableErr
		}
		result.Decision = &DecisionEvidence{Balance: source.Balance, Held: source.Held, Available: available, Requested: amount}
		if err = decide(ctx, queries, runID, command, amount, accounts, &result); err != nil {
			return Result{}, err
		}
	}
	if result.Status == "accepted" && run.Profile == "fixture" && len(result.Legs) > 0 {
		policy, policyErr := domain.ParsePolicy(run.Policy)
		if policyErr != nil {
			return Result{}, policyErr
		}
		latest, lookupErr := queries.LatestBookedDay(ctx, runID)
		if lookupErr != nil {
			return Result{}, lookupErr
		}
		fees, feeErr := missingFees(ctx, queries, runID, accounts[command.Account], command.ValueDay,
			max(command.BookedDay, latest)-1, result.Legs, policy)
		if feeErr != nil {
			return Result{}, feeErr
		}
		result.Legs = append(result.Legs, fees...)
	}
	if err = applyBalances(ctx, queries, runID, accounts, result); err != nil {
		return Result{}, err
	}
	if err = s.appendResult(ctx, queries, run, command, &result); err != nil {
		return Result{}, err
	}
	if err = commit(); err != nil {
		return Result{}, err
	}
	return result, nil
}

func lockAccounts(ctx context.Context, queries *db.Queries, runID string, command Command, profile string, result *Result) (map[string]*db.Account, error) {
	ids := []string{command.Account}
	switch command.Kind {
	case "transfer", "split_transfer":
		ids = append(ids, command.Destination)
	case "purchase":
		ids = append(ids, command.Destination, "tax-"+command.Currency)
	case "credit", "debit", "capture", "reversal":
		ids = append(ids, "settlement-"+command.Currency)
	case "hold":
	default:
		result.reject("unsupported command kind")
	}
	if profile == "fixture" && command.Currency == "AED" {
		ids = append(ids, "fees-AED")
	}
	sort.Strings(ids)
	ids = slices.Compact(ids)
	accounts := make(map[string]*db.Account, len(ids))
	for _, id := range ids {
		account, err := queries.LockAccount(ctx, db.LockAccountParams{RunID: runID, ID: id})
		if errors.Is(err, pgx.ErrNoRows) {
			result.reject("unknown account")
			continue
		}
		if err != nil {
			return nil, err
		}
		accounts[id] = &account
		if account.Currency != command.Currency {
			result.reject("currency mismatch")
		}
	}
	if source := accounts[command.Account]; source != nil && !source.Customer {
		result.reject("source must be a customer account")
	}
	if command.Kind == "transfer" || command.Kind == "split_transfer" || command.Kind == "purchase" {
		destination := accounts[command.Destination]
		if command.Account == command.Destination || destination != nil && !destination.Customer {
			result.reject("choose two different customer accounts")
		}
	}
	return accounts, nil
}

func decide(ctx context.Context, queries *db.Queries, runID string, command Command, amount int64, accounts map[string]*db.Account, result *Result) error {
	source := accounts[command.Account]
	switch command.Kind {
	case "credit":
		count := command.Installments
		if count == 0 {
			count = 1
		}
		parts, err := domain.Allocate(amount, int(count))
		if err != nil {
			result.reject(err.Error())
			return nil
		}
		kind := "credit"
		if count > 1 {
			kind = "installment_credit"
		}
		for _, part := range parts {
			result.Legs = append(result.Legs, movement("settlement-"+command.Currency, command.Account, command.Currency, part, command.ValueDay, kind)...)
		}
	case "debit", "transfer":
		available, err := domain.Add(source.Balance, -source.Held)
		if err != nil {
			return err
		}
		if command.Kind == "transfer" && available < amount {
			result.Status, result.Reason = "declined", "insufficient available funds"
			return nil
		}
		destination := command.Destination
		if command.Kind == "debit" {
			destination = "settlement-" + command.Currency
		}
		result.Legs = movement(command.Account, destination, command.Currency, amount, command.ValueDay, command.Kind)
	case "purchase", "split_transfer":
		return decideIllustration(command, amount, source, result)
	case "hold":
		return createHold(ctx, queries, runID, command, amount, source, result)
	case "capture":
		return captureHold(ctx, queries, runID, command, amount, source, result)
	case "reversal":
		return reverseDebit(ctx, queries, runID, command, result)
	}
	return nil
}

func createHold(ctx context.Context, queries *db.Queries, runID string, command Command, amount int64, source *db.Account, result *Result) error {
	latest, err := queries.LatestBookedDay(ctx, runID)
	if err != nil {
		return err
	}
	if command.ValueDay != command.BookedDay || command.BookedDay < latest {
		result.reject("authorization date unsupported")
		return nil
	}
	if command.Authorization == "" {
		result.reject("authorization required")
		return nil
	}
	balance, err := queries.HistoricalBalance(ctx, db.HistoricalBalanceParams{RunID: runID, AccountID: command.Account, ValueDay: command.ValueDay})
	if err != nil {
		return err
	}
	available, err := domain.Add(balance, -source.Held)
	if err != nil {
		return err
	}
	state := "active"
	if available < amount {
		state = "declined"
		result.Status, result.Reason = "declined", "insufficient available funds"
	}
	inserted, err := queries.CreateHold(ctx, db.CreateHoldParams{RunID: runID, ID: command.Authorization, AccountID: command.Account, Amount: amount, State: state, ValueDay: command.ValueDay})
	if err != nil {
		return err
	}
	if inserted == 0 {
		result.reject("authorization already exists")
		return nil
	}
	if state == "active" {
		source.Held, err = domain.Add(source.Held, amount)
	}
	return err
}

func captureHold(ctx context.Context, queries *db.Queries, runID string, command Command, amount int64, source *db.Account, result *Result) error {
	hold, err := queries.LockHold(ctx, db.LockHoldParams{RunID: runID, ID: command.Authorization})
	if errors.Is(err, pgx.ErrNoRows) {
		result.reject("authorization not found")
		return nil
	}
	if err != nil {
		return err
	}
	if hold.AccountID != command.Account || hold.State != "active" || amount > hold.Amount || command.ValueDay < hold.ValueDay {
		result.reject("authorization inactive, mismatched or over-captured")
		return nil
	}
	result.Captured, result.Released = amount, hold.Amount-amount
	source.Held -= hold.Amount
	err = queries.CaptureHold(ctx, db.CaptureHoldParams{RunID: runID, ID: command.Authorization, Captured: amount, Released: result.Released})
	if err != nil {
		return err
	}
	result.Legs = movement(command.Account, "settlement-"+command.Currency, command.Currency, amount, command.ValueDay, "capture")
	return nil
}

func applyBalances(ctx context.Context, queries *db.Queries, runID string, accounts map[string]*db.Account, result Result) error {
	if result.Status != "accepted" {
		return nil
	}
	for _, leg := range result.Legs {
		account := accounts[leg.Account]
		delta := leg.Units
		if account.Class == "liability" || account.Class == "income" || account.Class == "equity" {
			delta = -delta
		}
		balance, err := domain.Add(account.Balance, delta)
		if err != nil {
			return err
		}
		account.Balance = balance
	}
	ids := make([]string, 0, len(accounts))
	for id := range accounts {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, id := range ids {
		account := accounts[id]
		err := queries.UpdateAccount(ctx, db.UpdateAccountParams{RunID: runID, ID: id, Balance: account.Balance, Held: account.Held})
		if err != nil {
			return err
		}
	}
	return nil
}

func (s *Store) appendResult(ctx context.Context, queries *db.Queries, run db.Run, command Command, result *Result) error {
	sequence, err := queries.NextSequence(ctx, run.ID)
	if err != nil {
		return err
	}
	result.Sequence = sequence
	result.Policy = run.Policy
	result.Command = &command
	envelope, err := json.Marshal(result)
	if err != nil {
		return err
	}
	booked, value := command.BookedDay, command.ValueDay
	if booked < 1 {
		booked = run.Day
	}
	if value < 1 {
		value = run.Day
	}
	err = queries.AppendBatch(ctx, db.AppendBatchParams{RunID: run.ID, Sequence: sequence, CommandID: command.ID, Kind: command.Kind, BookedDay: booked, ValueDay: value, Instance: s.Instance, Envelope: envelope})
	if err != nil {
		return err
	}
	for index, leg := range result.Legs {
		err = queries.AppendPosting(ctx, db.AppendPostingParams{RunID: run.ID, Sequence: sequence, Leg: int32(index), AccountID: leg.Account, Currency: leg.Currency, Units: leg.Units, ValueDay: leg.ValueDay, Kind: leg.Kind})
		if err != nil {
			return err
		}
	}
	if err = queries.CompleteCommand(ctx, db.CompleteCommandParams{RunID: run.ID, ID: command.ID, Response: envelope}); err != nil {
		return err
	}
	return queries.EnqueueDelivery(ctx, db.EnqueueDeliveryParams{RunID: run.ID, Sequence: sequence})
}
