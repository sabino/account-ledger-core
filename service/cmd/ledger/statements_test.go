package main

import (
	"net/url"
	"testing"
)

func TestStatementQuery(t *testing.T) {
	for _, query := range []string{"account=a", "account=a&cutoff=0", "account=a&cutoff=12&after_sequence=4&after_leg=1&limit=100"} {
		values, _ := url.ParseQuery(query)
		if _, err := parseStatementRequest(values); err != nil {
			t.Errorf("%s: %v", query, err)
		}
	}
	for _, query := range []string{"", "account=a&limit=0", "account=a&limit=101", "account=a&cutoff=-1", "account=a&cutoff=x", "account=a&cutoff=9223372036854775808", "account=a&cutoff=1&cutoff=2", "account=a&after_sequence=1&after_leg=0", "account=a&cutoff=4&after_sequence=5&after_leg=0", "account=a&cutoff=4&after_sequence=1", "account=a&after_leg=0", "account=a&surprise=1", "account=a&limit="} {
		values, _ := url.ParseQuery(query)
		if _, err := parseStatementRequest(values); err == nil {
			t.Errorf("accepted %s", query)
		}
	}
}
