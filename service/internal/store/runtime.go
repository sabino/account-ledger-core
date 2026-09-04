package store

import (
	"context"
	"fmt"
	"runtime"
	"time"

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
	source, destination := int(ordinal%20)+1, int((ordinal*7+3)%20)+1
	if destination == source {
		destination = destination%20 + 1
	}
	currency := "AED"
	if ordinal%2 == 1 {
		source += 20
		destination += 20
		currency = "BHD"
	}
	_, err = s.Process(ctx, "demo", Command{
		ID: fmt.Sprintf("generated-%010d", ordinal), Kind: "transfer",
		Account: fmt.Sprintf("ACC-%03d", source), Destination: fmt.Sprintf("ACC-%03d", destination),
		Currency: currency, Amount: fmt.Sprintf("%d.00", ordinal%9+1), BookedDay: 1, ValueDay: 1,
	})
	if err != nil {
		return err
	}
	return s.Queries.AcknowledgeGeneratedCommand(ctx, ordinal)
}

// The first delivery adapter uses a durable local inbox, not a network sink.
func (s *Store) Deliver(ctx context.Context) error {
	tx, err := s.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	queries := s.Queries.WithTx(tx)
	item, err := queries.ClaimDelivery(ctx)
	if err != nil {
		return err
	}
	if err = queries.AcceptDelivery(ctx, db.AcceptDeliveryParams{RunID: item.RunID, Sequence: item.Sequence}); err != nil {
		return err
	}
	if err = queries.CompleteDelivery(ctx, db.CompleteDeliveryParams{RunID: item.RunID, Sequence: item.Sequence}); err != nil {
		return err
	}
	return tx.Commit(ctx)
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
		"replicas": replicas, "serving_instance": s.Instance, "cdc": "not implemented",
		"profile": "continuous transfers; assessment compatibility in development"}, nil
}

func (s *Store) SetRate(ctx context.Context, eps int32) error {
	if eps < 0 || eps > 20 {
		return ErrCapacity
	}
	return s.Queries.SetRate(ctx, eps)
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
