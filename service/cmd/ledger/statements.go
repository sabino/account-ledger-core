package main

import (
	"github.com/sabino/account-ledger-core/service/internal/store"
	"net/url"
	"strconv"
)

func parseStatementRequest(values url.Values) (store.StatementRequest, error) {
	request := store.StatementRequest{Account: values.Get("account"), Cutoff: -1, AfterLeg: -1, Limit: 50}
	for key, items := range values {
		if len(items) != 1 || items[0] == "" {
			return request, store.ErrStatementInput
		}
		if key == "account" {
			continue
		}
		bits := 64
		if key == "limit" || key == "after_leg" {
			bits = 32
		}
		number, err := strconv.ParseInt(items[0], 10, bits)
		if err != nil || number < 0 {
			return request, store.ErrStatementInput
		}
		switch key {
		case "cutoff":
			request.Cutoff = number
		case "after_sequence":
			request.AfterSequence = number
		case "after_leg":
			request.AfterLeg = int32(number)
		case "limit":
			request.Limit = int32(number)
		default:
			return request, store.ErrStatementInput
		}
	}
	return request, request.Validate()
}
