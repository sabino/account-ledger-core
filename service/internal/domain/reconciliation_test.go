package domain

import (
	"math"
	"reflect"
	"testing"
)

func TestSettlementComparisonNamesDifferencesWithoutNettingThemAway(t *testing.T) {
	line := func(ref string, amount int64) SettlementLine {
		return SettlementLine{Reference: ref, Currency: "AED", ValueDay: 2, Amount: amount}
	}
	ledger := []SettlementLine{line("matched", -101), line("wrong-amount", 100), line("wrong-day", 7), line("both", 5), line("missing-bank", 10), line("dup", 20), line("dup", 20)}
	statement := []SettlementLine{line("matched", -101), line("wrong-amount", 101), line("wrong-day", 7), line("both", 6), line("missing-ledger", 9), line("dup", 20)}
	statement[2].ValueDay = 3
	statement[3].ValueDay = 3
	before := append([]SettlementLine(nil), ledger...)
	result, err := CompareSettlement(ledger, statement)
	if err != nil || result.Matched != 1 || len(result.Differences) != 6 {
		t.Fatalf("%+v %v", result, err)
	}
	want := []string{"amount_and_value_day_mismatch", "duplicate_reference_ledger", "missing_from_statement", "missing_from_ledger", "amount_mismatch", "value_day_mismatch"}
	for i, d := range result.Differences {
		if d.Reason != want[i] {
			t.Fatalf("difference %d: %+v", i, d)
		}
	}
	if !reflect.DeepEqual(ledger, before) {
		t.Fatal("comparison modified ledger input")
	}
}

func TestSettlementComparisonKeepsCurrenciesSignsAndDuplicatesDistinct(t *testing.T) {
	a := SettlementLine{Reference: "same-reference", Currency: "AED", ValueDay: 1, Amount: math.MaxInt64}
	b := a
	b.Currency = "BHD"
	r, err := CompareSettlement([]SettlementLine{a}, []SettlementLine{b})
	if err != nil || r.Matched != 0 || len(r.Differences) != 2 {
		t.Fatalf("invented FX match: %+v %v", r, err)
	}
	b = a
	b.Amount = -a.Amount
	r, err = CompareSettlement([]SettlementLine{a}, []SettlementLine{b})
	if err != nil || r.Differences[0].Reason != "amount_mismatch" {
		t.Fatalf("lost sign: %+v %v", r, err)
	}
	for _, sides := range []struct {
		l, r   []SettlementLine
		reason string
	}{
		{[]SettlementLine{a}, []SettlementLine{a, a}, "duplicate_reference_statement"},
		{[]SettlementLine{a, a}, []SettlementLine{a, a}, "duplicate_reference_both"},
	} {
		r, err = CompareSettlement(sides.l, sides.r)
		if err != nil || r.Matched != 0 || r.Differences[0].Reason != sides.reason {
			t.Fatalf("duplicate silently accepted: %+v %v", r, err)
		}
	}
	r, err = CompareSettlement([]SettlementLine{a, b}, []SettlementLine{a, b})
	if err != nil || r.Matched != 0 {
		t.Fatal("duplicate reference was hidden by zero net movement")
	}
}

func TestSettlementComparisonRejectsInvalidAndUnboundedInput(t *testing.T) {
	valid := SettlementLine{Reference: "a", Currency: "BHD", ValueDay: 1, Amount: 1}
	for _, bad := range []SettlementLine{{}, {Reference: "a", Currency: "USD", ValueDay: 1, Amount: 1}, {Reference: "a", Currency: "AED", ValueDay: 367, Amount: 1}} {
		if _, err := CompareSettlement([]SettlementLine{valid}, []SettlementLine{bad}); err == nil {
			t.Fatal("invalid external input accepted")
		}
	}
	if _, err := CompareSettlement(make([]SettlementLine, 10001), nil); err == nil {
		t.Fatal("unbounded comparison accepted")
	}
	r, err := CompareSettlement(nil, nil)
	if err != nil || r.Matched != 0 || len(r.Differences) != 0 {
		t.Fatalf("empty window: %+v %v", r, err)
	}
}
