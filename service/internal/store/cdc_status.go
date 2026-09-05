package store

import "github.com/sabino/account-ledger-core/service/internal/db"

type cdcSourceStatus struct {
	State            string  `json:"state"`
	Active           bool    `json:"active"`
	WALStatus        string  `json:"wal_status"`
	RetainedWALBytes *string `json:"retained_wal_bytes"`
	Note             string  `json:"note"`
}

func describeCDCSource(row db.CDCSourceStatusRow) cdcSourceStatus {
	result := cdcSourceStatus{State: "absent", Active: row.Active, WALStatus: row.WalStatus,
		Note: "Source slot only. A connected consumer does not prove that lake files are current or reconciled."}
	if row.Present {
		result.State = "inactive"
		if row.Active {
			result.State = "streaming"
		}
		if row.Invalidated {
			result.State = "invalidated"
		}
	}
	// A lost restart position is unknown retained storage, not zero bytes.
	if row.Present && row.RetainedWalBytes != "" {
		result.RetainedWALBytes = &row.RetainedWalBytes
	}
	return result
}
