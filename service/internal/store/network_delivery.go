package store

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/sabino/account-ledger-core/service/internal/db"
)

type notification struct {
	RunID    string          `json:"run_id"`
	Sequence int64           `json:"sequence,string"`
	Envelope json.RawMessage `json:"envelope"`
}

func (s *Store) Deliver(ctx context.Context) error {
	err := s.DeliverRun(ctx, "demo")
	if errors.Is(err, pgx.ErrNoRows) {
		return s.DeliverRun(ctx, FixtureRun)
	}
	return err
}

func (s *Store) DeliverRun(ctx context.Context, runID string) error {
	if s.SendNotification == nil {
		return errors.New("notification transport not configured")
	}
	token := rand.Text()
	item, err := s.Queries.LeaseDelivery(ctx, db.LeaseDeliveryParams{Token: pgtype.Text{String: token, Valid: true}, Instance: s.Instance, RunID: runID})
	if err != nil {
		return err
	}
	// Claim is committed before network IO. Death leaves a lease that expires.
	body, err := json.Marshal(notification{item.RunID, item.Sequence, item.Envelope})
	if err != nil {
		return err
	}
	deliveryErr := s.SendNotification(ctx, body)
	_, err = s.Queries.FinishDelivery(ctx, db.FinishDeliveryParams{RunID: item.RunID, Sequence: item.Sequence, Token: token, Instance: s.Instance, Success: deliveryErr == nil})
	if err != nil {
		return err
	}
	return deliveryErr
}

func (s *Store) ReceiveNotification(ctx context.Context, body []byte) error {
	var item notification
	if err := json.Unmarshal(body, &item); err != nil {
		return err
	}
	matched, err := s.Queries.ReceiveNotification(ctx, db.ReceiveNotificationParams{RunID: item.RunID, Sequence: item.Sequence, Envelope: item.Envelope})
	if err != nil {
		return err
	}
	if !matched {
		return errors.New("notification does not match a recorded batch")
	}
	return nil
}
