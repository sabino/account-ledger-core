package store

import (
	"github.com/sabino/account-ledger-core/service/internal/db"
	"github.com/sabino/account-ledger-core/service/internal/domain"
)

// These are explicit simulation extensions, not jurisdictional tax rules or a
// dated repayment schedule. Their calculation evidence is stored with the batch.
func decideIllustration(command Command, amount int64, source *db.Account, result *Result) error {
	gross := amount
	if command.Kind == "purchase" {
		tax, err := domain.RoundRatio(amount, 1, 20)
		if err != nil {
			return err
		}
		gross, err = domain.Add(amount, tax)
		if err != nil {
			return err
		}
		result.Calculation = &Calculation{Policy: "illustrative-tax-v1-not-compliance", Net: amount, Tax: tax, Gross: gross, Numerator: 1, Denominator: 20, Rounding: "half-even per purchase"}
	}
	available, err := domain.Add(source.Balance, -source.Held)
	if err != nil {
		return err
	}
	result.Decision.Requested = gross
	if available < gross {
		result.Status, result.Reason = "declined", "insufficient available funds"
		return nil
	}
	if command.Kind == "split_transfer" {
		parts, err := domain.Allocate(amount, int(command.Installments))
		if err != nil {
			result.reject(err.Error())
			return nil
		}
		for _, part := range parts {
			result.Legs = append(result.Legs, movement(command.Account, command.Destination, command.Currency, part, command.ValueDay, "split_transfer")...)
		}
		return nil
	}
	result.Legs = movement(command.Account, command.Destination, command.Currency, amount, command.ValueDay, "purchase_net")
	if result.Calculation.Tax > 0 {
		result.Legs = append(result.Legs, movement(command.Account, "tax-"+command.Currency, command.Currency, result.Calculation.Tax, command.ValueDay, "illustrative_tax")...)
	}
	return nil
}
