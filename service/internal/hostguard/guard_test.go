package hostguard

import (
	"testing"
	"time"
)

func TestEvaluate(t *testing.T) {
	previous := Sample{At: time.Unix(100, 0), SwapPages: 10}
	good := Sample{At: previous.At.Add(2 * time.Second), AvailableBytes: 1 << 30, DiskFreeBytes: 10 << 30, SwapPages: 10}
	if reason := Evaluate(good, &previous, DefaultLimits(), 4096); reason != "" {
		t.Fatal(reason)
	}
	cases := []struct {
		name   string
		change func(*Sample)
	}{
		{"memory", func(s *Sample) { s.AvailableBytes = 1 }},
		{"disk", func(s *Sample) { s.DiskFreeBytes = 1 }},
		{"memory pressure", func(s *Sample) { s.MemoryFull10 = 3 }},
		{"IO pressure", func(s *Sample) { s.IOFull10 = 6 }},
		{"swap", func(s *Sample) { s.SwapPages = 100000 }},
		{"stale", func(s *Sample) { s.At = previous.At.Add(11 * time.Second) }},
		{"counter reset", func(s *Sample) { s.SwapPages = 0 }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			s := good
			tc.change(&s)
			if Evaluate(s, &previous, DefaultLimits(), 4096) == "" {
				t.Fatal("unsafe sample allowed")
			}
		})
	}
	if Evaluate(good, nil, DefaultLimits(), 4096) == "" {
		t.Fatal("missing prior sample allowed")
	}
}
