package domain

import (
	"math"
	"testing"
)

func TestMoney(t *testing.T) {
	for _, tc := range []struct {
		s, c string
		n    int64
	}{{"1200.00", "AED", 120000}, {"10.000", "BHD", 10000}, {"0.01", "AED", 1}} {
		n, e := Parse(tc.s, tc.c)
		if e != nil || n != tc.n {
			t.Fatalf("parse %v %v", n, e)
		}
		if Format(n, tc.c) != tc.s {
			t.Fatal("format")
		}
	}
	for _, s := range []string{"NaN", "-1", "+1", "1e2", "0", ".1", "1.", "1.001", " 1", "999999999999999999999"} {
		if _, e := Parse(s, "AED"); e == nil {
			t.Fatal(s)
		}
	}
	if _, e := Add(math.MaxInt64, 1); e == nil {
		t.Fatal("overflow")
	}
}
func TestAssessmentInterest(t *testing.T) {
	var sum int64
	for _, b := range []int64{25000, 22500, 62500, 41500, 39000, 39000} {
		n, e := Interest(b, 1, 2500)
		if e != nil {
			t.Fatal(e)
		}
		sum += n
	}
	if sum != 93 {
		t.Fatal(sum)
	}
	for _, tc := range []struct{ n, w int64 }{{5, 2}, {7, 4}, {-5, 0}} {
		n, _ := Interest(tc.n, 1, 2)
		if n != tc.w {
			t.Fatal(n)
		}
	}
	n, _ := Allocate(10000, 3)
	if n[0] != 3334 || n[1] != 3333 || n[2] != 3333 {
		t.Fatal(n)
	}
}
func FuzzAllocation(f *testing.F) {
	f.Add(int64(10000), 3)
	f.Fuzz(func(t *testing.T, n int64, c int) {
		out, e := Allocate(n, c)
		if e != nil {
			return
		}
		var sum int64
		for _, v := range out {
			sum += v
		}
		if sum != n {
			t.Fatal(out)
		}
	})
}
