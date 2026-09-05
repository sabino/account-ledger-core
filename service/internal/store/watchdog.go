package store

import (
	"context"
	"encoding/json"
	"log"
	"os"
	"time"

	"github.com/sabino/account-ledger-core/service/internal/db"
	"github.com/sabino/account-ledger-core/service/internal/hostguard"
)

// WatchHost runs in a separate container with a restricted database role. The
// APIs cannot extend this lease. Missing readings and a dead watcher fail closed.
func (s *Store) WatchHost(ctx context.Context, proc, disk string) {
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()
	var previous *hostguard.Sample
	for {
		sample, err := hostguard.Read(proc, disk)
		reason := "host metrics unavailable"
		if err == nil {
			reason = hostguard.Evaluate(sample, previous, hostguard.DefaultLimits(), os.Getpagesize())
			previous = &sample
		} else {
			previous = nil
			log.Printf("host watcher read failed: %v", err)
		}
		evidence, _ := json.Marshal(sample)
		job, cancel := context.WithTimeout(ctx, time.Second)
		err = s.Queries.PublishHostGuard(job, db.PublishHostGuardParams{Reason: reason, Evidence: evidence})
		cancel()
		if err != nil {
			log.Printf("host watcher publish failed: %v", err)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
