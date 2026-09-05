// Package domain contains exact money operations, independent of storage and HTTP.
package domain

import (
	"errors"
	"fmt"
	"math"
	"math/big"
	"strconv"
	"strings"
)

const MaxRequest int64 = 100_000_000 // Minor units; bounded public simulation commands.

func Precision(currency string) (int, error) {
	switch currency {
	case "AED":
		return 2, nil
	case "BHD":
		return 3, nil
	}
	return 0, errors.New("unsupported currency")
}

func Parse(text, currency string) (int64, error) {
	p, err := Precision(currency)
	if err != nil {
		return 0, err
	}
	parts := strings.Split(text, ".")
	if len(parts) > 2 || len(parts[0]) == 0 {
		return 0, errors.New("use decimal text")
	}
	if len(parts) > 1 && (len(parts[1]) == 0 || len(parts[1]) > p) {
		return 0, errors.New("unsupported precision")
	}
	for _, c := range strings.Join(parts, "") {
		if c < '0' || c > '9' {
			return 0, errors.New("use unsigned decimal text")
		}
	}
	fractional := ""
	if len(parts) == 2 {
		fractional = parts[1]
	}
	n, err := strconv.ParseInt(parts[0]+fractional+strings.Repeat("0", p-len(fractional)), 10, 64)
	if err != nil || n <= 0 || n > MaxRequest {
		return 0, errors.New("amount outside simulation limit")
	}
	return n, nil
}

func Format(n int64, currency string) string {
	p, _ := Precision(currency)
	v := big.NewInt(n)
	sign := ""
	if v.Sign() < 0 {
		sign = "-"
		v.Abs(v)
	}
	text := v.String()
	if len(text) <= p {
		text = strings.Repeat("0", p+1-len(text)) + text
	}
	return sign + text[:len(text)-p] + "." + text[len(text)-p:]
}

func Add(a, b int64) (int64, error) {
	if (b > 0 && a > math.MaxInt64-b) || (b < 0 && a < math.MinInt64-b) {
		return 0, errors.New("money overflow")
	}
	return a + b, nil
}

func Interest(balance, numerator, denominator int64) (int64, error) {
	return RoundRatio(balance, numerator, denominator)
}

// RoundRatio applies exact nonnegative rational arithmetic and half-even rounding.
func RoundRatio(balance, numerator, denominator int64) (int64, error) {
	if numerator < 0 || denominator <= 0 {
		return 0, errors.New("invalid rate")
	}
	if balance <= 0 {
		return 0, nil
	}
	product := new(big.Int).Mul(big.NewInt(balance), big.NewInt(numerator))
	q, r := new(big.Int), new(big.Int)
	q.QuoRem(product, big.NewInt(denominator), r)
	cmp := new(big.Int).Lsh(r, 1).Cmp(big.NewInt(denominator))
	if cmp > 0 || (cmp == 0 && q.Bit(0) == 1) {
		q.Add(q, big.NewInt(1))
	}
	if !q.IsInt64() {
		return 0, errors.New("rounded amount overflow")
	}
	return q.Int64(), nil
}

func Allocate(total int64, count int) ([]int64, error) {
	if total <= 0 || count < 1 || count > 100 || int64(count) > total {
		return nil, fmt.Errorf("invalid allocation")
	}
	out := make([]int64, count)
	for i := range out {
		out[i] = total / int64(count)
		if int64(i) < total%int64(count) {
			out[i]++
		}
	}
	return out, nil
}
