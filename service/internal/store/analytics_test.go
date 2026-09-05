//go:build integration

package store

import (
	"context"
	"encoding/json"
	"testing"
)

func TestAnalyticsCountsDecisionsNotRetriesAndScopesCurrency(t *testing.T) {
	a, _, run := testLedger(t)
	ctx := context.Background()
	input := command("analytics-transfer", "transfer")
	for i := 0; i < 2; i++ {
		if _, err := a.Process(ctx, run, input); err != nil {
			t.Fatal(err)
		}
	}
	declined := command("analytics-declined", "transfer")
	if _, err := a.Process(ctx, run, declined); err != nil {
		t.Fatal(err)
	}
	bhd := Command{ID: "bhd-rejected", Kind: "transfer", Account: "c", Destination: "a", Currency: "BHD", Amount: "0.001", BookedDay: 1, ValueDay: 1}
	if _, err := a.Process(ctx, run, bhd); err != nil {
		t.Fatal(err)
	}
	for _, tt := range []struct {
		currency                            string
		total, accepted, declined, rejected int
	}{{"AED", 4, 3, 1, 0}, {"BHD", 1, 0, 0, 1}, {"", 5, 3, 1, 1}} {
		raw, err := a.Analytics(ctx, run, tt.currency, 600)
		if err != nil {
			t.Fatal(err)
		}
		var got struct {
			Buckets   []struct{ Total, Accepted, Declined, Rejected int }
			Instances []struct{ Total int }
		}
		if err = json.Unmarshal(raw, &got); err != nil {
			t.Fatal(err)
		}
		if len(got.Buckets) != 60 {
			t.Fatalf("%d buckets", len(got.Buckets))
		}
		total, accepted, declined, rejected := 0, 0, 0, 0
		for _, b := range got.Buckets {
			total += b.Total
			accepted += b.Accepted
			declined += b.Declined
			rejected += b.Rejected
		}
		if total != tt.total || accepted != tt.accepted || declined != tt.declined || rejected != tt.rejected {
			t.Fatalf("%s: %d/%d/%d/%d", tt.currency, total, accepted, declined, rejected)
		}
		instances := 0
		for _, r := range got.Instances {
			instances += r.Total
		}
		if instances != total {
			t.Fatal("instance total differs")
		}
	}
}
