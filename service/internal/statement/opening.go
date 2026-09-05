// Package statement owns independent synthetic bank input, not ledger queries.
package statement

import (
	"crypto/sha256"
	_ "embed"
	"encoding/csv"
	"encoding/hex"
	"encoding/json"
	"errors"
	"reflect"
	"strconv"
	"strings"

	"github.com/sabino/account-ledger-core/service/internal/domain"
)

//go:embed opening.csv
var opening string

var ErrScenario = errors.New("unknown synthetic statement scenario")

type Document struct {
	ID     string                  `json:"id"`
	SHA256 string                  `json:"sha256"`
	Lines  []domain.SettlementLine `json:"lines"`
}

// Opening never reads balances, postings or the seed implementation. Fault
// scenarios alter a fresh copy of the statement, never the ledger or baseline.
func Opening(scenario string) (Document, error) {
	if scenario == "" {
		scenario = "clean"
	}
	switch scenario {
	case "clean", "missing", "duplicate", "amount", "date":
	default:
		return Document{}, ErrScenario
	}
	rows, err := csv.NewReader(strings.NewReader(opening)).ReadAll()
	if err != nil {
		return Document{}, err
	}
	if len(rows) != 41 || !reflect.DeepEqual(rows[0], []string{"reference", "currency", "value_day", "amount"}) {
		return Document{}, errors.New("invalid embedded opening statement")
	}
	doc := Document{ID: "synthetic-opening-v1/" + scenario, Lines: make([]domain.SettlementLine, 0, 40)}
	for _, row := range rows[1:] {
		day, err := strconv.ParseInt(row[2], 10, 32)
		if err != nil {
			return Document{}, err
		}
		amount, err := domain.Parse(row[3], row[1])
		if err != nil {
			return Document{}, err
		}
		doc.Lines = append(doc.Lines, domain.SettlementLine{Reference: row[0], Currency: row[1], ValueDay: int32(day), Amount: amount})
	}
	switch scenario {
	case "missing":
		doc.Lines = doc.Lines[1:]
	case "duplicate":
		doc.Lines = append(doc.Lines, doc.Lines[0])
	case "amount":
		doc.Lines[0].Amount++
	case "date":
		doc.Lines[0].ValueDay++
	}
	encoded, err := json.Marshal(doc.Lines)
	if err != nil {
		return Document{}, err
	}
	digest := sha256.Sum256(encoded)
	doc.SHA256 = hex.EncodeToString(digest[:])
	return doc, nil
}
