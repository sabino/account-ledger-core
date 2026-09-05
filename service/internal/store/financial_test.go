//go:build integration

package store

import (
	"context"
	"encoding/json"
	"os"
	"reflect"
	"testing"

	"github.com/sabino/account-ledger-core/service/internal/db"
)

type moneyPeriod struct {
	Transfers  string `json:"transfersMinor"`
	Captures   string `json:"capturesMinor"`
	Purchases  string `json:"purchasesGrossMinor"`
	Processed  string `json:"processedMinor"`
	Operations int    `json:"operations"`
}

func TestFinancialCountsEconomicValueOnceAndKeepsCurrenciesSeparate(t *testing.T) {
	a, _, run := testLedger(t)
	ctx := context.Background()
	owner, err := Open(ctx, os.Getenv("TEST_DATABASE_URL"), "financial-setup")
	if err != nil {
		t.Fatal(err)
	}
	defer owner.Pool.Close()
	for _, account := range []db.CreateAccountParams{
		{RunID: run, ID: "tax-AED", Name: "Tax", Currency: "AED", Class: "liability"},
		{RunID: run, ID: "settlement-BHD", Name: "Settlement", Currency: "BHD", Class: "asset"},
		{RunID: run, ID: "d", Name: "D", Currency: "BHD", Class: "liability", Customer: true},
	} {
		if err := owner.Queries.CreateAccount(ctx, account); err != nil {
			t.Fatal(err)
		}
	}
	for i := int64(0); i < 12; i++ {
		input := GeneratedCommand(i)
		input.Account, input.Destination = "a", "b"
		if i == 7 {
			input.Destination = "c"
		}
		if _, err := a.Process(ctx, run, input); err != nil {
			t.Fatal(err)
		}
	}
	input := Command{ID: "fund-c", Kind: "credit", Account: "c", Currency: "BHD", Amount: "10.000", BookedDay: 1, ValueDay: 1}
	if result, err := a.Process(ctx, run, input); err != nil || result.Status != "accepted" {
		t.Fatal(result, err)
	}
	input.ID, input.Kind, input.Destination, input.Installments = "split-bhd", "split_transfer", "d", 3
	for i := 0; i < 2; i++ {
		if result, err := a.Process(ctx, run, input); err != nil || result.Status != "accepted" {
			t.Fatal(result, err)
		}
	}
	hold := command("remaining-hold", "hold")
	hold.Amount, hold.Authorization = "0.03", "open-hold"
	if result, err := a.Process(ctx, run, hold); err != nil || result.Status != "accepted" {
		t.Fatal(result, err)
	}
	raw, err := a.Financial(ctx, run)
	if err != nil {
		t.Fatal(err)
	}
	var got struct {
		RunID      string `json:"runId"`
		TimeZone   string `json:"timeZone"`
		ByCurrency map[string]struct {
			Today    moneyPeriod `json:"today"`
			Run      moneyPeriod `json:"run"`
			Balances struct {
				Posted    string `json:"postedMinor"`
				Held      string `json:"heldMinor"`
				Available string `json:"availableMinor"`
				Customers int    `json:"customerCount"`
			} `json:"balances"`
		} `json:"byCurrency"`
		Hourly map[string][]struct {
			Amount string `json:"amountMinor"`
		} `json:"hourly"`
		Minute map[string][]struct {
			Amount string `json:"amountMinor"`
		} `json:"minute"`
		Daily []struct {
			AED     string
			BHD     string
			Partial bool
		} `json:"daily"`
	}
	if err := json.Unmarshal(raw, &got); err != nil {
		t.Fatal(err)
	}
	if got.RunID != run || got.TimeZone != "UTC" {
		t.Fatal(string(raw))
	}
	for currency, want := range map[string]moneyPeriod{
		"AED": {"1001", "2", "42", "1045", 5},
		"BHD": {"10000", "0", "0", "10000", 1},
	} {
		actual := got.ByCurrency[currency]
		if !reflect.DeepEqual(actual.Run, want) || !reflect.DeepEqual(actual.Today, want) {
			t.Fatalf("%s: %+v want %+v", currency, actual, want)
		}
		if len(got.Hourly[currency]) != 24 || len(got.Minute[currency]) != 60 {
			t.Fatal("unbounded/missing buckets")
		}
	}
	balances := got.ByCurrency["AED"].Balances
	if balances.Posted != "19996" || balances.Held != "3" || balances.Available != "19993" || balances.Customers != 2 {
		t.Fatal(balances)
	}
	if got.ByCurrency["BHD"].Balances.Posted != "10000" || len(got.Daily) != 7 || !got.Daily[6].Partial || got.Daily[6].AED != "1045" || got.Daily[6].BHD != "10000" {
		t.Fatal(string(raw))
	}
	assertReconciled(t, a, run)
}
