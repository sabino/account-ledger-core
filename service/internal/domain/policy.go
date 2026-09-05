package domain

import (
	"encoding/json"
	"errors"
)

// Policy is persisted once per run. The runtime role cannot update it.
type Policy struct {
	Version     string `json:"version"`
	FeeAED      int64  `json:"fee_aed"`
	Numerator   int64  `json:"rate_numerator"`
	Denominator int64  `json:"rate_denominator"`
}

func ParsePolicy(raw []byte) (Policy, error) {
	// Version 1 recorded the fixed numerator implicitly as one.
	policy := Policy{Numerator: 1}
	if err := json.Unmarshal(raw, &policy); err != nil {
		return policy, err
	}
	if policy.Version == "" || policy.FeeAED <= 0 || policy.FeeAED > MaxRequest || policy.Numerator < 0 || policy.Denominator <= 0 {
		return policy, errors.New("invalid persisted policy")
	}
	return policy, nil
}
