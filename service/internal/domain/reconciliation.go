package domain

import (
	"errors"
	"sort"
)

// SettlementLine is normalized to the bank settlement-asset perspective:
// positive means funds arrived, negative means funds left. The adapter must
// preserve the external reference; it must not infer a match from amount alone.
type SettlementLine struct {
	Reference string `json:"reference"`
	Currency  string `json:"currency"`
	ValueDay  int32  `json:"value_day"`
	Amount    int64  `json:"amount,string"`
}

type SettlementDifference struct {
	Reference string           `json:"reference"`
	Currency  string           `json:"currency"`
	Reason    string           `json:"reason"`
	Ledger    []SettlementLine `json:"ledger"`
	Statement []SettlementLine `json:"statement"`
}

type SettlementComparison struct {
	Matched     int                    `json:"matched"`
	Differences []SettlementDifference `json:"differences"`
}

// CompareSettlement requires one normalized movement per reference/currency on
// each side. Multi-posting ledger batches must be normalized by their adapter.
// Duplicate references remain discrepancies, even when their amounts agree;
// this function cannot decide whether they mean redelivery or duplicate money.
// Neither input is modified and no repair posting is produced.
func CompareSettlement(ledger, statement []SettlementLine) (SettlementComparison, error) {
	result := SettlementComparison{Differences: []SettlementDifference{}}
	if len(ledger) > 10000 || len(statement) > 10000 {
		return result, errors.New("settlement comparison exceeds bounded window")
	}
	type key struct{ reference, currency string }
	index := func(lines []SettlementLine) (map[key][]SettlementLine, error) {
		out := make(map[key][]SettlementLine)
		for _, line := range lines {
			if len(line.Reference) == 0 || len(line.Reference) > 100 || line.ValueDay < 1 || line.ValueDay > 366 || line.Amount == 0 {
				return nil, errors.New("invalid settlement line")
			}
			if _, err := Precision(line.Currency); err != nil {
				return nil, err
			}
			k := key{line.Reference, line.Currency}
			out[k] = append(out[k], line)
		}
		return out, nil
	}
	left, err := index(ledger)
	if err != nil {
		return result, err
	}
	right, err := index(statement)
	if err != nil {
		return result, err
	}
	keys := make([]key, 0, len(left)+len(right))
	for k := range left {
		keys = append(keys, k)
	}
	for k := range right {
		if _, exists := left[k]; !exists {
			keys = append(keys, k)
		}
	}
	sort.Slice(keys, func(i, j int) bool {
		if keys[i].currency != keys[j].currency {
			return keys[i].currency < keys[j].currency
		}
		return keys[i].reference < keys[j].reference
	})
	for _, k := range keys {
		l, r := left[k], right[k]
		reason := ""
		switch {
		case len(l) > 1 && len(r) > 1:
			reason = "duplicate_reference_both"
		case len(l) > 1:
			reason = "duplicate_reference_ledger"
		case len(r) > 1:
			reason = "duplicate_reference_statement"
		case len(l) == 0:
			reason = "missing_from_ledger"
		case len(r) == 0:
			reason = "missing_from_statement"
		case l[0].Amount != r[0].Amount && l[0].ValueDay != r[0].ValueDay:
			reason = "amount_and_value_day_mismatch"
		case l[0].Amount != r[0].Amount:
			reason = "amount_mismatch"
		case l[0].ValueDay != r[0].ValueDay:
			reason = "value_day_mismatch"
		default:
			result.Matched++
			continue
		}
		result.Differences = append(result.Differences, SettlementDifference{Reference: k.reference, Currency: k.currency, Reason: reason, Ledger: l, Statement: r})
	}
	return result, nil
}
