//go:build integration

package store

import (
	"context"
	"errors"
	"reflect"
	"testing"
)

func TestStatementStablePagination(t *testing.T) {
	a, b, run := testLedger(t)
	ctx := context.Background()
	for _, id := range []string{"one", "two", "three"} {
		cmd := command(id, "transfer")
		cmd.Amount = "0.01"
		if result, err := a.Process(ctx, run, cmd); err != nil || result.Status != "accepted" {
			t.Fatalf("transfer: %+v %v", result, err)
		}
	}
	rejected := command("wrong-day", "transfer")
	rejected.ValueDay = 2
	if result, err := a.Process(ctx, run, rejected); err != nil || result.Status != "rejected" {
		t.Fatalf("rejection: %+v %v", result, err)
	}
	hold := command("hold", "hold")
	hold.Authorization = "hold"
	hold.Amount = "1"
	if result, err := a.Process(ctx, run, hold); err != nil || result.Status != "accepted" {
		t.Fatalf("hold: %+v %v", result, err)
	}
	request := StatementRequest{Account: "a", Cutoff: -1, AfterLeg: -1, Limit: 2}
	first, err := a.Statement(ctx, run, request)
	if err != nil {
		t.Fatal(err)
	}
	if first.PostingCount != 4 || first.Next == nil || first.Closing != "9997" || first.PageOpening != "0" || first.PageClosing != "9999" {
		t.Fatalf("first: %+v", first)
	}
	cmd := command("later", "transfer")
	cmd.Amount = "0.01"
	if _, err = b.Process(ctx, run, cmd); err != nil {
		t.Fatal(err)
	}
	request.Cutoff = first.Cutoff
	request.AfterSequence = first.Next.Sequence
	request.AfterLeg = first.Next.Leg
	second, err := b.Statement(ctx, run, request)
	if err != nil {
		t.Fatal(err)
	}
	if second.Next != nil || len(second.Lines) != 2 || second.PageOpening != first.PageClosing || second.PageClosing != first.Closing {
		t.Fatalf("second: %+v", second)
	}
	repeated, err := a.Statement(ctx, run, request)
	if err != nil || !reflect.DeepEqual(second, repeated) {
		t.Fatalf("unstable page: %v", err)
	}
	request.AfterSequence = 0
	request.AfterLeg = -1
	request.Cutoff = 0
	empty, err := a.Statement(ctx, run, request)
	if err != nil || empty.PostingCount != 0 || len(empty.Lines) != 0 || empty.Closing != "0" {
		t.Fatalf("zero cutoff: %+v %v", empty, err)
	}
	request.Cutoff = first.Cutoff + 100
	if _, err = a.Statement(ctx, run, request); !errors.Is(err, ErrStatementInput) {
		t.Fatalf("future cutoff: %v", err)
	}
	request.Account = "unknown"
	request.Cutoff = -1
	if _, err = a.Statement(ctx, run, request); !errors.Is(err, ErrStatementAccount) {
		t.Fatalf("missing account: %v", err)
	}
	request.Account = "c"
	bhd, err := a.Statement(ctx, run, request)
	if err != nil || bhd.Currency != "BHD" || bhd.Closing != "0" {
		t.Fatalf("empty BHD: %+v %v", bhd, err)
	}
}

func TestStatementPagesWithinSplitBatch(t *testing.T) {
	a, _, run := testLedger(t)
	ctx := context.Background()
	cmd := command("split", "split_transfer")
	cmd.Amount = "0.10"
	cmd.Installments = 3
	if result, err := a.Process(ctx, run, cmd); err != nil || result.Status != "accepted" {
		t.Fatalf("split: %+v %v", result, err)
	}
	request := StatementRequest{Account: "b", Cutoff: -1, AfterLeg: -1, Limit: 1}
	var amounts []string
	var cutoff int64
	for {
		page, err := a.Statement(ctx, run, request)
		if err != nil {
			t.Fatal(err)
		}
		if cutoff == 0 {
			cutoff = page.Cutoff
		}
		if page.Cutoff != cutoff {
			t.Fatal("cutoff changed")
		}
		for _, line := range page.Lines {
			amounts = append(amounts, line.Change)
		}
		if page.Next == nil {
			if page.Closing != "10010" {
				t.Fatalf("balance: %+v", page)
			}
			break
		}
		request.Cutoff = page.Cutoff
		request.AfterSequence = page.Next.Sequence
		request.AfterLeg = page.Next.Leg
	}
	if !reflect.DeepEqual(amounts, []string{"10000", "4", "3", "3"}) {
		t.Fatalf("skipped/repeated legs: %v", amounts)
	}
}
