package store

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"runtime"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/sabino/account-ledger-core/service/internal/db"
)

// Admit counts all public commands across both instances, including invalid ones.
func (s *Store) Admit(ctx context.Context) error {
	admitted, err := s.Queries.Admit(ctx)
	if err != nil {
		return err
	}
	if admitted != 1 {
		return ErrCapacity
	}
	return nil
}

// This database guard does not replace the independent host watcher required for deployment.
func (s *Store) Guard(ctx context.Context) error {
	footprint, err := s.Queries.DatabaseFootprint(ctx)
	if err != nil {
		return err
	}
	reason := ""
	if footprint.Size > 512*1024*1024 {
		reason = "database size budget reached"
	}
	if footprint.Retained > 256*1024*1024 {
		reason = "CDC retained WAL limit"
	}
	return s.Queries.RefreshGuard(ctx, reason)
}

// The durable ordinal advances only after a stored result. A crash repeats the
// same command rather than losing it. Races may consume extra admission tokens,
// but cannot create extra financial effects or increase the requested rate.
func (s *Store) Generate(ctx context.Context) error {
	ordinal, err := s.Queries.NextGeneratedCommand(ctx)
	if err != nil {
		return err
	}
	if err = s.Admit(ctx); err != nil {
		return err
	}
	_, err = s.Process(ctx, "demo", GeneratedCommand(ordinal))
	if err != nil {
		return err
	}
	return s.Queries.AcknowledgeGeneratedCommand(ctx, ordinal)
}

func (s *Store) Workers(ctx context.Context) {
	fast := time.NewTicker(50 * time.Millisecond)
	defer fast.Stop()
	slow := time.NewTicker(2 * time.Second)
	defer slow.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-fast.C:
			job, cancel := context.WithTimeout(ctx, 3*time.Second)
			_ = s.Generate(job)
			_ = s.Deliver(job)
			cancel()
		case <-slow.C:
			job, cancel := context.WithTimeout(ctx, 3*time.Second)
			_ = s.Guard(job)
			var memory runtime.MemStats
			runtime.ReadMemStats(&memory)
			_ = s.Queries.Heartbeat(job, db.HeartbeatParams{ID: s.Instance, HeapBytes: int64(memory.HeapAlloc)})
			cancel()
		}
	}
}

func (s *Store) Status(ctx context.Context) (map[string]any, error) {
	host := map[string]any{"safe": false, "reason": "host watcher not initialized"}
	guard, guardErr := s.Queries.HostGuardStatus(ctx)
	if guardErr == nil {
		var evidence any
		if err := json.Unmarshal(guard.Evidence, &evidence); err != nil {
			return nil, err
		}
		host = map[string]any{"safe": guard.Safe, "reason": guard.Reason, "observed_at": guard.ObservedAt.Time, "evidence": evidence}
	} else if !errors.Is(guardErr, pgx.ErrNoRows) {
		return nil, guardErr
	}
	state, err := s.Queries.SimulationStatus(ctx)
	if err != nil {
		return nil, err
	}
	rows, err := s.Queries.ListReplicas(ctx)
	if err != nil {
		return nil, err
	}
	replicas := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		replicas = append(replicas, map[string]any{"id": row.ID, "seen_at": row.SeenAt.Time,
			"heap_bytes": row.HeapBytes, "healthy": time.Since(row.SeenAt.Time) < 10*time.Second})
	}
	return map[string]any{"eps": state.Eps, "generated": fmt.Sprint(state.Ordinal),
		"sequence": fmt.Sprint(state.Position), "guard_reason": state.GuardReason,
		"pause_reason": state.PauseReason, "guard_fresh": state.Fresh,
		"pending_deliveries": state.Pending, "database_bytes": state.DatabaseBytes,
		"replicas": replicas, "serving_instance": s.Instance, "cdc": "optional lake profile; freshness not observed by this endpoint",
		"host_guard": host, "profile": "synthetic scenario mix; separate six-day assessment replay"}, nil
}

func (s *Store) SetRate(ctx context.Context, eps int32) error {
	if eps < 0 || eps > 20 {
		return ErrCapacity
	}
	changed, err := s.Queries.SetRate(ctx, eps)
	if err != nil {
		return err
	}
	if changed == 0 {
		return ErrCapacity
	}
	return nil
}

func (s *Store) PauseOutbox(ctx context.Context) error {
	affected, err := s.Queries.PauseOutbox(ctx)
	if err != nil {
		return err
	}
	if affected == 0 {
		return ErrCapacity
	}
	return nil
}
