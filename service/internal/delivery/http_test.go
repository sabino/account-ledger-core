package delivery

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestSignedDeliveryAndInvalidSignature(t *testing.T) {
	secret := strings.Repeat("s", 32)
	calls := 0
	server := httptest.NewServer(Handler(secret, func(_ context.Context, b []byte) error {
		calls++
		if string(b) != "payload" {
			t.Error("changed body")
		}
		return nil
	}))
	defer server.Close()
	if err := Sender(server.URL, secret)(context.Background(), []byte("payload")); err != nil {
		t.Fatal(err)
	}
	if err := Sender(server.URL, strings.Repeat("x", 32))(context.Background(), []byte("payload")); err == nil {
		t.Fatal("accepted wrong signature")
	}
	if calls != 1 {
		t.Fatalf("receiver called %d times", calls)
	}
}

func TestOversizeAndRedirectRejected(t *testing.T) {
	secret := strings.Repeat("s", 32)
	handler := Handler(secret, func(context.Context, []byte) error { t.Fatal("oversize reached receiver"); return nil })
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest("POST", "/", strings.NewReader(strings.Repeat("x", MaxPayload+1))))
	if recorder.Code != 413 {
		t.Fatal(recorder.Code)
	}
	target := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { t.Error("followed redirect") }))
	defer target.Close()
	redirect := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { http.Redirect(w, r, target.URL, 307) }))
	defer redirect.Close()
	if err := Sender(redirect.URL, secret)(context.Background(), []byte("payload")); err == nil {
		t.Fatal("accepted redirect")
	}
}
