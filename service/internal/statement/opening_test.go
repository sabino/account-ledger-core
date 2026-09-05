package statement

import (
	"errors"
	"github.com/sabino/account-ledger-core/service/internal/domain"
	"testing"
)

func TestIndependentOpeningStatementAndControlledFaults(t *testing.T) {
	clean, err := Opening("clean")
	if err != nil {
		t.Fatal(err)
	}
	if len(clean.Lines) != 40 || len(clean.SHA256) != 64 {
		t.Fatalf("bad document: %+v", clean)
	}
	totals := map[string]int64{}
	for _, line := range clean.Lines {
		totals[line.Currency] += line.Amount
	}
	if totals["AED"] != 2000000 || totals["BHD"] != 20000000 {
		t.Fatal(totals)
	}
	for scenario, reason := range map[string]string{"missing": "missing_from_statement", "duplicate": "duplicate_reference_statement", "amount": "amount_mismatch", "date": "value_day_mismatch"} {
		doc, err := Opening(scenario)
		if err != nil {
			t.Fatal(err)
		}
		result, err := domain.CompareSettlement(clean.Lines, doc.Lines)
		if err != nil || result.Matched != 39 || len(result.Differences) != 1 || result.Differences[0].Reason != reason || doc.SHA256 == clean.SHA256 {
			t.Fatalf("%s: %+v %v", scenario, result, err)
		}
	}
	again, err := Opening("")
	if err != nil || again.SHA256 != clean.SHA256 {
		t.Fatal("fault changed baseline")
	}
	if _, err := Opening("untrusted"); !errors.Is(err, ErrScenario) {
		t.Fatal(err)
	}
}
