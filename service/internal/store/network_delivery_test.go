//go:build integration

package store

import (
	"context"
	"encoding/json"
	"errors"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/sabino/account-ledger-core/service/internal/delivery"
)

func TestDeliveryRetriesAfterReceiverCommitsButAckIsLost(t *testing.T) {
	a, b, run := testLedger(t)
	ctx := context.Background()
	server := httptest.NewServer(delivery.Handler(strings.Repeat("s", 32), b.ReceiveNotification))
	defer server.Close()
	send := delivery.Sender(server.URL, strings.Repeat("s", 32))
	var first notification
	a.SendNotification = func(ctx context.Context, body []byte) error {
		if err := json.Unmarshal(body, &first); err != nil {
			return err
		}
		if err := send(ctx, body); err != nil {
			return err
		}
		return errors.New("simulated acknowledgement loss after receipt committed")
	}
	if err := a.DeliverRun(ctx, run); err == nil {
		t.Fatal("missing simulated transport error")
	}
	a.SendNotification = send
	// Deliver the other seed notification while the first waits for its retry.
	if err := a.DeliverRun(ctx, run); err != nil {
		t.Fatal(err)
	}
	time.Sleep(2100 * time.Millisecond)
	if err := a.DeliverRun(ctx, run); err != nil {
		t.Fatal(err)
	}
	var inbox, attempts int
	var delivered bool
	if err := a.Pool.QueryRow(ctx, "SELECT count(*) FROM notification_inbox WHERE run_id=$1 AND sequence=$2", run, first.Sequence).Scan(&inbox); err != nil {
		t.Fatal(err)
	}
	if err := a.Pool.QueryRow(ctx, "SELECT attempts,delivered_at IS NOT NULL FROM outbox WHERE run_id=$1 AND sequence=$2", run, first.Sequence).Scan(&attempts, &delivered); err != nil {
		t.Fatal(err)
	}
	if inbox != 1 || attempts != 2 || !delivered {
		t.Fatalf("inbox=%d attempts=%d delivered=%v", inbox, attempts, delivered)
	}
	first.Envelope = json.RawMessage(`{"changed":true}`)
	body, _ := json.Marshal(first)
	if err := b.ReceiveNotification(ctx, body); err == nil {
		t.Fatal("accepted mismatching envelope")
	}
}
