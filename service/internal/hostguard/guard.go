// Package hostguard reads host resource evidence without controlling containers.
// Only telemetry uses floating point; ledger money never does.
package hostguard

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"
)

type Sample struct {
	At             time.Time `json:"at"`
	AvailableBytes uint64    `json:"available_bytes"`
	DiskFreeBytes  uint64    `json:"disk_free_bytes"`
	MemoryFull10   float64   `json:"memory_full_avg10"`
	IOFull10       float64   `json:"io_full_avg10"`
	SwapPages      uint64    `json:"swap_pages_total"`
}

type Limits struct {
	MinAvailableBytes     uint64
	MinDiskFreeBytes      uint64
	MaxMemoryFull10       float64
	MaxIOFull10           float64
	MaxSwapBytesPerSecond float64
}

func DefaultLimits() Limits {
	return Limits{512 << 20, 5 << 30, 2, 5, 16 << 20}
}

func Read(proc, disk string) (Sample, error) {
	s := Sample{At: time.Now()}
	mem, err := fields(filepath.Join(proc, "meminfo"))
	if err != nil {
		return s, err
	}
	available, err := integer(mem, "MemAvailable:")
	if err != nil {
		return s, err
	}
	s.AvailableBytes = available * 1024
	vm, err := fields(filepath.Join(proc, "vmstat"))
	if err != nil {
		return s, err
	}
	in, err := integer(vm, "pswpin")
	if err != nil {
		return s, err
	}
	out, err := integer(vm, "pswpout")
	if err != nil {
		return s, err
	}
	s.SwapPages = in + out
	s.MemoryFull10, err = pressure(filepath.Join(proc, "pressure", "memory"))
	if err != nil {
		return s, err
	}
	s.IOFull10, err = pressure(filepath.Join(proc, "pressure", "io"))
	if err != nil {
		return s, err
	}
	var stat syscall.Statfs_t
	if err = syscall.Statfs(disk, &stat); err != nil {
		return s, err
	}
	s.DiskFreeBytes = stat.Bavail * uint64(stat.Bsize)
	return s, nil
}

func Evaluate(now Sample, previous *Sample, limits Limits, pageSize int) string {
	if now.AvailableBytes < limits.MinAvailableBytes {
		return "host available memory below reserve"
	}
	if now.DiskFreeBytes < limits.MinDiskFreeBytes {
		return "host disk below reserve"
	}
	if now.MemoryFull10 > limits.MaxMemoryFull10 {
		return "host memory pressure"
	}
	if now.IOFull10 > limits.MaxIOFull10 {
		return "host IO pressure"
	}
	if previous == nil {
		return "host watcher warming up"
	}
	elapsed := now.At.Sub(previous.At).Seconds()
	if elapsed <= 0 || elapsed > 10 || now.SwapPages < previous.SwapPages {
		return "host sample discontinuity"
	}
	if float64(now.SwapPages-previous.SwapPages)*float64(pageSize)/elapsed > limits.MaxSwapBytesPerSecond {
		return "host swap activity above budget"
	}
	return ""
}

func fields(path string) (map[string][]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	values := map[string][]string{}
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		parts := strings.Fields(scanner.Text())
		if len(parts) >= 2 {
			values[parts[0]] = parts[1:]
		}
	}
	return values, scanner.Err()
}

func integer(values map[string][]string, key string) (uint64, error) {
	v := values[key]
	if len(v) == 0 {
		return 0, fmt.Errorf("missing host metric %s", key)
	}
	return strconv.ParseUint(v[0], 10, 64)
}

func pressure(path string) (float64, error) {
	values, err := fields(path)
	if err != nil {
		return 0, err
	}
	for _, value := range values["full"] {
		if raw, ok := strings.CutPrefix(value, "avg10="); ok {
			v, err := strconv.ParseFloat(raw, 64)
			if err != nil || !(v >= 0 && v <= 100) {
				return 0, fmt.Errorf("invalid pressure sample")
			}
			return v, nil
		}
	}
	return 0, fmt.Errorf("missing full avg10 pressure sample")
}
