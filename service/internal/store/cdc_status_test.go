package store

import (
	"github.com/sabino/account-ledger-core/service/internal/db"
	"testing"
)

func TestCDCSourceStatesDoNotClaimLakeFreshness(t *testing.T) {
	for _, test := range []struct {
		name string
		row  db.CDCSourceStatusRow
		want string
	}{
		{"absent", db.CDCSourceStatusRow{}, "absent"},
		{"stopped", db.CDCSourceStatusRow{Present: true}, "inactive"},
		{"connected", db.CDCSourceStatusRow{Present: true, Active: true}, "streaming"},
		{"lost", db.CDCSourceStatusRow{Present: true, Active: true, Invalidated: true}, "invalidated"},
	} {
		t.Run(test.name, func(t *testing.T) {
			result := describeCDCSource(test.row)
			if result.State != test.want || result.RetainedWALBytes != nil || result.Note == "" {
				t.Fatalf("unexpected status: %+v", result)
			}
		})
	}
	large := "9223372036854775806"
	result := describeCDCSource(db.CDCSourceStatusRow{Present: true, RetainedWalBytes: large})
	if result.RetainedWALBytes == nil || *result.RetainedWALBytes != large {
		t.Fatal("retained bytes lost precision")
	}
}
